"""Typed external export capability for process-local diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.trace.export import SpanExporter

from workstream_external_services import ExternalServiceAdapter


OBSERVABILITY_EXPORT_CAPABILITY_KEY = "observability_export"
OTLP_HTTP_PROVIDER_KEY = "otlp_http"


@dataclass(frozen=True, slots=True)
class ObservabilityExporterBundle:
    """One process-owned trace exporter and metric reader."""

    span_exporter: SpanExporter
    metric_reader: MetricReader


class ObservabilityExportAdapter(ExternalServiceAdapter, Protocol):
    """Construct the configured exporter resources in the current process."""

    def create_exporters(self) -> ObservabilityExporterBundle:
        """Return newly owned exporter resources or a stable adapter error."""


ObservabilityExportAdapterBuilder = Callable[[], ObservabilityExportAdapter | None]
