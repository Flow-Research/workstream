"""Database access methods for tasks, assignments, submissions, and audit events."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.audit.repository import AuditRepository
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

    async def get_task(self, task_id: str) -> WorkstreamTask | None:
        """Load one task by primary key.

        Args:
            task_id: Task id to load.

        Returns:
            Task model when found; otherwise ``None``.
        """
        return await self._session.get(WorkstreamTask, task_id)

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

    async def get_active_assignment(self, task_id: str) -> TaskAssignment | None:
        """Load the active assignment for a task.

        Args:
            task_id: Task id whose active assignment should be loaded.

        Returns:
            Active assignment when present; otherwise ``None``.
        """
        result = await self._session.execute(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.status == "active",
            )
        )
        return result.scalar_one_or_none()

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

    async def get_latest_submission_for_task(self, task_id: str) -> Submission | None:
        """Load the latest submission version for a task.

        Args:
            task_id: Task whose latest submission should be loaded.

        Returns:
            Latest submission by version when present; otherwise ``None``.
        """
        result = await self._session.execute(
            select(Submission)
            .where(Submission.task_id == task_id)
            .order_by(Submission.version.desc(), Submission.submitted_at.desc())
            .limit(1)
        )
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
