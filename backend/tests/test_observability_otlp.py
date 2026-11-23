"""Real OTLP HTTP/protobuf boundary proof for Workstream diagnostics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import io
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
from threading import Event, Lock, Thread
import time
from time import monotonic
from uuid import uuid4

from celery import Celery, current_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link, SpanContext, TraceFlags, TraceState
import pytest

from app.adapters import observability as otlp_adapter
from app.adapters.observability import create_observability_export_adapter
from app.core import diagnostic_logging
from app.core import celery_observability as celery_diagnostics
from app.core.api_controls import RequestContextMiddleware
from app.core.celery_observability import configure_celery_observability
from app.core.config import Settings
from app.core.observability import ObservabilityMiddleware, ObservabilityRuntime
from workstream_external_services import ExternalServiceConfigurationError
from app.interfaces.observability import OTLP_HTTP_PROVIDER_KEY
from observability_test_support import fake_export_adapter


PAGINATION_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
HOSTILE_EVENT_CANARY = "private-span-event-canary"
HOSTILE_LINK_CANARY = "private-span-link-canary"


class _Receiver(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *, status: int = 200, delay_seconds: float = 0.0) -> None:
        super().__init__(("127.0.0.1", 0), _ReceiverHandler)
        self.status = status
        self.delay_seconds = delay_seconds
        self.requests: list[tuple[str, bytes]] = []
        self.requests_lock = Lock()


class _ReceiverHandler(BaseHTTPRequestHandler):
    server: _Receiver

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP hook
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        with self.server.requests_lock:
            self.server.requests.append((self.path, body))
        if self.server.delay_seconds:
            time.sleep(self.server.delay_seconds)
        try:
            self.send_response(self.server.status)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, _format: str, *_args: object) -> None:
        return None


@contextmanager
def _receiver(*, status: int = 200, delay_seconds: float = 0.0) -> Iterator[_Receiver]:
    receiver = _Receiver(status=status, delay_seconds=delay_seconds)
    thread = Thread(target=receiver.serve_forever, name="otlp-test-receiver", daemon=True)
    thread.start()
    try:
        yield receiver
    finally:
        receiver.shutdown()
        receiver.server_close()
        thread.join(timeout=2)


def _settings(endpoint: str, **values: object) -> Settings:
    configured: dict[str, object] = {
        "app_version": "private-release-canary",
        "environment": "test",
        "pagination_cursor_hmac_secret": PAGINATION_SECRET,
        "observability_otlp_endpoint": endpoint,
        "observability_trace_sample_ratio": 1.0,
        "observability_export_timeout_seconds": 0.1,
        "observability_shutdown_timeout_seconds": 0.2,
    }
    configured.update(values)
    return Settings(**configured)


def _safe_logging_released() -> bool:
    deadline = monotonic() + 0.5
    while monotonic() < deadline:
        if diagnostic_logging.safe_handler() is None:
            return True
        time.sleep(0.01)
    return diagnostic_logging.safe_handler() is None


def _runtime(settings: Settings) -> ObservabilityRuntime:
    runtime = ObservabilityRuntime(
        settings,
        service_name="workstream-api",
        route_templates=frozenset({"/probe"}),
        export_adapter=create_observability_export_adapter(
            settings, service_name="workstream-api"
        ),
    )
    runtime.start()
    return runtime


def _app(runtime: ObservabilityRuntime) -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ObservabilityMiddleware, runtime=runtime)
    return app


async def _request(runtime: ObservabilityRuntime) -> int:
    async with AsyncClient(
        transport=ASGITransport(app=_app(runtime)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/probe?token=query-privacy-canary",
            headers={
                "X-Request-ID": str(uuid4()),
                "X-Correlation-ID": str(uuid4()),
            },
        )
    return response.status_code


def _emit_hostile_span_content(runtime: ObservabilityRuntime) -> None:
    link = Link(
        SpanContext(
            trace_id=int("a" * 32, 16),
            span_id=int("b" * 16, 16),
            is_remote=True,
            trace_flags=TraceFlags.SAMPLED,
            trace_state=TraceState((("vendor", HOSTILE_LINK_CANARY),)),
        ),
        {"private.link.attribute": HOSTILE_LINK_CANARY},
    )
    with runtime.tracer.start_as_current_span(
        "hostile-span-input",
        links=(link,),
    ) as span:
        span.add_event(
            HOSTILE_EVENT_CANARY,
            {"private.event.attribute": HOSTILE_EVENT_CANARY},
        )


def _assert_serialized_span_content_is_closed(
    request: ExportTraceServiceRequest,
) -> None:
    spans = [
        span
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
    ]
    assert spans
    assert all(not span.events for span in spans), "serialized span events retained"
    assert all(not span.links for span in spans), "serialized span links retained"
    payload = request.SerializeToString()
    assert HOSTILE_EVENT_CANARY.encode() not in payload
    assert HOSTILE_LINK_CANARY.encode() not in payload


def _run_registered_eager_task_against_collector_failure(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Exercise one registered local/eager task; real prefork is proved separately."""
    task_name = "workstream.test.otlp_failure"
    prior_current_app = current_app._get_current_object()
    task_app = Celery(
        "workstream-observability-otlp-failure",
        set_as_current=False,
    )
    task_app.conf.task_always_eager = True
    invocations: list[str] = []
    canary = "eager-task-private-canary"

    @task_app.task(name=task_name, shared=False)
    def task() -> dict[str, str]:
        invocations.append("invoked")
        logging.getLogger("celery.task").error("task failure detail: %s", canary)
        return {"status": "ok"}

    configure_celery_observability(
        settings,
        frozenset({task_name}),
        lambda: create_observability_export_adapter(
            settings, service_name="workstream-celery"
        ),
    )
    celery_diagnostics.initialize_worker_observability()
    runtime = celery_diagnostics._WORKER_RUNTIME
    assert runtime is not None and runtime.started
    handler = diagnostic_logging.safe_handler()
    assert handler is not None
    stream = io.StringIO()
    monkeypatch.setattr(handler, "stream", stream)
    try:
        task_id = str(uuid4())
        result = task.apply(task_id=task_id, throw=True).get()
        assert result == {"status": "ok"}
        assert invocations == ["invoked"]
        assert celery_diagnostics._ACTIVE_TASKS == {}
        runtime.force_flush()
    finally:
        celery_diagnostics.shutdown_worker_observability()
        task_app.tasks.pop(task_name, None)
        task_app.close()
    assert current_app._get_current_object() is prior_current_app
    encoded = stream.getvalue()
    assert canary not in encoded
    return encoded


