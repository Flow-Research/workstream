"""Canonical project-authorized task commands with one transaction owner."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID
from app.core.identifiers import new_record_id

from pydantic import TypeAdapter

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.db.errors import integrity_constraint_name
from app.modules.tasks.api.authorization import (
    TaskAuthorityDecision,
    TaskAuthorityFacts,
    TaskAuthorityOperation,
    TaskAuthorizationPort,
)
from app.modules.tasks.api.task_detail import (
    ContributorTaskDetail, ContributorTaskDetailRequest, ManagementTaskDetail, ManagementTaskDetailRequest,
)
from app.modules.tasks.api.transition_audit import TaskPolicyLineage, TaskTransitionAuditPort, TaskTransitionFacts
from app.modules.tasks.api.audit_evidence import AuditTaskEvidenceRequest, AuditTaskEvidencePage, TaskEvidenceInvalid
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.command_replay import TaskCommandReplay
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    ContributorTaskLifecycle, ContributorTaskWorkContext, ManagementTaskWorkContext,
    ContributorTaskSubmissionRequirements, ManagementTaskSubmissionRequirements,
    ManagementTaskLockedContext, OperationalTaskLockedContext, AuditTaskLockedContext,
    AssignmentResponse,
    TaskCreate,
    TaskResponse,
    TaskWithAssignmentResponse,
)
from app.modules.tasks.service import (
    LOCKED_CONTEXT_REQUIRED_FIELDS,
    TaskAssignmentConflict,
    TaskNotFound,
    TaskProjectNotReady,
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
        contexts: TaskService,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._audit = audit
        self._actor_id = actor_profile_id
        self._repo = TaskRepository(session)
        self._contexts = contexts
        self._replay = TaskCommandReplay(session)

    def _facts(
        self,
        task: WorkstreamTask,
        assignment: TaskAssignment | None,
        operation: TaskAuthorityOperation,
        reason: str | None,
        idempotency_key: UUID | None = None,
        replay_assignment_id: UUID | None = None,
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
                {field: (str(getattr(task, field)) if isinstance(getattr(task, field), UUID)
                         else getattr(task, field)) for field in LOCKED_CONTEXT_REQUIRED_FIELDS}
            ),
            reason=reason,
            idempotency_key=idempotency_key,
            replay_assignment_id=replay_assignment_id,
        )

    async def _locked_task(
        self,
        task_id: UUID,
        operation: TaskAuthorityOperation,
        reason: str | None = None,
        project_id: UUID | None = None,
        idempotency_key: UUID | None = None,
        receipt: TaskCommandReceipt | None = None,
        request_digest: str | None = None,
    ) -> tuple[WorkstreamTask, TaskAssignment | None, TaskAuthorityDecision]:
        # Match submission creation: TASK/assignment locks precede AUTH locks.
        task = (await self._repo.lock_project_task(project_id, task_id) if project_id is not None
                else await self._repo.get_task(str(task_id), for_update=True))
        if task is None:
            raise TaskNotFound("task not found")
        assignment = await self._repo.get_active_assignment(task.id, for_update=True)
        facts = self._facts(
            task, assignment, operation, reason, idempotency_key,
            self._replay.replay_assignment(receipt, task_id) if receipt else None,
        )
        if request_digest is not None:
            facts = replace(facts, request_digest=request_digest,
                            replay_command_id=self._replay.manager_replay(receipt, operation, task_id, self._actor_id, idempotency_key) if receipt else None)
        handle = await self._authorization.prepare(facts)
        try:
            decision_id = await self._authorization.consume(handle, facts)
            return task, assignment, decision_id
        finally:
            self._authorization.close(handle)

    async def create_task(self, project_id: UUID, payload: TaskCreate, *, idempotency_key: UUID) -> TaskResponse:
        """Authorize the exact proposed task before creating it in the same transaction."""
        operation = TaskAuthorityOperation.CREATE
        async with self._session.begin():
            receipt, digest, reserved = await self._replay.reserve(
                self._actor_id, operation, idempotency_key, new_record_id(), None,
                request_value={"project_id": str(project_id), "payload": payload.model_dump(mode="json")},
            )
            # A duplicate may address an existing task: keep TASK before AUTH.
            current = await self._repo.get_task(receipt.task_id, for_update=True) if not reserved else None
            proposed = WorkstreamTask(id=receipt.task_id, project_id=str(project_id), status="draft",
                                     created_by=str(self._actor_id), **payload.model_dump())
            facts = replace(self._facts(proposed, None, operation, None, idempotency_key),
                            request_digest=digest, replay_command_id=self._replay.manager_replay(receipt, operation, UUID(proposed.id), self._actor_id, idempotency_key))
            handle = await self._authorization.prepare(facts)
            try:
                decision_id = await self._authorization.consume(handle, facts)
            finally:
                self._authorization.close(handle)
            project = await self._contexts._project_contexts.read_project_display(project_id)
            if project is None or project.id != project_id:
                raise TaskProjectNotReady("project not found")
            task = current if current is not None else proposed
            replayed = self._replay.recover(receipt, digest, self._facts(task, None, operation, None),
                                           task, None, reserved=reserved)
            if replayed is not None:
                return replayed
            task = await self._repo.add_task(task)
            await self._record_management(task, operation, decision_id, None, None)
            response = self._contexts.task_response_for_authority(task, can_manage=True)
            self._replay.complete(receipt, None, self._facts(task, None, operation, None), response)
            await self._session.flush()
        return response

    async def screen(self, task_id: UUID, reason: str | None, *, idempotency_key: UUID) -> TaskResponse:
        return await self._manage_transition(task_id, TaskAuthorityOperation.SCREEN, reason, idempotency_key)

    async def release(self, task_id: UUID, reason: str | None, *, idempotency_key: UUID) -> TaskResponse:
        return await self._manage_transition(task_id, TaskAuthorityOperation.RELEASE, reason, idempotency_key)

    async def _manage_transition(
        self, task_id: UUID, operation: TaskAuthorityOperation, reason: str | None, key: UUID,
    ) -> TaskResponse:
        async with self._session.begin():
            receipt, digest, reserved = await self._replay.reserve(self._actor_id, operation, key, task_id, reason)
            task, assignment, decision_id = await self._locked_task(
                task_id, operation, reason, idempotency_key=key, receipt=receipt, request_digest=digest,
            )
            replayed = self._replay.recover(receipt, digest, self._facts(task, assignment, operation, reason),
                                           task, assignment, reserved=reserved)
            if replayed is not None:
                return replayed
            before = task.status
            target = "screening" if operation is TaskAuthorityOperation.SCREEN else "ready"
            self._contexts._ensure_transition_allowed(before, target)
            if operation is TaskAuthorityOperation.SCREEN:
                context = await self._contexts._load_active_policy_context(task.project_id)
                self._contexts._validate_task_contract_fields(task)
                self._contexts._stamp_locked_context(task, context)
            else:
                if not reason or not reason.strip():
                    raise TaskValidationError("release decision reason is required")
                self._contexts._ensure_locked_context(task)
                context = await self._contexts._load_locked_task_context(task)
                self._contexts._validate_installed_plans(context.facts)
            task.status = target
            await self._session.flush()
            await self._record_management(task, operation, decision_id, before, reason)
            await self._session.flush()
            await self._session.refresh(task)
            response = self._contexts.task_response_for_authority(task, can_manage=True)
            self._replay.complete(receipt, None, self._facts(task, None, operation, reason), response)
            await self._session.flush()
        return response

    async def _record_management(
        self, task: WorkstreamTask, operation: TaskAuthorityOperation,
        decision_id: TaskAuthorityDecision, before: str | None, reason: str | None,
    ) -> None:
        await self._audit.record(TaskTransitionFacts(
            operation=operation, project_id=UUID(task.project_id), task_id=UUID(task.id),
            assignment_id=None, actor_profile_id=self._actor_id, authorization_decision_id=decision_id.decision_id,
            authority=decision_id,
            from_status=before, to_status=task.status, reason=reason,
            source_type=task.source_type if operation is TaskAuthorityOperation.CREATE else None,
            locked_lineage=TaskPolicyLineage.model_validate_json(json.dumps({
                field: str(getattr(task, field)) if isinstance(getattr(task, field), UUID) else getattr(task, field)
                for field in TaskPolicyLineage.model_fields}))
            if operation is not TaskAuthorityOperation.CREATE else None,
        ))

    async def claim(
        self, task_id: UUID, reason: str | None = None, *, idempotency_key: UUID,
    ) -> TaskWithAssignmentResponse:
        try:
            async with self._session.begin():
                receipt, digest, reserved = await self._replay.reserve(
                    self._actor_id, TaskAuthorityOperation.CLAIM, idempotency_key, task_id, reason,
                )
                task, assignment, decision_id = await self._locked_task(
                    task_id,
                    TaskAuthorityOperation.CLAIM,
                    reason,
                    idempotency_key=idempotency_key, receipt=receipt,
                )
                facts = self._facts(task, assignment, TaskAuthorityOperation.CLAIM, reason, idempotency_key)
                replayed = self._replay.recover(receipt, digest, facts, task, assignment, reserved=reserved)
                if replayed is not None:
                    if not isinstance(replayed, TaskWithAssignmentResponse):
                        raise RuntimeError("invalid claim response")
                    return replayed
                self._contexts._ensure_transition_allowed(task.status, "claimed")
                if assignment is not None or task.assigned_to is not None:
                    raise TaskAssignmentConflict("task already has an active assignment")
                await self._contexts._load_locked_task_context(task)
                assignment = await self._repo.add_assignment(
                    TaskAssignment(
                        id=str(new_record_id()),
                        task_id=task.id,
                        project_id=task.project_id,
                        submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
                        contributor_id=str(self._actor_id),
                        assigned_by=str(self._actor_id),
                        # Claim insertion follows live AUTH consumption; transaction
                        # start time cannot establish invalidation chronology.
                        assigned_at=func.clock_timestamp(),
                        accepted_at=datetime.now(UTC),
                        status="active",
                    )
                )
                task.assigned_to = str(self._actor_id)
                await self._transition(task, assignment, "claimed", decision_id.decision_id, reason)
                await self._session.flush()
                await self._session.refresh(task)
                response = TaskWithAssignmentResponse(
                    task=self._contexts.task_response_for_authority(task, can_manage=False),
                    assignment=AssignmentResponse.model_validate(assignment),
                )
                self._replay.complete(receipt, assignment, facts, response)
                await self._session.flush()
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
        idempotency_key: UUID,
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
            receipt, digest, reserved = await self._replay.reserve(
                self._actor_id, operation, idempotency_key, task_id, reason,
            )
            task, assignment, decision_id = await self._locked_task(
                task_id, operation, reason, idempotency_key=idempotency_key, receipt=receipt,
            )
            facts = self._facts(task, assignment, operation, reason, idempotency_key)
            replayed = self._replay.recover(receipt, digest, facts, task, assignment, reserved=reserved)
            if replayed is not None:
                if not isinstance(replayed, TaskResponse):
                    raise RuntimeError("invalid start response")
                return replayed
            self._contexts._ensure_transition_allowed(task.status, "in_progress")
            if assignment is None or assignment.contributor_id != task.assigned_to:
                raise TaskTransitionBlocked("task has no consistent active assignment")
            await self._contexts._load_locked_task_context(task)
            await self._transition(
                task,
                assignment,
                "in_progress",
                decision_id.decision_id,
                reason,
                operator_override=operator_override,
            )
            await self._session.flush()
            await self._session.refresh(task)
            response = self._contexts.task_response_for_authority(task, can_manage=False)
            self._replay.complete(receipt, assignment, facts, response)
            await self._session.flush()
        return response

    async def contributor_detail(self, task_id: UUID) -> ContributorTaskDetail:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.READ)

    async def management_detail(self, project_id: UUID, task_id: UUID) -> ManagementTaskDetail:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.MANAGEMENT_READ, project_id)

    async def contributor_requirements(self, task_id: UUID) -> ContributorTaskSubmissionRequirements:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.REQUIREMENTS)

    async def management_requirements(self, project_id: UUID, task_id: UUID) -> ManagementTaskSubmissionRequirements:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.MANAGEMENT_REQUIREMENTS, project_id)

    async def management_locked_context(self, project_id: UUID, task_id: UUID) -> ManagementTaskLockedContext:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.MANAGEMENT_LOCKED_CONTEXT, project_id)

    async def operational_locked_context(self, project_id: UUID, task_id: UUID) -> OperationalTaskLockedContext:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.OPERATIONAL_LOCKED_CONTEXT, project_id)

    async def audit_locked_context(self, project_id: UUID, task_id: UUID) -> AuditTaskLockedContext:
        return await self._read_task_projection(task_id, TaskAuthorityOperation.AUDIT_LOCKED_CONTEXT, project_id)

    async def audit_evidence(self, request: AuditTaskEvidenceRequest) -> AuditTaskEvidencePage:
        """Read bounded history under live exact authority, committing only valid facts."""
        if type(request) is not AuditTaskEvidenceRequest:
            raise TaskValidationError("task evidence request is invalid")
        request.__post_init__()
        async with self._session.begin():
            await self._locked_task(request.task_id, TaskAuthorityOperation.AUDIT_EVIDENCE, project_id=request.project_id)
            try:
                response = await self._repo.read_audit_task_evidence(request)
                if response is None:
                    raise TaskNotFound("task not found")
                adapter = TypeAdapter(AuditTaskEvidencePage)
                response = adapter.validate_json(adapter.dump_json(response, warnings="error"))
            except TaskEvidenceInvalid:
                raise TaskValidationError("task audit evidence is invalid") from None
        return response

    async def _read_task_projection(self, task_id: UUID, operation: TaskAuthorityOperation, project_id: UUID | None = None):
        """Consume exact authority and serialize detached facts before committing evidence."""
        if not isinstance(task_id, UUID) or (
            operation not in {TaskAuthorityOperation.READ, TaskAuthorityOperation.REQUIREMENTS}
            and not isinstance(project_id, UUID)
        ):
            raise TaskValidationError("task read selectors are invalid")
        response_type = {
            TaskAuthorityOperation.READ: ContributorTaskDetail,
            TaskAuthorityOperation.MANAGEMENT_READ: ManagementTaskDetail,
            TaskAuthorityOperation.REQUIREMENTS: ContributorTaskSubmissionRequirements,
            TaskAuthorityOperation.MANAGEMENT_REQUIREMENTS: ManagementTaskSubmissionRequirements,
            TaskAuthorityOperation.MANAGEMENT_LOCKED_CONTEXT: ManagementTaskLockedContext,
            TaskAuthorityOperation.OPERATIONAL_LOCKED_CONTEXT: OperationalTaskLockedContext,
            TaskAuthorityOperation.AUDIT_LOCKED_CONTEXT: AuditTaskLockedContext,
        }[operation]
        async with self._session.begin():
            task, _, _ = await self._locked_task(task_id, operation, project_id=project_id)
            exact_project = UUID(task.project_id)
            if operation is TaskAuthorityOperation.READ:
                response = await self._repo.read_contributor_task_detail(
                    ContributorTaskDetailRequest(exact_project, task_id, self._actor_id),
                )
            elif operation is TaskAuthorityOperation.MANAGEMENT_READ:
                response = await self._repo.read_management_task_detail(ManagementTaskDetailRequest(exact_project, task_id))
            else:
                context = await self._contexts._load_locked_task_context(task)
                if operation is TaskAuthorityOperation.REQUIREMENTS:
                    response = self._contexts._contributor_submission_requirements_response(task, context)
                elif operation is TaskAuthorityOperation.MANAGEMENT_REQUIREMENTS:
                    response = ManagementTaskSubmissionRequirements(**self._contexts._submission_requirement_values(task, context))
                elif operation is TaskAuthorityOperation.MANAGEMENT_LOCKED_CONTEXT:
                    response = self._contexts._management_locked_context_response(task, context)
                else:
                    response = response_type(**self._contexts._locked_context_reference_values(task))
            if response is None:
                raise TaskNotFound("task not found")
            adapter = TypeAdapter(response_type)
            response = adapter.validate_json(adapter.dump_json(response, warnings="error"))
        return response

    async def contributor_work_context(self, task_id: UUID) -> ContributorTaskWorkContext:
        """Project current contributor instructions under the existing exact authority."""
        if not isinstance(task_id, UUID):
            raise TaskValidationError("work context task ID is invalid")
        async with self._session.begin():
            task, assignment, _ = await self._locked_task(task_id, TaskAuthorityOperation.WORK_CONTEXT)
            context = await self._contexts._load_locked_task_context(task)
            detail = await self._repo.read_contributor_task_detail(
                ContributorTaskDetailRequest(UUID(task.project_id), task_id, self._actor_id),
            )
            if detail is None:
                raise TaskNotFound("task not found")
            own_assignment = bool(
                assignment is not None
                and assignment.contributor_id == str(self._actor_id)
                and task.assigned_to == str(self._actor_id)
            )
            actions = ()
            if task.status == "ready" and assignment is None and task.assigned_to is None:
                actions = ("claim",)
            elif task.status == "claimed" and own_assignment:
                actions = ("start",)
            selection = context.facts.activation_receipt.command
            response = ContributorTaskWorkContext(
                task=detail, project=context.facts.project, guide=context.facts.guide,
                review_policy=selection.review, revision_policy=selection.revision,
                contribution_policy_version_id=selection.contribution_policy_version_id,
                lifecycle=ContributorTaskLifecycle(
                    assigned_to_current_actor=own_assignment, next_actions=actions,
                ),
            )
        return response

    async def management_work_context(
        self, project_id: UUID, task_id: UUID,
    ) -> ManagementTaskWorkContext:
        """Project manager instructions through the existing exact project authority."""
        if not isinstance(project_id, UUID) or not isinstance(task_id, UUID):
            raise TaskValidationError("work context project or task ID is invalid")
        async with self._session.begin():
            task, _, _ = await self._locked_task(
                task_id, TaskAuthorityOperation.MANAGEMENT_WORK_CONTEXT, project_id=project_id,
            )
            context = await self._contexts._load_locked_task_context(task)
            detail = await self._repo.read_management_task_detail(ManagementTaskDetailRequest(project_id, task_id))
            if detail is None:
                raise TaskNotFound("task not found")
            selection = context.facts.activation_receipt.command
            response = ManagementTaskWorkContext(
                task=detail, project=context.facts.project, guide=context.facts.guide,
                review_policy=selection.review, revision_policy=selection.revision,
                contribution_policy_version_id=selection.contribution_policy_version_id,
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
