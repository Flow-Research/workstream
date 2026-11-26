"""Actual process death retains accepted custody before and after T5 commit."""
import asyncio
from contextlib import asynccontextmanager
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


def _broker_scanner(app, hostname, completed):
    """Run the production scan task with its own real prefork consumer."""
    from celery.signals import task_postrun
    from app.workers.outbox_topology import OUTBOX_DELIVERY_TASK, OUTBOX_SCAN_QUEUE, OUTBOX_SCAN_TASK

    def record(task_id, task, retval, state, **_kwargs):
        if task.name in {OUTBOX_SCAN_TASK, OUTBOX_DELIVERY_TASK}:
            completed.put((task_id, task.name, state, str(retval) if state == "FAILURE" else retval,
                           os.getpid(), task.request.is_eager,
                           task.request.delivery_info["routing_key"]))

    os.setsid()
    task_postrun.connect(record, weak=False)
    app.Worker(pool="prefork", concurrency=1, queues=[OUTBOX_SCAN_QUEUE], hostname=hostname,
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


async def _assert_broker_finalized_once(f, operation_id, accepted, *, attempts=1, generation=1):
    """Require one durable graph after original and duplicate tasks return."""
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    from app.modules.outbox.models import OutboxDeliveryAttempt

    async with f.factory() as session:
        operation = await session.get(SubmissionIntakeOperation, operation_id)
        event = await session.get(OutboxEvent, UUID(operation.finalization_event_id))
        charge = await session.get(SubmissionSourceCharge, operation_id)
        assert operation.state == "finalized" and operation.finalized_submission_id is not None
        assert operation.acceptance_receipt == accepted and operation.continuation_generation == generation
        assert event.delivery_state == "acknowledged" and event.attempt_count == attempts
        rows = (await session.scalars(select(OutboxDeliveryAttempt).where(
            OutboxDeliveryAttempt.event_id == event.event_id))).all()
        assert len(rows) == attempts and all(row.stage == "completed" for row in rows)
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
    if process is not None and process.pid is not None:
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


async def _accept_public_broker_source(case, f, tmp_path, monkeypatch):
    """Use signed HTTP and current owners; only the PRE transport is controlled."""
    from app.core.identifiers import new_record_id
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.test_trusted_intake import _archive

    case.payload = _archive()
    case.client, settings, case.errors, case.calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, case.payload, "completed")
    case.headers = f.access.target.headers | {
        "Content-Type": "application/zip", "X-Task-Assignment-Id": str(f.assignment),
        "Idempotency-Key": str(new_record_id()), "Content-Length": str(len(case.payload)),
    }
    case.url = f"/api/v1/tasks/{f.task}/submissions"
    response = await case.client.post(case.url, headers=case.headers, content=case.payload)
    assert response.status_code == 202, response.text
    assert len(case.calls) == 1 and not case.errors, case.errors
    case.accepted = response.json()
    case.operation_id = UUID(case.accepted["operation_id"])
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    _broker_settings(settings, monkeypatch)
    case.before = await _accepted_broker_facts(f, case.operation_id)
    assert case.before[0] == "finalization_pending" and case.before[5:7] == ("pending", 0)


