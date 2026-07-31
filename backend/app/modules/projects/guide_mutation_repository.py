"""Persistence for idempotent guide-metadata mutations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import GuideMutationIdempotencyRecord
from app.modules.projects.repository import ProjectRepositoryIntegrityError


class GuideMutationRepository:
    """Own guide-mutation replay reservations in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(
        self, actor_profile_id: str, action_id: str, idempotency_key: UUID
    ) -> GuideMutationIdempotencyRecord | None:
        """Load an existing replay record without creating product state."""
        return await self._session.scalar(
            select(GuideMutationIdempotencyRecord).where(
                GuideMutationIdempotencyRecord.actor_profile_id == actor_profile_id,
                GuideMutationIdempotencyRecord.action_id == action_id,
                GuideMutationIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )

    async def reserve(
        self,
        *,
        actor_profile_id: str,
        identity_link_id: str,
        action_id: str,
        idempotency_key: UUID,
        request_digest: str,
        resource_context_digest: str,
        operation_id: UUID,
        project_id: str,
        resource_id: str,
        operation_generation: int,
    ) -> tuple[str, GuideMutationIdempotencyRecord]:
        """Claim or lock one actor/action replay namespace."""
        values = {
            "id": uuid4(),
            "actor_profile_id": actor_profile_id,
            "identity_link_id": identity_link_id,
            "action_id": action_id,
            "idempotency_key": idempotency_key,
            "request_digest": request_digest,
            "resource_context_digest": resource_context_digest,
            "operation_id": operation_id,
            "project_id": project_id,
            "resource_id": resource_id,
            "operation_generation": operation_generation,
            "status": "pending",
        }
        record_id = await self._session.scalar(
            insert(GuideMutationIdempotencyRecord)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    GuideMutationIdempotencyRecord.actor_profile_id,
                    GuideMutationIdempotencyRecord.action_id,
                    GuideMutationIdempotencyRecord.idempotency_key,
                ],
                set_={"id": GuideMutationIdempotencyRecord.id},
            )
            .returning(GuideMutationIdempotencyRecord.id)
        )
        if record_id is None:
            raise ProjectRepositoryIntegrityError("guide mutation reservation disappeared")
        record = await self._session.get(GuideMutationIdempotencyRecord, record_id)
        if record is None:
            raise ProjectRepositoryIntegrityError("guide mutation reservation disappeared")
        if record_id == values["id"]:
            return "claimed", record
        if record.identity_link_id != identity_link_id or record.request_digest != request_digest:
            return "mismatch", record
        return ("replayed" if record.status == "committed" else "pending"), record

    async def complete(
        self,
        record: GuideMutationIdempotencyRecord,
        *,
        response_json: dict,
        setup_run_id: str | None = None,
    ) -> None:
        """Complete one reservation with its exact replay response."""
        completed = await self._session.scalar(
            update(GuideMutationIdempotencyRecord)
            .where(
                GuideMutationIdempotencyRecord.id == record.id,
                GuideMutationIdempotencyRecord.status == "pending",
            )
            .values(
                status="committed",
                response_json=response_json,
                setup_run_id=setup_run_id,
                committed_at=datetime.now(UTC),
            )
            .returning(GuideMutationIdempotencyRecord.id)
        )
        if completed is None:
            raise ProjectRepositoryIntegrityError("invalid guide mutation completion")
