"""Real accepted and exhausted source setup for finalization recovery proofs."""

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text

from app.adapters.auth import outbox_dispatch_authorization, submission_recovery_authorization
from app.adapters.checkers import selected_pre_submit_coordinator
from app.adapters.outbox import outbox_append, outbox_delivery, finalized_unknown_deliveries
from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.api.submission_recovery import SubmissionRecoveryCommand, SubmissionRecoverySource
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.artifacts.intake.recovery import SubmissionFinalizationRecovery
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from app.modules.tasks.intake_custody import IntakeTaskCustody
from tests.artifacts.intake_acceptance_support import completed_source
from tests.checkers.execution.support import provision_post_submit_service


@pytest.fixture
async def recovery_intake(admission_intake, tmp_path):
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        event_id = UUID(row.finalization_event_id)
        metadata = SubmissionIntakeMetadata.model_validate_json(json.dumps(row.command_metadata))
        intake_key = UUID(row.idempotency_key)
    async def lost(_envelope):
        raise RuntimeError("lost original finalizer")
    delivery = outbox_delivery(f.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([("SubmissionFinalizationRequested", 1, lost)],
            replay_safe=frozenset({("SubmissionFinalizationRequested", 1)})),
        options=DeliveryOptions(lease_seconds=5, handler_timeout_seconds=4, max_attempts=1))
    await delivery.deliver(event_id, f.project, "lost-finalizer")
    await asyncio.sleep(5.05)  # The later finalizer must use the live child's lease.
    key = new_record_id()
    context = f.actor.model_copy(update={"request_id": key, "correlation_id": key})
    command = SubmissionRecoveryCommand(operation_id=owner.operation_id, project_id=f.project,
        actor_profile_id=f.actor.actor_profile_id, request_id=key, reason="Restore unavailable finalizer")
    async def recover(value=command):
        async with f.factory.begin() as session:
            return await SubmissionFinalizationRecovery(session,
                tasks=IntakeTaskCustody(session, task_submission_context_port(session)),
                events=outbox_append(session), deliveries=finalized_unknown_deliveries(session),
                authorization=submission_recovery_authorization(session, context)).request(value)
    async with f.factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event.delivery_state == "dead_letter" and event.last_error_code == "INVOKE_OUTCOME_UNKNOWN"
        source = SubmissionRecoverySource(operation_id=owner.operation_id, project_id=f.project,
            task_id=f.task, original_event_id=event_id, original_claim_generation=event.claim_generation,
            original_payload_digest=event.payload_digest,
            acceptance_receipt_sha256=row.acceptance_receipt_sha256)
    return SimpleNamespace(f=f, owner=owner, event_id=event_id, metadata=metadata, intake_key=intake_key,
                           context=context, command=command, source=source, recover=recover)


async def insert_recovery_payload(session, payload, *, digest=None):
    """Raw SQL positive/negative control; deliberately bypass typed command admission."""
    source, command = payload["source"], payload["command"]
    event_id = new_record_id()
    await session.execute(text("""INSERT INTO outbox_events(event_id,event_type,event_version,
        aggregate_type,aggregate_id,project_id,correlation_id,causation_event_id,
        idempotency_key,payload,payload_digest)
        VALUES (:id,'SubmissionFinalizationRecoveryRequested',1,'outbox_delivery',:original,
        :project,:request,:original,:key,cast(:payload as jsonb),:digest)"""),
        {"id": event_id, "original": UUID(source["original_event_id"]),
         "project": UUID(source["project_id"]), "request": command["request_id"],
         "key": "submission-finalization-recovery:" + source["original_event_id"],
         "payload": json.dumps(payload), "digest": digest or canonical_json_hash(payload)})
    return event_id


async def forge_recovery_audit(session, reference_id, payload, overrides):
    """Prove an existing self-consistent allow row cannot substitute exact authority."""
    source, command, authority = payload["source"], payload["command"], payload["authority"]
    digest = canonical_json_hash({"resource_context": {
        "resource_type": "submission_operation", "resource_id": source["operation_id"],
        "scope_project_id": source["project_id"], "identity_link_id": authority["identity_link_id"],
        "command": command, "source": source,
    }})
    decision_id = new_record_id()
    patch = {"id": str(decision_id), "entity_id": str(decision_id), "after_facts": {"allowed": True, "resource_context_digest": digest},
             **overrides}
    await session.execute(text("""INSERT INTO audit_events
        SELECT (jsonb_populate_record(NULL::public.audit_events,
            to_jsonb(a) || cast(:patch as jsonb))).*
        FROM audit_events a WHERE id=:reference"""),
        {"patch": json.dumps(patch), "reference": reference_id})
    assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE id=:id"),
                                {"id": decision_id}) == 1
    authority.update(decision_id=str(decision_id), resource_digest=digest)
