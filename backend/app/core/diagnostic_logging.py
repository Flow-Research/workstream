"""Closed structured logging and context-local diagnostic identifiers."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import sys
from threading import Lock
from uuid import RFC_4122, UUID

from opentelemetry import trace

from app.core.config import Settings

_SAFE_WORKSTREAM_MESSAGES = {
    "request_failed_after_response_start": "request_failed_after_response_start",
    "request_failed_before_response_start": "request_failed_before_response_start",
    "authorization actor resolution failed": "authorization_actor_resolution_failed",
    "authorization decision transaction failed": "authorization_decision_transaction_failed",
    "prepared authorization transaction failed": "prepared_authorization_transaction_failed",
    "auth_verifier_metric %s": "auth_verifier_metric",
    "artifact_admission_metric %s": "artifact_admission_metric",
    "project setup pipeline enqueue failed after commit": "project_setup_enqueue_failed",
    "project setup queue accepted the wrong task identity": "project_setup_identity_mismatch",
    "project guide compilation stopped": "project_guide_compilation_stopped",
    "guide resource cleanup configuration rejected": "guide_resource_cleanup_rejected",
    "outbox delivery unavailable": "outbox_delivery_unavailable",
    "outbox discovery unavailable": "outbox_discovery_unavailable",
    "outbox publication unavailable": "outbox_publication_unavailable",
    "outbox continuation unavailable": "outbox_continuation_unavailable",
    "post-policy derivation unavailable": "post_policy_derivation_unavailable",
    "post-policy recovery scan unavailable": "post_policy_recovery_unavailable",
    "post-policy publication unavailable; approval retained for recovery": (
        "post_policy_publication_unavailable"
    ),
    "observability_export_unavailable": "observability_export_unavailable",
}
_THIRD_PARTY_LOG_FAMILIES = (
    "uvicorn",
    "celery",
    "kombu",
    "opentelemetry",
    "sqlalchemy",
)
_OWNED_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
    "celery",
    "celery.task",
    "celery.worker",
    "celery.worker.strategy",
    "celery.app.trace",
    "celery.redirected",
    "kombu",
    "opentelemetry",
    "sqlalchemy",
)
_REQUEST_ID: ContextVar[str | None] = ContextVar("diagnostic_request_id", default=None)
_CORRELATION_ID: ContextVar[str | None] = ContextVar("diagnostic_correlation_id", default=None)
_SERVICE_NAME: ContextVar[str | None] = ContextVar("diagnostic_service_name", default=None)
_LOGGING_LOCK = Lock()
_LOGGING_OWNERS = 0
_LOGGING_SNAPSHOT: dict[str, tuple[list[logging.Handler], bool, int]] = {}
_SAFE_HANDLER: logging.Handler | None = None
_PROCESS_SERVICE_NAME: str | None = None
_SERVICE_NAMES = frozenset({"workstream-api", "workstream-celery"})


def canonical_uuid_text(value: object) -> str | None:
    """Return one canonical nonzero RFC UUID string or ``None``."""
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    if (
        parsed.int == 0
        or parsed.variant != RFC_4122
        or parsed.version not in range(1, 9)
        or str(parsed) != value
    ):
        return None
    return value


@dataclass(frozen=True)
class DiagnosticContextTokens:
    """Tokens owned by exactly one request or worker task."""

    request_id: Token[str | None]
    correlation_id: Token[str | None]
    service_name: Token[str | None]


def bind_diagnostic_context(
    request_id: str, correlation_id: str, service_name: str
) -> DiagnosticContextTokens:
    """Bind already validated diagnostic identifiers for one execution context."""
    return DiagnosticContextTokens(
        request_id=_REQUEST_ID.set(request_id),
        correlation_id=_CORRELATION_ID.set(correlation_id),
        service_name=_SERVICE_NAME.set(service_name),
    )


def reset_diagnostic_context(tokens: DiagnosticContextTokens) -> None:
    """Reset only tokens created by the current execution context."""
    _SERVICE_NAME.reset(tokens.service_name)
    _CORRELATION_ID.reset(tokens.correlation_id)
    _REQUEST_ID.reset(tokens.request_id)


def clear_diagnostic_context() -> None:
    """Clear abandoned child state before accepting another worker task."""
    _REQUEST_ID.set(None)
    _CORRELATION_ID.set(None)
    _SERVICE_NAME.set(None)


def current_diagnostic_ids() -> tuple[str | None, str | None]:
    """Return only canonical IDs from the current execution context."""
    return canonical_uuid_text(_REQUEST_ID.get()), canonical_uuid_text(_CORRELATION_ID.get())


class SafeJsonFormatter(logging.Formatter):
    """Format a closed diagnostic record without rendering its message or exception."""

    def __init__(self, environment: str, service_name: str) -> None:
        super().__init__()
        self._environment = environment
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        severity = (
            record.levelname
            if record.levelname in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            else "INFO"
        )
        value: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "service": _SERVICE_NAME.get() or self._service_name,
            "environment": self._environment,
            "severity": severity,
            "event": self._event(record, severity.lower()),
        }
        request_id, correlation_id = current_diagnostic_ids()
        if request_id is not None:
            value["request_id"] = request_id
        if correlation_id is not None:
            value["correlation_id"] = correlation_id
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            value["trace_id"] = trace.format_trace_id(span_context.trace_id)
            value["span_id"] = trace.format_span_id(span_context.span_id)
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _event(record: logging.LogRecord, severity: str) -> str:
        if record.name.startswith("app.") and isinstance(record.msg, str):
            known = _SAFE_WORKSTREAM_MESSAGES.get(record.msg)
            return known if known is not None else f"workstream.{severity}"
        for family in _THIRD_PARTY_LOG_FAMILIES:
            if record.name == family or record.name.startswith(f"{family}."):
                return f"{family}.{severity}"
        return f"external.{severity}"


def _logging_targets() -> tuple[logging.Logger, ...]:
    return (logging.getLogger(),) + tuple(logging.getLogger(name) for name in _OWNED_LOGGERS)


def acquire_safe_logging(settings: Settings, service_name: str) -> None:
    """Acquire one process-wide safe logging lease."""
    global _LOGGING_OWNERS, _PROCESS_SERVICE_NAME, _SAFE_HANDLER
    if service_name not in _SERVICE_NAMES:
        raise ValueError("invalid diagnostic process service")
    with _LOGGING_LOCK:
        if _LOGGING_OWNERS == 0:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(SafeJsonFormatter(settings.environment, service_name))
            handler.setLevel(getattr(logging, settings.observability_log_level))
            _PROCESS_SERVICE_NAME = service_name
            _SAFE_HANDLER = handler
            for logger in _logging_targets():
                key = logger.name or "root"
                _LOGGING_SNAPSHOT[key] = (list(logger.handlers), logger.propagate, logger.level)
                logger.handlers = [handler]
                logger.propagate = False
                logger.setLevel(getattr(logging, settings.observability_log_level))
        elif _PROCESS_SERVICE_NAME != service_name:
            raise ValueError("conflicting diagnostic process service")
        _LOGGING_OWNERS += 1


def release_safe_logging() -> None:
    """Release one lease, restoring prior logging only after the last owner."""
    global _LOGGING_OWNERS, _PROCESS_SERVICE_NAME, _SAFE_HANDLER
    with _LOGGING_LOCK:
        if _LOGGING_OWNERS == 0:
            return
        _LOGGING_OWNERS -= 1
        if _LOGGING_OWNERS != 0:
            return
        for logger in _logging_targets():
            key = logger.name or "root"
            handlers, propagate, level = _LOGGING_SNAPSHOT.pop(key)
            logger.handlers = handlers
            logger.propagate = propagate
            logger.setLevel(level)
        _PROCESS_SERVICE_NAME = None
        _SAFE_HANDLER = None


def safe_handler() -> logging.Handler | None:
    """Return the installed handler for focused operational tests."""
    with _LOGGING_LOCK:
        return _SAFE_HANDLER
