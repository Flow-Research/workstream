"""Derive accepted finalization progress from its exact durable delivery owner."""

from uuid import UUID

from app.core.hashing import canonical_json_hash

from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationProgress
from app.modules.artifacts.intake.acceptance import finalization_event
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.artifacts.intake.recovery import recovery_event
from app.modules.artifacts.api.submission_recovery import (
    FINALIZATION_RECOVERY_EVENT, FINALIZATION_RECOVERY_SOURCES, SubmissionRecoveryPayload,
)
from app.modules.outbox.api import OutboxAppendPort, OutboxIdempotencyConflict, DeliveryUnavailable
from app.modules.checkers.api.delivery_reconciliation import (
    POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS,
    PostSubmitDeliveryChildPayload, post_submit_reconciliation_event,
)


async def finalization_progress(row, events: OutboxAppendPort, deliveries) -> SubmissionFinalizationProgress | None:
    if row.state not in {"finalization_pending", "finalized"}:
        return None
    try:
        delivery = await events.observe_delivery(UUID(row.finalization_event_id), finalization_event(row))
    except OutboxIdempotencyConflict as exc:
        raise IntakeCustodyConflict("submission_finalization_progress_unavailable") from exc
    finalized = row.state == "finalized"
    attempt_count = delivery.attempt_count
    try:
        if delivery.state == "dead_letter" and delivery.error_code == "INVOKE_OUTCOME_UNKNOWN":
            retained = await deliveries.read_finalized_unknown(
                project_id=UUID(row.project_id), event_id=UUID(row.finalization_event_id),
                event_types=FINALIZATION_RECOVERY_SOURCES,
                child_event_type=FINALIZATION_RECOVERY_EVENT, lock=False,
            )
            if retained is not None and retained.child is not None:
                payload = SubmissionRecoveryPayload.model_validate_json(retained.child.payload_json)
                source = payload.source
                if (source.operation_id != UUID(row.id) or source.project_id != UUID(row.project_id)
                        or source.task_id != UUID(row.task_id)
                        or source.original_event_id != UUID(row.finalization_event_id)
                        or source.original_claim_generation != retained.envelope.claim.claim_generation
                        or source.original_payload_digest != retained.envelope.claim.payload_digest
                        or source.acceptance_receipt_sha256 != row.acceptance_receipt_sha256):
                    raise IntakeCustodyConflict("submission_finalization_progress_inconsistent")
                delivery = await events.observe_delivery(retained.child.event_id, recovery_event(payload))
                attempt_count += delivery.attempt_count
    except (OutboxIdempotencyConflict, DeliveryUnavailable, ValueError) as exc:
        raise IntakeCustodyConflict("submission_finalization_progress_unavailable") from exc
    if not finalized and delivery.state in {"acknowledged", "cancelled"}:
        raise IntakeCustodyConflict("submission_finalization_progress_inconsistent")
    stalled = not finalized and delivery.state == "dead_letter"
    return SubmissionFinalizationProgress(
        operation_id=UUID(row.id), finalized=finalized, operationally_stalled=stalled,
        stalled_at=delivery.finalized_at if stalled else None,
        next_retry_at=delivery.next_attempt_at if not finalized else None,
        attempt_count=attempt_count, stalled_reason=delivery.error_code if stalled else None,
    )


async def evaluation_delivery_progress(event_id, event, evaluation, events, deliveries):
    """Observe one exact current evaluation delivery, including its recovery child."""
    unavailable = "submission_evaluation_progress_unavailable"
    try:
        observation = await events.observe_delivery(event_id, event)
        if observation.state != "dead_letter" or observation.error_code != "INVOKE_OUTCOME_UNKNOWN":
            return observation
        retained = await deliveries.read_finalized_unknown(
            project_id=event.project_id, event_id=event_id,
            event_types=POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS,
            child_event_type=POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, lock=False,
        )
        if retained is None:
            raise IntakeCustodyConflict(unavailable)
        if retained.child is None:
            return observation
        payload = PostSubmitDeliveryChildPayload.model_validate_json(retained.child.payload_json)
        claim = retained.envelope.claim
        request, reservation = evaluation.current.request, evaluation.current.reservation
        if (payload.original_event_id != event_id or claim.event_id != event_id
                or claim.project_id != event.project_id
                or payload.original_claim_generation != claim.claim_generation
                or payload.original_payload_digest != claim.payload_digest
                or claim.payload_digest != canonical_json_hash(event.payload)
                or payload.original_event_type != event.event_type
                or payload.original_event_version != event.event_version
                or payload.evaluation_request_id != request.evaluation_request_id
                or payload.checker_run_id != reservation.attempt_id
                or payload.evaluation_generation != reservation.evaluation_generation):
            raise IntakeCustodyConflict(unavailable)
        return await events.observe_delivery(
            retained.child.event_id, post_submit_reconciliation_event(event.project_id, payload),
        )
    except (OutboxIdempotencyConflict, DeliveryUnavailable, ValueError) as exc:
        raise IntakeCustodyConflict(unavailable) from exc
