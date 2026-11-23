"""Sole concrete OTLP HTTP composition for the observability capability."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from threading import Thread
from time import monotonic
from typing import Literal

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from app.core.config import Settings
from app.core.diagnostic_logging import acquire_safe_logging, release_safe_logging
from workstream_external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
    ExternalServiceConfigurationError,
)
from app.interfaces.observability import (
    OBSERVABILITY_EXPORT_CAPABILITY_KEY,
    OTLP_HTTP_PROVIDER_KEY,
    ObservabilityExportAdapter,
    ObservabilityExporterBundle,
)


_IDENTITY = ExternalServiceAdapterIdentity(
    OBSERVABILITY_EXPORT_CAPABILITY_KEY,
    OTLP_HTTP_PROVIDER_KEY,
)


@dataclass(frozen=True, slots=True)
class _OtlpHttpObservabilityExportAdapter:
    """Build a fresh OTLP exporter bundle in its owning process."""

    endpoint: str
    timeout_seconds: float
    shutdown_timeout_seconds: float
    logging_settings: Settings = field(repr=False, compare=False)
    service_name: Literal["workstream-api", "workstream-celery"]

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        return _IDENTITY

    def create_exporters(self) -> ObservabilityExporterBundle:
        span_exporter: OTLPSpanExporter | None = None
        metric_exporter: OTLPMetricExporter | None = None
        metric_reader: PeriodicExportingMetricReader | None = None
        try:
            span_exporter = OTLPSpanExporter(
                endpoint=f"{self.endpoint}/v1/traces",
                timeout=self.timeout_seconds,
            )
            metric_exporter = OTLPMetricExporter(
                endpoint=f"{self.endpoint}/v1/metrics",
                timeout=self.timeout_seconds,
            )
            metric_reader = PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=10_000,
                export_timeout_millis=self.timeout_seconds * 1000,
            )
            bundle = ObservabilityExporterBundle(span_exporter, metric_reader)
            span_exporter = None
            metric_exporter = None
            metric_reader = None
            return bundle
        except Exception:
            _close_partial_exporters(
                span_exporter,
                metric_exporter,
                metric_reader,
                timeout_seconds=self.shutdown_timeout_seconds,
                logging_settings=self.logging_settings,
                service_name=self.service_name,
            )
            raise ExternalServiceConfigurationError(_IDENTITY) from None


def _close_partial_exporters(
    span_exporter: OTLPSpanExporter | None,
    metric_exporter: OTLPMetricExporter | None,
    metric_reader: PeriodicExportingMetricReader | None,
    *,
    timeout_seconds: float,
    logging_settings: Settings,
    service_name: Literal["workstream-api", "workstream-celery"],
) -> None:
    """Release every resource created before a bundle construction failure."""
    operations: list[Callable[[], object]] = []
    if metric_reader is not None:
        operations.append(
            lambda: metric_reader.shutdown(timeout_millis=max(1, int(timeout_seconds * 1000)))
        )
        metric_exporter = None
    elif metric_exporter is not None:
        operations.append(
            lambda: metric_exporter.shutdown(timeout_millis=max(1, int(timeout_seconds * 1000)))
        )
    if span_exporter is not None:
        operations.append(span_exporter.shutdown)

    def attempt(operation: Callable[[], object]) -> None:
        try:
            operation()
        except Exception:
            logging.getLogger(__name__).error("observability_export_unavailable")
        finally:
            release_safe_logging()

    workers = [
        Thread(
            target=attempt,
            args=(operation,),
            name="workstream-observability-partial-cleanup",
            daemon=True,
        )
        for operation in operations
    ]
    started_workers: list[Thread] = []
    for worker in workers:
        try:
            acquire_safe_logging(logging_settings, service_name)
            worker.start()
            started_workers.append(worker)
        except Exception:
            release_safe_logging()
            logging.getLogger(__name__).error("observability_export_unavailable")
    deadline = monotonic() + timeout_seconds
    for worker in started_workers:
        if worker.ident is not None:
            worker.join(max(0.0, deadline - monotonic()))


def create_observability_export_adapter(
    settings: Settings,
    *,
    service_name: Literal["workstream-api", "workstream-celery"],
) -> ObservabilityExportAdapter | None:
    """Compose the one explicitly registered provider, or disable export."""
    endpoint = settings.observability_otlp_endpoint
    if endpoint is None:
        return None
    factory = ExternalServiceAdapterFactory[ObservabilityExportAdapter](
        OBSERVABILITY_EXPORT_CAPABILITY_KEY
    )
    factory.register(
        OTLP_HTTP_PROVIDER_KEY,
        lambda: _OtlpHttpObservabilityExportAdapter(
            endpoint,
            settings.observability_export_timeout_seconds,
            settings.observability_shutdown_timeout_seconds,
            settings,
            service_name,
        ),
    )
    return factory.create(OTLP_HTTP_PROVIDER_KEY)
