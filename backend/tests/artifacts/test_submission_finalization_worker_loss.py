"""Actual process death retains accepted custody before and after T5 commit."""
import asyncio
from datetime import timedelta
import multiprocessing
import os
import signal
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import submission_finalization_handler
from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.checkers import selected_pre_submit_coordinator
from app.adapters.outbox import outbox_append, outbox_delivery
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.outbox.api import DeliveryOptions, HandlerOutcome
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from tests.artifact_store_helpers import initialize_local_store
from tests.artifacts.intake_acceptance_support import completed_source
from tests.artifacts.test_submission_intake_admission import admission_intake as admission_intake
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env, clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access, admin_access as admin_access,
)
from tests.checkers.execution.support import provision_post_submit_service
from tests.test_artifact_admission import _settings


def _delivery(factory, path, *, kill_at=None, observations=None, forbid_observation=False):
    store = initialize_local_store(root=path / "durable", buffer_bytes=256 * 1024)

    class ObservedStore:
        async def observe_sealed_source(self, source):
            if kill_at == "before_observation":
                os.kill(os.getpid(), signal.SIGKILL)
            assert not forbid_observation, "committed finalization reread source"
            if observations is not None:
                observations.append(source)
            return await store.observe_sealed_source(source)

    handler = submission_finalization_handler(sessions=factory, settings=_settings(path),
        store=ObservedStore(), lease_duration=timedelta(seconds=60))

    async def invoke(envelope):
        result = await handler(envelope)
        assert result == HandlerOutcome.ACKNOWLEDGE
        if kill_at == "after_commit":
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    event = ("SubmissionFinalizationRequested", 1)
    return outbox_delivery(factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(*event, invoke)], replay_safe=frozenset({event})),
        options=DeliveryOptions(lease_seconds=60, handler_timeout_seconds=55,
            retry_base_seconds=1, retry_cap_seconds=1)), store


def _crash_worker(database_url, path, event_id, project_id, kill_at):
    """Use fresh SQL resources in a process which cannot run cleanup on SIGKILL."""
    async def run():
        engine = create_async_engine(database_url)
        delivery, store = _delivery(async_sessionmaker(engine, expire_on_commit=False), path, kill_at=kill_at)
        try:
            result = await delivery.deliver(event_id, project_id, "killed-finalizer")
            raise AssertionError(f"worker returned before SIGKILL: {result}")
        finally:
            store.close()
            await engine.dispose()
    asyncio.run(run())


async def _wait_until_database_time(factory, target):
    """The lease uses PostgreSQL wall time, not the test process's sleep clock."""
    async with asyncio.timeout(75):
        while True:
            async with factory() as session:
                now = await session.scalar(select(func.clock_timestamp()))
            if now >= target:
                return
            await asyncio.sleep(min(0.1, (target - now).total_seconds()))