@asynccontextmanager
async def _public_broker_case(f, tmp_path, monkeypatch, *, kill_at=None):
    """Own one isolated endpoint, worker group and Redis prefix for a public T4."""
    import socket
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    import redis
    from app.core.identifiers import new_record_id
    from app.core.config import get_settings

    broker = urlsplit(os.environ["WORKSTREAM_TEST_BROKER_URL"])
    assert broker.scheme == "redis" and broker.hostname and broker.port
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", broker.geturl())
    get_settings.cache_clear()
    from app.workers import outbox as worker
    case = SimpleNamespace(connection=redis.Redis.from_url(broker.geturl(), socket_timeout=2),
        prefix=f"finalizer-proof-{new_record_id()}:", hostname=f"finalizer-{new_record_id()}@localhost",
        endpoint=socket.socket(), proxy=None, connections=set(), process=None, scan_process=None,
        completed=multiprocessing.get_context("fork").Queue(),
        scan_completed=multiprocessing.get_context("fork").Queue(), app=worker.celery_app,
        destination=(broker.hostname, broker.port), worker=worker,
        marker=tmp_path / "broker-child-kill.json", trace=tmp_path / "broker-delivery.jsonl")
    try:
        assert case.connection.ping()
        case.endpoint.bind(("127.0.0.1", 0))  # No listener: real connection refusal.
        case.port = case.endpoint.getsockname()[1]
        monkeypatch.setattr(case.app, "_pool", None)
        monkeypatch.setattr(case.app.amqp, "_producer_pool", None)
        monkeypatch.setitem(case.app.conf, "broker_url", f"redis://127.0.0.1:{case.port}/{broker.path.lstrip('/')}")
        monkeypatch.setitem(case.app.conf, "broker_transport_options", {
            **case.app.conf.broker_transport_options, "global_keyprefix": case.prefix,
            "socket_connect_timeout": 0.25, "socket_timeout": 5, "max_retries": 0,
        })
        monkeypatch.setitem(case.app.conf, "task_publish_retry", False)
        monkeypatch.setitem(case.app.conf, "task_always_eager", False)
        await _accept_public_broker_source(case, f, tmp_path, monkeypatch)
        target = _broker_finalizer if kill_at is None else _crashing_broker_finalizer
        arguments = (case.app, case.hostname, case.completed)
        if kill_at is not None:
            arguments += (str(case.operation_id), kill_at, case.marker, case.trace)
        case.process = multiprocessing.get_context("fork").Process(target=target, args=arguments)
        yield case
    finally:
        await _close_broker_case(case)


async def _close_broker_case(case):
    """Drain only owned processes, sockets and keys; preserve the shared Redis."""
    from app.core.config import get_settings

    case.endpoint.close()
    await _stop_broker_worker(case.scan_process, case.scan_completed)
    await _stop_broker_worker(case.process, case.completed)
    for pool in (case.app.amqp._producer_pool, case.app._pool):
        if pool is not None:
            pool.force_close_all()
    if case.proxy is not None:
        case.proxy.close()
        await case.proxy.wait_closed()
    for pending in tuple(case.connections):
        pending.cancel()
    await asyncio.gather(*tuple(case.connections), return_exceptions=True)
    keys = list(case.connection.scan_iter(match=case.prefix + "*"))
    if keys:
        case.connection.delete(*keys)
    assert list(case.connection.scan_iter(match=case.prefix + "*")) == []
    case.connection.close()
    get_settings.cache_clear()


async def _restore_broker_endpoint(case):
    """Make the unchanged producer endpoint forward to real Redis again."""
    case.endpoint.close()
    case.proxy = await asyncio.start_server(
        lambda reader, writer: _redis_forwarder(reader, writer, case.destination, case.connections),
        "127.0.0.1", case.port)


async def _next_broker_result(case):
    """Observe a real task return while the proxy event loop remains live."""
    import queue
    import time

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        assert case.process.is_alive(), f"finalization worker exited: {case.process.exitcode}"
        try:
            result = await asyncio.to_thread(case.completed.get, True, 0.2)
        except queue.Empty:
            continue
        from app.workers.outbox_topology import FINALIZATION_QUEUE
        assert result[1] == "SUCCESS" and result[3] not in {os.getpid(), case.process.pid}, result
        assert result[4:] == (False, FINALIZATION_QUEUE), result
        return result
    raise AssertionError("production finalization task did not return")


async def _next_scan_result(case):
    """Observe real scanner completion in a child of its exclusive worker."""
    import queue
    import time
    from app.workers.outbox_topology import OUTBOX_SCAN_QUEUE

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        assert case.scan_process.is_alive(), f"scan worker exited: {case.scan_process.exitcode}"
        try:
            result = await asyncio.to_thread(case.scan_completed.get, True, 0.2)
        except queue.Empty:
            continue
        assert result[1:3] == ("workstream.outbox.scan_pending", "SUCCESS")
        assert result[4] not in {os.getpid(), case.scan_process.pid}
        assert result[5:] == (False, OUTBOX_SCAN_QUEUE)
        return result
    raise AssertionError("dedicated scan worker did not publish finalization")


