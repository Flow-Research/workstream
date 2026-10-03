"""Real PostgreSQL races using canonical fixed-service phase authorization."""

import asyncio
from dataclasses import fields, replace
from datetime import timedelta
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import event as sqlalchemy_event, select, text

from app.adapters.auth import outbox_dispatch_authorization
from app.modules.authorization.api.outbox_dispatch import OutboxDispatchFacts, OutboxDispatchPhase
from app.modules.outbox.api import DeliveryUnavailable, FinalizationCause, HandlerOutcome
from app.modules.outbox.api import OutboxEventEnvelope
from app.modules.outbox import delivery as delivery_module
from app.modules.outbox.delivery_repository import DeliveryRepository, database_time
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.outbox.registry import HandlerRegistry


async def test_claim_race_commits_one_generation(delivery_harness):
    h = delivery_harness
    event = await h.append()
    entered = 0
    ready = asyncio.Event()

    async def barrier(facts):
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 5)

    h.prepare_hook = barrier
    outcomes = await asyncio.gather(
        *(h.delivery.claim(event.event_id, h.project, owner) for owner in ("one", "two"))
    )
    assert sum(result is not None for result in outcomes) == 1
    assert len(h.consumed) == 1
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].claim_generation == 1


async def test_claim_lease_expiring_behind_lock_consumes_no_authority(delivery_harness):
    h = delivery_harness
    event = await h.append()
    proposed = asyncio.Event()

    async def prepared(facts):
        proposed.set()

    h.prepare_hook = prepared
    async with h.factory() as blocker, blocker.begin():
        await DeliveryRepository(blocker).event(event.event_id, h.project, lock=True)
        task = asyncio.create_task(h.delivery.claim(event.event_id, h.project, "waiting"))
        await asyncio.wait_for(proposed.wait(), 3)
        await blocker.execute(text("select pg_sleep(3.1)"))
    assert await asyncio.wait_for(task, 5) is None
    assert h.consumed == []
    async with h.factory() as session:
        assert (await session.get(OutboxEvent, event.event_id)).delivery_state == "pending"
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []


