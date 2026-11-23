"""Real dispatcher authority and immutable phase decision custody."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile

from app.adapters.auth import outbox_dispatch_authorization
from app.modules.authorization.api import (
    OutboxDispatchFacts,
    OutboxDispatchPhase,
    outbox_dispatch_resource_digest,
    PreparedAuthorizationInvalid,
)
from app.modules.outbox.api import DeliveryUnavailable, FinalizationCause
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.outbox.models import OutboxDeliveryAttempt
from app.modules.tasks.models import AuditEvent
from tests.outbox.conftest import Harness


def phase_facts(claim, phase, outcome=None):
    return OutboxDispatchFacts(**claim.model_dump(), phase=phase, outcome_digest=outcome)


async def test_real_dispatcher_records_exact_phase_decisions(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    receipt = await h.delivery.invoke(claim)
    async with h.factory() as session:
        attempt = await DeliveryRepository(session).attempt(claim)
        ids = [
            attempt.claim_decision_event_id,
            attempt.invoke_decision_event_id,
            attempt.finalize_decision_event_id,
        ]
        assert len(set(ids)) == 3 and all(ids)
        for phase, decision_id in zip(OutboxDispatchPhase, ids, strict=True):
            event = await session.get(AuditEvent, decision_id)
            expected = phase_facts(
                claim,
                phase,
                receipt.outcome_digest if phase is OutboxDispatchPhase.FINALIZE else None,
            )
            assert event.actor_id == str(h.actor_id)
            assert event.event_type == "SensitiveAuthorizationAllowed"
            assert event.action_id == event.permission_id == "outbox.dispatch"
            assert event.project_id == str(h.project)
            assert event.resource_type == "outbox_event" and event.resource_id == str(
                claim.event_id
            )
            assert event.after_facts == {
                "allowed": True,
                "resource_context_digest": outbox_dispatch_resource_digest(expected),
            }
            sql_digest = await session.scalar(
                text(
                    "select outbox_dispatch_authority_digest(a,:phase) from outbox_delivery_attempts a where event_id=:id"
                ),
                {"phase": phase.value, "id": claim.event_id},
            )
            assert sql_digest == outbox_dispatch_resource_digest(expected)
    assert await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE) == receipt
    async with h.factory() as session:
        attempt = await DeliveryRepository(session).attempt(claim)
        assert ids == [
            attempt.claim_decision_event_id,
            attempt.invoke_decision_event_id,
            attempt.finalize_decision_event_id,
        ]
        events = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch")
            )
        ).all()
        assert len(events) == 4
        replay = next(event for event in events if event.id not in ids)
        assert replay.after_facts == {
            "allowed": True,
            "resource_context_digest": outbox_dispatch_resource_digest(
                phase_facts(claim, OutboxDispatchPhase.FINALIZE, receipt.outcome_digest)
            ),
        }


async def test_missing_dispatcher_denies_without_claim(outbox_factory):
    factory, project = outbox_factory
    h = Harness(factory, project)
    event = await h.append()
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.claim(event.event_id, project, "missing-principal")
    async with factory() as session:
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []
        assert (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch")
            )
        ).all() == []


@pytest.mark.parametrize("phase", ["invoke", "replay"])
async def test_revocation_between_phases_denies_without_rewriting_custody(delivery_harness, phase):
    h = delivery_harness
    claim = await h.claim()
    if phase == "replay":
        await h.delivery.invoke(claim)
    async with h.factory() as session:
        before = (
            await session.execute(
                text("select to_jsonb(a) from outbox_delivery_attempts a where event_id=:id"),
                {"id": claim.event_id},
            )
        ).scalar_one()
        count = await session.scalar(
            text("select count(*) from audit_events where action_id='outbox.dispatch'")
        )
        await session.execute(
            text(
                "update actor_identity_links set status='revoked',revoked_by='test',"
                "revoked_at=clock_timestamp(),revoked_reason='test' where id=:id"
            ),
            {"id": str(h.link_id)},
        )
        await session.commit()
    with pytest.raises(DeliveryUnavailable):
        if phase == "invoke":
            await h.delivery.invoke(claim)
        else:
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        assert (
            await session.execute(
                text("select to_jsonb(a) from outbox_delivery_attempts a where event_id=:id"),
                {"id": claim.event_id},
            )
        ).scalar_one() == before
        assert (
            await session.scalar(
                text("select count(*) from audit_events where action_id='outbox.dispatch'")
            )
            == count
        )
    assert len(h.handled) == (1 if phase == "replay" else 0)


@pytest.mark.parametrize(
    "field",
    [
        "phase",
        "event_id",
        "project_id",
        "claim_generation",
        "claim_owner",
        "claimed_at",
        "claim_expires_at",
        "payload_digest",
        "outcome_digest",
    ],
)
async def test_prepared_dispatch_binds_all_facts(delivery_harness, field):
    h = delivery_harness
    # This test checks fact substitution, not lease expiry under CI load.
    h.options = h.options.model_copy(update={"lease_seconds": 60})
    h.delivery = h.build()
    claim = await h.claim()
    facts = phase_facts(claim, OutboxDispatchPhase.FINALIZE, "sha256:" + "a" * 64)
    value = getattr(facts, field)
    changed = (
        new_record_id()
        if isinstance(value, UUID)
        else value + timedelta(microseconds=1)
        if field in {"claimed_at", "claim_expires_at"}
        else value + 1
        if field == "claim_generation"
        else "different"
        if field == "claim_owner"
        else "sha256:" + "b" * 64
    )
    substitutions = {field: changed}
    if field == "phase":
        substitutions = {"phase": OutboxDispatchPhase.INVOKE, "outcome_digest": None}
    async with h.factory() as session, session.begin():
        async with outbox_dispatch_authorization(session).prepare_outbox_dispatch(
            facts=facts,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        ) as prepared:
            with pytest.raises(PreparedAuthorizationInvalid):
                await prepared.consume(replace(facts, **substitutions))
            valid = await prepared.consume(facts)
            assert valid.action_id == valid.permission_id == "outbox.dispatch"
            with pytest.raises(PreparedAuthorizationInvalid):
                await prepared.consume(facts)
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume(facts)


@pytest.mark.parametrize("status", ["suspended", "deactivated"])
async def test_dispatcher_lifecycle_denies_without_claim(delivery_harness, status):
    h = delivery_harness
    event = await h.append()
    async with h.factory() as session, session.begin():
        prefix, reason = (
            ("suspended", "suspension_reason")
            if status == "suspended"
            else ("deactivated", "deactivation_reason")
        )
        await session.execute(
            text(
                f"update actor_profiles set status=:status,{prefix}_by='test',"
                f"{prefix}_at=clock_timestamp(),{reason}='test' where id=:id"
            ),
            {"status": status, "id": str(h.actor_id)},
        )
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.claim(event.event_id, h.project, "worker")
    async with h.factory() as session:
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []
        assert (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch")
            )
        ).all() == []


async def test_prepared_dispatch_cannot_cross_root_transaction(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    facts = phase_facts(claim, OutboxDispatchPhase.INVOKE)
    async with h.factory() as session:
        await session.begin()
        async with outbox_dispatch_authorization(session).prepare_outbox_dispatch(
            facts=facts,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        ) as prepared:
            await session.commit()
            await session.begin()
            with pytest.raises(PreparedAuthorizationInvalid):
                await prepared.consume(facts)
        await session.rollback()
    assert await h.delivery._begin_invocation(claim)


async def test_distinct_events_use_one_real_authority_lock_order(delivery_harness):
    import asyncio

    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30})
    h.delivery = h.build()
    first, second = await h.append(), await h.append()
    receipts = await asyncio.wait_for(
        asyncio.gather(
            h.delivery.deliver(first.event_id, h.project, "worker-one"),
            h.delivery.deliver(second.event_id, h.project, "worker-two"),
        ),
        10,
    )
    assert all(receipts) and len(h.handled) == 2
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert {a.event_id for a in attempts} == {first.event_id, second.event_id}
        assert (
            len(
                {
                    identity
                    for a in attempts
                    for identity in (
                        a.claim_decision_event_id,
                        a.invoke_decision_event_id,
                        a.finalize_decision_event_id,
                    )
                }
            )
            == 6
        )


async def test_revocation_wins_while_dispatch_waits_for_real_authority_lock(delivery_harness):
    import asyncio

    h = delivery_harness
    claim = await h.claim()
    running = None
    try:
        async with h.factory() as revoker, revoker.begin():
            await revoker.execute(
                text("select id from actor_profiles where id=:id for update"),
                {"id": str(h.actor_id)},
            )
            blocker_pid = await revoker.scalar(text("select pg_backend_pid()"))
            running = asyncio.create_task(h.delivery._begin_invocation(claim))
            async with h.factory() as observer:
                for _ in range(100):
                    waiting = await observer.scalar(
                        text(
                            "select exists(select 1 from pg_stat_activity where :pid=any(pg_blocking_pids(pid)))"
                        ),
                        {"pid": blocker_pid},
                    )
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
                assert waiting, "dispatch never reached the real blocked authority lock"
            await revoker.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by='test',"
                    "revoked_at=clock_timestamp(),revoked_reason='test' where id=:id"
                ),
                {"id": str(h.link_id)},
            )
        with pytest.raises(DeliveryUnavailable):
            await asyncio.wait_for(running, 5)
        async with h.factory() as session:
            attempt = await DeliveryRepository(session).attempt(claim)
            assert attempt.stage == "claimed" and attempt.invoke_decision_event_id is None
            assert (
                len(
                    (
                        await session.scalars(
                            select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch")
                        )
                    ).all()
                )
                == 1
            )
    finally:
        if running is not None:
            if not running.done():
                running.cancel()
            await asyncio.gather(running, return_exceptions=True)


async def test_prepared_dispatch_cannot_move_to_another_session(delivery_harness):
    from app.modules.actors.api import ServiceIdentity
    from app.modules.authorization.catalogue import ActionId
    from app.modules.authorization.domain.outbox_dispatch import outbox_dispatch_resource
    from app.modules.authorization.prepared import fixed_service_prepared_authorization
    from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
    h = delivery_harness
    claim = await h.claim()
    facts = phase_facts(claim, OutboxDispatchPhase.INVOKE)
    async with h.factory() as first, first.begin(), h.factory() as second, second.begin():
        async with outbox_dispatch_authorization(first).prepare_outbox_dispatch(
            facts=facts, request_id=new_record_id(), correlation_id=new_record_id(),
        ) as prepared:
            async with fixed_service_prepared_authorization(second,
                service_identity=ServiceIdentity.OUTBOX_DISPATCHER,
                request_id=new_record_id(), correlation_id=new_record_id(),
            ) as other:
                with pytest.raises(PreparedAuthorizationHandleInvalid):
                    await other.service.consume(prepared._handle, ActionId.OUTBOX_DISPATCH,
                        prepared._input, outbox_dispatch_resource(facts))
            assert (await prepared.consume(facts)).action_id == "outbox.dispatch"


async def test_fixed_service_identity_cannot_be_relabelled(outbox_factory):
    factory, project = outbox_factory
    h = Harness(factory, project)
    foreign_id = str(new_record_id())

    async def provision(identity, actor_id):
        async with factory() as session, session.begin():
            session.add(ActorProfile(
                id=actor_id, actor_kind="service", status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=identity.value, created_by=actor_id,
            ))
            await session.flush()
            session.add(ActorIdentityLink(
                id=str(new_record_id()), actor_profile_id=actor_id,
                issuer="configured-provider", subject=str(new_record_id()),
                subject_kind="service", status="active", linked_by=actor_id,
            ))

    await provision(ServiceIdentity.PROJECT_SETUP, foreign_id)
    event = await h.append()
    with pytest.raises(DBAPIError, match="actor profile identity is immutable"):
        async with factory() as session, session.begin():
            await session.execute(text(
                "update actor_profiles set service_identity=:identity where id=:id"
            ), {"identity": ServiceIdentity.OUTBOX_DISPATCHER.value, "id": foreign_id})

    async with factory() as session:
        profile = await session.get(ActorProfile, foreign_id)
        assert profile.service_identity == ServiceIdentity.PROJECT_SETUP.value
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []
        assert (await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "outbox.dispatch"
        ))).all() == []
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.claim(event.event_id, project, "foreign-principal")

    await provision(ServiceIdentity.OUTBOX_DISPATCHER, str(new_record_id()))
    claim = await h.delivery.claim(event.event_id, project, "provisioned-dispatcher")
    assert claim is not None
    assert claim.event_id == event.event_id
