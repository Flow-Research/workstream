"""Derive accepted finalization progress from its exact durable delivery owner."""

from uuid import UUID

from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationProgress
from app.modules.artifacts.intake.acceptance import finalization_event
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.outbox.api import OutboxAppendPort, OutboxIdempotencyConflict


async def finalization_progress(row, events: OutboxAppendPort) -> SubmissionFinalizationProgress | None:
    if row.state not in {"finalization_pending", "finalized"}:
        return None
    try:
        delivery = await events.observe_delivery(UUID(row.finalization_event_id), finalization_event(row))
    except OutboxIdempotencyConflict as exc:
        raise IntakeCustodyConflict("submission_finalization_progress_unavailable") from exc
    finalized = row.state == "finalized"
    if not finalized and delivery.state in {"acknowledged", "cancelled"}:
        raise IntakeCustodyConflict("submission_finalization_progress_inconsistent")
    stalled = not finalized and delivery.state == "dead_letter"
    return SubmissionFinalizationProgress(
        operation_id=UUID(row.id), finalized=finalized, operationally_stalled=stalled,
        stalled_at=delivery.finalized_at if stalled else None,
        next_retry_at=delivery.next_attempt_at if not finalized else None,
        attempt_count=delivery.attempt_count,
    )
