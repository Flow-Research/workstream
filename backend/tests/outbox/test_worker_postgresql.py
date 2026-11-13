"""Actual Celery task functions with real OUTBOX custody and fixed-service AUTH."""

import json
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, text

from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.outbox import outbox_delivery
from app.core.config import get_settings
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.outbox.registry import HandlerRegistry


@pytest.fixture
def worker(delivery_harness, monkeypatch):
    h = delivery_harness
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import outbox as worker

    # Shared SQL/timeout proofs isolate topology, covered by the real broker drill.
    monkeypatch.setattr(worker, "require_outbox_worker", lambda _task: None)
    monkeypatch.setattr(worker, "get_database_url", lambda: h.factory.kw["bind"].url)
    monkeypatch.setattr(
        worker,
        "production_outbox_delivery",
        lambda factory: outbox_delivery(
            factory,
            authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry([("ContributionRecorded", 1, h.handle)]),
            options=h.options,
        ),
    )
    yield worker
    get_settings.cache_clear()


def deliver(worker, event, project):
    return worker.deliver_event.apply(
        args=(str(event), str(project)),
        task_id=str(new_record_id()),
        throw=True,
    ).get()


async def test_worker_duplicate_delivery(delivery_harness, worker):
    h = delivery_harness
    event = await h.append()
    assert deliver(worker, event.event_id, h.project) == {"status": "delivery_recorded"}
    assert deliver(worker, event.event_id, h.project) == {"status": "delivery_unavailable"}
    assert len(h.handled) == 1
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].stage == "completed"
        assert all(
            (
                attempts[0].claim_decision_event_id,
                attempts[0].invoke_decision_event_id,
                attempts[0].finalize_decision_event_id,
            )
        )


@pytest.mark.parametrize("invoked", [False, True])
async def test_worker_expired_recovery(delivery_harness, worker, invoked):
    h = delivery_harness
    claim = await h.claim()
    if invoked:
        await h.delivery._begin_invocation(claim)
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(3.05)"))
    assert deliver(worker, claim.event_id, h.project) == {"status": "delivery_recorded"}
    async with h.factory() as session:
        attempt = (await session.scalars(select(OutboxDeliveryAttempt))).one()
        body = json.loads(attempt.outcome_json)
        assert body["error_code"] == (
            "INVOKE_OUTCOME_UNKNOWN" if invoked else "LEASE_EXPIRED_BEFORE_INVOKE"
        )
        assert (attempt.invoke_decision_event_id is not None) is invoked
        assert attempt.finalize_decision_event_id
    assert h.handled == []


async def test_worker_scan_closes_sql_before_publication_and_retries_missing_hints(
    delivery_harness, worker, monkeypatch
):
    h = delivery_harness
    events = [await h.append() for _ in range(3)]
    published = []
    # Actual candidate query and engine disposal execute before this broker seam.
    real_candidates = worker._candidates
    read_closed = False

    async def candidates(after):
        nonlocal read_closed
        page = await real_candidates(after)
        read_closed = True
        return page

    def publish(*, args):
        assert read_closed
        published.append(args)
        if len(published) == 1:
            raise ConnectionError("broker unavailable")

    monkeypatch.setattr(worker, "_candidates", candidates)
    monkeypatch.setattr(worker.deliver_event, "apply_async", publish)
    result = worker.scan_pending.apply(task_id=str(new_record_id()), throw=True).get()
    assert result == {"selected": 3, "published": 2}
    assert {e.event_id for e in events} == {UUID(args[0]) for args in published}
    assert worker.scan_pending.apply(task_id=str(new_record_id()), throw=True).get() == {
        "selected": 3,
        "published": 3,
    }
    async with h.factory() as session:
        assert {e.delivery_state for e in (await session.scalars(select(OutboxEvent))).all()} == {
            "pending"
        }
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []


@pytest.mark.parametrize(
    "args,task_id",
    [
        (("bad", "bad"), str(new_record_id())),
        ((str(new_record_id()), str(new_record_id())), "not-a-task-uuid"),
        ((None, str(new_record_id())), str(new_record_id())),
    ],
)
async def test_worker_rejects_transport_before_sql(worker, monkeypatch, args, task_id):
    def forbidden():
        pytest.fail("malformed broker input reached SQL")

    monkeypatch.setattr(worker, "get_database_url", forbidden)
    assert worker.deliver_event.apply(args=args, task_id=task_id, throw=True).get() == {
        "status": "delivery_rejected"
    }
    assert worker.scan_pending.apply(args=("bad",), throw=True).get() == {"status": "scan_rejected"}


