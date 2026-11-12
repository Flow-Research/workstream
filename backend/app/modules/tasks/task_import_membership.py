"""One native membership validator shared by import/status and bulk transitions."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.task_import_membership import (
    TaskImportBatchError,
    TaskImportMemberIdentity,
)
from app.modules.tasks.command_replay import recorded_task_import_fields
from app.modules.tasks.models import TaskCommandReceipt, TaskImportBatch, TaskImportBatchMember
from app.modules.tasks.schemas import TaskImportBatchResponse


@dataclass(frozen=True, slots=True)
class TaskImportMembershipSnapshot:
    """TASK-internal typed original response plus complete immutable member custody."""

    creation: TaskImportBatchResponse
    manifest_digest: str
    members: tuple[TaskImportMemberIdentity, ...]


class TaskImportMembership:
    """Read actual immutable rows; caller AUTH remains separate and mandatory."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def prepare(self, project_id: UUID, batch_id: UUID) -> TaskImportMembershipSnapshot:
        """Select only a committed native batch in the existing caller transaction."""
        transaction = self._session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise RuntimeError("task import membership requires the caller transaction")
        batch = await self._session.scalar(select(TaskImportBatch).where(
            TaskImportBatch.id == str(batch_id), TaskImportBatch.project_id == str(project_id),
            TaskImportBatch.status == "committed",
        ).with_for_update(read=True, key_share=True).execution_options(populate_existing=True))
        if batch is None:
            raise TaskImportBatchError("task_import_batch_not_found", 404)
        return await self.validate(batch)

    async def validate(self, batch: TaskImportBatch) -> TaskImportMembershipSnapshot:
        """Recover immutable creation facts; mutable Task state is not replay input."""
        response = TaskImportBatchResponse.model_validate(batch.response)
        if (str(response.batch_id), str(response.project_id), str(response.source_id), response.sha256,
                response.byte_count, response.row_count, response.schema_version, response.mapping_version,
                response.created_at) != (
            batch.id, batch.project_id, batch.source_id, batch.sha256, batch.byte_count, batch.row_count,
            batch.schema_version, batch.mapping_version, batch.created_at,
        ):
            raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
        rows = (await self._session.execute(select(TaskImportBatchMember, TaskCommandReceipt).join(
            TaskCommandReceipt, TaskCommandReceipt.id == TaskImportBatchMember.task_command_receipt_id,
        ).where(TaskImportBatchMember.batch_id == batch.id).order_by(TaskImportBatchMember.row_index))).all()
        if len(rows) != batch.row_count:
            raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
        try:
            field_sets = tuple(recorded_task_import_fields(task) for task in batch.response["tasks"])
        except (ValueError, KeyError, TypeError) as exc:
            raise TaskImportBatchError("task_import_batch_custody_invalid", 409) from exc
        if len(set(field_sets)) != 1:
            raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
        fields = field_sets[0]
        manifest = {"schema_version": response.schema_version, "metadata": {"label": response.label},
                    "tasks": [{field: getattr(task, field) for field in fields} for task in response.tasks]}
        if response.label != batch.metadata_label or canonical_json_hash(manifest) != batch.manifest_digest:
            raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
        for index, (member, receipt) in enumerate(rows):
            original = response.tasks[index]
            instructions = {field: getattr(original, field) for field in fields}
            if (member.row_index != index or member.project_id != batch.project_id or member.task_id != original.id
                    or member.external_task_id != original.external_task_id
                    or member.row_digest != canonical_json_hash(instructions)
                    or member.response != original.model_dump(mode="json")
                    or receipt.response != member.response or receipt.status != "committed"
                    or receipt.action_id != "project.task.create" or receipt.task_id != member.task_id
                    or receipt.actor_profile_id != batch.actor_profile_id
                    or receipt.idempotency_key != member.create_idempotency_key
                    or original.created_by != batch.actor_profile_id):
                raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
        return TaskImportMembershipSnapshot(
            creation=response, manifest_digest=batch.manifest_digest,
            members=tuple(TaskImportMemberIdentity(
                member_id=UUID(member.id), task_id=UUID(member.task_id), row_index=member.row_index,
                external_task_id=member.external_task_id, row_digest=member.row_digest,
                create_idempotency_key=member.create_idempotency_key,
                task_command_receipt_id=member.task_command_receipt_id,
                authorization_decision_id=UUID(member.authorization_decision_id),
            ) for member, _ in rows),
        )
