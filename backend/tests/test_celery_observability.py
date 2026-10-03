"""Prefork and signal-boundary proof for Celery diagnostics."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import multiprocessing
import os
from pathlib import Path
import queue as queue_module
import signal
import time
from types import SimpleNamespace
from uuid import uuid4

from celery import signals
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest
import redis

from app.core import celery_observability as diagnostics
from app.core import diagnostic_logging
from app.core.celery_observability import (
    CORRELATION_ID_BROKER_HEADER,
    REQUEST_ID_BROKER_HEADER,
    configure_celery_observability,
)
from app.core.config import Settings
from app.core.api_controls import RequestContextMiddleware
from app.core.observability import ObservabilityMiddleware, ObservabilityRuntime

PAGINATION_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
KNOWN_TASK = "workstream.test.known"


def _settings() -> Settings:
    return Settings(
        environment="test",
        pagination_cursor_hmac_secret=PAGINATION_SECRET,
        observability_trace_sample_ratio=1.0,
    )


def _runtime() -> tuple[ObservabilityRuntime, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    runtime = ObservabilityRuntime(
        _settings(),
        service_name="workstream-celery",
        task_names=frozenset({KNOWN_TASK}),
        span_exporter=exporter,
        metric_reader=InMemoryMetricReader(),
    )
    runtime.start()
    return runtime, exporter


class _Task:
    def __init__(
        self,
        task_id: str,
        headers: dict[str, str] | None,
        *,
        name: str = KNOWN_TASK,
    ) -> None:
        self.name = name
        self.request = SimpleNamespace(id=task_id, headers=headers)


def _send_task(task_id: str, headers: dict[str, str] | None, state: str) -> None:
    task = _Task(task_id, headers)
    signals.task_prerun.send(sender=None, task_id=task_id, task=task)
    if state == "RETRY":
        signals.task_retry.send(sender=None, request=task.request, reason=RuntimeError("secret"))
    elif state == "FAILURE":
        signals.task_failure.send(sender=None, task_id=task_id, exception=RuntimeError("secret"))
    signals.task_postrun.send(sender=None, task_id=task_id, task=task, state=state)


def test_repeated_celery_receiver_setup_does_not_duplicate_spans_or_readers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, exporter = _runtime()
    monkeypatch.setattr(diagnostics, "_WORKER_RUNTIME", runtime)
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    task_id = str(uuid4())
    try:
        _send_task(task_id, None, "SUCCESS")
        assert runtime.force_flush()
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == f"celery {KNOWN_TASK}"
        assert spans[0].attributes["workstream.request_id"] == task_id
    finally:
        diagnostics._ACTIVE_TASKS.clear()
        runtime.shutdown()


def test_sequential_task_failures_and_retries_reset_every_context_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, exporter = _runtime()
    monkeypatch.setattr(diagnostics, "_WORKER_RUNTIME", runtime)
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    first_task_id, second_task_id, third_task_id = (str(uuid4()) for _ in range(3))
    first_request, first_correlation = str(uuid4()), str(uuid4())

    class Hostile(Exception):
        rendered = False

        def __str__(self) -> str:
            self.rendered = True
            raise AssertionError("exception rendered")

    hostile = Hostile()
    try:
        first = _Task(
            first_task_id,
            {
                REQUEST_ID_BROKER_HEADER: first_request,
                CORRELATION_ID_BROKER_HEADER: first_correlation,
            },
        )
        signals.task_prerun.send(sender=None, task_id=first_task_id, task=first)
        signals.task_failure.send(sender=None, task_id=first_task_id, exception=hostile)
        signals.task_postrun.send(sender=None, task_id=first_task_id, task=first, state="FAILURE")
        _send_task(
            second_task_id,
            {
                REQUEST_ID_BROKER_HEADER: "malformed",
                CORRELATION_ID_BROKER_HEADER: "malformed",
                "traceparent": "malformed",
            },
            "SUCCESS",
        )
        _send_task(third_task_id, None, "RETRY")
        assert runtime.force_flush()
        spans = exporter.get_finished_spans()
        assert len(spans) == 3
        assert spans[0].attributes["workstream.request_id"] == first_request
        assert spans[0].attributes["workstream.correlation_id"] == first_correlation
        assert spans[1].attributes["workstream.request_id"] == second_task_id
        assert spans[1].attributes["workstream.correlation_id"] == second_task_id
        assert spans[2].attributes["workstream.request_id"] == third_task_id
        assert spans[2].attributes["workstream.outcome"] == "retry"
        assert len({span.context.trace_id for span in spans}) == 3
        assert hostile.rendered is False
        assert diagnostic_logging.current_diagnostic_ids() == (None, None)
        assert diagnostics._ACTIVE_TASKS == {}
    finally:
        diagnostics._ACTIVE_TASKS.clear()
        runtime.shutdown()


def test_unknown_task_and_state_values_collapse_to_one_exact_metric_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    runtime = ObservabilityRuntime(
        _settings(),
        service_name="workstream-celery",
        task_names=frozenset({KNOWN_TASK}),
        span_exporter=exporter,
        metric_reader=reader,
    )
    runtime.start()
    monkeypatch.setattr(diagnostics, "_WORKER_RUNTIME", runtime)
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    identifiers = [(str(uuid4()), str(uuid4()), str(uuid4())) for _ in range(24)]
    try:
        for index, (task_id, request_id, correlation_id) in enumerate(identifiers):
            task = _Task(
                task_id,
                {
                    REQUEST_ID_BROKER_HEADER: request_id,
                    CORRELATION_ID_BROKER_HEADER: correlation_id,
                },
                name=f"unregistered.private.{index}",
            )
            signals.task_prerun.send(sender=None, task_id=task_id, task=task)
            signals.task_postrun.send(
                sender=None,
                task_id=task_id,
                task=task,
                state=f"PRIVATE_STATE_{index}",
            )

        assert runtime.force_flush()
        spans = exporter.get_finished_spans()
        assert len(spans) == len(identifiers)
        for span, (_, request_id, correlation_id) in zip(spans, identifiers, strict=True):
            assert span.name == "celery other"
            assert dict(span.attributes) == {
                "messaging.destination.name": "other",
                "workstream.outcome": "other",
                "workstream.request_id": request_id,
                "workstream.correlation_id": correlation_id,
            }

        metric_data = reader.get_metrics_data()
        assert metric_data is not None
        points = [
            (metric.name, dict(point.attributes))
            for resource_metrics in metric_data.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
            for point in metric.data.data_points
        ]
        assert points == [
            (
                "workstream.celery.task.duration",
                {
                    "messaging.destination.name": "other",
                    "workstream.outcome": "other",
                },
            )
        ]
        assert diagnostics._ACTIVE_TASKS == {}
        assert diagnostic_logging.current_diagnostic_ids() == (None, None)
    finally:
        diagnostics._ACTIVE_TASKS.clear()
        runtime.shutdown()


def _prefork_context_probe(queue: multiprocessing.Queue) -> None:
    """Create providers in the forked child and return two sequential span contexts."""
    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    runtime = ObservabilityRuntime(
        _settings(),
        service_name="workstream-celery",
        task_names=frozenset({KNOWN_TASK}),
        span_exporter=exporter,
        metric_reader=reader,
    )
    original_runtime_type = diagnostics.ObservabilityRuntime
    diagnostics.ObservabilityRuntime = lambda *_args, **_kwargs: runtime
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    diagnostics.initialize_worker_observability()
    try:
        first_id, second_id = str(uuid4()), str(uuid4())
        request_id, correlation_id = str(uuid4()), str(uuid4())
        _send_task(
            first_id,
            {
                REQUEST_ID_BROKER_HEADER: request_id,
                CORRELATION_ID_BROKER_HEADER: correlation_id,
            },
            "FAILURE",
        )
        _send_task(
            second_id,
            {
                REQUEST_ID_BROKER_HEADER: "bad",
                CORRELATION_ID_BROKER_HEADER: "bad",
            },
            "SUCCESS",
        )
        runtime.force_flush()
        spans = exporter.get_finished_spans()
        queue.put(
            {
                "pid": multiprocessing.current_process().pid,
                "ids": [
                    (
                        span.attributes["workstream.request_id"],
                        span.attributes["workstream.correlation_id"],
                    )
                    for span in spans
                ],
                "trace_ids": [span.context.trace_id for span in spans],
                "second_task_id": second_id,
                "clean": diagnostic_logging.current_diagnostic_ids() == (None, None),
            }
        )
    finally:
        diagnostics.shutdown_worker_observability()
        diagnostics.ObservabilityRuntime = original_runtime_type


def test_forked_child_signal_probe_resets_second_task_context() -> None:
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    diagnostics._WORKER_RUNTIME = None
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    process = context.Process(target=_prefork_context_probe, args=(queue,))
    process.start()
    process.join(timeout=10)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)
    assert process.exitcode == 0
    result = queue.get(timeout=1)
    assert result["pid"] != multiprocessing.current_process().pid
    assert result["ids"][1] == (result["second_task_id"], result["second_task_id"])
    assert result["trace_ids"][0] != result["trace_ids"][1]
    assert result["clean"] is True
    assert diagnostics._WORKER_RUNTIME is None


class _QueueSpanExporter(SpanExporter):
    def __init__(self, queue: multiprocessing.Queue) -> None:
        self.queue = queue

    def export(self, spans) -> SpanExportResult:
        for span in spans:
            self.queue.put(
                {
                    "kind": "span",
                    "pid": os.getpid(),
                    "name": span.name,
                    "trace_id": span.context.trace_id,
                    "span_id": span.context.span_id,
                    "parent_span_id": None if span.parent is None else span.parent.span_id,
                    "attributes": dict(span.attributes),
                    "events": len(span.events),
                }
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def _real_worker(app, hostname: str, log_path: str) -> None:
    os.setsid()
    descriptor = os.open(log_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    os.dup2(descriptor, 2)
    os.close(descriptor)
    app.Worker(
        pool="prefork",
        concurrency=1,
        queues=["celery"],
        hostname=hostname,
        loglevel="INFO",
        without_gossip=True,
        without_mingle=True,
        without_heartbeat=True,
    ).start()


@pytest.mark.skipif(
    "WORKSTREAM_TEST_BROKER_URL" not in os.environ,
    reason="real prefork proof requires the repository Redis test service",
)
async def test_real_celery_prefork_correlates_api_and_resets_sequential_task_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exercise actual Redis publication, worker parent, and one prefork child."""
    from app.core.config import get_settings

    broker = os.environ["WORKSTREAM_TEST_BROKER_URL"]
    connection = redis.Redis.from_url(broker)
    assert connection.ping()
    prefix = f"workstream-observability-{uuid4()}:"
    observations = multiprocessing.get_context("fork").Queue()
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", broker)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "false")
    monkeypatch.setenv("WORKSTREAM_ARTIFACT_STORE_BACKEND", "disabled")
    get_settings.cache_clear()
    from app.workers.celery_app import celery_app

    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))

    def runtime_factory(settings, *, service_name, task_names):
        reader = InMemoryMetricReader()
        runtime = ObservabilityRuntime(
            settings,
            service_name=service_name,
            task_names=task_names,
            span_exporter=_QueueSpanExporter(observations),
            metric_reader=reader,
        )
        runtime.probe_reader = reader
        return runtime

    monkeypatch.setattr(diagnostics, "ObservabilityRuntime", runtime_factory)
    assert diagnostics._WORKER_RUNTIME is None

    @celery_app.task(bind=True, name=KNOWN_TASK)
    def probe_task(self, mode: str):
        if mode == "failure":
            raise RuntimeError("credential=worker-failure-secret")
        if mode == "retry" and self.request.retries == 0:
            raise self.retry(
                exc=RuntimeError("credential=worker-retry-secret"),
                countdown=0,
                max_retries=1,
            )
        return {"status": "ok"}

    def capture_after_task(task_id=None, state=None, **_kwargs):
        runtime = diagnostics._WORKER_RUNTIME
        assert runtime is not None
        runtime.force_flush()
        points: list[tuple[str, dict[str, object]]] = []
        data = runtime.probe_reader.get_metrics_data()
        if data is not None:
            for resource_metrics in data.resource_metrics:
                for scope_metrics in resource_metrics.scope_metrics:
                    for metric in scope_metrics.metrics:
                        for point in metric.data.data_points:
                            points.append((metric.name, dict(point.attributes)))
        observations.put(
            {
                "kind": "task_exit",
                "pid": os.getpid(),
                "task_id": task_id,
                "state": state,
                "clean": diagnostic_logging.current_diagnostic_ids() == (None, None),
                "active": len(diagnostics._ACTIVE_TASKS),
                "metrics": points,
            }
        )

    signals.task_postrun.connect(
        capture_after_task,
        weak=False,
        dispatch_uid="workstream-observability-real-prefork-probe",
    )
    celery_app.conf.update(
        broker_url=broker,
        broker_transport_options={"global_keyprefix": prefix},
        task_always_eager=False,
    )
    hostname = f"observability-proof-{uuid4()}@localhost"
    log_path = tmp_path / "worker.log"
    process = multiprocessing.get_context("fork").Process(
        target=_real_worker,
        args=(celery_app, hostname, str(log_path)),
    )
    process.start()
    assert diagnostics._WORKER_RUNTIME is None
    api_runtime: ObservabilityRuntime | None = None
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert process.is_alive(), f"worker startup failed: {process.exitcode}"
            if celery_app.control.ping(destination=[hostname], timeout=0.2):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("real prefork worker did not become ready")

        api_exporter = InMemorySpanExporter()
        api_runtime = ObservabilityRuntime(
            _settings(),
            service_name="workstream-api",
            route_templates=frozenset({"/dispatch"}),
            span_exporter=api_exporter,
            metric_reader=InMemoryMetricReader(),
        )
        api_runtime.start()
        app = FastAPI()
        direct_task_id = str(uuid4())

        @app.post("/dispatch")
        async def dispatch() -> dict[str, str]:
            probe_task.apply_async(kwargs={"mode": "success"}, task_id=direct_task_id)
            return {"task_id": direct_task_id}

        app.add_middleware(RequestContextMiddleware)
        app.add_middleware(ObservabilityMiddleware, runtime=api_runtime)
        request_id, correlation_id = str(uuid4()), str(uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/dispatch",
                headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
            )
        assert response.status_code == 200
        api_runtime.force_flush()
        [server_span] = api_exporter.get_finished_spans()

        failure_task_id, retry_task_id = str(uuid4()), str(uuid4())
        probe_task.apply_async(
            kwargs={"mode": "failure"},
            task_id=failure_task_id,
            headers={
                REQUEST_ID_BROKER_HEADER: "malformed",
                CORRELATION_ID_BROKER_HEADER: "malformed",
                "traceparent": "malformed",
                "tracestate": "secret=state",
                "baggage": "secret=value",
            },
        )
        probe_task.apply_async(kwargs={"mode": "retry"}, task_id=retry_task_id)

        messages: list[dict] = []
        while time.monotonic() < deadline:
            try:
                messages.append(observations.get(timeout=0.5))
            except queue_module.Empty:
                pass
            if (
                len([item for item in messages if item["kind"] == "span"]) >= 4
                and len([item for item in messages if item["kind"] == "task_exit"]) >= 4
            ):
                break
        spans = [item for item in messages if item["kind"] == "span"]
        exits = [item for item in messages if item["kind"] == "task_exit"]
        assert len(spans) == 4
        assert len(exits) == 4
        assert len({item["pid"] for item in spans + exits}) == 1
        assert spans[0]["pid"] != process.pid and spans[0]["pid"] != os.getpid()
        assert all(item["clean"] and item["active"] == 0 for item in exits)
        assert all(item["events"] == 0 for item in spans)
        assert all("host.name" not in item["attributes"] for item in spans)
        direct = next(
            item for item in spans if item["attributes"]["workstream.request_id"] == request_id
        )
        assert direct["trace_id"] == server_span.context.trace_id
        assert direct["parent_span_id"] == server_span.context.span_id
        failure = next(
            item for item in spans if item["attributes"]["workstream.request_id"] == failure_task_id
        )
        assert failure["attributes"]["workstream.correlation_id"] == failure_task_id
        retry_spans = [
            item for item in spans if item["attributes"]["workstream.request_id"] == retry_task_id
        ]
        assert {item["attributes"]["workstream.outcome"] for item in retry_spans} == {
            "retry",
            "success",
        }
        final_metrics = exits[-1]["metrics"]
        task_metrics = [
            item for item in final_metrics if item[0] == "workstream.celery.task.duration"
        ]
        assert task_metrics
        assert all(
            set(attributes) == {"messaging.destination.name", "workstream.outcome"}
            and attributes["messaging.destination.name"] == KNOWN_TASK
            for _, attributes in task_metrics
        )
    finally:
        if api_runtime is not None:
            api_runtime.shutdown()
        signals.task_postrun.disconnect(dispatch_uid="workstream-observability-real-prefork-probe")
        if process.is_alive():
            os.killpg(process.pid, signal.SIGTERM)
        process.join(timeout=10)
        if process.is_alive():
            os.killpg(process.pid, signal.SIGKILL)
            process.join(timeout=5)
        keys = list(connection.scan_iter(match=prefix + "*"))
        if keys:
            connection.delete(*keys)
        connection.close()
        get_settings.cache_clear()
    assert not process.is_alive()
    assert diagnostics._WORKER_RUNTIME is None
    worker_logs = log_path.read_text(encoding="utf-8")
    assert "worker-failure-secret" not in worker_logs
    assert "worker-retry-secret" not in worker_logs


def test_celery_parent_logging_is_safe_without_parent_exporters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics.shutdown_celery_parent_observability()
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    signals.setup_logging.send(sender=None)
    assert diagnostics._WORKER_RUNTIME is None
    handler = diagnostic_logging.safe_handler()
    assert handler is not None
    stream = io.StringIO()
    monkeypatch.setattr(handler, "stream", stream)
    try:
        logging.getLogger("celery.retry").error(
            "retry failed for https://user:secret@broker.invalid/token"
        )
        record = json.loads(stream.getvalue())
        assert record["event"] == "celery.error"
        assert record["service"] == "workstream-celery"
        assert "broker.invalid" not in stream.getvalue()
    finally:
        diagnostics.shutdown_celery_parent_observability()
