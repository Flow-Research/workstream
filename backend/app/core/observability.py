"""Privacy-bounded OpenTelemetry providers and explicit HTTP diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
import logging
from threading import Lock, Thread
from time import monotonic
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Histogram, Meter, UpDownCounter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import Span, SpanContext, SpanKind, Status, StatusCode, TraceState
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.diagnostic_logging import (
    acquire_safe_logging,
    canonical_uuid_text,
    release_safe_logging,
)

_HTTP_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})
_HTTP_OUTCOMES = frozenset({"success", "client_error", "server_error"})
_TASK_OUTCOMES = frozenset({"success", "failure", "retry", "other"})
_CURRENT_RUNTIME: ContextVar[ObservabilityRuntime | None] = ContextVar(
    "diagnostic_runtime", default=None
)
_OWNED_INSTRUMENTATION_SCOPE = InstrumentationScope("workstream.observability")


class SanitizingSpanExporter(SpanExporter):
    """Copy only approved span data before delegating to storage or transport."""

    def __init__(
        self,
        exporter: SpanExporter,
        *,
        resource: Resource,
        route_templates: frozenset[str],
        task_names: frozenset[str],
    ) -> None:
        self._exporter = exporter
        self._resource = resource
        self._route_templates = route_templates
        self._task_names = task_names

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return self._exporter.export(tuple(self._sanitize(span) for span in spans))
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        try:
            self._exporter.shutdown()
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return self._exporter.force_flush(timeout_millis)
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            return False

    def _sanitize(self, span: ReadableSpan) -> ReadableSpan:
        attributes = self._safe_attributes(span.attributes)
        if span.kind is SpanKind.SERVER:
            method = attributes.get("http.request.method", "other")
            route = attributes.get("http.route", "unmatched")
            attributes["http.request.method"] = method
            attributes["http.route"] = route
            name = f"HTTP {method} {route}"
        elif span.kind is SpanKind.CONSUMER:
            task_name = attributes.get("messaging.destination.name", "other")
            attributes["messaging.destination.name"] = task_name
            name = f"celery {task_name}"
        else:
            name = "workstream.other"
            attributes = {}
        return ReadableSpan(
            name=name,
            context=self._safe_context(span.context),
            parent=self._safe_context(span.parent),
            resource=self._resource,
            attributes=attributes,
            events=(),
            links=(),
            kind=span.kind,
            instrumentation_scope=_OWNED_INSTRUMENTATION_SCOPE,
            status=Status(span.status.status_code),
            start_time=span.start_time,
            end_time=span.end_time,
        )

    @staticmethod
    def _safe_context(context: SpanContext | None) -> SpanContext | None:
        if context is None:
            return None
        return SpanContext(
            trace_id=context.trace_id,
            span_id=context.span_id,
            is_remote=context.is_remote,
            trace_flags=context.trace_flags,
            trace_state=TraceState(),
        )

    def _safe_attributes(self, attributes: Mapping[str, Any] | None) -> dict[str, str]:
        source = attributes or {}
        safe: dict[str, str] = {}
        method = source.get("http.request.method")
        if method in _HTTP_METHODS or method == "other":
            safe["http.request.method"] = method
        route = source.get("http.route")
        if route in self._route_templates or route == "unmatched":
            safe["http.route"] = route
        status_class = source.get("http.response.status_class")
        if status_class in {"1xx", "2xx", "3xx", "4xx", "5xx", "other"}:
            safe["http.response.status_class"] = status_class
        outcome = source.get("workstream.outcome")
        if outcome in _HTTP_OUTCOMES | _TASK_OUTCOMES:
            safe["workstream.outcome"] = outcome
        task_name = source.get("messaging.destination.name")
        if task_name in self._task_names or task_name == "other":
            safe["messaging.destination.name"] = task_name
        for key in (
            "workstream.request_id",
            "workstream.correlation_id",
            "workstream.outbox.correlation_id",
        ):
            value = canonical_uuid_text(source.get(key))
            if value is not None:
                safe[key] = value
        return safe


class ObservabilityRuntime:
    """Own one process-local provider pair and closed diagnostic instruments."""

    def __init__(
        self,
        settings: Settings,
        *,
        service_name: str,
        route_templates: frozenset[str] = frozenset(),
        task_names: frozenset[str] = frozenset(),
        span_exporter: SpanExporter | None = None,
        metric_reader: MetricReader | None = None,
    ) -> None:
        self.settings = settings
        self.service_name = service_name
        self.route_templates = route_templates
        self.task_names = task_names
        self._provided_span_exporter = span_exporter
        self._provided_metric_reader = metric_reader
        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self.tracer = trace.NoOpTracerProvider().get_tracer("workstream")
        self.meter: Meter | None = None
        self.http_duration: Histogram | None = None
        self.http_active: UpDownCounter | None = None
        self.task_duration: Histogram | None = None
        self.started = False
        self._logging_owned = False
        self._lock = Lock()

    def start(self) -> None:
        """Initialize owned providers once; exporter failures disable export only."""
        with self._lock:
            if self.started:
                return
            tracer_provider: TracerProvider | None = None
            meter_provider: MeterProvider | None = None
            span_exporter: SpanExporter | None = None
            metric_reader: MetricReader | None = None
            try:
                acquire_safe_logging(self.settings, self.service_name)
                self._logging_owned = True
                resource = Resource(
                    {
                        "service.name": self.service_name,
                        "service.version": self.settings.app_version,
                        "deployment.environment.name": self.settings.environment,
                    }
                )
                span_exporter = self._provided_span_exporter or self._build_span_exporter()
                metric_reader = self._provided_metric_reader or self._build_metric_reader()
                tracer_provider = TracerProvider(
                    sampler=TraceIdRatioBased(self.settings.observability_trace_sample_ratio),
                    resource=resource,
                    shutdown_on_exit=False,
                )
                if span_exporter is not None:
                    tracer_provider.add_span_processor(
                        BatchSpanProcessor(
                            SanitizingSpanExporter(
                                span_exporter,
                                resource=resource,
                                route_templates=self.route_templates,
                                task_names=self.task_names,
                            ),
                            max_queue_size=512,
                            max_export_batch_size=128,
                            schedule_delay_millis=1000,
                            export_timeout_millis=(
                                self.settings.observability_export_timeout_seconds * 1000
                            ),
                        )
                    )
                    span_exporter = None
                readers = () if metric_reader is None else (metric_reader,)
                meter_provider = MeterProvider(
                    resource=resource,
                    metric_readers=readers,
                    shutdown_on_exit=False,
                    views=(
                        View(
                            instrument_name="workstream.http.server.duration",
                            attribute_keys={
                                "http.request.method",
                                "http.route",
                                "http.response.status_class",
                                "workstream.outcome",
                            },
                        ),
                        View(
                            instrument_name="workstream.http.server.active_requests",
                            attribute_keys={"http.request.method"},
                        ),
                        View(
                            instrument_name="workstream.celery.task.duration",
                            attribute_keys={"messaging.destination.name", "workstream.outcome"},
                        ),
                    ),
                )
                metric_reader = None
                self._tracer_provider = tracer_provider
                self._meter_provider = meter_provider
                self.tracer = tracer_provider.get_tracer("workstream.observability")
                self.meter = meter_provider.get_meter("workstream.observability")
                self.http_duration = self.meter.create_histogram(
                    "workstream.http.server.duration", unit="s"
                )
                self.http_active = self.meter.create_up_down_counter(
                    "workstream.http.server.active_requests", unit="{request}"
                )
                self.task_duration = self.meter.create_histogram(
                    "workstream.celery.task.duration", unit="s"
                )
                self.started = True
            except Exception:
                logging.getLogger(__name__).error("observability_export_unavailable")
                self._reset_runtime_state()
                self._bounded_close(
                    tracer_provider,
                    meter_provider,
                    orphan_span_exporter=span_exporter,
                    orphan_metric_reader=metric_reader,
                    release_logging=self._logging_owned,
                )
                self._logging_owned = False

    def _reset_runtime_state(self) -> None:
        self._tracer_provider = None
        self._meter_provider = None
        self.tracer = trace.NoOpTracerProvider().get_tracer("workstream.observability")
        self.meter = None
        self.http_duration = None
        self.http_active = None
        self.task_duration = None
        self.started = False

    def _build_span_exporter(self) -> SpanExporter | None:
        endpoint = self.settings.observability_otlp_endpoint
        if endpoint is None:
            return None
        try:
            return OTLPSpanExporter(
                endpoint=f"{endpoint}/v1/traces",
                timeout=self.settings.observability_export_timeout_seconds,
            )
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            return None

    def _build_metric_reader(self) -> MetricReader | None:
        endpoint = self.settings.observability_otlp_endpoint
        if endpoint is None:
            return None
        try:
            exporter = OTLPMetricExporter(
                endpoint=f"{endpoint}/v1/metrics",
                timeout=self.settings.observability_export_timeout_seconds,
            )
            return PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=10_000,
                export_timeout_millis=self.settings.observability_export_timeout_seconds * 1000,
            )
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            return None

    def shutdown(self) -> None:
        """Bound provider flushing and shutdown without changing product outcomes."""
        with self._lock:
            if not self.started and not self._logging_owned:
                return
            tracer_provider = self._tracer_provider
            meter_provider = self._meter_provider
            release_logging = self._logging_owned
            self._logging_owned = False
            self._reset_runtime_state()
            self._bounded_close(
                tracer_provider,
                meter_provider,
                orphan_span_exporter=None,
                orphan_metric_reader=None,
                release_logging=release_logging,
            )

    def _bounded_close(
        self,
        tracer_provider: TracerProvider | None,
        meter_provider: MeterProvider | None,
        *,
        orphan_span_exporter: SpanExporter | None,
        orphan_metric_reader: MetricReader | None,
        release_logging: bool,
    ) -> None:
        timeout = self.settings.observability_shutdown_timeout_seconds
        timeout_millis = max(1, int(timeout * 500))

        def attempt(operation: Any) -> None:
            try:
                operation()
            except Exception:
                logging.getLogger(__name__).error("observability_export_unavailable")

        def close_traces() -> None:
            if tracer_provider is not None:
                attempt(lambda: tracer_provider.force_flush(timeout_millis))
                attempt(tracer_provider.shutdown)
            if orphan_span_exporter is not None:
                attempt(orphan_span_exporter.shutdown)

        def close_metrics() -> None:
            if meter_provider is not None:
                attempt(lambda: meter_provider.force_flush(timeout_millis))
                attempt(lambda: meter_provider.shutdown(timeout_millis=timeout_millis))
            if orphan_metric_reader is not None:
                attempt(lambda: orphan_metric_reader.shutdown(timeout_millis=timeout_millis))

        def close() -> None:
            workers = (
                Thread(
                    target=close_traces,
                    name="workstream-observability-trace-shutdown",
                    daemon=True,
                ),
                Thread(
                    target=close_metrics,
                    name="workstream-observability-metric-shutdown",
                    daemon=True,
                ),
            )
            try:
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join()
            except Exception:
                logging.getLogger(__name__).error("observability_export_unavailable")
            finally:
                if release_logging and all(not worker.is_alive() for worker in workers):
                    release_safe_logging()

        thread = Thread(target=close, name="workstream-observability-shutdown", daemon=True)
        try:
            thread.start()
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            return
        thread.join(timeout)

    def force_flush(self) -> bool:
        """Flush owned providers within the export timeout for tests and operators."""
        if not self.started:
            return False
        timeout_millis = max(1, int(self.settings.observability_export_timeout_seconds * 1000))
        try:
            trace_flushed = self._tracer_provider is None or self._tracer_provider.force_flush(
                timeout_millis
            )
            metric_flushed = self._meter_provider is None or self._meter_provider.force_flush(
                timeout_millis
            )
            return trace_flushed and metric_flushed
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            return False

    def normalize_route(self, value: object) -> str:
        return value if isinstance(value, str) and value in self.route_templates else "unmatched"

    def normalize_task(self, value: object) -> str:
        return value if isinstance(value, str) and value in self.task_names else "other"


class ObservabilityMiddleware:
    """Create one explicit server span and closed metric set for each HTTP request."""

    def __init__(self, app: ASGIApp, runtime: ObservabilityRuntime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.runtime.started:
            await self.app(scope, receive, send)
            return
        method_value = str(scope.get("method", "")).upper()
        method = method_value if method_value in _HTTP_METHODS else "other"
        span: Span | None = None
        span_token: object | None = None
        runtime_token: Token[ObservabilityRuntime | None] | None = None
        status_code = 500
        started = monotonic()
        active_attributes = {"http.request.method": method}
        try:
            span = self.runtime.tracer.start_span(
                "HTTP other unmatched", context=Context(), kind=SpanKind.SERVER
            )
            span_token = otel_context.attach(trace.set_span_in_context(span, Context()))
            runtime_token = _CURRENT_RUNTIME.set(self.runtime)
            if self.runtime.http_active is not None:
                self.runtime.http_active.add(1, active_attributes)
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
            if runtime_token is not None:
                try:
                    _CURRENT_RUNTIME.reset(runtime_token)
                except Exception:
                    _CURRENT_RUNTIME.set(None)
            if span_token is not None:
                try:
                    otel_context.detach(span_token)
                except Exception:
                    pass
            if span is not None:
                try:
                    span.end()
                except Exception:
                    pass
            await self.app(scope, receive, send)
            return

        async def send_observed(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_observed)
        finally:
            try:
                route_object = scope.get("route")
                route = self.runtime.normalize_route(getattr(route_object, "path", None))
                status_class = f"{status_code // 100}xx" if 100 <= status_code <= 599 else "other"
                outcome = (
                    "success"
                    if status_code < 400
                    else "client_error"
                    if status_code < 500
                    else "server_error"
                )
                metric_attributes = {
                    "http.request.method": method,
                    "http.route": route,
                    "http.response.status_class": status_class,
                    "workstream.outcome": outcome,
                }
                span.update_name(f"HTTP {method} {route}")
                for key, value in metric_attributes.items():
                    span.set_attribute(key, value)
                state = scope.get("state", {})
                if isinstance(state, Mapping):
                    request_id = canonical_uuid_text(state.get("request_id"))
                    correlation_id = canonical_uuid_text(state.get("correlation_id"))
                    if request_id is not None:
                        span.set_attribute("workstream.request_id", request_id)
                    if correlation_id is not None:
                        span.set_attribute("workstream.correlation_id", correlation_id)
                span.set_status(
                    Status(StatusCode.ERROR if status_code >= 500 else StatusCode.UNSET)
                )
                if self.runtime.http_duration is not None:
                    self.runtime.http_duration.record(monotonic() - started, metric_attributes)
            except Exception:
                logging.getLogger(__name__).error("observability_export_unavailable")
            finally:
                try:
                    if self.runtime.http_active is not None:
                        self.runtime.http_active.add(-1, active_attributes)
                except Exception:
                    logging.getLogger(__name__).error("observability_export_unavailable")
                try:
                    _CURRENT_RUNTIME.reset(runtime_token)
                except Exception:
                    _CURRENT_RUNTIME.set(None)
                try:
                    otel_context.detach(span_token)
                except Exception:
                    pass
                try:
                    span.end()
                except Exception:
                    pass


def annotate_current_span(*, outbox_correlation_id: object) -> None:
    """Attach one existing bounded outbox identifier to an active span, if any."""
    try:
        value = canonical_uuid_text(str(outbox_correlation_id))
        if value is None:
            return
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("workstream.outbox.correlation_id", value)
    except Exception:
        return
