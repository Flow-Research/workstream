"""Feature-neutral shared outbox append participant."""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.repository import OutboxRepository
from app.modules.outbox.api import (
    OutboxAppendDisposition,
    OutboxAppendInput,
    OutboxAppendResult,
    OutboxIdempotencyConflict,
    OutboxInputError,
    OutboxPersistenceError,
    OutboxDeliveryObservation,
)


def _raise_input_error() -> NoReturn:
    """Raise one stable input error from a payload-free frame."""
    raise OutboxInputError("outbox_invalid_input")


def _raise_persistence_error() -> NoReturn:
    """Raise one stable persistence error from a payload-free frame."""
    raise OutboxPersistenceError("outbox_persistence_failed")


def _raise_idempotency_conflict() -> NoReturn:
    """Raise one stable conflict from a payload-free frame."""
    raise OutboxIdempotencyConflict("outbox_idempotency_conflict")


def _validated_input(value: object) -> OutboxAppendInput:
    """Revalidate a typed input without reflecting payload details in failures."""
    fields: dict[str, object] | None = None
    validated: OutboxAppendInput | None = None
    try:
        fields = dict(object.__getattribute__(value, "__dict__"))
        validated = OutboxAppendInput.model_validate(fields)
    except Exception:  # noqa: BLE001 - rejected values must not escape diagnostics
        pass
    if validated is None:
        value = None
        fields = None
        _raise_input_error()
    return validated.model_copy(deep=True)


def _matches(record: OutboxEvent, value: OutboxAppendInput, digest: str) -> bool:
    """Compare every immutable caller fact while ignoring operational metadata."""
    return (
        record.event_type == value.event_type
        and record.event_version == value.event_version
        and record.producer == "workstream"
        and record.aggregate_type == value.aggregate_type
        and record.aggregate_id == value.aggregate_id
        and record.project_id == str(value.project_id)
        and record.correlation_id == value.correlation_id
        and record.causation_event_id == value.causation_event_id
        and record.idempotency_key == value.idempotency_key
        and record.payload_digest == digest
        and record.payload == value.payload
        and record.not_before_at == value.not_before_at
    )


class OutboxService:
    """Append immutable events by flushing only the caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the participant to one caller session; never commit or publish."""
        self._repository = OutboxRepository(session)

    async def _require_record(self, event_id: UUID | None, value: OutboxAppendInput) -> OutboxEvent:
        """One exact custody check shared by identity and operational reads."""
        validated = _validated_input(value)
        digest = canonical_json_hash(validated.payload)
        try:
            record = await self._repository.read_exact(event_id, validated)
        except SQLAlchemyError:
            _raise_persistence_error()
        if record is None or not _matches(record, validated, digest):
            _raise_idempotency_conflict()
        return record

    async def require_existing(self, event_id: UUID | None, value: OutboxAppendInput) -> UUID:
        """Validate exact immutable custody without inserting or locking delivery state."""
        return UUID(str((await self._require_record(event_id, value)).event_id))

    async def observe_delivery(self, event_id: UUID, value: OutboxAppendInput) -> OutboxDeliveryObservation:
        """Observe durable progress without claiming, retrying or publishing work."""
        record = await self._require_record(event_id, value)
        return OutboxDeliveryObservation(
            event_id=UUID(str(record.event_id)), state=record.delivery_state,
            attempt_count=record.attempt_count, next_attempt_at=record.next_attempt_at,
            finalized_at=record.finalized_at, error_code=record.last_error_code,
        )

    async def append(self, value: OutboxAppendInput) -> OutboxAppendResult:
        """Create one event or return its exact idempotent replay."""
        validated = None
        try:
            validated = _validated_input(value)
        except OutboxInputError:
            pass
        if validated is None:
            del self, value
            _raise_input_error()
        digest: str | None = None
        try:
            digest = canonical_json_hash(validated.payload)
        except (TypeError, ValueError):
            pass
        if digest is None:
            del self, value, validated
            _raise_input_error()
        reservation = None
        try:
            reservation = await self._repository.reserve(validated, payload_digest=digest)
        except SQLAlchemyError:
            pass
        if reservation is None:
            del self, value, validated
            _raise_persistence_error()
        if len(reservation.records) != 1 or not _matches(
            reservation.records[0], validated, digest
        ):
            del self, value, validated, reservation
            _raise_idempotency_conflict()
        record = reservation.records[0]
        return OutboxAppendResult(
            event_id=record.event_id,
            disposition=(
                OutboxAppendDisposition.CREATED
                if reservation.created
                else OutboxAppendDisposition.REPLAYED
            ),
            payload_digest=record.payload_digest,
            occurred_at=record.occurred_at,
        )
