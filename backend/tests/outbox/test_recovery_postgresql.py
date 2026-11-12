"""Crash boundaries, retry exhaustion and exact retained outcome replay."""

import asyncio
from dataclasses import fields
import json
from uuid import uuid4

from celery import signals
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest
from sqlalchemy import select, text

from app.adapters.outbox import outbox_delivery
from app.core import celery_observability as celery_diagnostics
from app.core.celery_observability import configure_celery_observability
from app.core.config import Settings, get_settings
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.core.observability import ObservabilityRuntime
from app.modules.outbox.api import DeliveryUnavailable, FinalizationCause, HandlerOutcome
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from app.workers.outbox_topology import OUTBOX_DELIVERY_TASK
from observability_test_support import fake_export_adapter
from tests.outbox.conftest import TracedPort


PAGINATION_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


async def expire(h):
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(3.05)"))


def _start_recovery_runtime(monkeypatch: pytest.MonkeyPatch):
    exporter = InMemorySpanExporter()
    runtime = ObservabilityRuntime(
        Settings(
            environment="test",
            pagination_cursor_hmac_secret=PAGINATION_SECRET,
            observability_trace_sample_ratio=1.0,
        ),
        service_name="workstream-celery",
        task_names=frozenset({OUTBOX_DELIVERY_TASK, "workstream.outbox.scan_pending"}),
        export_adapter=fake_export_adapter(exporter, InMemoryMetricReader()),
    )
    runtime.start()
    monkeypatch.setattr(celery_diagnostics, "_WORKER_RUNTIME", runtime)
    configure_celery_observability(
        runtime.settings,
        frozenset({OUTBOX_DELIVERY_TASK, "workstream.outbox.scan_pending"}),
        lambda: None,
    )
    return runtime, exporter


async def _immutable_event_snapshot(factory, event_id):
    async with factory() as session:
        row = await session.get(OutboxEvent, event_id)
        return (
            row.payload,
            row.payload_digest,
            row.correlation_id,
            row.event_type,
            row.event_version,
        )


