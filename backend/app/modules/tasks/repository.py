"""Database access methods for tasks, assignments, submissions, and audit events."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, Select, and_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repository import AuditRepository
from app.modules.tasks.api import (
    AuditTaskEvidence, AuditTaskEvidencePage, AuditTaskEvidenceRequest,
    TaskEvidenceCursor, TaskEvidenceInvalid,
    ContributorTaskDetail, ContributorTaskDetailRequest,
    ManagementTaskDetail, ManagementTaskDetailRequest,
    ManagementTaskPage,
    ManagementTaskSummary,
    OperationalTaskPage,
    OperationalTaskSummary,
    TaskQueueCursor,
    ReadyTaskPage,
    TaskQueueRequest,
    ReadyTaskSummary,
    SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationTarget, AssignmentInvalidationTargetsRequest,
    AssignmentInvalidationTargetsPage,
)
from app.modules.tasks.models import (
    AuditEvent,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)


def _unassigned_ready_task():
    """Shared ready visibility for queue discovery and contributor detail."""
    task = WorkstreamTask
    active_assignment = select(TaskAssignment.id).where(
        TaskAssignment.task_id == task.id, TaskAssignment.status == "active",
    ).exists()
    return and_(task.status == "ready", task.assigned_to.is_(None), ~active_assignment)


def _task_detail_columns():
    """Fixed common detail projection; never select a task ORM entity."""
    task = WorkstreamTask
    return (
        task.id.label("task_id"), task.project_id, task.title, task.description,
        task.task_type, task.difficulty, task.skill_tags, task.estimated_time_minutes,
        task.status, task.acceptance_criteria, task.rejection_criteria,
        task.deadline_at, task.created_at, task.updated_at,
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

    async def read_assignment_invalidation_targets_page(
        self, request: AssignmentInvalidationTargetsRequest,
    ) -> AssignmentInvalidationTargetsPage:
        """Nonlocking fixed projection; AUTH owns serialization and the root transaction."""
        request = AssignmentInvalidationTargetsRequest.model_validate(request.model_dump())
        assignment, task = TaskAssignment, WorkstreamTask
        statement = select(
            assignment.id, assignment.task_id, assignment.project_id, assignment.contributor_id,
        ).join(task, and_(task.id == assignment.task_id, task.project_id == assignment.project_id)).where(
            assignment.contributor_id == str(request.contributor_id),
            assignment.status == "active", assignment.released_at.is_(None),
            assignment.assigned_at <= request.invalidated_at,
            task.status.in_(("claimed", "in_progress")), task.assigned_to == assignment.contributor_id,
            assignment.submitter_contribution_policy_version_id == task.locked_contribution_policy_version_id,
            ~select(Submission.id).where(Submission.task_id == task.id).exists(),
        )
        if request.project_id is not None:
            statement = statement.where(assignment.project_id == str(request.project_id))
        if request.after is not None:
            statement = statement.where(assignment.id > request.after)
        with self._session.no_autoflush:
            rows = (await self._session.execute(statement.order_by(assignment.id).limit(101))).all()
        return AssignmentInvalidationTargetsPage(
            items=tuple(AssignmentInvalidationTarget(
                project_id=UUID(row.project_id), task_id=UUID(row.task_id), assignment_id=UUID(row.id),
                contributor_id=UUID(row.contributor_id),
                authority_invalidation_event_id=request.invalidation_event_id,
            ) for row in rows[:100]),
            next_after=UUID(rows[99].id) if len(rows) > 100 else None,
        )

    async def read_ready_tasks(self, request: TaskQueueRequest) -> ReadyTaskPage:
        """Read only eligible project rows before keyset pagination.

        This hidden owner read performs no authorization or reservation. It
        neither flushes pending writes nor commits/locks the caller's session.
        """
        task = WorkstreamTask
        statement = select(
            task.id, task.project_id, task.title, task.task_type, task.difficulty,
            task.skill_tags, task.estimated_time_minutes, task.created_at,
        ).where(_unassigned_ready_task())
        rows, continuation = await self._read_task_queue_rows(request, statement)
        items = tuple(
            ReadyTaskSummary(
                task_id=UUID(row.id), project_id=UUID(row.project_id), title=row.title,
                task_type=row.task_type, difficulty=row.difficulty,
                skill_tags=tuple(row.skill_tags), estimated_time_minutes=row.estimated_time_minutes,
                created_at=row.created_at,
            )
            for row in rows
        )
        return ReadyTaskPage(request.project_id, items, continuation)

    async def read_management_tasks(self, request: TaskQueueRequest) -> ManagementTaskPage:
        """Return all project tasks with fixed planning fields and no work content."""
        task = WorkstreamTask
        rows, cursor = await self._read_task_queue_rows(request, select(
            task.id, task.project_id, task.title, task.task_type, task.difficulty,
            task.skill_tags, task.estimated_time_minutes, task.status, task.deadline_at,
            task.created_at, task.updated_at,
        ))
        items = tuple(ManagementTaskSummary(
            task_id=UUID(row.id), project_id=UUID(row.project_id), title=row.title,
            task_type=row.task_type, difficulty=row.difficulty, skill_tags=tuple(row.skill_tags),
            estimated_time_minutes=row.estimated_time_minutes, status=row.status,
            deadline_at=row.deadline_at, created_at=row.created_at, updated_at=row.updated_at,
        ) for row in rows)
        return ManagementTaskPage(request.project_id, items, cursor)

    async def read_operational_tasks(self, request: TaskQueueRequest) -> OperationalTaskPage:
        """Select status-only columns, without loading private task content."""
        task = WorkstreamTask
        rows, cursor = await self._read_task_queue_rows(request, select(
            task.id, task.project_id, task.status, task.created_at, task.updated_at,
        ))
        items = tuple(OperationalTaskSummary(
            task_id=UUID(row.id), project_id=UUID(row.project_id), status=row.status,
            created_at=row.created_at, updated_at=row.updated_at,
        ) for row in rows)
        return OperationalTaskPage(request.project_id, items, cursor)

    async def _read_task_queue_rows(
        self, request: TaskQueueRequest, statement: Select,
    ) -> tuple[Sequence[Row], TaskQueueCursor | None]:
        """Apply one exact project and live position before the bounded query.

        Only TASK's fixed projection methods supply statements. This helper
        never authorizes, flushes, commits, rolls back or acquires row locks.
        """
        if not isinstance(request, TaskQueueRequest):
            raise ValueError("task queue request is invalid")
        task = WorkstreamTask
        statement = statement.where(task.project_id == str(request.project_id))
        if request.after is not None:
            statement = statement.where(
                tuple_(task.created_at, task.id) > tuple_(
                    request.after.created_at, request.after.task_id,
                ),
            )
        statement = statement.order_by(task.created_at, task.id).limit(request.limit + 1)
        with self._session.no_autoflush:
            rows = (await self._session.execute(statement)).all()
        continuation = (
            TaskQueueCursor(request.project_id, rows[request.limit - 1].created_at, UUID(rows[request.limit - 1].id))
            if len(rows) > request.limit else None
        )
        return rows[:request.limit], continuation

    async def read_contributor_task_detail(self, request: ContributorTaskDetailRequest) -> ContributorTaskDetail | None:
        """Read visible work facts in one scoped query; caller supplies authority."""
        if type(request) is not ContributorTaskDetailRequest:
            raise ValueError("task detail request is invalid")
        task, assignment = WorkstreamTask, TaskAssignment
        own_assignment = select(assignment.id).where(
            assignment.task_id == task.id,
            assignment.project_id == task.project_id,
            assignment.status == "active",
            assignment.contributor_id == str(request.contributor_id),
        ).exists()
        statement = select(*_task_detail_columns()).where(or_(
            _unassigned_ready_task(),
            and_(task.assigned_to == str(request.contributor_id), own_assignment),
        ))
        values = await self._read_task_detail_values(request, statement)
        return ContributorTaskDetail(**values) if values is not None else None

    async def read_management_task_detail(self, request: ManagementTaskDetailRequest) -> ManagementTaskDetail | None:
        """Read exact-project management facts without broad ORM loading."""
        if type(request) is not ManagementTaskDetailRequest:
            raise ValueError("task detail request is invalid")
        task = WorkstreamTask
        statement = select(
            *_task_detail_columns(), task.source_type, task.source_ref, task.source_payload_hash,
            task.import_batch_id, task.external_task_id, task.created_by, task.assigned_to,
        )
        values = await self._read_task_detail_values(request, statement)
        return ManagementTaskDetail(**values) if values is not None else None

    async def _read_task_detail_values(
        self, request: ContributorTaskDetailRequest | ManagementTaskDetailRequest, statement: Select,
    ) -> dict | None:
        """Keep exact scope, one query and transaction behavior common to both reads."""
        statement = statement.where(
            WorkstreamTask.project_id == str(request.project_id),
            WorkstreamTask.id == str(request.task_id),
        )
        with self._session.no_autoflush:
            row = (await self._session.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        return dict(row) | {
            "task_id": UUID(row["task_id"]), "project_id": UUID(row["project_id"]),
            "skill_tags": tuple(row["skill_tags"]),
        }

    async def read_audit_task_evidence(self, request: AuditTaskEvidenceRequest) -> AuditTaskEvidencePage | None:
        """Map one AUDIT-owned scoped statement into immutable TASK evidence."""
        if type(request) is not AuditTaskEvidenceRequest:
            raise ValueError("task evidence request is invalid")
        rows = await self._audit_repository.read_task_evidence_rows(
            request.project_id, request.task_id, request.limit,
            request.after.created_at if request.after else None,
            request.after.event_id if request.after else None,
        )
        if not rows:
            return None
        if rows[0].event_id is None:
            return AuditTaskEvidencePage(request.project_id, request.task_id, (), None)
        items = tuple(self._task_evidence_item(row, request) for row in rows[:request.limit])
        cursor = TaskEvidenceCursor(
            request.project_id, request.task_id, items[-1].created_at, items[-1].event_id,
        ) if len(rows) > request.limit else None
        return AuditTaskEvidencePage(request.project_id, request.task_id, items, cursor)

    @staticmethod
    def _task_evidence_item(row: Row, request: AuditTaskEvidenceRequest) -> AuditTaskEvidence:
        """Require exact transition references without exposing stored diagnostics."""
        assignment_id = decision_id = None
        try:
            if row.event_type in {"TaskCreated", "TaskScreened", "TaskReleased", "TaskClaimed", "TaskStarted", "TaskStartOverridden", "TaskAssignmentAuthorityRevoked"}:
                if (
                    UUID(row.reference_project_id) != request.project_id
                    or UUID(row.reference_task_id) != request.task_id
                ):
                    raise ValueError("scope")
                if row.event_type in {"TaskCreated", "TaskScreened", "TaskReleased"}:
                    if row.assignment_id is not None:
                        raise ValueError("manager assignment")
                else:
                    assignment_id = UUID(row.assignment_id)
                decision_id = UUID(row.authorization_decision_id)
            return AuditTaskEvidence(
                UUID(row.event_id), row.event_type, row.from_status, row.to_status,
                row.actor_id, row.created_at, assignment_id, decision_id,
            )
        except (TypeError, ValueError, AttributeError):
            raise TaskEvidenceInvalid("task audit evidence is invalid") from None

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

    async def lock_project_task(self, project_id: UUID, task_id: UUID) -> WorkstreamTask | None:
        """Conceal foreign tasks before taking their lock or resolving policy custody."""
        with self._session.no_autoflush:
            return await self._session.scalar(
                select(WorkstreamTask).where(
                    WorkstreamTask.project_id == str(project_id),
                    WorkstreamTask.id == str(task_id),
                ).with_for_update().execution_options(populate_existing=True)
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

    async def lock_invalidation_assignment(self, target) -> TaskAssignment | None:
        """Lock the event's original assignment, never a replacement active claim."""
        return await self._session.scalar(
            select(TaskAssignment).where(
                TaskAssignment.id == str(target.assignment_id),
                TaskAssignment.task_id == str(target.task_id),
                TaskAssignment.project_id == str(target.project_id),
                TaskAssignment.contributor_id == str(target.contributor_id),
            ).with_for_update().execution_options(populate_existing=True)
        )

    async def has_submission(self, task_id: UUID) -> bool:
        """Any retained Submission excludes ordinary pre-submit release."""
        return bool(await self._session.scalar(select(
            select(Submission.id).where(Submission.task_id == str(task_id)).exists(),
        )))

    async def lock_submission_context(
        self,
        request: TaskSubmissionContextRequest,
    ) -> TaskSubmissionContextFacts:
        """Lock and project exact TASK-owned Submission lifecycle facts.

        Args:
            request: Exact task, assignment, contributor, and predecessor selectors.

        Returns:
            Immutable TASK-owned context facts from the locked rows.

        Raises:
            TaskSubmissionContextUnavailable: When the context is invalid or the
                requested predecessor is no longer the latest Submission.
        """
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
            or assignment.project_id != task.project_id
            or assignment.submitter_contribution_policy_version_id is None
            or assignment.submitter_contribution_policy_version_id != task.locked_contribution_policy_version_id
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
                locked_contribution_policy_version_id=task.locked_contribution_policy_version_id,
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
                submitter_contribution_policy_version_id=assignment.submitter_contribution_policy_version_id,
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
            for_update: Whether to lock the selected Submission row.
            populate_existing: Whether to refresh an identity-mapped row from
                PostgreSQL.

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
