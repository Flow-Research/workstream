"""Exact accepted-event custody for the existing finalization operation."""

from dataclasses import dataclass
from collections.abc import Callable
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.intake.acceptance import finalization_event
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.outbox.api import HandlerOutcome, InvocationFencePort, OutboxEventEnvelope


def require_finalization_event(row, envelope):
    expected = finalization_event(row)
    if (
        str(envelope.claim.event_id) != row.finalization_event_id
        or str(envelope.claim.project_id) != row.project_id
        or any(getattr(envelope, key) != getattr(expected, key) for key in (
            "event_type", "event_version", "aggregate_type", "aggregate_id",
            "correlation_id", "causation_event_id", "idempotency_key",
        ))
        or envelope.payload_json != json.dumps(expected.payload, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        or envelope.claim.payload_digest != canonical_json_hash(expected.payload)
    ):
        raise IntakeCustodyConflict("finalization_delivery_mismatch")

@dataclass(frozen=True)
class FinalizationInvocation:
    """An invocation is evidence to recheck, never feature authorization."""

    envelope: OutboxEventEnvelope
    fence_factory: Callable[[AsyncSession], InvocationFencePort]

    @property
    def lease_expires_at(self):
        return self.envelope.claim.claim_expires_at

    async def fence(self, session, row):
        require_finalization_event(row, self.envelope)
        envelope = self.envelope
        observed = await self.fence_factory(session).fence_invocation(envelope)
        if observed is None or observed.claim != envelope.claim:
            raise IntakeCustodyConflict("finalization_delivery_stale")


class SubmissionFinalizationHandler:
    """Acknowledge only after T5 or its exact committed replay succeeds."""

    def __init__(self, *, observer, finalizer):
        self._observer, self._finalizer = observer, finalizer

    async def __call__(self, envelope):
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope.model_dump())
        except (AttributeError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        if envelope.event_type != "SubmissionFinalizationRequested" or envelope.event_version != 1:
            return HandlerOutcome.REJECT
        observed = await self._observer.observe_invocation(envelope)
        if observed is None or observed.claim != envelope.claim:
            return HandlerOutcome.REJECT
        # Exceptions remain uncertain to OUTBOX; replay uses the same accepted
        # evidence and observes a committed T5 before any provider access.
        await self._finalizer(envelope).run(envelope.aggregate_id)
        return HandlerOutcome.ACKNOWLEDGE