def _configure_recovery_worker(h, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import outbox as worker

    monkeypatch.setattr(worker, "require_outbox_worker", lambda _task: None)
    monkeypatch.setattr(worker, "get_database_url", lambda: h.factory.kw["bind"].url)
    worker_factories = []

    def compose_delivery(factory):
        worker_factories.append(factory)
        return outbox_delivery(
            factory,
            authorization_factory=lambda session: TracedPort(h, session),
            registry=HandlerRegistry([("ContributionRecorded", 1, h.handle)]),
            options=h.options,
        )

    monkeypatch.setattr(worker, "production_outbox_delivery", compose_delivery)
    return worker, worker_factories


async def _deliver_recovery_task(worker, h, event, task_id, *, headers=None):
    return await asyncio.to_thread(
        lambda: worker.deliver_event.apply(
            args=(str(event.event_id), str(h.project)),
            task_id=task_id,
            headers=headers,
            throw=True,
        ).get()
    )


def _install_committed_annotation_observer(h, worker_factories, event):
    annotation_seen: list[str] = []

    async def observe_annotation(_envelope) -> None:
        active = trace.get_current_span()
        assert active.is_recording()
        value = active.attributes.get("workstream.outbox.correlation_id")
        assert value == event.correlation_id
        annotation_seen.append(value)
        async with worker_factories[-1]() as independent:
            attempt = (
                await independent.scalars(
                    select(OutboxDeliveryAttempt).where(
                        OutboxDeliveryAttempt.event_id == event.event_id
                    )
                )
            ).one()
            stored_event = await independent.get(OutboxEvent, event.event_id)
            assert attempt.stage == "invoked"
            assert attempt.invoked_at is not None
            assert attempt.outcome_json is None
            assert stored_event.delivery_state == "claimed"

    h.handler_hook = observe_annotation
    return annotation_seen


async def _scan_recovery_event(worker, h, event, monkeypatch: pytest.MonkeyPatch):
    published: list[tuple[tuple[str, str], dict[str, object]]] = []

    def publish(*, args: tuple[str, str]) -> None:
        headers: dict[str, object] = {}
        signals.before_task_publish.send(sender=OUTBOX_DELIVERY_TASK, headers=headers)
        published.append((args, dict(headers)))

    monkeypatch.setattr(worker.deliver_event, "apply_async", publish)
    scan_task_id = str(uuid4())
    scan = await asyncio.to_thread(
        lambda: worker.scan_pending.apply(task_id=scan_task_id, throw=True).get()
    )
    assert scan == {"selected": 1, "published": 1}
    assert len(published) == 1
    published_args, published_headers = published[0]
    assert published_args == (str(event.event_id), str(h.project))
    assert set(published_headers) == {
        "traceparent",
        "workstream-request-id",
        "workstream-correlation-id",
    }
    assert published_headers["workstream-request-id"] == scan_task_id
    assert published_headers["workstream-correlation-id"] == scan_task_id
    return published_headers


def _assert_recovery_spans(exporter, event, original_trace_id):
    spans = exporter.get_finished_spans()
    assert len(spans) == 5
    original, scan_span, first, duplicate, expired = spans
    assert len({span.context.trace_id for span in spans}) == 4
    assert original.context.trace_id == original_trace_id
    assert original.parent is None
    assert scan_span.name == "celery workstream.outbox.scan_pending"
    assert scan_span.parent is None
    assert scan_span.context.trace_id != original_trace_id
    assert first.context.trace_id == scan_span.context.trace_id
    assert first.parent is not None
    assert first.parent.span_id == scan_span.context.span_id
    assert duplicate.parent is None and expired.parent is None
    assert first.attributes["workstream.outbox.correlation_id"] == event.correlation_id, [
        dict(span.attributes) for span in spans
    ]
    assert "workstream.outbox.correlation_id" not in duplicate.attributes
    assert "workstream.outbox.correlation_id" not in expired.attributes


async def _assert_recovery_storage(h, event, immutable_before):
    async with h.factory() as session:
        after = await session.get(OutboxEvent, event.event_id)
        immutable_after = (
            after.payload,
            after.payload_digest,
            after.correlation_id,
            after.event_type,
            after.event_version,
        )
        attempts = (
            await session.scalars(
                select(OutboxDeliveryAttempt).where(
                    OutboxDeliveryAttempt.event_id == event.event_id
                )
            )
        ).all()
    assert immutable_after == immutable_before
    assert len(attempts) == 1
    assert attempts[0].stage == "completed"
    assert attempts[0].outcome_json is not None
    assert not any(
        "trace" in column.name or "span" in column.name
        for model in (OutboxEvent, OutboxDeliveryAttempt)
        for column in model.__table__.columns
    )
    assert all(
        "trace" not in field.name and "span" not in field.name
        for facts in h.consumed
        for field in fields(facts)
    )


async def test_pending_recovery_trace_annotates_only_after_committed_invocation(
    delivery_harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = delivery_harness
    runtime, exporter = _start_recovery_runtime(monkeypatch)
    with runtime.tracer.start_as_current_span("original business event") as original_span:
        original_trace_id = original_span.get_span_context().trace_id
        event = await h.append(correlation_id=str(new_record_id()))
    immutable_before = await _immutable_event_snapshot(h.factory, event.event_id)
    worker, worker_factories = _configure_recovery_worker(h, monkeypatch)

    try:
        annotation_seen = _install_committed_annotation_observer(h, worker_factories, event)
        published_headers = await _scan_recovery_event(worker, h, event, monkeypatch)
        assert await _deliver_recovery_task(
            worker, h, event, str(uuid4()), headers=published_headers
        ) == {
            "status": "delivery_recorded"
        }
        assert annotation_seen == [event.correlation_id]
        assert len(h.handled) == 1

        assert await _deliver_recovery_task(worker, h, event, str(uuid4())) == {
            "status": "delivery_unavailable"
        }
        assert len(h.handled) == 1

        expired_event = await h.append(idempotency_key="recovery-expired-control")
        expired_claim = await h.delivery.claim(
            expired_event.event_id,
            h.project,
            "expired-control",
        )
        assert expired_claim is not None
        await expire(h)
        assert await _deliver_recovery_task(worker, h, expired_event, str(uuid4())) == {
            "status": "delivery_recorded"
        }
        assert len(h.handled) == 1
        assert runtime.force_flush()
        _assert_recovery_spans(exporter, event, original_trace_id)
        await _assert_recovery_storage(h, event, immutable_before)
    finally:
        celery_diagnostics._ACTIVE_TASKS.clear()
        runtime.shutdown()
        get_settings.cache_clear()


async def test_crash_before_invoke_recovers(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    assert await h.delivery.recover(claim.event_id, h.project) is None
    await expire(h)
    result = await h.delivery.recover(claim.event_id, h.project)
    body = json.loads(result.outcome_json)
    assert body["delivery_state"] == "retryable"
    assert body["error_code"] == "LEASE_EXPIRED_BEFORE_INVOKE"
    assert body["invoked_at"] is None and body["invocation_unknown"] is False
    assert h.handled == []


async def test_crash_after_invoke_commit_before_handler_entry_is_unknown(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    envelope = await h.delivery._begin_invocation(claim)
    assert envelope is not None
    assert h.handled == []
    await expire(h)
    assert await h.delivery.observe_invocation(envelope) is None
    receipt = await h.delivery.recover(claim.event_id, h.project)
    body = json.loads(receipt.outcome_json)
    assert (body["delivery_state"], body["error_code"], body["invocation_unknown"]) == (
        "dead_letter",
        "INVOKE_OUTCOME_UNKNOWN",
        True,
    )
    assert await h.delivery.claim(claim.event_id, h.project, "other") is None
    assert await h.delivery.invoke(claim) is None
    assert (await h.delivery.drain(h.project)).unresolved == 1
    assert h.handled == []


async def test_crash_after_handler_before_finalize_is_unknown(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    envelope = await h.delivery._begin_invocation(claim)
    assert await h.handle(envelope) is HandlerOutcome.ACKNOWLEDGE
    await expire(h)
    receipt = await h.delivery.recover(claim.event_id, h.project)
    assert json.loads(receipt.outcome_json)["invocation_unknown"] is True
    assert len(h.handled) == 1


async def test_finalize_commit_and_exact_replay(delivery_harness, monkeypatch):
    h = delivery_harness
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    from sqlalchemy.ext.asyncio import AsyncSession

    original = AsyncSession.flush

    async def fail_after_flush(session, *args, **kwargs):
        await original(session, *args, **kwargs)
        raise RuntimeError("simulated_loss_before_commit")

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "flush", fail_after_flush)
        with pytest.raises(RuntimeError, match="simulated_loss_before_commit"):
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
        assert (await session.get(OutboxEvent, claim.event_id)).delivery_state == "claimed"
    receipt = await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    assert await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE) == receipt
    body = json.loads(receipt.outcome_json)
    assert canonical_json_hash(body) == receipt.outcome_digest
    assert body["receipt_completed_at"] == body["finalized_at"]
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.finalize(claim, FinalizationCause.RETRY)
    for key, replacement in {
        "delivery_state": "dead_letter",
        "error_code": "HANDLER_REJECTED",
        "next_attempt_at": body["receipt_completed_at"],
        "finalized_at": None,
        "receipt_completed_at": claim.claimed_at.isoformat(),
        "invocation_unknown": True,
        "invoked_at": None,
    }.items():
        mutated = {**body, key: replacement}
        forged = receipt.model_copy(
            update={
                "outcome_json": json.dumps(mutated, sort_keys=True, separators=(",", ":")),
                "outcome_digest": canonical_json_hash(mutated),
            }
        )
        with pytest.raises(DeliveryUnavailable):
            await h.delivery._finalize(forged, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        rows = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(rows) == 1
        assert rows[0].outcome_json == receipt.outcome_json
        assert rows[0].outcome_digest == receipt.outcome_digest
        assert rows[0].claimed_at == claim.claimed_at
        assert rows[0].claim_expires_at == claim.claim_expires_at


async def test_retry_backoff_and_exhaustion(delivery_harness):
    from datetime import datetime

    h = delivery_harness
    h.options = h.options.model_copy(update={"max_attempts": 2})
    h.delivery = h.build()
    claim = await h.claim()
    h.result = HandlerOutcome.RETRY
    first = await h.delivery.invoke(claim)
    body = json.loads(first.outcome_json)
    assert (
        datetime.fromisoformat(body["next_attempt_at"])
        - datetime.fromisoformat(body["receipt_completed_at"])
    ).total_seconds() == 1
    assert await h.delivery.claim(claim.event_id, h.project, "early") is None
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(1.05)"))
    second = await h.delivery.claim(claim.event_id, h.project, "second")
    assert second.claim_generation == 2
    last = json.loads((await h.delivery.invoke(second)).outcome_json)
    assert last["delivery_state"] == "dead_letter" and last["error_code"] == "ATTEMPTS_EXHAUSTED"
    assert last["invocation_unknown"] is False and last["next_attempt_at"] is None
    assert await h.delivery.claim(claim.event_id, h.project, "third") is None
    control = await h.claim()
    h.result = HandlerOutcome.ACKNOWLEDGE
    assert (
        json.loads((await h.delivery.invoke(control)).outcome_json)["delivery_state"]
        == "acknowledged"
    )


async def test_completed_generation_replays_without_mutating_successor(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    await expire(h)
    original = await h.delivery.recover(claim.event_id, h.project)
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(1.05)"))
    second = await h.delivery.claim(claim.event_id, h.project, "second")
    assert second.claim_generation == 2
    consumed = len(h.consumed)
    assert await h.delivery.invoke(claim) is None
    assert len(h.consumed) == consumed
    assert await h.delivery.finalize(claim, FinalizationCause.EXPIRED) == original
    assert len(h.consumed) == consumed + 1
    forged = original.model_copy(update={"outcome_digest": "sha256:" + "0" * 64})
    with pytest.raises(DeliveryUnavailable):
        await h.delivery._finalize(forged, FinalizationCause.EXPIRED)
    assert len(h.consumed) == consumed + 1
    async with h.factory() as session:
        event = await session.get(OutboxEvent, claim.event_id)
        assert event.claim_generation == 2 and event.claim_owner == "second"


@pytest.mark.parametrize("fault", ["exception", "invalid", "timeout"])
async def test_handler_failure_is_unknown_not_retryable(delivery_harness, fault):
    import asyncio

    h = delivery_harness
    if fault == "timeout":
        # Isolate handler timeout from the independently tested lease-expiry guard.
        h.options = h.options.model_copy(update={"lease_seconds": 30})
        h.delivery = h.build()

    async def fail(envelope):
        if fault == "exception":
            raise RuntimeError("private provider content")
        if fault == "timeout":
            await asyncio.sleep(2.1)

    h.handler_hook = fail
    if fault == "invalid":
        h.result = "acknowledge"
    receipt = await h.delivery.invoke(await h.claim())
    assert "private" not in receipt.outcome_json
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"


async def test_concurrent_same_outcome_finalizers_replay_winner(delivery_harness):
    from app.modules.authorization.api.outbox_dispatch import OutboxDispatchPhase

    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30})
    h.delivery = h.build()
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    entered, ready = 0, asyncio.Event()

    async def barrier(facts):
        nonlocal entered
        if facts.phase is OutboxDispatchPhase.FINALIZE:
            entered += 1
            if entered == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 5)

    h.prepare_hook = barrier
    first = asyncio.create_task(h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE))
    await asyncio.sleep(0.02)
    receipts = await asyncio.gather(
        first, h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    )
    assert receipts[0] == receipts[1]
    finalized = [f for f in h.consumed if f.phase is OutboxDispatchPhase.FINALIZE]
    assert len(finalized) == 2
    assert {f.outcome_digest for f in finalized} == {receipts[0].outcome_digest}
    assert entered == 3  # Losing proposal prepares once more for the stored digest.
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].outcome_json == receipts[0].outcome_json
        from app.modules.tasks.models import AuditEvent
        original_ids = {attempts[0].claim_decision_event_id, attempts[0].invoke_decision_event_id,
                        attempts[0].finalize_decision_event_id}
        assert len(original_ids) == 3 and None not in original_ids
        audits = (await session.scalars(select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch"))).all()
        assert len(audits) == 4 and original_ids < {audit.id for audit in audits}


async def test_running_handler_expiry_preserves_unknown_and_late_replay(delivery_harness):
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 5, "handler_timeout_seconds": 4})
    h.delivery = h.build()
    claim = await h.claim()
    await asyncio.sleep(2)
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(envelope):
        entered.set()
        await release.wait()

    h.handler_hook = blocked
    invocation = asyncio.create_task(h.delivery.invoke(claim))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert (await h.delivery.drain(h.project)).invoked == 1
        await asyncio.sleep(3.05)
        receipt = await h.delivery.recover(claim.event_id, h.project)
        assert not invocation.done()
        assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        observation = await h.delivery.drain(h.project)
        assert observation.invoked == 0 and observation.unresolved == 1
        assert await h.delivery.claim(claim.event_id, h.project, "retry") is None
        release.set()
        assert await asyncio.wait_for(invocation, 2) == receipt
        assert len(h.handled) == 1
        assert await h.delivery.invoke(claim) is None
    finally:
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)


