"""Independent SQL rejection with valid surrounding custody and real phase decisions."""

from dataclasses import replace
from datetime import datetime, timezone, timedelta
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.authorization.api import OutboxDispatchFacts, OutboxDispatchPhase
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.tasks.models import AuditEvent
from tests.outbox.conftest import phase_decision


async def write_invocation(session, claim, decision):
    await session.execute(
        text(
            "update outbox_delivery_attempts set stage='invoked',invoked_at=clock_timestamp(),"
            "invoke_decision_event_id=:decision where event_id=:event"
        ),
        {"event": claim.event_id, "decision": decision},
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "phase",
        "event_id",
        "project_id",
        "claim_generation",
        "claim_owner",
        "claimed_at",
        "claim_expires_at",
        "payload_digest",
    ],
)
async def test_phase_decision_sql_substitutions(delivery_harness, fault):
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30})
    h.delivery = h.build()
    claim = await h.claim()
    facts = OutboxDispatchFacts(**claim.model_dump(), phase=OutboxDispatchPhase.INVOKE)
    changes = {
        "phase": OutboxDispatchPhase.CLAIM,
        "event_id": new_record_id(),
        "project_id": new_record_id(),
        "claim_generation": 2,
        "claim_owner": "different",
        "claimed_at": claim.claimed_at + timedelta(microseconds=1),
        "claim_expires_at": claim.claim_expires_at + timedelta(microseconds=1),
        "payload_digest": "sha256:" + "0" * 64,
    }
    # Different project facts require a real project for valid audit foreign keys.
    if fault == "project_id":
        from project_create_fixtures import seed_historical_project

        async with h.factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=str(changes[fault]),
                name="Other",
                slug="other-" + str(changes[fault]),
                status="active",
            )
    expected = (
        "phase_decisions" if fault == "missing" else "outbox phase authority evidence mismatch"
    )
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match=expected):
            async with session.begin():
                decision = (
                    None
                    if fault == "missing"
                    else await phase_decision(session, replace(facts, **{fault: changes[fault]}))
                )
                await write_invocation(session, claim, decision)
        attempt = await DeliveryRepository(session).attempt(claim)
        assert attempt.stage == "claimed" and attempt.invoke_decision_event_id is None
        decisions = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch")
            )
        ).all()
        assert [decision.id for decision in decisions] == [attempt.claim_decision_event_id]
    assert await h.delivery._begin_invocation(claim)


async def test_new_phase_reference_requires_current_authority(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    facts = OutboxDispatchFacts(**claim.model_dump(), phase=OutboxDispatchPhase.INVOKE)
    async with h.factory() as session, session.begin():
        decision = await phase_decision(session, facts)
    async with h.factory() as session, session.begin():
        await session.execute(
            text(
                "update actor_profiles set status='suspended',suspended_by='test',suspended_at=clock_timestamp(),suspension_reason='test' where id=:id"
            ),
            {"id": str(h.actor_id)},
        )
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match="outbox current dispatcher authority missing"):
            async with session.begin():
                await write_invocation(session, claim, decision)
        attempt = await DeliveryRepository(session).attempt(claim)
        assert attempt.stage == "claimed" and attempt.invoke_decision_event_id is None