async def test_claim_validator_requires_committed_invocation(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    envelope = await h.envelope(claim)
    assert await h.delivery.observe_invocation(envelope) is None
    async with h.factory() as writer, writer.begin():
        facts = OutboxDispatchFacts(**claim.model_dump(), phase=OutboxDispatchPhase.INVOKE)
        async with outbox_dispatch_authorization(writer).prepare_outbox_dispatch(
            facts=facts, request_id=new_record_id(), correlation_id=new_record_id(),
        ) as prepared:
            attempt = await DeliveryRepository(writer).attempt(claim, lock=True)
            decision = await prepared.consume(facts)
            invoked_at = await database_time(writer)
            attempt.invoke_decision_event_id = str(decision.decision_id)
            attempt.stage, attempt.invoked_at = "invoked", invoked_at
            await writer.flush()
            assert await h.delivery.observe_invocation(envelope) is None
    observed = await h.delivery.observe_invocation(envelope)
    assert (
        observed.claim == claim
        and claim.claimed_at <= observed.observed_at < claim.claim_expires_at
    )
    for changes in (
        {"project_id": new_record_id()},
        {"event_id": new_record_id()},
        {"payload_digest": "sha256:" + "0" * 64},
        {"claim_owner": "different"},
        {"claim_generation": 2},
        {"claimed_at": claim.claimed_at + timedelta(microseconds=1)},
        {"claim_expires_at": claim.claim_expires_at + timedelta(seconds=1)},
    ):
        assert await h.delivery.observe_invocation(envelope.model_copy(update={"claim": claim.model_copy(update=changes)})) is None
    for changes in (
        {"event_type": "DifferentEvent"}, {"event_version": 2},
        {"aggregate_type": "other"}, {"aggregate_id": new_record_id()},
        {"correlation_id": "different"}, {"causation_event_id": new_record_id()},
        {"idempotency_key": "different"},
        {"occurred_at": envelope.occurred_at + timedelta(microseconds=1)},
        {"payload_json": "{}"}, {"payload_json": "invalid"},
        {"payload_json": "[1]"}, {"payload_json": " " + envelope.payload_json},
    ):
        assert await h.delivery.observe_invocation(envelope.model_copy(update=changes)) is None
    assert await h.delivery.observe_invocation(object()) is None
    assert await h.delivery.observe_invocation(envelope) is not None
    await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    assert await h.delivery.observe_invocation(envelope) is None


@pytest.mark.parametrize("phase", list(OutboxDispatchPhase))
@pytest.mark.parametrize("fault", ["phase", "facts"])
async def test_each_phase_denies_mismatch_and_reused_authority(delivery_harness, phase, fault):
    h = delivery_harness
    event = await h.append()
    claim = None
    if phase is not OutboxDispatchPhase.CLAIM:
        claim = await h.delivery.claim(event.event_id, h.project, "worker")
    if phase is OutboxDispatchPhase.FINALIZE:
        assert await h.delivery._begin_invocation(claim)
    consumed = len(h.consumed)
    if fault == "facts":
        h.substitute = lambda facts: replace(facts, claim_owner="substituted")
    else:
        h.substitute = lambda facts: replace(
            facts,
            phase=OutboxDispatchPhase.INVOKE
            if phase is OutboxDispatchPhase.CLAIM
            else OutboxDispatchPhase.CLAIM,
            outcome_digest=None,
        )
    with pytest.raises(DeliveryUnavailable):
        if phase is OutboxDispatchPhase.CLAIM:
            await h.delivery.claim(event.event_id, h.project, "worker")
        elif phase is OutboxDispatchPhase.INVOKE:
            await h.delivery._begin_invocation(claim)
        else:
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    if fault in ("phase", "facts"):
        assert len(h.consumed) == consumed
    async with h.factory() as session:
        row = await session.get(OutboxEvent, event.event_id)
        assert row.delivery_state == (
            "pending" if phase is OutboxDispatchPhase.CLAIM else "claimed"
        )
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == (0 if phase is OutboxDispatchPhase.CLAIM else 1)
        if attempts:
            assert attempts[0].stage == (
                "claimed" if phase is OutboxDispatchPhase.INVOKE else "invoked"
            )


async def test_unknown_registration_stays_unclaimed_and_counted(delivery_harness):
    h = delivery_harness
    event = await h.append(event_version=2)
    assert await h.delivery.claim(event.event_id, h.project, "worker") is None
    observation = await h.delivery.drain(h.project)
    assert observation.pending == observation.unsupported == 1
    assert h.prepared == h.consumed == h.handled == []
    assert await h.build(HandlerRegistry([])).claim(event.event_id, h.project, "worker") is None


async def test_invoke_releases_locks_and_runs_generation_once(delivery_harness):
    h = delivery_harness
    claim = await h.claim()

    async def independent_lock(envelope):
        async with h.factory() as session, session.begin():
            await session.execute(text("set local lock_timeout='500ms'"))
            row = await DeliveryRepository(session).event(claim.event_id, h.project, lock=True)
            assert row.delivery_state == "claimed"

    h.handler_hook = independent_lock
    results = await asyncio.gather(h.delivery.invoke(claim), h.delivery.invoke(claim))
    assert sum(result is not None for result in results) == 1
    assert len(h.handled) == 1
    assert [f.phase for f in h.consumed] == list(OutboxDispatchPhase)


async def test_diagnostic_annotation_follows_committed_invocation_envelope(
    delivery_harness, monkeypatch
):
    h = delivery_harness
    event = await h.append()
    claim = await h.delivery.claim(event.event_id, h.project, "worker")
    assert claim is not None
    async with h.factory() as session:
        before = await session.get(OutboxEvent, event.event_id)
        immutable_before = (
            before.payload,
            before.payload_digest,
            before.correlation_id,
            before.event_type,
            before.event_version,
        )
    annotated: list[str] = []
    authorization_at_annotation: list[tuple[tuple[object, ...], ...]] = []

    def authorization_snapshot() -> tuple[tuple[object, ...], ...]:
        return tuple(
            tuple(getattr(facts, field.name) for field in fields(facts))
            for facts in h.consumed
        )

    def annotate(*, outbox_correlation_id):
        annotated.append(str(outbox_correlation_id))
        authorization_at_annotation.append(authorization_snapshot())

    monkeypatch.setattr(delivery_module, "annotate_current_span", annotate)

    async def observe_committed(_envelope):
        assert annotated == [event.correlation_id]
        assert authorization_at_annotation == [authorization_snapshot()]
        async with h.factory() as session:
            attempt = await DeliveryRepository(session).attempt(claim)
            assert attempt is not None and attempt.stage == "invoked"

    h.handler_hook = observe_committed
    receipt = await h.delivery.invoke(claim)
    assert receipt is not None
    async with h.factory() as session:
        after = await session.get(OutboxEvent, event.event_id)
        assert (
            after.payload,
            after.payload_digest,
            after.correlation_id,
            after.event_type,
            after.event_version,
        ) == immutable_before
    assert not any("trace" in column.name or "span" in column.name for column in OutboxEvent.__table__.columns)
    assert not any("trace" in field or "span" in field for field in OutboxEventEnvelope.model_fields)
    assert all(
        not any("trace" in field.name or "span" in field.name for field in fields(facts))
        for facts in h.consumed
    )


@pytest.mark.parametrize("phase", list(OutboxDispatchPhase))
async def test_authority_wait_cannot_commit_an_expired_live_phase(delivery_harness, phase):
    """A delay inside consume must roll back instead of committing stale live facts."""
    h = delivery_harness
    event = await h.append()
    claim = None
    if phase is not OutboxDispatchPhase.CLAIM:
        claim = await h.delivery.claim(event.event_id, h.project, "worker")
    if phase is OutboxDispatchPhase.FINALIZE:
        await h.delivery._begin_invocation(claim)

    async def delay(facts):
        await asyncio.sleep(3.1)

    h.consume_hook = delay
    with pytest.raises(DeliveryUnavailable):
        if phase is OutboxDispatchPhase.CLAIM:
            await h.delivery.claim(event.event_id, h.project, "worker")
        elif phase is OutboxDispatchPhase.INVOKE:
            await h.delivery._begin_invocation(claim)
        else:
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        row = await session.get(OutboxEvent, event.event_id)
        assert row.delivery_state == (
            "pending" if phase is OutboxDispatchPhase.CLAIM else "claimed"
        )
        if claim:
            attempt = await DeliveryRepository(session).attempt(claim)
            assert attempt.stage == (
                "claimed" if phase is OutboxDispatchPhase.INVOKE else "invoked"
            )
    assert h.handled == []


async def test_stale_eligible_generation_rejects_before_consumption(delivery_harness):
    """A safe retry makes the state eligible again but not the old generation."""
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30})
    h.delivery = h.build()
    event = await h.append()
    prepared, release = asyncio.Event(), asyncio.Event()

    async def pause_stale(facts):
        if facts.claim_owner == "stale":
            prepared.set()
            await asyncio.wait_for(release.wait(), 10)

    h.prepare_hook = pause_stale
    stale = asyncio.create_task(h.delivery.claim(event.event_id, h.project, "stale"))
    try:
        await asyncio.wait_for(prepared.wait(), 5)
        first = await h.delivery.claim(event.event_id, h.project, "first")
        h.result = HandlerOutcome.RETRY
        await h.delivery.invoke(first)
        async with h.factory() as session:
            await session.execute(text("select pg_sleep(1.05)"))
        consumed = len(h.consumed)
        release.set()
        assert await asyncio.wait_for(stale, 5) is None
        assert len(h.consumed) == consumed
        second = await h.delivery.claim(event.event_id, h.project, "second")
        assert second.claim_generation == 2
    finally:
        release.set()
        await asyncio.gather(stale, return_exceptions=True)


