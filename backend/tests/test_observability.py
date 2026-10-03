"""Behavior proof for the privacy-bounded diagnostics foundation."""

from __future__ import annotations

import asyncio
import copy
import faulthandler
import io
import json
import logging
import logging.config
import multiprocessing
from pathlib import Path
from threading import Event
import time
from time import monotonic
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from celery import signals
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import (
    SpanContext,
    SpanKind,
    Status,
    StatusCode,
    TraceFlags,
    TraceState,
)
import pytest
from uvicorn.config import LOGGING_CONFIG

from app.core.api_controls import RequestContextMiddleware
from app.core.config import Settings
from app.core import celery_observability as celery_diagnostics
from app.core import diagnostic_logging
from app.core import observability as diagnostics
from app.core.celery_observability import (
    CORRELATION_ID_BROKER_HEADER,
    REQUEST_ID_BROKER_HEADER,
    configure_celery_observability,
)
from app.core.observability import (
    ObservabilityMiddleware,
    ObservabilityRuntime,
    SanitizingSpanExporter,
)
from app.main import create_app

PAGINATION_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
KNOWN_TASK = "workstream.test.known"


def _settings(**values: object) -> Settings:
    configured: dict[str, object] = {
        "environment": "test",
        "pagination_cursor_hmac_secret": PAGINATION_SECRET,
        "observability_trace_sample_ratio": 1.0,
    }
    configured.update(values)
    return Settings(**configured)


class _RecordingInstrument:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.calls: list[tuple[float, dict[str, str]]] = []

    def add(self, value: float, attributes: dict[str, str]) -> None:
        self.calls.append((value, dict(attributes)))
        self.delegate.add(value, attributes)

    def record(self, value: float, attributes: dict[str, str]) -> None:
        self.calls.append((value, dict(attributes)))
        self.delegate.record(value, attributes)


def _runtime(
    *,
    routes: frozenset[str] = frozenset(),
    tasks: frozenset[str] = frozenset(),
    ratio: float = 1.0,
    exporter: SpanExporter | None = None,
) -> tuple[ObservabilityRuntime, InMemorySpanExporter, InMemoryMetricReader]:
    memory_exporter = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    runtime = ObservabilityRuntime(
        _settings(observability_trace_sample_ratio=ratio),
        service_name="workstream-api",
        route_templates=routes,
        task_names=tasks,
        span_exporter=exporter or memory_exporter,
        metric_reader=reader,
    )
    runtime.start()
    return runtime, memory_exporter, reader


def _api(runtime: ObservabilityRuntime, captured_headers: list[dict] | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        if captured_headers is not None:
            headers = {
                "traceparent": "00-11111111111111111111111111111111-2222222222222222-01",
                "tracestate": "secret=state",
                "baggage": "secret=value",
                REQUEST_ID_BROKER_HEADER: str(uuid4()),
                CORRELATION_ID_BROKER_HEADER: str(uuid4()),
            }
            signals.before_task_publish.send(sender=KNOWN_TASK, headers=headers)
            captured_headers.append(headers)
        return {"item": item_id}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("token=exception-secret")

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ObservabilityMiddleware, runtime=runtime)
    return app


async def _get(app: FastAPI, path: str, **kwargs: object):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.get(path, **kwargs)


def _metric_points(reader: InMemoryMetricReader) -> list[tuple[str, dict[str, object], object]]:
    data = reader.get_metrics_data()
    assert data is not None
    points: list[tuple[str, dict[str, object], object]] = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                for point in metric.data.data_points:
                    points.append((metric.name, dict(point.attributes), point))
    return points


