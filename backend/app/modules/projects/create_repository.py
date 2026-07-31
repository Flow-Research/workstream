"""Persistence boundary for authorized, idempotent project creation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import ProjectCreateIdempotencyRecord
from app.modules.projects.repository import ProjectRepositoryIntegrityError


class ProjectCreateRepository:
    """Own only the project-create reservation and completion protocol."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind project-create persistence to the caller's root transaction."""
        self._session = session

    async def reserve(
        self,
        *,
        actor_profile_id: str,
        identity_link_id: str,
        idempotency_key: UUID,
        request_digest: str,
    ) -> tuple[str, ProjectCreateIdempotencyRecord]:
        """Reserve or lock one actor-scoped project-create replay namespace."""
        values = {
            "id": uuid4(),
            "actor_profile_id": actor_profile_id,
            "identity_link_id": identity_link_id,
            "action_id": "project.create",
            "idempotency_key": idempotency_key,
            "request_digest": request_digest,
            "operation_id": uuid4(),
            "project_id": str(uuid4()),
            "operation_generation": 1,
            "status": "pending",
        }
        record_id = await self._session.scalar(
            insert(ProjectCreateIdempotencyRecord)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    ProjectCreateIdempotencyRecord.actor_profile_id,
                    ProjectCreateIdempotencyRecord.action_id,
                    ProjectCreateIdempotencyRecord.idempotency_key,
                ],
                set_={"id": ProjectCreateIdempotencyRecord.id},
            )
            .returning(ProjectCreateIdempotencyRecord.id)
        )
        if record_id is None:
            raise ProjectRepositoryIntegrityError("project reservation disappeared")
        record = await self._session.get(ProjectCreateIdempotencyRecord, record_id)
        if record is None:
            raise ProjectRepositoryIntegrityError("project reservation disappeared")
        if record_id == values["id"]:
            return "claimed", record
        if (
            record.identity_link_id != identity_link_id
            or record.request_digest != request_digest
        ):
            return "mismatch", record
        return ("replayed" if record.status == "committed" else "pending"), record

    async def complete(self, record: ProjectCreateIdempotencyRecord) -> None:
        """Commit exactly one pending project-create reservation."""
        completed = await self._session.scalar(
            update(ProjectCreateIdempotencyRecord)
            .where(
                ProjectCreateIdempotencyRecord.id == record.id,
                ProjectCreateIdempotencyRecord.status == "pending",
            )
            .values(status="committed", committed_at=datetime.now(UTC))
            .returning(ProjectCreateIdempotencyRecord.id)
        )
        if completed is None:
            raise ProjectRepositoryIntegrityError("invalid project reservation completion")
