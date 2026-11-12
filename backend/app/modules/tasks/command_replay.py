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
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.schemas import TaskResponse, TaskWithAssignmentResponse
from app.modules.tasks.service import TaskServiceError


# Frozen from genuine pre-size TaskResponse receipts. Never derive historical
# canonical fields from today's model defaults or retry an older hash on failure.
_RETAINED_TASK_RESPONSE_FIELDS = frozenset(
    (
        "acceptance_criteria",
        "assigned_to",
        "created_at",
        "created_by",
        "deadline_at",
        "description",
        "difficulty",
        "estimated_time_minutes",
        "external_task_id",
        "id",
        "import_batch_id",
        "locked_contribution_policy_version_id",
        "locked_effective_project_submission_artifact_policy_hash",
        "locked_effective_project_submission_artifact_policy_id",
        "locked_guide_source_snapshot_hash",
        "locked_guide_source_snapshot_id",
        "locked_guide_version",
        "locked_pre_submit_checker_bundle_hash",
        "locked_pre_submit_checker_policy_id",
        "locked_review_policy_generation",
        "locked_review_policy_hash",
        "locked_review_policy_id",
        "locked_revision_policy_generation",
        "locked_revision_policy_hash",
        "locked_revision_policy_id",
        "project_id",
        "rejection_criteria",
        "skill_tags",
        "source_payload_hash",
        "source_ref",
        "source_type",
        "status",
        "task_type",
        "title",
        "updated_at",
    )
)
RETAINED_TASK_IMPORT_FIELDS = (
    "external_task_id",
    "title",
    "description",
    "task_type",
    "difficulty",
    "skill_tags",
    "estimated_time_minutes",
    "acceptance_criteria",
    "rejection_criteria",
)


def retained_task_response(value: object) -> bool:
    """Recognize only the complete immutable pre-size response field set."""
    return type(value) is dict and value.keys() == _RETAINED_TASK_RESPONSE_FIELDS


def recorded_task_import_fields(value: object) -> tuple[str, ...]:
    """Choose canonical import fields from stored wire custody, before defaults."""
    if retained_task_response(value):
        return RETAINED_TASK_IMPORT_FIELDS
    if (
        type(value) is dict
        and value.keys() == _RETAINED_TASK_RESPONSE_FIELDS | {"task_size"}
        and value["task_size"] in ("small", "medium", "large")
    ):
        return (*RETAINED_TASK_IMPORT_FIELDS, "task_size")
    raise ValueError("recorded Task response format is invalid")


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

    async def creation_receipt(self, actor_id: UUID, key: UUID) -> TaskCommandReceipt | None:
        """Look up the exact receipt namespace before canonical creation defaults."""
        if not isinstance(key, UUID):
            raise ValueError("task command requires an idempotency UUID")
        return await self._session.scalar(
            select(TaskCommandReceipt)
            .where(
                TaskCommandReceipt.actor_profile_id == str(actor_id),
                TaskCommandReceipt.action_id == TaskAuthorityOperation.CREATE.value,
                TaskCommandReceipt.idempotency_key == key,
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def creation_value(
        project_id: UUID, payload, receipt: TaskCommandReceipt | None, *, size_explicit: bool
    ) -> dict:
        historical = bool(
            receipt is not None
            and receipt.status == "committed"
            and retained_task_response(receipt.response)
            and not size_explicit
        )
        return {
            "project_id": str(project_id),
            "payload": payload.model_dump(
                mode="json",
                exclude={"task_size"} if historical else set(),
            ),
        }

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

    @staticmethod
    def recover(
        receipt: TaskCommandReceipt, digest: str, facts: TaskAuthorityFacts,
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
                    or ("task_size" in response.model_fields_set and response.task_size != task.task_size)
                    or response.status != task.status or assignment is not None
                    or task.assigned_to is not None):
                raise TaskReplayConflict("task_replay_state_changed")
            return response
        if (
            assignment is None or assignment.status != "active"
            or receipt.assignment_id != assignment.id
            or receipt.contributor_id != assignment.contributor_id
            or task.assigned_to != assignment.contributor_id
            or receipt.locked_context_hash != facts.locked_context_hash
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
            or ("task_size" in captured_task.model_fields_set and captured_task.task_size != task.task_size)
            or captured_task.status != task.status or captured_task.assigned_to is not None
            or (isinstance(response, TaskWithAssignmentResponse) and (
                response.assignment.id != assignment.id
                or response.assignment.task_id != task.id
                or response.assignment.contributor_id != assignment.contributor_id
            ))
        ):
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