async def test_api_emits_exactly_one_http_span_and_metric_set_for_every_route_outcome() -> None:
    runtime, exporter, reader = _runtime(routes=frozenset({"/items/{item_id}", "/boom"}))
    duration = _RecordingInstrument(runtime.http_duration)
    active = _RecordingInstrument(runtime.http_active)
    runtime.http_duration = duration
    runtime.http_active = active
    app = _api(runtime)
    try:
        valid = await _get(app, "/items/secret-value?token=query-secret")
        invalid = await _get(app, "/items/value", headers={"X-Request-ID": "invalid"})
        unmatched = await _get(app, "/missing")
        failed = await _get(app, "/boom")
        assert [
            valid.status_code,
            invalid.status_code,
            unmatched.status_code,
            failed.status_code,
        ] == [
            200,
            400,
            404,
            500,
        ]
        assert runtime.force_flush()
        spans = exporter.get_finished_spans()
        assert len(spans) == 4
        assert [span.kind.name for span in spans] == ["SERVER"] * 4
        assert {span.name for span in spans} == {
            "HTTP GET /items/{item_id}",
            "HTTP GET unmatched",
            "HTTP GET /boom",
        }
        expected_resource = {
            "service.name": "workstream-api",
            "service.version": "0.1.0",
            "deployment.environment.name": "test",
        }
        assert all(dict(span.resource.attributes) == expected_resource for span in spans)
        assert all(
            span.instrumentation_scope == InstrumentationScope("workstream.observability")
            for span in spans
        )
        assert all(not span.events and not span.links for span in spans)
        assert len(duration.calls) == 4
        assert [value for value, _ in active.calls] == [1, -1] * 4
        points = _metric_points(reader)
        metric_data = reader.get_metrics_data()
        assert metric_data is not None
        assert all(
            dict(resource_metrics.resource.attributes) == expected_resource
            for resource_metrics in metric_data.resource_metrics
        )
        assert all(
            scope_metrics.scope == InstrumentationScope("workstream.observability")
            for resource_metrics in metric_data.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
        )
        assert {name for name, _, _ in points} == {
            "workstream.http.server.duration",
            "workstream.http.server.active_requests",
        }
        assert all(
            set(attributes)
            <= {
                "http.request.method",
                "http.route",
                "http.response.status_class",
                "workstream.outcome",
            }
            for _, attributes, _ in points
        )
        encoded = " ".join(
            [span.to_json() for span in spans]
            + [json.dumps(attributes, sort_keys=True) for _, attributes, _ in points]
        )
        for canary in ("secret-value", "query-secret", "exception-secret", "token="):
            assert canary not in encoded
    finally:
        runtime.shutdown()


async def test_unknown_http_method_and_varied_ids_collapse_to_one_exact_metric_series() -> None:
    runtime, exporter, reader = _runtime(routes=frozenset({"/unknown-method"}))
    duration = _RecordingInstrument(runtime.http_duration)
    active = _RecordingInstrument(runtime.http_active)
    runtime.http_duration = duration
    runtime.http_active = active
    app = FastAPI()

    @app.api_route("/unknown-method", methods=["BREW"])
    async def unknown_method() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ObservabilityMiddleware, runtime=runtime)
    identifiers = [(str(uuid4()), str(uuid4())) for _ in range(24)]
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            responses = [
                await client.request(
                    "BREW",
                    "/unknown-method",
                    headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
                )
                for request_id, correlation_id in identifiers
            ]
        assert {response.status_code for response in responses} == {200}
        assert runtime.force_flush()
        spans = exporter.get_finished_spans()
        assert len(spans) == len(identifiers)
        expected_metric_attributes = {
            "http.request.method": "other",
            "http.route": "/unknown-method",
            "http.response.status_class": "2xx",
            "workstream.outcome": "success",
        }
        for span, (request_id, correlation_id) in zip(spans, identifiers, strict=True):
            assert span.name == "HTTP other /unknown-method"
            assert dict(span.attributes) == {
                **expected_metric_attributes,
                "workstream.request_id": request_id,
                "workstream.correlation_id": correlation_id,
            }
        assert len(duration.calls) == len(identifiers)
        assert {tuple(sorted(attributes.items())) for _, attributes in duration.calls} == {
            tuple(sorted(expected_metric_attributes.items()))
        }
        assert [value for value, _ in active.calls] == [1, -1] * len(identifiers)
        assert {tuple(sorted(attributes.items())) for _, attributes in active.calls} == {
            (("http.request.method", "other"),)
        }
        points = _metric_points(reader)
        assert {(name, tuple(sorted(attributes.items()))) for name, attributes, _ in points} == {
            (
                "workstream.http.server.duration",
                tuple(sorted(expected_metric_attributes.items())),
            ),
            (
                "workstream.http.server.active_requests",
                (("http.request.method", "other"),),
            ),
        }
    finally:
        runtime.shutdown()