@pytest.mark.parametrize("failure", ["delivery", "scan"])
async def test_worker_infrastructure_failure_has_bounded_sanitized_retry(
    worker, monkeypatch, failure
):
    from celery.exceptions import Retry

    async def failed(*args):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(worker, "_deliver" if failure == "delivery" else "_candidates", failed)
    task = worker.deliver_event if failure == "delivery" else worker.scan_pending
    args = (str(new_record_id()), str(new_record_id())) if failure == "delivery" else ()
    with pytest.raises(Retry) as raised:
        task.apply(args=args, task_id=str(new_record_id()), throw=True)
    assert raised.value.when == 30
    assert "private" not in str(raised.value)
    with pytest.raises(RuntimeError, match="outbox .* unavailable") as exhausted:
        task.apply(args=args, task_id=str(new_record_id()), retries=3, throw=True)
    assert "private" not in str(exhausted.value)


async def test_worker_scan_continues_after_failed_publication(worker, monkeypatch):
    from app.modules.outbox.api import DeliveryCandidate, DeliveryCandidatePage

    selectors = (DeliveryCandidate(event_id=new_record_id(), project_id=new_record_id()),)
    cursor = selectors[-1].event_id

    async def page(after):
        return DeliveryCandidatePage(items=selectors, next_after=cursor)

    attempts = []

    def publish(*, args):
        attempts.append(args)
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(worker, "_candidates", page)
    monkeypatch.setattr(worker.deliver_event, "apply_async", publish)
    monkeypatch.setattr(worker.scan_pending, "apply_async", publish)
    assert worker.scan_pending.apply(task_id=str(new_record_id()), throw=True).get() == {
        "selected": 1,
        "published": 0,
    }
    assert attempts == [(str(cursor), str(selectors[0].project_id)), (str(cursor),)]


async def test_production_registry_claims_only_registered_features(delivery_harness):
    from app.adapters.outbox import production_outbox_delivery
    from app.modules.checkers.api.delivery_reconciliation import (
        POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT,
    )
    from app.modules.checkers.api.execution import COMPLETION_EVENT, REQUEST_EVENT

    h = delivery_harness
    event = await h.append()
    production = production_outbox_delivery(h.factory)
    assert production._registry.keys == (
        ("TaskAssignmentAuthorityInvalidationRequested", 1),
        ("TaskRevisionExpiryRequested", 1),
        ("TaskRevisionExpired", 1),
        ("TaskRevisionContextBlocked", 1),
        (REQUEST_EVENT, 1),
        (COMPLETION_EVENT, 1),
        (POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, 1),
    )
    assert production._registry.can_retry_unknown("TaskRevisionExpiryRequested", 1)
    assert production._registry.can_retry_unknown("TaskRevisionExpired", 1)
    assert production._registry.can_retry_unknown("TaskRevisionContextBlocked", 1)
    assert not production._registry.can_retry_unknown(REQUEST_EVENT, 1)
    assert not production._registry.can_retry_unknown(COMPLETION_EVENT, 1)
    assert not production._registry.can_retry_unknown(
        POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, 1
    )
    assert (await production.candidates()).items == ()
    assert await production.deliver(event.event_id, h.project, "worker") is None
    async with h.factory() as session:
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []
        assert (await session.get(OutboxEvent, event.event_id)).delivery_state == "pending"