@pytest.mark.parametrize("kill_at", ["before_observation", "after_commit"])
async def test_sigkill_finalizer_recovers_exact_accepted_operation(admission_intake, tmp_path, kill_at):
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        event_id = UUID(row.finalization_event_id)
    process = multiprocessing.get_context("fork").Process(target=_crash_worker, args=(
        f.factory.kw["bind"].url, tmp_path, event_id, f.project, kill_at))
    observations = []
    delivery, store = _delivery(f.factory, tmp_path, observations=observations,
        forbid_observation=kill_at == "after_commit")
    process.start()
    try:
        await asyncio.to_thread(process.join, 90)
        assert not process.is_alive(), "finalizer did not reach crash boundary"
        assert process.exitcode == -signal.SIGKILL
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event = await session.get(OutboxEvent, event_id)
            assert event.delivery_state == "claimed" and event.attempt_count == 1
            assert row.state == ("finalized" if kill_at == "after_commit" else "finalization_pending")
            original_submission = row.finalized_submission_id
            ready_at = max(event.claim_expires_at, row.continuation_expires_at)
        await _wait_until_database_time(f.factory, ready_at)
        assert await delivery.recover(event_id, f.project) is not None
        async with f.factory() as session:
            event = await session.get(OutboxEvent, event_id)
            assert event.delivery_state == "retryable"
            ready_at = event.next_attempt_at
        await _wait_until_database_time(f.factory, ready_at)
        assert await delivery.deliver(event_id, f.project, "replacement-finalizer") is not None
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event = await session.get(OutboxEvent, event_id)
            assert row.state == "finalized" and event.delivery_state == "acknowledged"
            assert event.attempt_count == 2
            assert row.continuation_generation == (1 if kill_at == "after_commit" else 2)
            if original_submission is not None:
                assert row.finalized_submission_id == original_submission
            for table in ("submissions", "submission_dispatches", "checker_runs"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE task_id=:id"), {"id": f.task}) == 1
            assert await session.scalar(text("SELECT count(*) FROM artifact_bindings WHERE resource_id=:id"),
                {"id": row.finalized_submission_id}) == 1
            assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE project_id=:id "
                "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 1
        assert observations == ([] if kill_at == "after_commit" else [request.source])
    finally:
        if process.is_alive():
            process.kill()
        await asyncio.to_thread(process.join, 5)
        assert not process.is_alive(), "crash worker cleanup failed"
        process.close()
        store.close()


def _broker_finalizer(app, hostname, completed):
    """Observe real returns after the production exclusive-prefork boundary."""
    from celery.signals import task_postrun
    from app.workers.outbox_topology import FINALIZATION_DELIVERY_TASK, FINALIZATION_QUEUE

    def record(task_id, task, retval, state, **_kwargs):
        if task.name == FINALIZATION_DELIVERY_TASK:
            completed.put((task_id, state, retval, os.getpid(), task.request.is_eager,
                           task.request.delivery_info["routing_key"]))

    os.setsid()
    task_postrun.connect(record, weak=False)
    app.Worker(pool="prefork", concurrency=1, queues=[FINALIZATION_QUEUE], hostname=hostname,
               loglevel="ERROR", without_gossip=True, without_mingle=True,
               without_heartbeat=True).start()


async def _redis_forwarder(reader, writer, destination, connections):
    """Restore only this test's TCP endpoint; Redis and its namespace stay real."""
    current = asyncio.current_task()
    connections.add(current)
    upstream, copies = None, []

    async def copy_bytes(source, target):
        while data := await source.read(64 * 1024):
            target.write(data)
            await target.drain()

    try:
        remote, upstream = await asyncio.open_connection(*destination)
        copies = [asyncio.create_task(copy_bytes(reader, upstream)),
                  asyncio.create_task(copy_bytes(remote, writer))]
        await asyncio.wait(copies, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for pending in copies:
            pending.cancel()
        await asyncio.gather(*copies, return_exceptions=True)
        for stream in (writer, upstream):
            if stream is not None:
                stream.close()
                try:
                    await stream.wait_closed()
                except ConnectionError:
                    pass
        connections.discard(current)


def _broker_settings(settings, monkeypatch):
    """Give the worker the same real local namespace as the public upload."""
    import json
    from app.core.config import get_settings

    for name, value in settings.model_dump(mode="json").items():
        if name.startswith("artifact_") and value is not None:
            encoded = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
            monkeypatch.setenv("WORKSTREAM_" + name.upper(), encoded)
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_HOSTED_PROFILE", "app")
    get_settings.cache_clear()


async def _accepted_broker_facts(f, operation_id):
    """Freeze accepted product/outbox custody across publication failure."""
    from app.modules.artifacts.intake.models import SubmissionSourceCharge

    async with f.factory() as session:
        operation = await session.get(SubmissionIntakeOperation, operation_id)
        event = await session.get(OutboxEvent, UUID(operation.finalization_event_id))
        charge = await session.get(SubmissionSourceCharge, operation_id)
        pointer = await session.scalar(text(
            "SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:task"
        ), {"task": f.task})
        return (operation.state, operation.acceptance_receipt, operation.finalized_submission_id,
                operation.continuation_generation, event.event_id, event.delivery_state,
                event.attempt_count, charge.state, charge.accounted_bytes, pointer)


async def _assert_broker_finalized_once(f, operation_id, accepted):
    """Require one durable graph after original and duplicate tasks return."""
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    from app.modules.outbox.models import OutboxDeliveryAttempt

    async with f.factory() as session:
        operation = await session.get(SubmissionIntakeOperation, operation_id)
        event = await session.get(OutboxEvent, UUID(operation.finalization_event_id))
        charge = await session.get(SubmissionSourceCharge, operation_id)
        assert operation.state == "finalized" and operation.finalized_submission_id is not None
        assert operation.acceptance_receipt == accepted and operation.continuation_generation == 1
        assert event.delivery_state == "acknowledged" and event.attempt_count == 1
        attempts = (await session.scalars(select(OutboxDeliveryAttempt).where(
            OutboxDeliveryAttempt.event_id == event.event_id))).all()
        assert len(attempts) == 1 and attempts[0].stage == "completed"
        assert charge.state == "sealed" and charge.accounted_bytes == operation.raw_byte_count > 0
        for table in ("submissions", "submission_dispatches", "checker_runs"):
            assert await session.scalar(text(
                f"SELECT count(*) FROM {table} WHERE task_id=:task"
            ), {"task": f.task}) == 1
        assert await session.scalar(text(
            "SELECT count(*) FROM artifact_bindings WHERE resource_id=:submission"
        ), {"submission": operation.finalized_submission_id}) == 1
        assert await session.scalar(text(
            "SELECT count(*) FROM outbox_events WHERE project_id=:project "
            "AND event_type='PostSubmissionEvaluationRequested'"
        ), {"project": f.project}) == 1
        assert await session.scalar(text(
            "SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:task"
        ), {"task": f.task}) is None
        return operation.finalized_submission_id


async def _stop_broker_worker(process, completed):
    """Stop only the owned worker group before removing this test's keys."""
    if process.pid is not None:
        if process.is_alive():
            os.killpg(process.pid, signal.SIGTERM)
        await asyncio.to_thread(process.join, 10)
        if process.is_alive():
            os.killpg(process.pid, signal.SIGKILL)
            await asyncio.to_thread(process.join, 5)
        assert not process.is_alive(), "owned finalization worker survived cleanup"
        process.close()
    completed.close()
    completed.join_thread()


async def test_real_broker_recovers_public_acceptance_and_deduplicates_finalization(
    admission_intake, tmp_path, monkeypatch,
):
    """Controlled public PRE, real outage/scanner, Redis and production prefork T5."""
    import queue
    import socket
    import time
    from urllib.parse import urlsplit
    import redis
    from app.core.config import get_settings
    from app.core.identifiers import new_record_id
    from app.workers import outbox as worker
    from app.workers.outbox_topology import FINALIZATION_QUEUE
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.test_trusted_intake import _archive

    f = admission_intake
    broker = urlsplit(os.environ["WORKSTREAM_TEST_BROKER_URL"])
    assert broker.scheme == "redis" and broker.hostname and broker.port
    connection = redis.Redis.from_url(broker.geturl())
    assert connection.ping()
    prefix, hostname = f"finalizer-proof-{new_record_id()}:", f"finalizer-{new_record_id()}@localhost"
    closed_endpoint = socket.socket()
    closed_endpoint.bind(("127.0.0.1", 0))
    port = closed_endpoint.getsockname()[1]
    app = worker.celery_app
    monkeypatch.setattr(app, "_pool", None)
    monkeypatch.setattr(app.amqp, "_producer_pool", None)
    monkeypatch.setitem(app.conf, "broker_url", f"redis://127.0.0.1:{port}/{broker.path.lstrip('/')}")
    monkeypatch.setitem(app.conf, "broker_transport_options", {
        **app.conf.broker_transport_options, "global_keyprefix": prefix,
        "socket_connect_timeout": 0.25, "socket_timeout": 5, "max_retries": 0,
    })
    monkeypatch.setitem(app.conf, "task_publish_retry", False)
    monkeypatch.setitem(app.conf, "task_always_eager", False)
    completed = multiprocessing.get_context("fork").Queue()
    process = multiprocessing.get_context("fork").Process(target=_broker_finalizer, args=(app, hostname, completed))
    proxy, connections = None, set()
    try:
        payload, key = _archive(), new_record_id()
        client, settings, errors, calls = await configure_source_http(
            f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, "completed")
        headers = f.access.target.headers | {
            "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
            "Idempotency-Key": str(key), "Content-Length": str(len(payload)),
        }
        url = f"/api/v1/tasks/{f.task}/submissions"
        accepted = await client.post(url, headers=headers, content=payload)
        assert accepted.status_code == 202, accepted.text
        assert len(calls) == 1 and not errors, errors
        operation_id = UUID(accepted.json()["operation_id"])
        for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
            await provision_post_submit_service(f.factory, identity)
        _broker_settings(settings, monkeypatch)
        before = await _accepted_broker_facts(f, operation_id)
        assert before[0] == "finalization_pending" and before[5:7] == ("pending", 0)
        failed = await asyncio.to_thread(worker.scan_pending.run)
        assert failed == {"selected": 1, "published": 0}
        assert await _accepted_broker_facts(f, operation_id) == before
        assert list(connection.scan_iter(match=prefix + "*")) == []
        closed_endpoint.close()
        proxy = await asyncio.start_server(
            lambda reader, writer: _redis_forwarder(reader, writer, (broker.hostname, broker.port), connections),
            "127.0.0.1", port)
        published = await asyncio.to_thread(worker.scan_pending.run)
        assert published == {"selected": 1, "published": 1}
        for _ in range(2):
            await asyncio.to_thread(worker.finalize_submission.apply_async, args=(str(before[4]), str(f.project)))
        assert connection.llen(prefix + FINALIZATION_QUEUE) == 3
        process.start()
        deadline, observations = time.monotonic() + 120, []
        while len(observations) < 3 and time.monotonic() < deadline:
            assert process.is_alive(), f"finalization worker exited: {process.exitcode}"
            try:
                observations.append(await asyncio.to_thread(completed.get, True, 0.2))
            except queue.Empty:
                pass
        assert len(observations) == 3, observations
        assert len({item[0] for item in observations}) == 3
        assert all(item[1] == "SUCCESS" and item[3] not in {os.getpid(), process.pid}
                   and item[4:] == (False, FINALIZATION_QUEUE) for item in observations), observations
        assert sorted(item[2]["status"] for item in observations) == [
            "delivery_recorded", "delivery_unavailable", "delivery_unavailable"]
        await _assert_broker_finalized_once(f, operation_id, before[1])
        replay = await client.post(url, headers=headers, content=payload)
        assert replay.status_code == 202 and replay.json() == dict(accepted.json(), replayed=True), replay.text
        assert len(calls) == 1 and not errors
        await _assert_broker_finalized_once(f, operation_id, before[1])
    finally:
        closed_endpoint.close()
        await _stop_broker_worker(process, completed)
        for pool in (app.amqp._producer_pool, app._pool):
            if pool is not None:
                pool.force_close_all()
        if proxy is not None:
            proxy.close()
            await proxy.wait_closed()
        for pending in tuple(connections):
            pending.cancel()
        await asyncio.gather(*tuple(connections), return_exceptions=True)
        keys = list(connection.scan_iter(match=prefix + "*"))
        if keys:
            connection.delete(*keys)
        assert list(connection.scan_iter(match=prefix + "*")) == []
        connection.close()
        get_settings.cache_clear()