def test_complete_export_sets_are_closed_and_bounded() -> None:
    delegate = InMemorySpanExporter()
    safe_resource = Resource.create(
        {
            "service.name": "workstream-api",
            "service.version": "0.1.0",
            "deployment.environment.name": "test",
        }
    )
    sanitizer = SanitizingSpanExporter(
        delegate,
        resource=safe_resource,
        route_templates=frozenset({"/items/{item_id}"}),
        task_names=frozenset(),
    )
    canary = "scope-and-resource-secret"
    tainted = ReadableSpan(
        name=f"GET /items/{canary}",
        context=SpanContext(
            trace_id=1,
            span_id=2,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
            trace_state=TraceState((("vendor", canary),)),
        ),
        parent=SpanContext(
            trace_id=1,
            span_id=3,
            is_remote=True,
            trace_flags=TraceFlags.SAMPLED,
            trace_state=TraceState((("vendor", canary),)),
        ),
        resource=Resource.create({"service.name": canary, "secret": canary}),
        attributes={
            "http.request.method": "GET",
            "http.route": "/items/{item_id}",
            "http.response.status_class": "2xx",
            "workstream.outcome": "success",
            "http.url": f"https://example.invalid/?token={canary}",
        },
        kind=SpanKind.SERVER,
        instrumentation_scope=InstrumentationScope(
            canary,
            version=canary,
            schema_url=f"https://{canary}.invalid/schema",
            attributes={"secret": canary},
        ),
        status=Status(StatusCode.ERROR, canary),
        start_time=1,
        end_time=2,
    )

    assert sanitizer.export((tainted,)) is SpanExportResult.SUCCESS
    [exported] = delegate.get_finished_spans()
    assert exported.instrumentation_scope == InstrumentationScope("workstream.observability")
    assert exported.resource == safe_resource
    assert exported.status.status_code is StatusCode.ERROR
    assert exported.status.description is None
    assert not exported.context.trace_state
    assert exported.parent is not None and not exported.parent.trace_state
    assert exported.events == ()
    assert exported.links == ()
    assert set(exported.attributes) == {
        "http.request.method",
        "http.route",
        "http.response.status_class",
        "workstream.outcome",
    }
    assert canary not in exported.to_json()


async def test_concurrent_api_diagnostic_context_is_isolated() -> None:
    runtime, exporter, _ = _runtime(routes=frozenset({"/items/{item_id}"}))
    app = _api(runtime)
    identifiers = [(str(uuid4()), str(uuid4())) for _ in range(12)]
    try:
        responses = await asyncio.gather(
            *(
                _get(
                    app,
                    f"/items/{index}",
                    headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
                )
                for index, (request_id, correlation_id) in enumerate(identifiers)
            )
        )
        assert all(response.status_code == 200 for response in responses)
        assert runtime.force_flush()
        observed = {
            (
                span.attributes["workstream.request_id"],
                span.attributes["workstream.correlation_id"],
            )
            for span in exporter.get_finished_spans()
        }
        assert observed == set(identifiers)
        assert diagnostic_logging.current_diagnostic_ids() == (None, None)
    finally:
        runtime.shutdown()


async def test_overlapping_app_lifespans_keep_owned_providers_and_one_log_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = create_app(_settings())
    second = create_app(_settings())
    first_runtime = first.state.observability_runtime
    second_runtime = second.state.observability_runtime
    assert first_runtime is not second_runtime
    assert first_runtime.started is False and second_runtime.started is False

    async with first.router.lifespan_context(first):
        first_provider = first_runtime._tracer_provider
        handler = diagnostic_logging.safe_handler()
        assert first_provider is not None and handler is not None
        stream = io.StringIO()
        monkeypatch.setattr(handler, "stream", stream)
        assert logging.getLogger().handlers == [handler]
        logging.getLogger("app.main").info("startup canary")
        async with second.router.lifespan_context(second):
            assert second_runtime._tracer_provider is not None
            assert second_runtime._tracer_provider is not first_provider
            assert diagnostic_logging.safe_handler() is handler
            assert logging.getLogger().handlers == [handler]
            logging.getLogger("app.main").info("overlap canary")
        assert first_runtime.started is True
        assert diagnostic_logging.safe_handler() is handler
        assert {json.loads(line)["service"] for line in stream.getvalue().splitlines()} == {
            "workstream-api"
        }

    deadline = monotonic() + 1
    while diagnostic_logging.safe_handler() is not None and monotonic() < deadline:
        time.sleep(0.01)
    assert first_runtime.started is False and second_runtime.started is False
    assert diagnostic_logging.safe_handler() is None