async def test_prefork_bounds_cancellation_resistant_worker(
    delivery_harness, worker, monkeypatch, tmp_path
):
    """Actual sync task shutdown is bounded after real invocation records UNKNOWN."""
    import ast
    import asyncio
    from threading import Event

    from billiard.einfo import ExceptionWithTraceback
    from billiard.connection import wait
    from celery.concurrency.prefork import TaskPool
    from celery.exceptions import TimeLimitExceeded
    from celery.worker.request import Request
    from kombu.message import Message

    from app.modules.outbox.api import DeliveryOptions

    h = delivery_harness
    marker = tmp_path / "handler-calls.txt"

    async def stubborn(envelope):
        with marker.open("a") as stream:
            stream.write("invoked\n")
        while True:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                with marker.open("a") as stream:
                    stream.write("cancelled\n")

    h.handler_hook = stubborn
    h.options = DeliveryOptions(lease_seconds=30, handler_timeout_seconds=1)
    event = await h.append()
    task = worker.deliver_event
    # Scale an installed process deadline only. Removing it leaves the real
    # prefork task hanging until the independent test watchdog detects it.
    if task.time_limit is not None:
        monkeypatch.setattr(task, "time_limit", 5)
        from app.workers import outbox_topology
        monkeypatch.setattr(outbox_topology, "OUTBOX_HARD_LIMIT_SECONDS", 5)
    monkeypatch.setenv("WORKSTREAM_ARTIFACT_STORE_BACKEND", "disabled")
    get_settings.cache_clear()
    acked = Event()
    rejected = []
    pool = TaskPool(1, app=worker.celery_app, initargs=(worker.celery_app, "outbox-proof"))
    pool.start()
    child = pool._pool._pool[0]
    try:
        task_id = str(new_record_id())
        message = Message(
            headers={"id": task_id, "task": task.name},
            properties={"correlation_id": task_id},
            body=((str(event.event_id), str(h.project)), {}, {}),
        )
        request = Request(
            message,
            app=worker.celery_app,
            task=task,
            decoded=True,
            on_ack=lambda *args: acked.set(),
            on_reject=lambda *args: rejected.append(args),
        )
        result = request.execute_using_pool(pool)
        with pytest.raises(ExceptionWithTraceback) as timed_out:
            result.get(timeout=15)
        assert isinstance(timed_out.value.exc, TimeLimitExceeded)
        assert acked.wait(3), "hard timeout must acknowledge without retrying the handler"
        assert rejected == []
        # The pool owns waitpid/reaping. A competing join can observe stale
        # returncode metadata; the owned child sentinel proves actual exit.
        assert wait([child.sentinel], timeout=5), (
            "hard timeout must terminate the stuck worker process"
        )
        duplicate_id = str(new_record_id())
        duplicate = Request(
            Message(
                headers={"id": duplicate_id, "task": task.name},
                properties={"correlation_id": duplicate_id},
                body=message.body,
            ),
            app=worker.celery_app,
            task=task,
            decoded=True,
            on_reject=lambda *args: rejected.append(args),
        )
        failed, body, _ = duplicate.execute_using_pool(pool).get(timeout=15)
        assert not failed and ast.literal_eval(body) == {"status": "delivery_unavailable"}
        assert duplicate.worker_pid != child.pid
        assert rejected == []
    finally:
        processes = pool._pool
        pool.terminate()
        processes.join()
        get_settings.cache_clear()

    lines = marker.read_text().splitlines()
    assert lines.count("invoked") == 1
    assert lines.count("cancelled") >= 2  # invocation timeout and asyncio.run shutdown
    async with h.factory() as session:
        attempt = (await session.scalars(select(OutboxDeliveryAttempt))).one()
        assert attempt.stage == "completed"
        assert json.loads(attempt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        assert attempt.finalize_decision_event_id
        original = attempt.outcome_json
    assert deliver(worker, event.event_id, h.project) == {"status": "delivery_unavailable"}
    assert marker.read_text().splitlines().count("invoked") == 1
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].outcome_json == original


def test_delivery_task_has_independent_hard_limit(worker):
    from app.modules.outbox.api import DeliveryOptions

    task = worker.deliver_event
    from app.modules.checkers.api.external_policy import (
        SELECTED_POST_DELIVERY_LEASE_SECONDS, SELECTED_POST_HANDLER_TIMEOUT_SECONDS,
    )
    from app.workers.outbox_topology import OUTBOX_PROCESS_SHUTDOWN_MARGIN_SECONDS
    assert task.time_limit == (
        SELECTED_POST_DELIVERY_LEASE_SECONDS + OUTBOX_PROCESS_SHUTDOWN_MARGIN_SECONDS
    )
    assert task.time_limit > SELECTED_POST_HANDLER_TIMEOUT_SECONDS
    assert task.time_limit > DeliveryOptions().handler_timeout_seconds
    assert task.acks_late and task.acks_on_failure_or_timeout
    assert task.reject_on_worker_lost is True
    assert task.soft_time_limit is None