@pytest.mark.parametrize("phase", [OutboxDispatchPhase.CLAIM, OutboxDispatchPhase.INVOKE, OutboxDispatchPhase.FINALIZE])
@pytest.mark.parametrize("microseconds", [0, 123400])
async def test_sql_phase_digest_matches_exact_public_timestamp_format(
    delivery_harness, phase, microseconds
):
    import json
    from app.modules.authorization.api import outbox_dispatch_resource_digest

    h = delivery_harness
    claim = await h.claim()
    claimed = claim.claimed_at.replace(microsecond=microseconds)
    facts = OutboxDispatchFacts(
        **{
            **claim.model_dump(),
            "claimed_at": claimed,
            "claim_expires_at": claimed + timedelta(seconds=3),
        },
        phase=phase,
        outcome_digest="sha256:" + "a" * 64 if phase is OutboxDispatchPhase.FINALIZE else None,
    )
    # Composite construction is read-only: no changed persisted custody or fake authority.
    row = {
        **claim.model_dump(mode="json"),
        "claimed_at": facts.claimed_at.isoformat(),
        "claim_expires_at": facts.claim_expires_at.isoformat(),
        "outcome_digest": facts.outcome_digest,
    }
    async with h.factory() as session:
        digest = await session.scalar(
            text(
                "select outbox_dispatch_authority_digest(jsonb_populate_record(null::outbox_delivery_attempts,cast(:row as jsonb)),:phase)"
            ),
            {"row": json.dumps(row), "phase": phase.value},
        )
        assert digest == outbox_dispatch_resource_digest(facts)


@pytest.mark.parametrize("phase", [OutboxDispatchPhase.CLAIM, OutboxDispatchPhase.INVOKE, OutboxDispatchPhase.FINALIZE])
async def test_missing_phase_decision_rolls_back_owner_write_and_audit(delivery_harness, phase):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
    from app.modules.outbox.api import FinalizationCause

    h = delivery_harness
    pending = await h.append()
    claim = None
    if phase is not OutboxDispatchPhase.CLAIM:
        claim = await h.delivery.claim(pending.event_id, h.project, "worker")
    if phase is OutboxDispatchPhase.FINALIZE:
        await h.delivery._begin_invocation(claim)
    column = phase.value + "_decision_event_id"
    stage = {
        OutboxDispatchPhase.CLAIM: "claimed",
        OutboxDispatchPhase.INVOKE: "invoked",
        OutboxDispatchPhase.FINALIZE: "completed",
    }[phase]
    faults = []

    def omit(session, context, instances):
        for row in list(session.new) + list(session.dirty):
            if isinstance(row, OutboxDeliveryAttempt) and row.stage == stage:
                assert getattr(row, column)
                faults.append(True)
                setattr(row, column, None)

    event.listen(Session, "before_flush", omit)
    try:
        with pytest.raises(DBAPIError, match="claim_decision_event_id|phase_decisions"):
            if phase is OutboxDispatchPhase.CLAIM:
                await h.delivery.claim(pending.event_id, h.project, "worker")
            elif phase is OutboxDispatchPhase.INVOKE:
                await h.delivery._begin_invocation(claim)
            else:
                await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    finally:
        event.remove(Session, "before_flush", omit)
    assert faults == [True]
    async with h.factory() as session:
        audits = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch")
            )
        ).all()
        assert len(audits) == (
            [OutboxDispatchPhase.CLAIM, OutboxDispatchPhase.INVOKE, OutboxDispatchPhase.FINALIZE]
            .index(phase)
        )
        assert (await session.get(OutboxEvent, pending.event_id)).delivery_state == (
            "pending" if claim is None else "claimed"
        )
    if phase is OutboxDispatchPhase.CLAIM:
        assert await h.delivery.claim(pending.event_id, h.project, "worker")
    elif phase is OutboxDispatchPhase.INVOKE:
        assert await h.delivery._begin_invocation(claim)
    else:
        assert await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)


async def test_finalization_decision_binds_actual_outcome(delivery_harness):
    from app.modules.outbox.api import FinalizationCause
    from app.modules.outbox.delivery import _outcome
    from app.modules.outbox.delivery_repository import database_time
    from tests.outbox.test_custody_postgresql import _write_paired_outcome

    h = delivery_harness
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match="outbox phase authority evidence mismatch"):
            async with session.begin():
                attempt = await DeliveryRepository(session).attempt(claim)
                outcome = _outcome(
                    claim,
                    attempt.invoked_at,
                    FinalizationCause.ACKNOWLEDGE,
                    await database_time(session),
                    h.options,
                )
                decision = await phase_decision(
                    session,
                    OutboxDispatchFacts(
                        **claim.model_dump(),
                        phase=OutboxDispatchPhase.FINALIZE,
                        outcome_digest="sha256:" + "0" * 64,
                    ),
                )
                await _write_paired_outcome(session, claim, outcome, decision=decision)
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
    assert await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)


