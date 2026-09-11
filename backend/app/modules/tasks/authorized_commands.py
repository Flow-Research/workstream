"""Canonical project-authorized task commands with one transaction owner."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.db.errors import integrity_constraint_name
from app.modules.tasks.api.authorization import (
    TaskAuthorityFacts,
    TaskAuthorityOperation,
    TaskAuthorizationPort,
)
from app.modules.tasks.api.transition_audit import TaskTransitionAuditPort, TaskTransitionFacts
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    AssignmentResponse,
    TaskResponse,
    TaskWithAssignmentResponse,
    TaskWorkContextResponse,
    TaskWorkerLifecycleContext,
)
from app.modules.tasks.service import (
    LOCKED_CONTEXT_REQUIRED_FIELDS,
    TaskAssignmentConflict,
    TaskNotFound,
    TaskService,
    TaskTransitionBlocked,
    TaskValidationError,
)


class AuthorizedTaskCommands:
    """TASK owns state and assignment; AUTH owns permission and current grants."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: TaskAuthorizationPort,
        audit: TaskTransitionAuditPort,
        actor_profile_id: UUID,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._audit = audit
        self._actor_id = actor_profile_id
        self._repo = TaskRepository(session)
        self._contexts = TaskService(session)

    def _facts(
        self,
        task: WorkstreamTask,
        assignment: TaskAssignment | None,
        operation: TaskAuthorityOperation,
        reason: str | None,
    ) -> TaskAuthorityFacts:
        return TaskAuthorityFacts(
            operation=operation,
            task_id=UUID(task.id),
            project_id=UUID(task.project_id),
            actor_profile_id=self._actor_id,
            task_status=task.status,
            assigned_to=UUID(task.assigned_to) if task.assigned_to else None,
            assignment_id=UUID(assignment.id) if assignment else None,
            assignment_contributor_id=UUID(assignment.contributor_id) if assignment else None,
            locked_context_hash=canonical_json_hash(
                {field: getattr(task, field) for field in LOCKED_CONTEXT_REQUIRED_FIELDS}
            ),
            reason=reason,
        )

    async def _locked_task(
        self,
        task_id: UUID,
        operation: TaskAuthorityOperation,
        reason: str | None = None,
        project_id: UUID | None = None,
    ) -> tuple[WorkstreamTask, TaskAssignment | None, UUID]:
        # Match submission creation: TASK/assignment locks precede AUTH locks.
        task = await self._repo.get_task(str(task_id), for_update=True)
        if task is None or (project_id is not None and task.project_id != str(project_id)):
            raise TaskNotFound("task not found")
        assignment = await self._repo.get_active_assignment(task.id, for_update=True)
        facts = self._facts(task, assignment, operation, reason)
        handle = await self._authorization.prepare(facts)
        try:
            decision_id = await self._authorization.consume(handle, facts)
            return task, assignment, decision_id
        finally:
            self._authorization.close(handle)

    async def claim(self, task_id: UUID, reason: str | None = None) -> TaskWithAssignmentResponse:
        try:
            async with self._session.begin():
                task, assignment, decision_id = await self._locked_task(
                    task_id,
                    TaskAuthorityOperation.CLAIM,
                    reason,
                )
                self._contexts._ensure_transition_allowed(task.status, "claimed")
                if assignment is not None or task.assigned_to is not None:
                    raise TaskAssignmentConflict("task already has an active assignment")
                await self._contexts._load_locked_task_context(task)
                assignment = await self._repo.add_assignment(
                    TaskAssignment(
                        id=str(uuid4()),
                        task_id=task.id,
                        contributor_id=str(self._actor_id),
                        assigned_by=str(self._actor_id),
                        accepted_at=datetime.now(UTC),
                        status="active",
                    )
                )
                task.assigned_to = str(self._actor_id)
                await self._transition(task, assignment, "claimed", decision_id, reason)
                await self._session.flush()
                await self._session.refresh(task)
                response = TaskWithAssignmentResponse(
                    task=self._contexts.task_response_for_authority(task, can_manage=False),
                    assignment=AssignmentResponse.model_validate(assignment),
                )
            return response
        except IntegrityError as exc:
            if integrity_constraint_name(exc) == "uq_task_assignments_one_active_per_task":
                raise TaskAssignmentConflict("task already has an active assignment") from exc
            raise

    async def start(
        self,
        task_id: UUID,
        reason: str | None = None,
        *,
        operator_override: bool = False,
    ) -> TaskResponse:
        if operator_override and not (reason and reason.strip()):
            raise TaskValidationError("operator start override reason is required")
        operation = (
            TaskAuthorityOperation.START_OVERRIDE
            if operator_override
            else TaskAuthorityOperation.START
        )
        async with self._session.begin():
            task, assignment, decision_id = await self._locked_task(task_id, operation, reason)
            self._contexts._ensure_transition_allowed(task.status, "in_progress")
            if assignment is None or assignment.contributor_id != task.assigned_to:
                raise TaskTransitionBlocked("task has no consistent active assignment")
            await self._contexts._load_locked_task_context(task)
            await self._transition(
                task,
                assignment,
                "in_progress",
                decision_id,
                reason,
                operator_override=operator_override,
            )
            await self._session.flush()
            await self._session.refresh(task)
            response = self._contexts.task_response_for_authority(task, can_manage=False)
        return response

    async def work_context(
        self,
        task_id: UUID,
        *,
        project_id: UUID | None = None,
    ) -> TaskWorkContextResponse:
        operation = (
            TaskAuthorityOperation.MANAGEMENT_WORK_CONTEXT
            if project_id is not None
            else TaskAuthorityOperation.WORK_CONTEXT
        )
        async with self._session.begin():
            task, assignment, _ = await self._locked_task(task_id, operation, project_id=project_id)
            context = await self._contexts._load_locked_task_context(task)
            own_assignment = bool(
                assignment is not None
                and assignment.contributor_id == str(self._actor_id)
                and task.assigned_to == str(self._actor_id)
            )
            actions = []
            if project_id is None:
                if task.status == "ready" and assignment is None and task.assigned_to is None:
                    actions = ["claim"]
                elif task.status == "claimed" and own_assignment:
                    actions = ["start"]
            response = self._contexts._work_context_response(
                task,
                context,
                lifecycle=TaskWorkerLifecycleContext(
                    status=task.status,
                    assigned_to_current_actor=own_assignment,
                    can_run_pre_submit_check=False,
                    can_submit=False,
                    next_actions=actions,
                ),
            )
        return response

    async def _transition(
        self,
        task: WorkstreamTask,
        assignment: TaskAssignment,
        status: str,
        decision_id: UUID,
        reason: str | None,
        *,
        operator_override: bool = False,
    ) -> None:
        before = task.status
        task.status = status
        await self._audit.record(TaskTransitionFacts(
            operation=(
                TaskAuthorityOperation.START_OVERRIDE if operator_override
                else TaskAuthorityOperation.CLAIM if status == "claimed"
                else TaskAuthorityOperation.START
            ),
            project_id=UUID(task.project_id), task_id=UUID(task.id),
            assignment_id=UUID(assignment.id), actor_profile_id=self._actor_id,
            authorization_decision_id=decision_id,
            from_status=before, to_status=status, reason=reason,
        ))