async def _next_scan_foreign_result(case):
    """Observe a substituted broker delivery rejected before owner I/O."""
    import queue
    import time
    from app.workers.outbox_topology import OUTBOX_SCAN_QUEUE

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        assert case.scan_process.is_alive(), f"scan worker exited: {case.scan_process.exitcode}"
        try:
            result = await asyncio.to_thread(case.scan_completed.get, True, 0.2)
        except queue.Empty:
            continue
        assert result[4] not in {os.getpid(), case.scan_process.pid}
        assert result[5:] == (False, OUTBOX_SCAN_QUEUE)
        return result
    raise AssertionError("foreign task did not reach dedicated scan worker")


async def test_dedicated_scanner_publishes_finalization_without_general_consumer(
    admission_intake, tmp_path, monkeypatch,
):
    """Pending public acceptance reaches T5 through only scan and finalizer queues."""
    from app.core.identifiers import new_record_id
    from app.workers.outbox_topology import OUTBOX_DELIVERY_TASK, OUTBOX_SCAN_QUEUE

    f = admission_intake
    async with _public_broker_case(f, tmp_path, monkeypatch) as case:
        await _restore_broker_endpoint(case)
        case.scan_process = multiprocessing.get_context("fork").Process(
            target=_broker_scanner,
            args=(case.app, f"outbox-scan-{new_record_id()}@localhost", case.scan_completed),
        )
        case.scan_process.start()
        case.process.start()
        await asyncio.to_thread(case.worker.deliver_event.apply_async,
            args=(str(case.before[4]), str(f.project)), queue=OUTBOX_SCAN_QUEUE,
            task_id=str(new_record_id()))
        foreign = await _next_scan_foreign_result(case)
        assert foreign[1:3] == (OUTBOX_DELIVERY_TASK, "FAILURE")
        assert foreign[3] == "dedicated worker rejects a foreign task"
        assert await _accepted_broker_facts(f, case.operation_id) == case.before
        await asyncio.to_thread(case.worker.scan_pending.apply_async,
            task_id=str(new_record_id()))
        scan = await _next_scan_result(case)
        assert scan[3] == {"selected": 1, "published": 1}
        finalization = await _next_broker_result(case)
        assert finalization[2] == {"status": "delivery_recorded"}
        await _assert_broker_finalized_once(f, case.operation_id, case.before[1])
        await _assert_public_broker_replay(case)
        await _assert_broker_finalized_once(f, case.operation_id, case.before[1])


async def _assert_public_broker_replay(case):
    """Exact accepted replay never uploads again or invokes PRE again."""
    response = await case.client.post(case.url, headers=case.headers, content=case.payload)
    assert response.status_code == 202, response.text
    assert response.json() == dict(case.accepted, replayed=True)
    assert len(case.calls) == 1 and not case.errors


async def test_real_broker_recovers_public_acceptance_and_deduplicates_finalization(
    admission_intake, tmp_path, monkeypatch,
):
    """Controlled public PRE, real outage/scanner, Redis and production prefork T5."""
    from app.workers.outbox_topology import FINALIZATION_QUEUE

    f = admission_intake
    async with _public_broker_case(f, tmp_path, monkeypatch) as case:
        failed = await asyncio.to_thread(case.worker._scan_pending, case.worker.scan_pending)
        assert failed == {"selected": 1, "published": 0}
        assert await _accepted_broker_facts(f, case.operation_id) == case.before
        assert list(case.connection.scan_iter(match=case.prefix + "*")) == []
        await _restore_broker_endpoint(case)
        assert await asyncio.to_thread(case.worker._scan_pending, case.worker.scan_pending) == {"selected": 1, "published": 1}
        for _ in range(2):
            await asyncio.to_thread(case.worker.finalize_submission.apply_async,
                args=(str(case.before[4]), str(f.project)))
        assert case.connection.llen(case.prefix + FINALIZATION_QUEUE) == 3
        case.process.start()
        observations = [await _next_broker_result(case) for _ in range(3)]
        assert len({item[0] for item in observations}) == 3
        assert sorted(item[2]["status"] for item in observations) == [
            "delivery_recorded", "delivery_unavailable", "delivery_unavailable"]
        await _assert_broker_finalized_once(f, case.operation_id, case.before[1])
        await _assert_public_broker_replay(case)
        await _assert_broker_finalized_once(f, case.operation_id, case.before[1])


