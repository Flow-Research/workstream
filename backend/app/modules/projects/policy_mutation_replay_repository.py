"""Replay-only persistence for guide-bound policy mutations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import PolicyMutationIdempotencyRecord
from app.modules.projects.repository import ProjectRepositoryIntegrityError


class PolicyMutationReplayRepository:
    """Own only policy-mutation replay records in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(
        self, actor_profile_id: str, action_id: str, idempotency_key: UUID
    ) -> PolicyMutationIdempotencyRecord | None:
        return await self._session.scalar(
            select(PolicyMutationIdempotencyRecord).where(
                PolicyMutationIdempotencyRecord.actor_profile_id == actor_profile_id,
                PolicyMutationIdempotencyRecord.action_id == action_id,
                PolicyMutationIdempotencyRecord.idempotency_key == idempotency_key,
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
        policy_hash: str,
        resource_context_digest: str,
        operation_id: UUID,
        project_id: str,
        guide_id: str,
        policy_id: str,
        policy_generation: int,
    ) -> tuple[str, PolicyMutationIdempotencyRecord]:
        values = {
            "id": uuid4(),
            "actor_profile_id": actor_profile_id,
            "identity_link_id": identity_link_id,
            "action_id": action_id,
            "idempotency_key": idempotency_key,
            "request_digest": request_digest,
            "policy_hash": policy_hash,
            "resource_context_digest": resource_context_digest,
            "operation_id": operation_id,
            "project_id": project_id,
            "guide_id": guide_id,
            "policy_id": policy_id,
            "policy_generation": policy_generation,
            "status": "pending",
        }
        record_id = await self._session.scalar(
            insert(PolicyMutationIdempotencyRecord)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    PolicyMutationIdempotencyRecord.actor_profile_id,
                    PolicyMutationIdempotencyRecord.action_id,
                    PolicyMutationIdempotencyRecord.idempotency_key,
                ],
                set_={"id": PolicyMutationIdempotencyRecord.id},
            )
            .returning(PolicyMutationIdempotencyRecord.id)
        )
        if record_id is None:
            raise ProjectRepositoryIntegrityError("policy mutation reservation disappeared")
        record = await self._session.get(PolicyMutationIdempotencyRecord, record_id)
        if record is None:
            raise ProjectRepositoryIntegrityError("policy mutation reservation disappeared")
        if record_id == values["id"]:
            return "claimed", record
        if (
            record.project_id != project_id
            or record.guide_id != guide_id
            or record.request_digest != request_digest
            or record.policy_hash != policy_hash
        ):
            return "mismatch", record
        return ("replayed" if record.status == "committed" else "pending"), record

    async def complete(
        self, record: PolicyMutationIdempotencyRecord, *, response_json: dict
    ) -> None:
        completed = await self._session.scalar(
            update(PolicyMutationIdempotencyRecord)
            .where(
                PolicyMutationIdempotencyRecord.id == record.id,
                PolicyMutationIdempotencyRecord.status == "pending",
            )
            .values(
                status="committed",
                response_json=response_json,
                committed_at=datetime.now(UTC),
            )
            .returning(PolicyMutationIdempotencyRecord.id)
        )
        if completed is None:
            raise ProjectRepositoryIntegrityError("invalid policy mutation completion")
