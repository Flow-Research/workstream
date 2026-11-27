"""One audited follow-up for the original uncertain accepted-finalization event."""

from uuid import UUID

from sqlalchemy import text

from app.modules.artifacts.api.submission_recovery import (
    FINALIZATION_RECOVERY_EVENT, FINALIZATION_RECOVERY_SOURCES,
    SubmissionRecoveryCommand, SubmissionRecoveryPayload, SubmissionRecoveryResult,
    SubmissionRecoverySource, SubmissionRecoveryUnavailable,
)
from app.modules.artifacts.intake.acceptance import finalization_event
from app.modules.artifacts.intake.repository import SubmissionIntakeRepository
from app.modules.outbox.api import OutboxAppendInput


def recovery_event(payload: SubmissionRecoveryPayload) -> OutboxAppendInput:
    source, command = payload.source, payload.command
    return OutboxAppendInput(
        event_type=FINALIZATION_RECOVERY_EVENT, event_version=1,
        aggregate_type="outbox_delivery", aggregate_id=source.original_event_id,
        project_id=command.project_id, correlation_id=str(command.request_id),
        causation_event_id=source.original_event_id,
        idempotency_key="submission-finalization-recovery:" + str(source.original_event_id),
        payload=payload.model_dump(mode="json"),
    )


class SubmissionFinalizationRecovery:
    """Participate in a caller root; TASK lock precedes AUTH and OUTBOX locks."""

    def __init__(self, session, *, tasks, events, deliveries, authorization):
        self._session = session
        self._repository = SubmissionIntakeRepository(session, tasks)
        self._events, self._deliveries, self._authorization = events, deliveries, authorization

    async def request(self, command: SubmissionRecoveryCommand) -> SubmissionRecoveryResult:
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise SubmissionRecoveryUnavailable("submission_recovery_transaction_required")
        command = SubmissionRecoveryCommand.model_validate(command)
        row = await self._repository._lock(command.operation_id)
        if row.project_id != str(command.project_id) or row.state not in {"finalization_pending", "finalized"}:
            raise SubmissionRecoveryUnavailable("submission_recovery_unavailable")
        await self._session.execute(text(
            "SELECT public.require_submission_acceptance(o) "
            "FROM public.submission_intake_operations o WHERE id=:id"
        ), {"id": row.id})
        original_id = UUID(row.finalization_event_id)
        await self._events.require_existing(original_id, finalization_event(row))
        original = await self._read(command.project_id, original_id, lock=False)
        if original is None:
            raise SubmissionRecoveryUnavailable("submission_recovery_unavailable")
        source = SubmissionRecoverySource(
            operation_id=command.operation_id, project_id=command.project_id,
            task_id=UUID(row.task_id), original_event_id=original_id,
            original_claim_generation=original.envelope.claim.claim_generation,
            original_payload_digest=original.envelope.claim.payload_digest,
            acceptance_receipt_sha256=row.acceptance_receipt_sha256,
        )
        # Current authority is mandatory even for a previously accepted recovery key.
        authority = await self._authorization.authorize(command, source)
        locked = await self._read(command.project_id, original_id, lock=True)
        if locked is None or locked.envelope != original.envelope:
            raise SubmissionRecoveryUnavailable("submission_recovery_source_changed")
        if locked.child is not None:
            payload = SubmissionRecoveryPayload.model_validate_json(locked.child.payload_json)
            if payload.command != command or payload.source != source:
                raise SubmissionRecoveryUnavailable("submission_recovery_conflict")
            await self._authorization.validate_cause(payload)
            return SubmissionRecoveryResult(operation_id=command.operation_id,
                recovery_event_id=locked.child.event_id, state=locked.child.state)
        if row.state != "finalization_pending":
            raise SubmissionRecoveryUnavailable("submission_recovery_already_finalized")
        payload = SubmissionRecoveryPayload(command=command, source=source, authority=authority)
        appended = await self._events.append(recovery_event(payload))
        return SubmissionRecoveryResult(operation_id=command.operation_id,
            recovery_event_id=appended.event_id, state="pending")

    async def _read(self, project_id, event_id, *, lock):
        return await self._deliveries.read_finalized_unknown(
            project_id=project_id, event_id=event_id,
            event_types=FINALIZATION_RECOVERY_SOURCES,
            child_event_type=FINALIZATION_RECOVERY_EVENT, lock=lock,
        )