async def test_cancelled_invocation_leaves_custody_for_unknown_recovery(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    entered = asyncio.Event()

    async def blocked(envelope):
        entered.set()
        await asyncio.Event().wait()

    h.handler_hook = blocked
    invocation = asyncio.create_task(h.delivery.invoke(claim))
    await asyncio.wait_for(entered.wait(), 2)
    invocation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await invocation
    async with h.factory() as session:
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
    await expire(h)
    receipt = await h.delivery.recover(claim.event_id, h.project)
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
    observation = await h.delivery.drain(h.project)
    assert observation.invoked == 0 and observation.unresolved == 1
    assert await h.delivery.invoke(claim) is None and len(h.handled) == 1


async def test_handler_suppressing_cancellation_cannot_ack_after_deadline(delivery_harness, monkeypatch):
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30, "handler_timeout_seconds": 1})
    h.delivery = h.build()
    claim = await h.claim()
    cancelled, release = asyncio.Event(), asyncio.Event()
    finalizing, allow_finalize = asyncio.Event(), asyncio.Event()
    real_finalize = h.delivery.finalize

    async def observe_finalize(*args, **kwargs):
        finalizing.set()
        await allow_finalize.wait()
        return await real_finalize(*args, **kwargs)

    monkeypatch.setattr(h.delivery, "finalize", observe_finalize)

    async def suppress_cancellation(envelope):
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()

    h.handler_hook = suppress_cancellation
    invocation = asyncio.create_task(h.delivery.invoke(claim))
    try:
        await asyncio.wait_for(cancelled.wait(), 3)
        # The dispatcher must reach finalization promptly without awaiting the
        # uncooperative handler. Database latency is a separate observation.
        await asyncio.wait_for(finalizing.wait(), 2)
        assert not release.is_set() and not invocation.done()
        assert h.delivery._running_handlers
        allow_finalize.set()
        receipt = await asyncio.wait_for(asyncio.shield(invocation), 10)
        assert h.delivery._running_handlers
        assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        assert (await h.delivery.drain(h.project)).unresolved == 1
        release.set()
        await asyncio.gather(*tuple(h.delivery._running_handlers))
        assert await h.delivery.finalize(claim, FinalizationCause.UNKNOWN) == receipt
        assert await h.delivery.invoke(claim) is None and len(h.handled) == 1
    finally:
        allow_finalize.set()
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)
        await asyncio.gather(*tuple(h.delivery._running_handlers), return_exceptions=True)


async def test_completed_handler_after_deadline_is_unknown(delivery_harness):
    """A completed task must not turn event-loop delay into a timely success."""
    import time

    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30, "handler_timeout_seconds": 1})
    h.delivery = h.build()

    async def blocking_handler(envelope):
        time.sleep(1.1)

    h.handler_hook = blocking_handler
    receipt = await h.delivery.invoke(await h.claim())
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
    assert len(h.handled) == 1
    assert (await h.delivery.drain(h.project)).unresolved == 1