async def test_static_and_dynamic_routes_keep_the_selected_registered_template() -> None:
    runtime, exporter, _ = _runtime(routes=frozenset({"/items/static", "/items/{item_id}"}))
    app = FastAPI()

    @app.get("/items/static")
    async def static_item() -> dict[str, bool]:
        return {"static": True}

    @app.get("/items/{item_id}")
    async def dynamic_item(item_id: str) -> dict[str, str]:
        return {"item": item_id}

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ObservabilityMiddleware, runtime=runtime)
    try:
        assert (await _get(app, "/items/static")).status_code == 200
        assert (await _get(app, "/items/value")).status_code == 200
        assert runtime.force_flush()
        assert [span.name for span in exporter.get_finished_spans()] == [
            "HTTP GET /items/static",
            "HTTP GET /items/{item_id}",
        ]
    finally:
        runtime.shutdown()


async def test_public_propagation_and_sampling_input_cannot_control_local_trace() -> None:
    chosen_trace = "11111111111111111111111111111111"
    headers = {
        "traceparent": f"00-{chosen_trace}-2222222222222222-01",
        "tracestate": "secret=state",
        "baggage": "secret=value",
    }
    runtime, exporter, _ = _runtime(routes=frozenset({"/items/{item_id}"}))
    try:
        response = await _get(_api(runtime), "/items/value", headers=headers)
        assert response.status_code == 200
        assert runtime.force_flush()
        [span] = exporter.get_finished_spans()
        assert f"{span.context.trace_id:032x}" != chosen_trace
        assert not span.context.trace_state
    finally:
        runtime.shutdown()

    unsampled, unsampled_exporter, _ = _runtime(routes=frozenset({"/items/{item_id}"}), ratio=0.0)
    try:
        response = await _get(_api(unsampled), "/items/value", headers=headers)
        assert response.status_code == 200
        assert unsampled.force_flush()
        assert unsampled_exporter.get_finished_spans() == ()
    finally:
        unsampled.shutdown()


class _Task:
    def __init__(self, task_id: str, headers: dict[str, str] | None) -> None:
        self.name = KNOWN_TASK
        self.request = SimpleNamespace(id=task_id, headers=headers)


async def test_api_to_celery_trace_is_parent_child_and_headers_are_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, exporter, _ = _runtime(
        routes=frozenset({"/items/{item_id}"}), tasks=frozenset({KNOWN_TASK})
    )
    task_duration = _RecordingInstrument(runtime.task_duration)
    runtime.task_duration = task_duration
    monkeypatch.setattr(celery_diagnostics, "_WORKER_RUNTIME", runtime)
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    configure_celery_observability(_settings(), frozenset({KNOWN_TASK}))
    published: list[dict] = []
    request_id, correlation_id = str(uuid4()), str(uuid4())
    try:
        response = await _get(
            _api(runtime, published),
            "/items/value",
            headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
        )
        assert response.status_code == 200
        [broker_headers] = published
        assert set(broker_headers) == {
            "traceparent",
            REQUEST_ID_BROKER_HEADER,
            CORRELATION_ID_BROKER_HEADER,
        }
        assert broker_headers[REQUEST_ID_BROKER_HEADER] == request_id
        assert broker_headers[CORRELATION_ID_BROKER_HEADER] == correlation_id
        task_id = str(uuid4())
        task = _Task(task_id, broker_headers)
        signals.task_prerun.send(sender=None, task_id=task_id, task=task)
        signals.task_postrun.send(sender=None, task_id=task_id, task=task, state="SUCCESS")
        assert runtime.force_flush()
        spans = exporter.get_finished_spans()
        server = next(span for span in spans if span.kind.name == "SERVER")
        consumers = [span for span in spans if span.kind.name == "CONSUMER"]
        assert len(consumers) == 1
        [consumer] = consumers
        assert consumer.context.trace_id == server.context.trace_id
        assert consumer.parent is not None and consumer.parent.span_id == server.context.span_id
        assert consumer.attributes["workstream.request_id"] == request_id
        assert consumer.attributes["workstream.correlation_id"] == correlation_id
        assert len(task_duration.calls) == 1
        assert "host.name" not in task_duration.calls[0][1]
    finally:
        celery_diagnostics._ACTIVE_TASKS.clear()
        runtime.shutdown()


