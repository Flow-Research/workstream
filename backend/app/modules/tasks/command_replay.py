"""Durable task command replay within the existing caller-owned transaction."""

from datetime import UTC, datetime
from uuid import UUID
from app.core.identifiers import new_record_id

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.authorization import TaskAuthorityFacts, TaskAuthorityOperation
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask, Submission
from app.modules.tasks.schemas import ContributorClaimTaskResponse, TaskResponse, TaskWithAssignmentResponse
from app.modules.tasks.service import TaskServiceError, LOCKED_CONTEXT_REQUIRED_FIELDS


class TaskReplayConflict(TaskServiceError):
    """A currently authorized retry conflicts with its durable command receipt."""

    status_code = 409

    def __init__(self, code: str):
        self.code = code
        super().__init__("Task command conflicts with the original request or current state")


class TaskCommandReplay:
    """Reserve first, then lock TASK and AUTH; never own a separate transaction."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def reserve(
        self, actor_id: UUID, operation: TaskAuthorityOperation, key: UUID,
        task_id: UUID, reason: str | None, *, request_value: dict | None = None,
        batch_transition_receipt_id: UUID | None = None,
    ) -> tuple[TaskCommandReceipt, str, bool]:
        if not isinstance(key, UUID):
            raise ValueError("task command requires an idempotency UUID")
        if batch_transition_receipt_id is not None and (
            operation not in {TaskAuthorityOperation.SCREEN, TaskAuthorityOperation.RELEASE}
            or request_value is not None or not isinstance(batch_transition_receipt_id, UUID)
        ):
            raise ValueError("batch receipt binding requires a canonical SCREEN/RELEASE participant")
        values = request_value if request_value is not None else {"task_id": str(task_id), "reason": reason}
        if batch_transition_receipt_id is not None:
            values = {**values, "batch_transition_receipt_id": str(batch_transition_receipt_id)}
        digest = canonical_json_hash(values)
        inserted_id = new_record_id()
        receipt_id = await self._session.scalar(
            insert(TaskCommandReceipt).values(
                id=inserted_id, actor_profile_id=str(actor_id), action_id=operation.value,
                idempotency_key=key, request_digest=digest, task_id=str(task_id), status="pending",
                batch_transition_receipt_id=batch_transition_receipt_id,
            ).on_conflict_do_update(
                index_elements=[TaskCommandReceipt.actor_profile_id, TaskCommandReceipt.action_id,
                                TaskCommandReceipt.idempotency_key],
                set_={"id": TaskCommandReceipt.id},
            ).returning(TaskCommandReceipt.id)
        )
        receipt = await self._session.get(TaskCommandReceipt, receipt_id, populate_existing=True)
        if receipt is None:
            raise RuntimeError("task command reservation disappeared")
        return receipt, digest, receipt_id == inserted_id

    @staticmethod
    def manager_replay(
        receipt: TaskCommandReceipt, operation: TaskAuthorityOperation, task_id: UUID,
        actor_id: UUID, key: UUID | None,
    ) -> UUID | None:
        """The namespace lookup, never request input, supplies post-state admission."""
        if (receipt.status == "committed" and receipt.action_id == operation.value
                and receipt.task_id == str(task_id) and receipt.actor_profile_id == str(actor_id)
                and key is not None and receipt.idempotency_key == key):
            return receipt.id
        return None

    @staticmethod
    def replay_assignment(receipt: TaskCommandReceipt, task_id: UUID) -> UUID | None:
        """Only a committed same-task receipt may request post-state authorization."""
        if receipt.status == "committed" and receipt.task_id == str(task_id) and receipt.assignment_id:
            return UUID(receipt.assignment_id)
        return None

    async def recover(
        self, receipt: TaskCommandReceipt, digest: str, facts: TaskAuthorityFacts,
        task: WorkstreamTask, assignment: TaskAssignment | None, *, reserved: bool,
    ) -> TaskResponse | TaskWithAssignmentResponse | None:
        """Call only after fresh exact AUTH; a receipt never supplies authority."""
        if receipt.request_digest != digest or receipt.task_id != task.id:
            raise TaskReplayConflict("idempotency_mismatch")
        if receipt.status == "pending":
            if reserved:
                return None
            raise TaskReplayConflict("idempotency_pending")
        if facts.operation in {TaskAuthorityOperation.CREATE, TaskAuthorityOperation.SCREEN, TaskAuthorityOperation.RELEASE}:
            try:
                response = TaskResponse.model_validate(receipt.response)
            except ValidationError as exc:
                raise TaskReplayConflict("task_replay_state_changed") from exc
            if (receipt.assignment_id is not None or receipt.contributor_id is not None
                    or receipt.locked_context_hash != facts.locked_context_hash
                    or response.id != task.id or response.project_id != task.project_id
                    or response.task_size != task.task_size
                    or response.status != task.status or assignment is not None
                    or task.assigned_to is not None):
                raise TaskReplayConflict("task_replay_state_changed")
            return response
        if (
            assignment is None or assignment.status != "active"
            or receipt.assignment_id != assignment.id
            or receipt.contributor_id != assignment.contributor_id
            or task.assigned_to != assignment.contributor_id
        ):
            raise TaskReplayConflict("task_replay_state_changed")
        response_type = TaskWithAssignmentResponse if facts.operation is TaskAuthorityOperation.CLAIM else TaskResponse
        try:
            response = response_type.model_validate(receipt.response)
        except ValidationError as exc:
            raise TaskReplayConflict("task_replay_state_changed") from exc
        captured_task = response.task if isinstance(response, TaskWithAssignmentResponse) else response
        if (
            captured_task.id != task.id or captured_task.project_id != task.project_id
            or captured_task.task_size != task.task_size
            or captured_task.status != "in_progress" or captured_task.assigned_to is not None
            or (isinstance(response, TaskWithAssignmentResponse) and (
                response.assignment.id != assignment.id
                or response.assignment.task_id != task.id
                or response.assignment.contributor_id != assignment.contributor_id
            ))
        ):
            raise TaskReplayConflict("task_replay_state_changed")
        if (receipt.actor_profile_id != str(facts.actor_profile_id)
                or task.status not in {"in_progress", "needs_revision", "evaluation_pending", "review_pending"}):
            raise TaskReplayConflict("task_replay_state_changed")
        if receipt.locked_context_hash != facts.locked_context_hash or task.status != captured_task.status:
            original = await self._session.scalar(select(Submission).where(
                Submission.task_id == task.id, Submission.task_assignment_id == assignment.id,
                Submission.contributor_id == assignment.contributor_id,
            ).order_by(Submission.version).limit(1))
            if original is None:
                raise TaskReplayConflict("task_replay_state_changed")
            context = {
                field: getattr(original, "contribution_policy_version_id" if field ==
                               "locked_contribution_policy_version_id" else field)
                for field in LOCKED_CONTEXT_REQUIRED_FIELDS
            }
            original_hash = canonical_json_hash({
                field: str(value) if isinstance(value, UUID) else value
                for field,value in context.items()
            })
            # The full immutable context proves the receipt hash. The captured
            # contributor result intentionally masks private policy coordinates.
            if (original.task_size != captured_task.task_size or original_hash != receipt.locked_context_hash
                    or any(str(getattr(captured_task, field)) != str(value)
                           for field,value in context.items() if field in ContributorClaimTaskResponse.model_fields)):
                raise TaskReplayConflict("task_replay_state_changed")
        return response

    @staticmethod
    def complete(
        receipt: TaskCommandReceipt, assignment: TaskAssignment | None, facts: TaskAuthorityFacts,
        response: TaskResponse | TaskWithAssignmentResponse,
    ) -> None:
        """Stage the result alongside the assignment, transition and evidence."""
        if receipt.status != "pending":
            raise RuntimeError("task command receipt already completed")
        receipt.assignment_id = assignment.id if assignment else None
        receipt.contributor_id = assignment.contributor_id if assignment else None
        receipt.locked_context_hash = facts.locked_context_hash
        receipt.response = response.model_dump(mode="json")
        receipt.status = "committed"
        receipt.committed_at = datetime.now(UTC)
