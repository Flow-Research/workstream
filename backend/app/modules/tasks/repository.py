"""Database access methods for tasks, assignments, submissions, and audit events."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.audit.repository import AuditRepository
from app.modules.tasks.api import (
    SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import (
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)


class TaskRepository:
    """Wraps SQLAlchemy persistence for task queue operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a repository bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current unit of work.
        """
        self._session = session
        self._audit_repository = AuditRepository(session)

    async def add_task(self, task: WorkstreamTask) -> WorkstreamTask:
        """Persist a new task and refresh generated database fields.

        Args:
            task: Task model to persist.

        Returns:
            Persisted task model.
        """
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def get_task(
        self,
        task_id: str,
        *,
        for_update: bool = False,
    ) -> WorkstreamTask | None:
        """Load one task by primary key.

        Args:
            task_id: Task id to load.
            for_update: Whether to lock and refresh the selected row.

        Returns:
            Task model when found; otherwise ``None``.
        """
        statement = select(WorkstreamTask).where(WorkstreamTask.id == task_id)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(
            statement.execution_options(populate_existing=True)
        )

    async def add_assignment(self, assignment: TaskAssignment) -> TaskAssignment:
        """Persist an assignment and refresh generated database fields.

        Args:
            assignment: Assignment model to persist.

        Returns:
            Persisted assignment model.
        """
        self._session.add(assignment)
        await self._session.flush()
        await self._session.refresh(assignment)
        return assignment

    async def get_active_assignment(
        self,
        task_id: str,
        *,
        for_update: bool = False,
    ) -> TaskAssignment | None:
        """Load the active assignment for a task.

        Args:
            task_id: Task id whose active assignment should be loaded.
            for_update: Whether to lock and refresh the selected row.

        Returns:
            Active assignment when present; otherwise ``None``.
        """
        statement = select(TaskAssignment).where(
            TaskAssignment.task_id == task_id,
            TaskAssignment.status == "active",
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(
            statement.execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def lock_submission_context(
        self,
        request: TaskSubmissionContextRequest,
    ) -> TaskSubmissionContextFacts:
        """Lock and project exact TASK-owned Submission lifecycle facts."""
        task = await self.get_task(str(request.task_id), for_update=True)
        assignment = await self._session.scalar(
            select(TaskAssignment)
            .where(TaskAssignment.id == str(request.assignment_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        latest_submission = await self.get_latest_submission_for_task(
            str(request.task_id),
            for_update=True,
            populate_existing=True,
        )
        contributor_id = str(request.contributor_id)
        if (
            task is None
            or assignment is None
            or assignment.task_id != str(request.task_id)
            or assignment.contributor_id != contributor_id
            or assignment.status != "active"
            or task.assigned_to != contributor_id
            or task.status not in {"in_progress", "needs_revision"}
        ):
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")

        latest_id = latest_submission.id if latest_submission is not None else None
        requested_predecessor_id = (
            str(request.predecessor_submission_id)
            if request.predecessor_submission_id is not None
            else None
        )
        if latest_id != requested_predecessor_id:
            raise TaskSubmissionContextUnavailable("task_submission_predecessor_changed")
        if (
            (task.status == "in_progress" and latest_submission is not None)
            or (task.status == "needs_revision" and latest_submission is None)
            or (
                latest_submission is not None
                and latest_submission.contributor_id != contributor_id
            )
        ):
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")

        locked_values = (
            task.project_id,
            task.locked_guide_version,
            task.locked_guide_source_snapshot_id,
            task.locked_guide_source_snapshot_hash,
            task.locked_effective_project_submission_artifact_policy_id,
            task.locked_effective_project_submission_artifact_policy_hash,
            task.locked_pre_submit_checker_policy_id,
            task.locked_pre_submit_checker_bundle_hash,
        )
        if any(value is None for value in locked_values):
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        try:
            locked_project_context = TaskLockedProjectContextReferences(
                project_id=UUID(task.project_id),
                guide_version=task.locked_guide_version,
                source_snapshot_id=UUID(task.locked_guide_source_snapshot_id),
                source_snapshot_hash=task.locked_guide_source_snapshot_hash,
                effective_policy_id=UUID(
                    task.locked_effective_project_submission_artifact_policy_id
                ),
                effective_policy_hash=(
                    task.locked_effective_project_submission_artifact_policy_hash
                ),
                pre_submit_policy_id=UUID(task.locked_pre_submit_checker_policy_id),
                pre_submit_policy_bundle_hash=task.locked_pre_submit_checker_bundle_hash,
            )
            predecessor = (
                SubmissionPredecessorFacts(
                    submission_id=UUID(latest_submission.id),
                    version=latest_submission.version,
                )
                if latest_submission is not None
                else None
            )
            return TaskSubmissionContextFacts(
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                contributor_id=request.contributor_id,
                status=task.status,
                kind="revision" if predecessor is not None else "initial",
                predecessor=predecessor,
                locked_project_context=locked_project_context,
            )
        except (TypeError, ValueError) as exc:
            raise TaskSubmissionContextUnavailable(
                "task_submission_context_invalid"
            ) from exc

    async def add_submission(self, submission: Submission) -> Submission:
        """Persist a submission packet and its evidence items.

        Args:
            submission: Submission model to persist.

        Returns:
            Persisted submission with generated database fields refreshed.
        """
        self._session.add(submission)
        await self._session.flush()
        await self._session.refresh(submission)
        return submission

    async def get_submission(
        self,
        submission_id: str,
        *,
        populate_existing: bool = False,
    ) -> Submission | None:
        """Load one submission by id with evidence items.

        Args:
            submission_id: Submission id to load.
            populate_existing: Whether to refresh an already-loaded ORM instance
                from the database.

        Returns:
            Submission when found; otherwise ``None``.
        """
        statement = (
            select(Submission)
            .options(selectinload(Submission.evidence_items))
            .where(Submission.id == submission_id)
        )
        if populate_existing:
            statement = statement.execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_latest_submission_for_task(
        self,
        task_id: str,
        *,
        for_update: bool = False,
        populate_existing: bool = False,
    ) -> Submission | None:
        """Load the latest submission version for a task.

        Args:
            task_id: Task whose latest submission should be loaded.

        Returns:
            Latest submission by version when present; otherwise ``None``.
        """
        statement = (
            select(Submission)
            .where(Submission.task_id == task_id)
            .order_by(Submission.version.desc(), Submission.submitted_at.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        if populate_existing:
            statement = statement.execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_submissions_for_task(self, task_id: str) -> Sequence[Submission]:
        """List submission versions for one task.

        Args:
            task_id: Task whose submissions should be listed.

        Returns:
            Submission versions ordered from oldest to newest.
        """
        result = await self._session.execute(
            select(Submission)
            .options(selectinload(Submission.evidence_items))
            .where(Submission.task_id == task_id)
            .order_by(Submission.version.asc(), Submission.submitted_at.asc())
        )
        return result.scalars().all()

    async def lock_submission_evidence(self, submission_id: str, locked_at: datetime) -> None:
        """Stamp evidence rows with the submission lock timestamp.

        Args:
            submission_id: Submission whose evidence rows should be locked.
            locked_at: Timestamp applied to each evidence item.
        """
        result = await self._session.execute(
            select(EvidenceItem).where(EvidenceItem.submission_id == submission_id)
        )
        for evidence in result.scalars():
            evidence.locked_at = locked_at

    async def finalize_submission_if_unlocked(
        self,
        submission_id: str,
        finalized_at: datetime,
    ) -> bool:
        """Atomically stamp a submission as finalized if it is still open.

        The persistence column remains ``locked_at`` because it represents the
        immutable storage boundary. This repository method uses finalize
        terminology to match the public API lifecycle.

        Args:
            submission_id: Submission id to finalize.
            finalized_at: Timestamp applied to the submission row.

        Returns:
            ``True`` when this call won the finalize guard; otherwise ``False``.
        """
        result = await self._session.execute(
            update(Submission)
            .where(Submission.id == submission_id, Submission.locked_at.is_(None))
            .values(locked_at=finalized_at)
            .returning(Submission.id)
        )
        return result.scalar_one_or_none() is not None

    async def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Persist an audit event.

        Args:
            event: Audit event model to persist.

        Returns:
            Persisted audit event model.
        """
        return await self._audit_repository.add_audit_event(event)

    async def list_audit_events(self, entity_type: str, entity_id: str) -> Sequence[AuditEvent]:
        """List audit events for one entity in creation order.

        Args:
            entity_type: Entity type recorded in audit events.
            entity_id: Entity id recorded in audit events.

        Returns:
            Matching audit events ordered by creation time.
        """
        return await self._audit_repository.list_audit_events(entity_type, entity_id)