def _record_broker_trace(path, body):
    """Make each observed boundary durable before its process can be killed."""
    import json

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, (json.dumps(body) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _kill_broker_child_once(marker, operation_id, boundary, result=None):
    """Kill the actual child exactly once, never synthesize a finalizer result."""
    import json

    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    try:
        os.write(descriptor, json.dumps({"pid": os.getpid(), "operation_id": operation_id,
            "boundary": boundary, "submission_id": str(result.submission_id) if result else None}).encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.kill(os.getpid(), signal.SIGKILL)
    raise AssertionError("SIGKILL unexpectedly returned")


def _crashing_broker_finalizer(app, hostname, completed, operation_id, kill_at, marker, trace):
    """Install observation-only hooks around real production T5 and broker delivery."""
    from celery.signals import task_prerun
    from app.adapters.artifacts import _WorkerSourceObservation
    from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
    from app.workers.outbox_topology import FINALIZATION_DELIVERY_TASK

    original_observe = _WorkerSourceObservation.observe_sealed_source
    original_run = AcceptedSubmissionFinalization.run

    async def observe(store, source):
        if str(source.location.operation_id) == operation_id:
            if kill_at == "before_observation":
                _kill_broker_child_once(marker, operation_id, kill_at)
            _record_broker_trace(trace, {"kind": "source_observation", "pid": os.getpid()})
        return await original_observe(store, source)

    async def run(finalizer, actual_id):
        result = await original_run(finalizer, actual_id)
        if str(actual_id) == operation_id and kill_at == "after_commit":
            _kill_broker_child_once(marker, operation_id, kill_at, result)
        return result

    def record(task_id, task, args, **_kwargs):
        if task.name == FINALIZATION_DELIVERY_TASK:
            _record_broker_trace(trace, {"kind": "delivery", "task_id": task_id,
                "event_id": args[0], "pid": os.getpid(),
                "redelivered": bool(task.request.delivery_info.get("redelivered"))})

    _WorkerSourceObservation.observe_sealed_source = observe
    AcceptedSubmissionFinalization.run = run
    task_prerun.connect(record, weak=False)
    _broker_finalizer(app, hostname, completed)


async def _assert_broker_redelivery(case, f, kill_at, result):
    """Require broker requeue of the same message while the owner lease stays live."""
    import json

    marker = json.loads(case.marker.read_text())
    deliveries = [json.loads(line) for line in case.trace.read_text().splitlines()
                  if json.loads(line)["kind"] == "delivery"]
    assert marker["operation_id"] == str(case.operation_id) and marker["boundary"] == kill_at
    assert len(deliveries) == 2 and deliveries[0]["task_id"] == deliveries[1]["task_id"] == result[0]
    assert [item["redelivered"] for item in deliveries] == [False, True]
    assert all(item["event_id"] == str(case.before[4]) for item in deliveries)
    assert deliveries[0]["pid"] == marker["pid"] and deliveries[1]["pid"] == result[3] != marker["pid"]
    with pytest.raises(ProcessLookupError):
        os.kill(marker["pid"], 0)
    assert result[2] == {"status": "delivery_unavailable"}
    async with f.factory() as session:
        operation = await session.get(SubmissionIntakeOperation, case.operation_id)
        event = await session.get(OutboxEvent, case.before[4])
        now = await session.scalar(select(func.clock_timestamp()))
        assert event.delivery_state == "claimed" and event.attempt_count == 1
        assert now < event.claim_expires_at
        assert (event.claim_expires_at - event.claimed_at).total_seconds() == 300
        assert operation.continuation_generation == 1
        assert operation.state == ("finalized" if kill_at == "after_commit" else "finalization_pending")
        assert operation.acceptance_receipt == case.before[1]
        assert operation.finalized_submission_id == marker["submission_id"]
        return max(event.claim_expires_at, operation.continuation_expires_at), marker["submission_id"]


async def _wait_for_broker_database_time(factory, target):
    """Wait through the unchanged production lease/backoff on PostgreSQL time."""
    async with asyncio.timeout(360):
        while True:
            async with factory() as session:
                now = await session.scalar(select(func.clock_timestamp()))
            if now >= target:
                return
            await asyncio.sleep(min(1, (target - now).total_seconds()))


async def _assert_broker_recovered_unknown(case, f):
    """The real worker records uncertainty before any new handler claim."""
    import json
    from datetime import datetime
    from app.modules.outbox.models import OutboxDeliveryAttempt

    async with f.factory() as session:
        event = await session.get(OutboxEvent, case.before[4])
        attempts = (await session.scalars(select(OutboxDeliveryAttempt).where(
            OutboxDeliveryAttempt.event_id == event.event_id))).all()
        assert event.delivery_state == "retryable" and event.attempt_count == 1
        assert len(attempts) == 1 and attempts[0].stage == "completed"
        outcome = json.loads(attempts[0].outcome_json)
        assert outcome["invocation_unknown"] is True and outcome["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        assert (event.next_attempt_at - datetime.fromisoformat(outcome["receipt_completed_at"])).total_seconds() == 5
        return event.next_attempt_at


@pytest.mark.parametrize("kill_at", ["before_observation", "after_commit"])
async def test_real_broker_redelivers_killed_finalizer_and_recovers_owner_lease(
    admission_intake, tmp_path, monkeypatch, kill_at,
):
    """Actual Redis redelivery plus expired-invocation recovery preserves one T5."""
    import json

    f = admission_intake
    async with _public_broker_case(f, tmp_path, monkeypatch, kill_at=kill_at) as case:
        await _restore_broker_endpoint(case)
        assert await asyncio.to_thread(case.worker._scan_pending, case.worker.scan_pending) == {"selected": 1, "published": 1}
        case.process.start()
        redelivery = await _next_broker_result(case)
        due, original_submission = await _assert_broker_redelivery(case, f, kill_at, redelivery)
        await _wait_for_broker_database_time(f.factory, due)
        assert await asyncio.to_thread(case.worker._scan_pending, case.worker.scan_pending) == {"selected": 1, "published": 1}
        recovered = await _next_broker_result(case)
        assert recovered[2] == {"status": "delivery_recorded"}
        due = await _assert_broker_recovered_unknown(case, f)
        await _wait_for_broker_database_time(f.factory, due)
        assert await asyncio.to_thread(case.worker._scan_pending, case.worker.scan_pending) == {"selected": 1, "published": 1}
        finalized = await _next_broker_result(case)
        assert finalized[2] == {"status": "delivery_recorded"}
        submission = await _assert_broker_finalized_once(f, case.operation_id, case.before[1],
            attempts=2, generation=1 if kill_at == "after_commit" else 2)
        if original_submission is not None:
            assert submission == original_submission
        trace = [json.loads(line) for line in case.trace.read_text().splitlines()]
        deliveries = [item for item in trace if item["kind"] == "delivery"]
        assert len(deliveries) == 4 and len({item["task_id"] for item in deliveries}) == 3
        assert [item["redelivered"] for item in deliveries] == [False, True, False, False]
        assert len([item for item in trace if item["kind"] == "source_observation"]) == 1
        await _assert_public_broker_replay(case)
        assert await _assert_broker_finalized_once(f, case.operation_id, case.before[1],
            attempts=2, generation=1 if kill_at == "after_commit" else 2) == submission