def test_real_loggers_and_hostile_exception_never_render_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_names = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
    configured_loggers = [logging.getLogger(name) for name in configured_names]
    snapshots = [
        (list(logger.handlers), logger.propagate, logger.level, logger.disabled)
        for logger in configured_loggers
    ]
    logging.config.dictConfig(copy.deepcopy(LOGGING_CONFIG))
    runtime, _, _ = _runtime()
    stream = io.StringIO()
    assert diagnostic_logging.safe_handler() is not None
    monkeypatch.setattr(diagnostic_logging.safe_handler(), "stream", stream)

    class Hostile(Exception):
        rendered = False

        def __str__(self) -> str:
            self.rendered = True
            raise AssertionError("exception rendered")

    hostile = Hostile()
    try:
        logging.getLogger("app.core.api_controls").error(
            "request_failed_before_response_start",
            "credential=argument-secret",
            extra={"token": "extra-secret"},
            exc_info=(Hostile, hostile, None),
        )
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:1",
            "GET",
            "/health?token=uvicorn-query-secret",
            "1.1",
            200,
        )
        for logger_name in (
            "uvicorn.access",
            "uvicorn.error",
            "celery.task",
            "celery.retry",
            "kombu.connection",
            "opentelemetry.exporter",
            "sqlalchemy.engine",
            "unknown.library",
        ):
            logging.getLogger(logger_name).error(
                hostile, extra={"signed_url": "https://secret.invalid/token"}
            )
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert len(records) == 10
        assert hostile.rendered is False
        allowed = {
            "timestamp",
            "service",
            "environment",
            "severity",
            "event",
            "request_id",
            "correlation_id",
            "trace_id",
            "span_id",
        }
        assert all(set(record) <= allowed for record in records)
        assert {record["service"] for record in records} == {"workstream-api"}
        encoded = stream.getvalue()
        for canary in (
            "argument-secret",
            "extra-secret",
            "secret.invalid",
            "credential=",
            "uvicorn-query-secret",
        ):
            assert canary not in encoded
    finally:
        runtime.shutdown()
        for logger, snapshot in zip(configured_loggers, snapshots, strict=True):
            handlers, propagate, level, disabled = snapshot
            logger.handlers = handlers
            logger.propagate = propagate
            logger.setLevel(level)
            logger.disabled = disabled


class _FailingExporter(SpanExporter):
    def export(self, spans):
        raise RuntimeError("credential=collector-secret")

    def shutdown(self) -> None:
        raise RuntimeError("credential=shutdown-secret")


class _ExplodingInstrument:
    def add(self, _value: float, _attributes: dict[str, str]) -> None:
        raise RuntimeError("instrument failure")

    def record(self, _value: float, _attributes: dict[str, str]) -> None:
        raise RuntimeError("instrument failure")


async def test_telemetry_instrument_failure_never_masks_http_or_leaks_context() -> None:
    runtime, exporter, _ = _runtime(routes=frozenset({"/items/{item_id}"}))
    runtime.http_duration = _ExplodingInstrument()
    try:
        response = await _get(_api(runtime), "/items/value")
        assert response.status_code == 200
        assert runtime.force_flush()
        assert len(exporter.get_finished_spans()) == 1
        assert diagnostics._CURRENT_RUNTIME.get() is None
        assert diagnostic_logging.current_diagnostic_ids() == (None, None)
        assert not diagnostics.trace.get_current_span().get_span_context().is_valid
    finally:
        runtime.shutdown()


class _ShutdownProbeExporter(SpanExporter):
    def __init__(self, *, block: bool = False) -> None:
        self.block = block
        self.entered = Event()
        self.release = Event()
        self.closed = Event()

    def export(self, _spans) -> SpanExportResult:
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.entered.set()
        if self.block:
            self.release.wait(5)
        self.closed.set()


