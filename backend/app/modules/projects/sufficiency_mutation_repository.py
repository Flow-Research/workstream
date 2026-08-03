"""Replay persistence for authorized guide-sufficiency mutations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import GuideSufficiencyMutationIdempotencyRecord
from app.modules.projects.repository import ProjectRepositoryIntegrityError


class GuideSufficiencyMutationReplayRepository:
    """Own only guide-sufficiency replay rows in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(
        self, actor_profile_id: str, action_id: str, idempotency_key: UUID
    ) -> GuideSufficiencyMutationIdempotencyRecord | None:
        """Find one actor/key replay record; callers verify the requested action."""
        del action_id
        return await self._session.scalar(
            select(GuideSufficiencyMutationIdempotencyRecord).where(
                GuideSufficiencyMutationIdempotencyRecord.actor_profile_id == actor_profile_id,
                GuideSufficiencyMutationIdempotencyRecord.idempotency_key == idempotency_key,
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
        guide_id: str,
        source_snapshot_id: str,
        report_id: str | None,
        setup_run_id: str | None,
        setup_generation: int,
    ) -> tuple[
        Literal["claimed", "mismatch", "pending", "replayed"],
        GuideSufficiencyMutationIdempotencyRecord,
    ]:
        """Claim or classify one exact replay namespace."""
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
            "guide_id": guide_id,
            "source_snapshot_id": source_snapshot_id,
            "report_id": report_id,
            "setup_run_id": setup_run_id,
            "setup_generation": setup_generation,
            "status": "pending",
        }
        record_id = await self._session.scalar(
            insert(GuideSufficiencyMutationIdempotencyRecord)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    GuideSufficiencyMutationIdempotencyRecord.actor_profile_id,
                    GuideSufficiencyMutationIdempotencyRecord.idempotency_key,
                ]
            )
            .returning(GuideSufficiencyMutationIdempotencyRecord.id)
        )
        if record_id is None:
            record = await self.find(actor_profile_id, action_id, idempotency_key)
            if record is None:
                raise ProjectRepositoryIntegrityError("sufficiency replay reservation disappeared")
        else:
            record = await self._session.get(GuideSufficiencyMutationIdempotencyRecord, record_id)
            if record is None:
                raise ProjectRepositoryIntegrityError("sufficiency replay reservation disappeared")
        if record_id == values["id"]:
            return "claimed", record
        if (
            record.action_id != action_id
            or record.identity_link_id != identity_link_id
            or record.request_digest != request_digest
            or record.project_id != project_id
            or record.guide_id != guide_id
            or record.source_snapshot_id != source_snapshot_id
            or record.report_id != report_id
            or record.setup_run_id != setup_run_id
            or record.setup_generation != setup_generation
        ):
            return "mismatch", record
        return ("replayed" if record.status == "committed" else "pending"), record

    async def complete(
        self,
        record: GuideSufficiencyMutationIdempotencyRecord,
        *,
        response_json: dict,
        report_id: str,
    ) -> None:
        """Complete one pending reservation with stable response custody."""
        completed = await self._session.scalar(
            update(GuideSufficiencyMutationIdempotencyRecord)
            .where(
                GuideSufficiencyMutationIdempotencyRecord.id == record.id,
                GuideSufficiencyMutationIdempotencyRecord.status == "pending",
            )
            .values(
                status="committed",
                response_json=response_json,
                report_id=report_id,
                committed_at=datetime.now(UTC),
            )
            .returning(GuideSufficiencyMutationIdempotencyRecord.id)
        )
        if completed is None:
            raise ProjectRepositoryIntegrityError("invalid sufficiency replay completion")
