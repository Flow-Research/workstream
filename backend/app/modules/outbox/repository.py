"""Caller-transaction persistence for shared outbox append and replay."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.schemas import OutboxAppendInput


@dataclass(frozen=True, slots=True)
class OutboxReservation:
    """Rows locked for one completed insert reservation or replay decision."""

    created: bool
    records: tuple[OutboxEvent, ...]


class OutboxRepository:
    """Reserve and lock event identities without taking transaction ownership."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind all persistence to the caller's exact session."""
        self._session = session

    async def reserve(
        self,
        value: OutboxAppendInput,
        *,
        payload_digest: str,
    ) -> OutboxReservation:
        """Insert a complete event or lock every conflicting identity in UUID order."""
        created_id = await self._session.scalar(
            insert(OutboxEvent)
            .values(
                event_id=value.event_id,
                event_type=value.event_type,
                event_version=value.event_version,
                aggregate_type=value.aggregate_type,
                aggregate_id=value.aggregate_id,
                project_id=str(value.project_id),
                correlation_id=value.correlation_id,
                causation_event_id=value.causation_event_id,
                idempotency_key=value.idempotency_key,
                payload=value.payload,
                payload_digest=payload_digest,
            )
            .on_conflict_do_nothing()
            .returning(OutboxEvent.event_id)
        )
        await self._session.flush()
        records = tuple(
            (
                await self._session.scalars(
                    select(OutboxEvent)
                    .where(
                        or_(
                            OutboxEvent.event_id == value.event_id,
                            OutboxEvent.idempotency_key == value.idempotency_key,
                        )
                    )
                    .order_by(OutboxEvent.event_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if not records:
            raise RuntimeError("outbox_reservation_not_visible")
        return OutboxReservation(created=created_id is not None, records=records)