class _ShutdownProbeReader(InMemoryMetricReader):
    def __init__(self) -> None:
        super().__init__()
        self.closed = Event()

    def shutdown(self, timeout_millis: float = 30000, **kwargs: object) -> None:
        self.closed.set()
        super().shutdown(timeout_millis=timeout_millis, **kwargs)


class _ProcessBlockingExporter(SpanExporter):
    def export(self, _spans) -> SpanExportResult:
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        Event().wait(30)


_PROCESS_TRACE_STREAM: Any = None


def _bounded_process_exit_probe(
    status: Any,
    trace_path: str,
    *,
    call_runtime_shutdown: bool = True,
    register_sdk_atexit: bool = False,
) -> None:
    global _PROCESS_TRACE_STREAM
    if register_sdk_atexit:
        tracer_provider_type = diagnostics.TracerProvider
        meter_provider_type = diagnostics.MeterProvider
        diagnostics.TracerProvider = lambda **kwargs: tracer_provider_type(
            **{**kwargs, "shutdown_on_exit": True}
        )
        diagnostics.MeterProvider = lambda **kwargs: meter_provider_type(
            **{**kwargs, "shutdown_on_exit": True}
        )
    runtime = ObservabilityRuntime(
        _settings(observability_shutdown_timeout_seconds=0.1),
        service_name="workstream-api",
        span_exporter=_ProcessBlockingExporter(),
    )
    runtime.start()
    status.send("runtime_started")
    _PROCESS_TRACE_STREAM = Path(trace_path).open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(
        1.0,
        repeat=True,
        file=_PROCESS_TRACE_STREAM,
    )
    if call_runtime_shutdown:
        runtime.shutdown()
        status.send("shutdown_returned")
    else:
        status.send("probe_returning")
    status.close()


def _start_process_exit_probe(
    tmp_path: Path,
    *,
    call_runtime_shutdown: bool = True,
    register_sdk_atexit: bool = False,
) -> tuple[Any, Any, Path]:
    context = multiprocessing.get_context("spawn")
    status, child_status = context.Pipe(duplex=False)
    trace_path = tmp_path / (
        "sdk-atexit-trace.log" if register_sdk_atexit else "process-exit-trace.log"
    )
    process = context.Process(
        target=_bounded_process_exit_probe,
        args=(child_status, str(trace_path)),
        kwargs={
            "call_runtime_shutdown": call_runtime_shutdown,
            "register_sdk_atexit": register_sdk_atexit,
        },
    )
    process.start()
    child_status.close()
    return process, status, trace_path


def _stop_process(process: Any, status: Any) -> None:
    status.close()
    if process.is_alive():
        process.kill()
    process.join(timeout=2)


def test_partial_provider_startup_closes_created_exporter_and_releases_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _ShutdownProbeExporter()
    reader = _ShutdownProbeReader()

    def fail_meter_provider(**_kwargs: object):
        raise RuntimeError("metric provider construction failed")

    monkeypatch.setattr(diagnostics, "MeterProvider", fail_meter_provider)
    runtime = ObservabilityRuntime(
        _settings(observability_shutdown_timeout_seconds=0.2),
        service_name="workstream-api",
        span_exporter=exporter,
        metric_reader=reader,
    )
    runtime.start()
    assert runtime.started is False
    assert exporter.closed.wait(1)
    assert reader.closed.wait(1)
    deadline = monotonic() + 1
    while diagnostic_logging.safe_handler() is not None and monotonic() < deadline:
        time.sleep(0.01)
    assert diagnostic_logging.safe_handler() is None


def test_tracer_provider_construction_failure_closes_unattached_exporter_and_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _ShutdownProbeExporter()
    reader = _ShutdownProbeReader()

    def fail_tracer_provider(**_kwargs: object):
        raise RuntimeError("trace provider construction failed")

    monkeypatch.setattr(diagnostics, "TracerProvider", fail_tracer_provider)
    runtime = ObservabilityRuntime(
        _settings(observability_shutdown_timeout_seconds=0.2),
        service_name="workstream-api",
        span_exporter=exporter,
        metric_reader=reader,
    )
    runtime.start()
    assert runtime.started is False
    assert exporter.closed.wait(1)
    assert reader.closed.wait(1)
    deadline = monotonic() + 1
    while diagnostic_logging.safe_handler() is not None and monotonic() < deadline:
        time.sleep(0.01)
    assert diagnostic_logging.safe_handler() is None


