"""Private ART persistence primitives; no storage, acceptance or AUTH capability.

The future foreground composition must authorize and reserve physical capacity
before allowing storage writes. These flush-only operations leave root commits
and replay authorization to that composition. Expired foreground work is never
resumed by another request or by a background PRE worker.
"""

from datetime import datetime
import json
import re
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource, SubmissionIntakeMetadata, SubmissionSourceLocation,
    SubmissionSourceCapacityLimits,
)
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.artifacts.intake.capacity import SubmissionSourceCapacity
from app.modules.artifacts.models import ArtifactStorageNamespace
from app.modules.tasks.api.intake_custody import IntakeTaskCustodyPort
from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest


class IntakeCustodyConflict(RuntimeError):
    """A private owner conflict, never a quality verdict or permission grant."""


class SubmissionIntakeRepository:
    """Persist exact source facts under TASK-first locks and a live owner fence."""

    def __init__(self, session: AsyncSession, tasks: IntakeTaskCustodyPort) -> None:
        self._session = session
        self._tasks = tasks
        self._capacity = SubmissionSourceCapacity(session)

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise IntakeCustodyConflict("intake_requires_root_transaction")

    async def reserve(
        self, *, metadata: SubmissionIntakeMetadata, actor_id: UUID, identity_link_id: UUID,
        idempotency_key: UUID, maximum_raw_bytes: int,
        upload_deadline_at: datetime, lease_expires_at: datetime,
        capacity_limits: SubmissionSourceCapacityLimits, declared_raw_bytes: int | None,
    ) -> SubmissionIntakeOperation:
        """Reserve command and physical bytes; callers still own AUTH and full T1 admission."""
        self._require_transaction()
        metadata = SubmissionIntakeMetadata.model_validate(metadata)
        operation_id = new_record_id()
        snapshot = await self._tasks.claim(TaskSubmissionContextRequest(
            metadata.task_id, metadata.assignment_id, actor_id, metadata.predecessor_submission_id,
        ), operation_id)
        namespace = await self._session.get(ArtifactStorageNamespace, "primary")
        if namespace is None:
            raise IntakeCustodyConflict("intake_namespace_unavailable")
        location = SubmissionSourceLocation(
            operation_id=operation_id, namespace_id=namespace.id,
            namespace_fingerprint=namespace.namespace_fingerprint,
            provider_profile=namespace.provider_profile,
        )
        context = json.loads(snapshot.context_json)
        row = SubmissionIntakeOperation(
            id=str(operation_id), project_id=str(snapshot.project_id),
            task_id=str(metadata.task_id), assignment_id=str(metadata.assignment_id),
            actor_profile_id=str(actor_id), identity_link_id=str(identity_link_id),
            idempotency_key=str(idempotency_key), command_metadata=metadata.model_dump(mode="json"),
            metadata_sha256=metadata.metadata_sha256(), locked_task_context=context,
            locked_context_sha256=canonical_json_hash(context), eligible_task_status=snapshot.eligible_status,
            namespace_id=location.namespace_id, namespace_fingerprint=location.namespace_fingerprint,
            provider_profile=location.provider_profile, object_ref=location.object_ref,
            maximum_raw_bytes=maximum_raw_bytes, state="receiving",
            lease_id=str(new_record_id()), lease_generation=1,
            lease_expires_at=lease_expires_at, upload_deadline_at=upload_deadline_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        await self._capacity.reserve(row, limits=capacity_limits, declared_raw_bytes=declared_raw_bytes)
        return row

    async def _lock(self, operation_id: UUID) -> SubmissionIntakeOperation:
        self._require_transaction()
        task_id = await self._session.scalar(select(SubmissionIntakeOperation.task_id).where(
            SubmissionIntakeOperation.id == str(operation_id),
        ))
        if task_id is None:
            raise IntakeCustodyConflict("intake_unavailable")
        await self._tasks.lock(UUID(task_id))
        row = await self._session.scalar(select(SubmissionIntakeOperation).where(
            SubmissionIntakeOperation.id == str(operation_id),
        ).with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise IntakeCustodyConflict("intake_unavailable")
        return row

    async def _owned(self, operation_id: UUID, lease_id: UUID, generation: int) -> SubmissionIntakeOperation:
        row = await self._lock(operation_id)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (row.state not in {"receiving", "pre_checking"} or row.lease_id != str(lease_id)
                or row.lease_generation != generation or row.lease_expires_at <= now):
            raise IntakeCustodyConflict("intake_owner_stale")
        return row

    async def record_eof(self, operation_id: UUID, lease_id: UUID, generation: int,
                         *, raw_sha256: str, raw_byte_count: int) -> None:
        """Persist ingress identity before the adapter may complete the object."""
        row = await self._owned(operation_id, lease_id, generation)
        if row.state != "receiving" or row.raw_sha256 is not None:
            raise IntakeCustodyConflict("intake_eof_already_recorded")
        row.raw_sha256, row.raw_byte_count = raw_sha256, raw_byte_count
        row.eof_at = func.clock_timestamp()
        await self._session.flush()

    async def seal(self, operation_id: UUID, lease_id: UUID, generation: int,
                   *, provider_generation: str, pre_deadline_at: datetime,
                   lease_expires_at: datetime) -> SealedSubmissionSource:
        """Bind the known completed generation; this does not prove provider I/O."""
        row = await self._owned(operation_id, lease_id, generation)
        if row.state != "receiving" or row.raw_sha256 is None or row.provider_generation is not None:
            raise IntakeCustodyConflict("intake_source_not_sealable")
        row.provider_generation, row.pre_deadline_at = provider_generation, pre_deadline_at
        row.sealed_at, row.sealed_upload_fence = func.clock_timestamp(), generation
        row.state, row.lease_expires_at = "pre_checking", lease_expires_at
        await self._session.flush()
        await self._session.refresh(row)
        await self._capacity.seal(row)
        return SealedSubmissionSource(
            location=SubmissionSourceLocation(
                operation_id=operation_id, namespace_id=row.namespace_id,
                namespace_fingerprint=row.namespace_fingerprint, provider_profile=row.provider_profile,
            ), provider_generation=row.provider_generation, raw_sha256=row.raw_sha256,
            raw_byte_count=row.raw_byte_count, sealed_upload_fence=row.sealed_upload_fence,
        )

    async def heartbeat(self, operation_id: UUID, lease_id: UUID, generation: int,
                        *, lease_expires_at: datetime) -> None:
        """Renew within the immutable phase deadline; never revive an expired owner."""
        row = await self._owned(operation_id, lease_id, generation)
        row.lease_expires_at = lease_expires_at
        await self._session.flush()

    async def terminalize(self, operation_id: UUID, lease_id: UUID, generation: int,
                          *, state: str, failure_code: str) -> None:
        """Fence conclusively ended foreground work and clear only its task guard."""
        if state not in {"failed", "rejected", "cancelled"}:
            raise IntakeCustodyConflict("intake_terminal_state_invalid")
        row = await self._owned(operation_id, lease_id, generation)
        await self._terminal(row, state, failure_code)

    async def abandon_expired(self, operation_id: UUID) -> bool:
        """Recovery can end expired foreground custody, never resume or accept it."""
        row = await self._lock(operation_id)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if row.state not in {"receiving", "pre_checking"} or row.lease_expires_at > now:
            return False
        await self._terminal(row, "abandoned", "submission_foreground_expired")
        return True

    async def _terminal(self, row: SubmissionIntakeOperation, state: str, code: str) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,99}", code) is None:
            raise IntakeCustodyConflict("intake_failure_code_invalid")
        row.state, row.failure_code = state, code
        row.lease_generation += 1
        row.terminal_at = func.clock_timestamp()
        await self._session.flush()
        await self._tasks.release(UUID(row.task_id), UUID(row.id))