@pytest.mark.parametrize("fault", ["human", "foreign_service", "denied"])
async def test_sql_rejects_forged_phase_principal_or_denial(delivery_harness, fault):
    import json
    from app.modules.actors.models import ActorProfile, ActorIdentityLink
    from app.modules.actors.api import ServiceIdentity

    h = delivery_harness
    claim = await h.claim()
    facts = OutboxDispatchFacts(**claim.model_dump(), phase=OutboxDispatchPhase.INVOKE)
    async with h.factory() as session, session.begin():
        original = await phase_decision(session, facts)
        changes = {"id": str(new_record_id())}
        changes["entity_id"] = changes["id"]
        if fault == "denied":
            audit = await session.get(AuditEvent, original)
            changes.update(
                event_type="SensitiveAuthorizationDenied",
                denial_code="permission_not_granted",
                after_facts={**audit.after_facts, "allowed": False},
            )
        else:
            foreign = str(new_record_id())
            session.add(
                ActorProfile(
                    id=foreign,
                    actor_kind="human" if fault == "human" else "service",
                    status="active",
                    provisioning_method="automatic_first_access"
                    if fault == "human"
                    else "manual_service_provisioning",
                    service_identity=None
                    if fault == "human"
                    else ServiceIdentity.PROJECT_SETUP.value,
                    created_by="test",
                )
            )
            await session.flush()
            session.add(
                ActorIdentityLink(
                    id=str(new_record_id()),
                    actor_profile_id=foreign,
                    issuer="flow.test" if fault == "human" else "workstream.internal",
                    subject=foreign if fault == "human" else ServiceIdentity.PROJECT_SETUP.value,
                    subject_kind="human" if fault == "human" else "service",
                    status="active",
                    linked_by="test",
                    last_verified_at=datetime.now(timezone.utc) if fault == "human" else None,
                )
            )
            await session.flush()
            changes["actor_id"] = foreign
        # Adversarial SQL control, never evidence of an authentic allowed decision.
        await session.execute(
            text(
                "insert into audit_events select (jsonb_populate_record(null::audit_events,"
                "to_jsonb(a)||cast(:changes as jsonb))).* from audit_events a where a.id=:id"
            ),
            {"changes": json.dumps(changes), "id": original},
        )
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match="outbox phase authority (identity|evidence) mismatch"):
            async with session.begin():
                await write_invocation(session, claim, changes["id"])
        assert (await DeliveryRepository(session).attempt(claim)).stage == "claimed"
    assert await h.delivery._begin_invocation(claim)


async def test_phase_reference_cannot_be_replaced_during_valid_transition(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match="outbox phase authority is immutable"):
            async with session.begin():
                replacement = await phase_decision(session, OutboxDispatchFacts(
                    **claim.model_dump(), phase=OutboxDispatchPhase.CLAIM))
                invocation = await phase_decision(session, OutboxDispatchFacts(
                    **claim.model_dump(), phase=OutboxDispatchPhase.INVOKE))
                await session.execute(text(
                    "update outbox_delivery_attempts set stage='invoked',invoked_at=clock_timestamp(),"
                    "claim_decision_event_id=:claim,invoke_decision_event_id=:invoke where event_id=:event"
                ), {"event": claim.event_id, "claim": replacement, "invoke": invocation})
        attempt = await DeliveryRepository(session).attempt(claim)
        assert attempt.stage == "claimed" and attempt.claim_decision_event_id != replacement
    assert await h.delivery._begin_invocation(claim)