def _resource_attributes(resource: object) -> dict[str, object]:
    attributes = getattr(resource, "attributes")
    return {item.key: getattr(item.value, item.value.WhichOneof("value")) for item in attributes}


async def test_serialized_otlp_payload_has_exact_resource_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canaries = (
        "private-release-canary",
        "environment-service-canary",
        "environment-resource-canary",
        "query-privacy-canary",
    )
    monkeypatch.setenv("OTEL_SERVICE_NAME", canaries[1])
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        f"service.version={canaries[2]},private.attribute={canaries[2]}",
    )
    with _receiver() as receiver:
        endpoint = f"http://127.0.0.1:{receiver.server_port}"
        runtime = _runtime(_settings(endpoint))
        try:
            _emit_hostile_span_content(runtime)
            assert await _request(runtime) == 200
            assert runtime.force_flush()
        finally:
            runtime.shutdown()

        with receiver.requests_lock:
            requests = tuple(receiver.requests)

    paths = {path for path, _ in requests}
    assert paths == {"/v1/traces", "/v1/metrics"}
    trace_request = ExportTraceServiceRequest()
    metric_request = ExportMetricsServiceRequest()
    trace_request.ParseFromString(next(body for path, body in requests if path == "/v1/traces"))
    metric_request.ParseFromString(
        next(body for path, body in requests if path == "/v1/metrics")
    )
    expected = {
        "service.name": "workstream-api",
        "deployment.environment.name": "test",
    }
    assert trace_request.resource_spans
    _assert_serialized_span_content_is_closed(trace_request)
    assert metric_request.resource_metrics
    assert {
        tuple(sorted(_resource_attributes(item.resource).items()))
        for item in trace_request.resource_spans
    } == {tuple(sorted(expected.items()))}
    assert {
        tuple(sorted(_resource_attributes(item.resource).items()))
        for item in metric_request.resource_metrics
    } == {tuple(sorted(expected.items()))}
    payload = b"".join(body for _, body in requests)
    for canary in canaries:
        assert canary.encode() not in payload
    assert b"service.version" not in payload