def test_failure_after_provider_assignment_clears_every_runtime_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _ShutdownProbeExporter()
    reader = _ShutdownProbeReader()

    def fail_get_tracer(self: object, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("tracer acquisition failed")

    monkeypatch.setattr(diagnostics.TracerProvider, "get_tracer", fail_get_tracer)
    runtime = ObservabilityRuntime(
        _settings(observability_shutdown_timeout_seconds=0.2),
        service_name="workstream-api",
        span_exporter=exporter,
        metric_reader=reader,
    )
    runtime.start()

    assert runtime.started is False
    assert runtime._tracer_provider is None
    assert runtime._meter_provider is None
    assert runtime.meter is None
    assert runtime.http_duration is None
    assert runtime.http_active is None
    assert runtime.task_duration is None
    assert runtime.force_flush() is False
    assert exporter.closed.wait(1)
    assert reader.closed.wait(1)
    deadline = monotonic() + 1
    while diagnostic_logging.safe_handler() is not None and monotonic() < deadline:
        time.sleep(0.01)
    assert diagnostic_logging.safe_handler() is None


def test_trace_flush_failure_still_closes_trace_and_metric_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _ShutdownProbeExporter()
    reader = _ShutdownProbeReader()
    runtime = ObservabilityRuntime(
        _settings(observability_shutdown_timeout_seconds=0.2),
        service_name="workstream-api",
        span_exporter=exporter,
        metric_reader=reader,
    )
    runtime.start()
    tracer_provider = runtime._tracer_provider
    assert tracer_provider is not None

    def fail_trace_flush(_timeout_millis: int) -> bool:
        raise RuntimeError("trace flush failed")

    monkeypatch.setattr(tracer_provider, "force_flush", fail_trace_flush)
    runtime.shutdown()
    assert exporter.closed.wait(1)
    assert reader.closed.wait(1)


def test_timed_out_shutdown_keeps_safe_logging_until_exporter_thread_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = _ShutdownProbeExporter(block=True)
    runtime = ObservabilityRuntime(
        _settings(observability_shutdown_timeout_seconds=0.1),
        service_name="workstream-api",
        span_exporter=exporter,
    )
    runtime.start()
    assert diagnostic_logging.safe_handler() is not None
    stream = io.StringIO()
    monkeypatch.setattr(diagnostic_logging.safe_handler(), "stream", stream)
    started = monotonic()
    runtime.shutdown()
    assert monotonic() - started < 0.5
    assert exporter.entered.wait(1)
    assert diagnostic_logging.safe_handler() is not None
    logging.getLogger("celery.retry").error("credential=late-secret")
    assert "late-secret" not in stream.getvalue()
    exporter.release.set()
    assert exporter.closed.wait(1)
    deadline = monotonic() + 1
    while diagnostic_logging.safe_handler() is not None and monotonic() < deadline:
        time.sleep(0.01)
    assert diagnostic_logging.safe_handler() is None


def test_bounded_runtime_shutdown_returns_before_process_exit(
    tmp_path: Path,
) -> None:
    process, status, trace_path = _start_process_exit_probe(tmp_path)
    try:
        assert status.poll(10), "child did not finish runtime startup"
        assert status.recv() == "runtime_started"
        assert status.poll(2), "bounded runtime shutdown did not return"
        assert status.recv() == "shutdown_returned"
        started = monotonic()
        process.join(timeout=2)
        if process.is_alive():
            trace = trace_path.read_text(encoding="utf-8") if trace_path.exists() else ""
            pytest.fail(f"child did not exit after bounded shutdown\n{trace}")
        assert process.exitcode == 0
        assert monotonic() - started < 2
    finally:
        _stop_process(process, status)


def test_owned_providers_do_not_register_unbounded_interpreter_exit_hooks(
    tmp_path: Path,
) -> None:
    process, status, trace_path = _start_process_exit_probe(
        tmp_path,
        call_runtime_shutdown=False,
    )
    try:
        assert status.poll(10), "child did not finish runtime startup"
        assert status.recv() == "runtime_started"
        assert status.poll(2), "child did not reach interpreter exit"
        assert status.recv() == "probe_returning"
        started = monotonic()
        process.join(timeout=2)
        if process.is_alive():
            trace = trace_path.read_text(encoding="utf-8") if trace_path.exists() else ""
            pytest.fail(f"child did not complete normal interpreter exit\n{trace}")
        assert process.exitcode == 0
        assert monotonic() - started < 2
    finally:
        _stop_process(process, status)


def test_process_exit_probe_rejects_sdk_atexit_shutdown_registration(
    tmp_path: Path,
) -> None:
    process, status, trace_path = _start_process_exit_probe(
        tmp_path,
        call_runtime_shutdown=False,
        register_sdk_atexit=True,
    )
    try:
        assert status.poll(10), "mutant child did not finish runtime startup"
        assert status.recv() == "runtime_started"
        assert status.poll(2), "mutant child did not reach interpreter exit"
        assert status.recv() == "probe_returning"
        process.join(timeout=2)
        assert process.is_alive(), "SDK atexit registration mutant escaped the exit bound"
        trace = trace_path.read_text(encoding="utf-8")
        assert "test_observability.py" in trace and " in shutdown" in trace
        assert "opentelemetry/sdk/trace" in trace
    finally:
        _stop_process(process, status)


async def test_collector_failure_is_bounded_and_product_flow_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing, _, _ = _runtime(routes=frozenset({"/items/{item_id}"}))
    try:
        assert (await _get(_api(missing), "/items/value")).status_code == 200
    finally:
        missing.shutdown()

    monkeypatch.setattr(
        diagnostics,
        "OTLPSpanExporter",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("construction-secret")),
    )
    monkeypatch.setattr(
        diagnostics,
        "OTLPMetricExporter",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("construction-secret")),
    )
    construction = ObservabilityRuntime(
        _settings(observability_otlp_endpoint="http://127.0.0.1:4318"),
        service_name="workstream-api",
        route_templates=frozenset({"/items/{item_id}"}),
    )
    construction.start()
    try:
        assert construction.started
        assert (await _get(_api(construction), "/items/value")).status_code == 200
    finally:
        construction.shutdown()

    failing, _, _ = _runtime(routes=frozenset({"/items/{item_id}"}), exporter=_FailingExporter())
    stream = io.StringIO()
    assert diagnostic_logging.safe_handler() is not None
    monkeypatch.setattr(diagnostic_logging.safe_handler(), "stream", stream)
    try:
        started = monotonic()
        assert (await _get(_api(failing), "/items/value")).status_code == 200
        failing.force_flush()
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert records
        assert {record["service"] for record in records} == {"workstream-api"}
        failing.shutdown()
        assert monotonic() - started < 5.0
    finally:
        failing.shutdown()


