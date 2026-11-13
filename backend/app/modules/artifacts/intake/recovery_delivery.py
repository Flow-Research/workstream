"""Replay T5 under a live recovery child while preserving the accepted event."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.artifacts.api.submission_recovery import (
    FINALIZATION_RECOVERY_EVENT, FINALIZATION_RECOVERY_SOURCES,
    SubmissionRecoveryPayload, SubmissionRecoveryUnavailable,
)
from app.modules.artifacts.intake.finalization_delivery import require_finalization_event
from app.modules.outbox.api import HandlerOutcome, OutboxEventEnvelope


@dataclass(frozen=True)
class FinalizationRecoveryInvocation:
    envelope: OutboxEventEnvelope
    child: OutboxEventEnvelope
    payload: SubmissionRecoveryPayload
    deliveries: object
    authorization: object

    @property
    def lease_expires_at(self):
        return self.child.claim.claim_expires_at

    async def fence(self, session, row):
        require_finalization_event(row, self.envelope)
        source = self.payload.source
        if (source.operation_id != UUID(row.id) or source.project_id != UUID(row.project_id)
                or source.task_id != UUID(row.task_id)
                or source.acceptance_receipt_sha256 != row.acceptance_receipt_sha256):
            raise SubmissionRecoveryUnavailable("submission_recovery_source_changed")
        await self.authorization(session).validate_cause(self.payload)
        observed = await self.deliveries(session).fence_reconciliation(
            original=self.envelope, child=self.child,
            event_types=FINALIZATION_RECOVERY_SOURCES,
            child_event_type=FINALIZATION_RECOVERY_EVENT,
        )
        if observed is None or observed.claim != self.child.claim:
            raise SubmissionRecoveryUnavailable("submission_recovery_stale")


class SubmissionFinalizationRecoveryHandler:
    def __init__(self, *, sessions, deliveries, authorization, finalizer):
        self._sessions, self._deliveries = sessions, deliveries
        self._authorization, self._finalizer = authorization, finalizer

    async def __call__(self, child):
        try:
            child = OutboxEventEnvelope.model_validate(child.model_dump())
            payload = SubmissionRecoveryPayload.model_validate_json(child.payload_json)
        except (AttributeError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        source, command = payload.source, payload.command
        if (child.event_type != FINALIZATION_RECOVERY_EVENT or child.event_version != 1
                or child.aggregate_type != "outbox_delivery"
                or child.aggregate_id != source.original_event_id
                or child.causation_event_id != source.original_event_id
                or child.claim.project_id != source.project_id
                or child.correlation_id != str(command.request_id)
                or child.idempotency_key != "submission-finalization-recovery:" + str(source.original_event_id)):
            return HandlerOutcome.REJECT
        async with self._sessions() as session:
            retained = await self._deliveries(session).read_finalized_unknown(
                project_id=source.project_id, event_id=source.original_event_id,
                event_types=FINALIZATION_RECOVERY_SOURCES,
                child_event_type=FINALIZATION_RECOVERY_EVENT, lock=False,
            )
            if (retained is None or retained.child is None
                    or retained.child.event_id != child.claim.event_id
                    or retained.envelope.aggregate_id != source.operation_id
                    or retained.envelope.claim.claim_generation != source.original_claim_generation
                    or retained.envelope.claim.payload_digest != source.original_payload_digest):
                return HandlerOutcome.REJECT
            await self._authorization(session).validate_cause(payload)
        invocation = FinalizationRecoveryInvocation(retained.envelope, child, payload,
            self._deliveries, self._authorization)
        await self._finalizer(invocation).run(source.operation_id)
        return HandlerOutcome.ACKNOWLEDGE