@pytest.mark.parametrize("failure_mode", ["status", "refusal", "timeout"])
async def test_real_otlp_http_transport_is_sanitized_and_fail_open(
    failure_mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if failure_mode == "refusal":
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        endpoint = f"http://127.0.0.1:{port}"
        receiver_context = None
    else:
        receiver_context = _receiver(
            status=503 if failure_mode == "status" else 200,
            delay_seconds=0.5 if failure_mode == "timeout" else 0.0,
        )

    async def exercise(endpoint: str) -> None:
        settings = _settings(endpoint)
        runtime = _runtime(settings)
        handler = diagnostic_logging.safe_handler()
        assert handler is not None
        stream = io.StringIO()
        monkeypatch.setattr(handler, "stream", stream)
        started = monotonic()
        try:
            assert await _request(runtime) == 200
            runtime.force_flush()
        finally:
            runtime.shutdown()
        assert _safe_logging_released()
        task_encoded = _run_registered_eager_task_against_collector_failure(
            settings, monkeypatch
        )
        assert monotonic() - started < 2.0
        encoded = stream.getvalue() + task_encoded
        assert endpoint not in encoded
        assert "query-privacy-canary" not in encoded
        records = [json.loads(line) for line in encoded.splitlines()]
        events = {record["event"] for record in records}
        assert events <= {
            "celery.error",
            "celery.info",
            "external.info",
            "opentelemetry.error",
            "observability_export_unavailable",
        }, events
        assert {"celery.error", "celery.info", "opentelemetry.error"} <= events

    if receiver_context is None:
        await exercise(endpoint)
    else:
        with receiver_context as receiver:
            port = receiver.server_port
            await exercise(f"http://127.0.0.1:{port}")


class _BlockingSpanExporter:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.finished = Event()
        self.log_after_release: str | None = None

    def shutdown(self) -> None:
        self.entered.set()
        self.release.wait(5)
        if self.log_after_release is not None:
            logging.getLogger("opentelemetry.exporter.otlp").error(
                "exporter cleanup failed: %s", self.log_after_release
            )
        self.finished.set()


class _RaisingMetricExporter:
    def __init__(self, **_kwargs: object) -> None:
        self.closed = Event()

    def shutdown(self, **_kwargs: object) -> None:
        self.closed.set()
        raise RuntimeError("metric-shutdown-private")


def test_partial_export_bundle_construction_closes_owned_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = _BlockingSpanExporter()
    metric = _RaisingMetricExporter()
    monkeypatch.setattr(otlp_adapter, "OTLPSpanExporter", lambda **_kwargs: span)
    monkeypatch.setattr(otlp_adapter, "OTLPMetricExporter", lambda **_kwargs: metric)
    monkeypatch.setattr(
        otlp_adapter,
        "PeriodicExportingMetricReader",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("reader-construction-private")
        ),
    )
    adapter = create_observability_export_adapter(
        _settings(
            "http://127.0.0.1:4318",
            observability_shutdown_timeout_seconds=0.1,
        ),
        service_name="workstream-api",
    )
    assert adapter is not None
    started = monotonic()
    try:
        with pytest.raises(ExternalServiceConfigurationError) as caught:
            adapter.create_exporters()
        assert monotonic() - started < 0.5
        assert caught.value.identity is not None
        assert caught.value.identity.provider_key == OTLP_HTTP_PROVIDER_KEY
        assert "4318" not in f"{caught.value!s} {caught.value!r}"
        assert span.entered.wait(0.5)
        assert metric.closed.wait(0.5)
    finally:
        span.release.set()
        assert span.finished.wait(0.5)
        assert _safe_logging_released()


def test_partial_cleanup_retains_safe_logging_after_bounded_runtime_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "partial-cleanup-private-canary"
    span = _BlockingSpanExporter()
    span.log_after_release = canary
    monkeypatch.setattr(otlp_adapter, "OTLPSpanExporter", lambda **_kwargs: span)
    monkeypatch.setattr(
        otlp_adapter,
        "OTLPMetricExporter",
        lambda **_kwargs: _RaisingMetricExporter(),
    )
    monkeypatch.setattr(
        otlp_adapter,
        "PeriodicExportingMetricReader",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("reader-construction-private")
        ),
    )
    settings = _settings(
        "http://127.0.0.1:4318",
        observability_shutdown_timeout_seconds=0.1,
    )
    runtime = ObservabilityRuntime(
        settings,
        service_name="workstream-api",
        export_adapter=create_observability_export_adapter(
            settings, service_name="workstream-api"
        ),
    )
    runtime.start()
    handler = diagnostic_logging.safe_handler()
    assert handler is not None
    stream = io.StringIO()
    monkeypatch.setattr(handler, "stream", stream)
    assert span.entered.wait(0.5)

    started = monotonic()
    runtime.shutdown()
    assert monotonic() - started < 0.5
    assert diagnostic_logging.safe_handler() is handler

    span.release.set()
    assert span.finished.wait(0.5)
    assert _safe_logging_released()
    encoded = stream.getvalue()
    assert canary not in encoded
    records = [json.loads(line) for line in encoded.splitlines()]
    assert {record["service"] for record in records} == {"workstream-api"}
    events = {record["event"] for record in records}
    assert "opentelemetry.error" in events
    assert events <= {"opentelemetry.error", "observability_export_unavailable"}


def test_runtime_uses_only_the_typed_export_adapter() -> None:
    core_source = Path("app/core/observability.py").read_text(encoding="utf-8")
    assert "opentelemetry.exporter.otlp" not in core_source
    assert "PeriodicExportingMetricReader" not in core_source
    assert "observability_otlp_endpoint" not in core_source
    exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    delegate = fake_export_adapter(exporter, reader)

    class CountingAdapter:
        calls = 0

        @property
        def identity(self):
            return delegate.identity

        def create_exporters(self):
            self.calls += 1
            return delegate.create_exporters()

    adapter = CountingAdapter()
    runtime = ObservabilityRuntime(
        Settings(environment="test", pagination_cursor_hmac_secret=PAGINATION_SECRET),
        service_name="workstream-api",
        export_adapter=adapter,
    )
    runtime.start()
    try:
        assert runtime.started
        assert adapter.calls == 1
    finally:
        runtime.shutdown()