def test_observability_core_has_no_worker_or_module_imports() -> None:
    source = Path("app/core/observability.py").read_text(encoding="utf-8")
    assert "app.workers" not in source
    assert "app.modules" not in source


def test_operator_docs_match_runtime_observability_contract() -> None:
    documentation = Path("../docs/engineering/observability.md").read_text(encoding="utf-8")
    example = Path(".env.example").read_text(encoding="utf-8")
    for setting in (
        "WORKSTREAM_OBSERVABILITY_LOG_LEVEL",
        "WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT",
        "WORKSTREAM_OBSERVABILITY_TRACE_SAMPLE_RATIO",
        "WORKSTREAM_OBSERVABILITY_EXPORT_TIMEOUT_SECONDS",
        "WORKSTREAM_OBSERVABILITY_SHUTDOWN_TIMEOUT_SECONDS",
    ):
        assert setting in documentation
        assert setting in example
    for boundary in (
        "outbox recovery",
        "does not persist trace context",
        "on-demand profiling",
        "implemented",
        "deployed",
        "staging, preview, prod, and production require https",
        "workstream-api",
        "workstream-celery",
        "http {method} {route}",
        "celery {task}",
        "workstream.http.server.duration",
        "workstream.http.server.active_requests",
        "workstream.celery.task.duration",
        "{request}",
        "scripts.run_isolated_tests",
    ):
        assert boundary in documentation.lower()