async def test_invocation_observation_uses_one_stable_database_instant(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    envelope = await h.delivery._begin_invocation(claim)
    statements = []
    bind = h.factory.kw["bind"].sync_engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy_event.listen(bind, "before_cursor_execute", capture)
    try:
        observed = await h.delivery.observe_invocation(envelope)
    finally:
        sqlalchemy_event.remove(bind, "before_cursor_execute", capture)
    assert claim.claimed_at <= observed.observed_at < claim.claim_expires_at
    assert len(statements) == 1
    assert statements[0].count("statement_timestamp()") == 2
    assert "clock_timestamp()" not in statements[0]
    assert "FOR UPDATE" not in statements[0].upper()


async def test_effect_fence_holds_custody_until_caller_transaction_ends(delivery_harness, monkeypatch):
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30, "handler_timeout_seconds": 20})
    h.delivery = h.build()
    claim = await h.claim()
    envelope = await h.delivery._begin_invocation(claim)
    entered = asyncio.Event()
    waiter_name = "fence-finalizer-" + new_record_id().hex
    original_event = DeliveryRepository.event

    async def named_event(owner, *args, **kwargs):
        if asyncio.current_task().get_name() == waiter_name:
            await owner.session.execute(text("select set_config('application_name', :name, true)"), {"name": waiter_name})
        return await original_event(owner, *args, **kwargs)

    monkeypatch.setattr(DeliveryRepository, "event", named_event)

    async def finalize():
        entered.set()
        return await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)

    pending = None
    try:
        async with h.factory() as effect, effect.begin():
            fenced = await DeliveryRepository(effect).fence_invocation(envelope)
            assert fenced is not None and fenced.claim == claim
            pending = asyncio.create_task(finalize(), name=waiter_name)
            await entered.wait()
            # Independently observe PostgreSQL waiting, not merely an unfinished coroutine.
            from auth_concurrency_support import wait_for_named_database_lock
            await asyncio.wait_for(wait_for_named_database_lock(
                h.factory.kw["bind"].url.render_as_string(hide_password=False), waiter_name,
            ), 5)
            assert not pending.done()
        receipt = await asyncio.wait_for(pending, 5)
        assert receipt.claim == claim
    finally:
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
    async with h.factory() as session:
        with pytest.raises(DeliveryUnavailable, match="root transaction"):
            await DeliveryRepository(session).fence_invocation(envelope)
        async with session.begin():
            assert await DeliveryRepository(session).fence_invocation(envelope) is None
            assert await DeliveryRepository(session).fence_invocation(object()) is None
