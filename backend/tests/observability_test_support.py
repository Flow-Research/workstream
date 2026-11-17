"""Focused test adapter for process-local observability resources."""

from __future__ import annotations

from dataclasses import dataclass
import faulthandler
from pathlib import Path
from threading import Event
from typing import Any

from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from workstream_external_services import ExternalServiceAdapterIdentity
from app.interfaces.observability import (
    OBSERVABILITY_EXPORT_CAPABILITY_KEY,
    ObservabilityExporterBundle,
)

PAGINATION_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
_PROCESS_TRACE_STREAM: Any = None


@dataclass(frozen=True, slots=True)
class FakeObservabilityExportAdapter:
    """Return one test-owned exporter bundle through the production port."""

    span_exporter: SpanExporter
    metric_reader: MetricReader

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        return ExternalServiceAdapterIdentity(
            OBSERVABILITY_EXPORT_CAPABILITY_KEY,
            "test_memory",
        )

    def create_exporters(self) -> ObservabilityExporterBundle:
        return ObservabilityExporterBundle(self.span_exporter, self.metric_reader)


def fake_export_adapter(
    span_exporter: SpanExporter,
    metric_reader: MetricReader | None = None,
) -> FakeObservabilityExportAdapter:
    """Build the shared fake through the same typed production port."""
    return FakeObservabilityExportAdapter(
        span_exporter,
        metric_reader or InMemoryMetricReader(),
    )


class ProcessBlockingExporter(SpanExporter):
    """Block SDK shutdown so the process-exit probe can enforce its bound."""

    def export(self, _spans) -> SpanExportResult:
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        Event().wait(30)


def bounded_process_exit_probe(
    status: Any,
    trace_path: str,
    *,
    call_runtime_shutdown: bool = True,
    register_sdk_atexit: bool = False,
) -> None:
    """Run one lightweight spawn target for bounded SDK shutdown proof."""
    from app.core import observability as diagnostics
    from app.core.config import Settings
    from app.core.observability import ObservabilityRuntime

    global _PROCESS_TRACE_STREAM
    _PROCESS_TRACE_STREAM = Path(trace_path).open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(1.0, repeat=True, file=_PROCESS_TRACE_STREAM)
    status.send("target_entered")
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
        Settings(
            environment="test",
            pagination_cursor_hmac_secret=PAGINATION_SECRET,
            observability_trace_sample_ratio=1.0,
            observability_shutdown_timeout_seconds=0.1,
        ),
        service_name="workstream-api",
        export_adapter=fake_export_adapter(ProcessBlockingExporter()),
    )
    runtime.start()
    status.send("runtime_started")
    if call_runtime_shutdown:
        runtime.shutdown()
        status.send("shutdown_returned")
    else:
        status.send("probe_returning")
    status.close()
