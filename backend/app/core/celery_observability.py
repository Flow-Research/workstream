"""Public-signal observability composition for Celery publishers and children."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
from threading import Lock
from time import monotonic
from typing import Any
from uuid import uuid4

from celery import signals
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.core.config import Settings
from app.core.diagnostic_logging import (
    DiagnosticContextTokens,
    acquire_safe_logging,
    bind_diagnostic_context,
    canonical_uuid_text,
    clear_diagnostic_context,
    current_diagnostic_ids,
    release_safe_logging,
    reset_diagnostic_context,
)
from app.core.observability import ObservabilityRuntime

REQUEST_ID_BROKER_HEADER = "workstream-request-id"
CORRELATION_ID_BROKER_HEADER = "workstream-correlation-id"
TRACEPARENT_HEADER = "traceparent"
_PROPAGATION_HEADERS = frozenset(
    {
        TRACEPARENT_HEADER,
        "tracestate",
        "baggage",
        REQUEST_ID_BROKER_HEADER,
        CORRELATION_ID_BROKER_HEADER,
    }
)
_TASK_OUTCOMES = frozenset({"success", "failure", "retry", "other"})
_CELERY_LOCK = Lock()
_CELERY_SETTINGS: Settings | None = None
_CELERY_TASK_NAMES: frozenset[str] = frozenset()
_WORKER_RUNTIME: ObservabilityRuntime | None = None
_CELERY_PARENT_LOGGING_OWNED = False


@dataclass
class _TaskObservation:
    span: Span
    span_token: object
    diagnostic_tokens: DiagnosticContextTokens
    runtime: ObservabilityRuntime
    task_name: str
    started: float


_ACTIVE_TASKS: dict[str, _TaskObservation] = {}


def configure_celery_observability(settings: Settings, task_names: frozenset[str]) -> None:
    """Register one public-signal receiver set without creating process providers."""
    global _CELERY_SETTINGS, _CELERY_TASK_NAMES
    with _CELERY_LOCK:
        _CELERY_SETTINGS = settings
        _CELERY_TASK_NAMES = frozenset(task_names)
        signals.before_task_publish.connect(
            _before_task_publish, weak=False, dispatch_uid="workstream-observability-publish"
        )
        signals.task_prerun.connect(
            _task_prerun, weak=False, dispatch_uid="workstream-observability-prerun"
        )
        signals.task_postrun.connect(
            _task_postrun, weak=False, dispatch_uid="workstream-observability-postrun"
        )
        signals.task_failure.connect(
            _task_failure, weak=False, dispatch_uid="workstream-observability-failure"
        )
        signals.task_retry.connect(
            _task_retry, weak=False, dispatch_uid="workstream-observability-retry"
        )
        signals.setup_logging.connect(
            _setup_celery_parent_logging,
            weak=False,
            dispatch_uid="workstream-observability-parent-logging",
        )


def initialize_worker_observability() -> None:
    """Create exporters only after Celery enters a worker child process."""
    global _WORKER_RUNTIME
    with _CELERY_LOCK:
        settings = _CELERY_SETTINGS
        task_names = _CELERY_TASK_NAMES
    if settings is None:
        return
    prior = _WORKER_RUNTIME
    if prior is not None:
        prior.shutdown()
    runtime = ObservabilityRuntime(
        settings, service_name="workstream-celery", task_names=task_names
    )
    runtime.start()
    _WORKER_RUNTIME = runtime


def shutdown_worker_observability() -> None:
    """Flush and close the child-owned worker providers within the configured bound."""
    global _WORKER_RUNTIME
    runtime, _WORKER_RUNTIME = _WORKER_RUNTIME, None
    if runtime is not None:
        runtime.shutdown()
    clear_diagnostic_context()


def shutdown_celery_parent_observability() -> None:
    """Release the worker-parent logging lease after broker activity ends."""
    global _CELERY_PARENT_LOGGING_OWNED
    with _CELERY_LOCK:
        if not _CELERY_PARENT_LOGGING_OWNED:
            return
        _CELERY_PARENT_LOGGING_OWNED = False
    release_safe_logging()


def _setup_celery_parent_logging(**_kwargs: object) -> None:
    """Install closed logging in the worker parent without creating exporters."""
    global _CELERY_PARENT_LOGGING_OWNED
    with _CELERY_LOCK:
        if _CELERY_PARENT_LOGGING_OWNED or _CELERY_SETTINGS is None:
            return
        acquire_safe_logging(_CELERY_SETTINGS, "workstream-celery")
        _CELERY_PARENT_LOGGING_OWNED = True


def _before_task_publish(headers: dict[str, Any] | None = None, **_kwargs: object) -> None:
    if headers is None:
        return
    for key in tuple(headers):
        if str(key).lower() in _PROPAGATION_HEADERS:
            headers.pop(key, None)
    try:
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            carrier: dict[str, str] = {}
            TraceContextTextMapPropagator().inject(carrier, context=otel_context.get_current())
            traceparent = carrier.get(TRACEPARENT_HEADER)
            if traceparent is not None:
                headers[TRACEPARENT_HEADER] = traceparent
        request_id, correlation_id = current_diagnostic_ids()
        if request_id is not None:
            headers[REQUEST_ID_BROKER_HEADER] = request_id
        if correlation_id is not None:
            headers[CORRELATION_ID_BROKER_HEADER] = correlation_id
    except Exception:
        logging.getLogger(__name__).error("observability_export_unavailable")


def _task_key(task_id: object) -> str:
    return task_id if isinstance(task_id, str) else "missing"


def _task_prerun(task_id: object = None, task: object = None, **_kwargs: object) -> None:
    runtime = _WORKER_RUNTIME
    if runtime is None or not runtime.started:
        return
    key = _task_key(task_id)
    stale = _ACTIVE_TASKS.pop(key, None)
    if stale is not None:
        _finish_task(stale, "other")
    clear_diagnostic_context()
    span: Span | None = None
    span_token: object | None = None
    diagnostic_tokens: DiagnosticContextTokens | None = None
    try:
        raw_headers = getattr(getattr(task, "request", None), "headers", None)
        headers = raw_headers if isinstance(raw_headers, Mapping) else {}
        fallback = canonical_uuid_text(task_id) or str(uuid4())
        request_id = canonical_uuid_text(headers.get(REQUEST_ID_BROKER_HEADER)) or fallback
        correlation_id = canonical_uuid_text(headers.get(CORRELATION_ID_BROKER_HEADER)) or fallback
        carrier: dict[str, str] = {}
        traceparent = headers.get(TRACEPARENT_HEADER)
        if isinstance(traceparent, str):
            carrier[TRACEPARENT_HEADER] = traceparent
        parent = TraceContextTextMapPropagator().extract(carrier=carrier)
        task_name = runtime.normalize_task(getattr(task, "name", None))
        span = runtime.tracer.start_span(
            f"celery {task_name}", context=parent, kind=SpanKind.CONSUMER
        )
        span_token = otel_context.attach(trace.set_span_in_context(span, parent))
        diagnostic_tokens = bind_diagnostic_context(request_id, correlation_id, "workstream-celery")
        _ACTIVE_TASKS[key] = _TaskObservation(
            span=span,
            span_token=span_token,
            diagnostic_tokens=diagnostic_tokens,
            runtime=runtime,
            task_name=task_name,
            started=monotonic(),
        )
    except Exception:
        logging.getLogger(__name__).error("observability_export_unavailable")
        if diagnostic_tokens is not None:
            try:
                reset_diagnostic_context(diagnostic_tokens)
            except Exception:
                clear_diagnostic_context()
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
        clear_diagnostic_context()


def _finish_task(observation: _TaskObservation, outcome: str) -> None:
    normalized_outcome = outcome if outcome in _TASK_OUTCOMES else "other"
    attributes = {
        "messaging.destination.name": observation.task_name,
        "workstream.outcome": normalized_outcome,
    }
    try:
        observation.span.set_attribute("messaging.destination.name", observation.task_name)
        observation.span.set_attribute("workstream.outcome", normalized_outcome)
        request_id, correlation_id = current_diagnostic_ids()
        if request_id is not None:
            observation.span.set_attribute("workstream.request_id", request_id)
        if correlation_id is not None:
            observation.span.set_attribute("workstream.correlation_id", correlation_id)
        if normalized_outcome == "failure":
            observation.span.set_status(Status(StatusCode.ERROR))
        if observation.runtime.task_duration is not None:
            observation.runtime.task_duration.record(monotonic() - observation.started, attributes)
    except Exception:
        logging.getLogger(__name__).error("observability_export_unavailable")
    finally:
        try:
            reset_diagnostic_context(observation.diagnostic_tokens)
        except Exception:
            clear_diagnostic_context()
        try:
            otel_context.detach(observation.span_token)
        except Exception:
            pass
        try:
            observation.span.end()
        except Exception:
            pass
        clear_diagnostic_context()


def _complete_task(task_id: object, outcome: str) -> None:
    observation = _ACTIVE_TASKS.pop(_task_key(task_id), None)
    if observation is None:
        clear_diagnostic_context()
        return
    _finish_task(observation, outcome)


def _task_postrun(task_id: object = None, state: object = None, **_kwargs: object) -> None:
    outcome = "success" if state == "SUCCESS" else "failure" if state == "FAILURE" else "other"
    _complete_task(task_id, outcome)


def _task_failure(task_id: object = None, **_kwargs: object) -> None:
    _complete_task(task_id, "failure")


def _task_retry(request: object = None, **_kwargs: object) -> None:
    _complete_task(getattr(request, "id", None), "retry")
