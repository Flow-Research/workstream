"""Secret-safe MCP boundary observability helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import time
from typing import Any, Awaitable, Callable

from workstream_mcp.auth import RequestContext


LOGGER = logging.getLogger(__name__)


async def observe_operation(
    context: RequestContext,
    *,
    kind: str,
    identifier: str,
    action: Callable[[], Awaitable[dict[str, Any]]],
    request_id: str | None = None,
) -> dict[str, Any]:
    """Run one MCP operation and log only safe operational metadata."""
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    try:
        result = await action()
    except Exception:
        _log_operation(
            context,
            kind=kind,
            identifier=identifier,
            request_id=request_id,
            started_at=started_at,
            started=started,
            outcome="unexpected_server_error",
            outcome_class="infrastructure_error",
            retryable=False,
            idempotent_replay=None,
        )
        raise
    error = result.get("error") if isinstance(result, dict) else None
    if isinstance(error, dict):
        outcome = error.get("code", "unexpected_server_error")
        retryable = bool(error.get("retryable", False))
        outcome_class = _error_outcome_class(str(outcome))
    else:
        outcome = result.get("outcome", "read")
        retryable = False
        outcome_class = "success"
    _log_operation(
        context,
        kind=kind,
        identifier=identifier,
        request_id=request_id,
        started_at=started_at,
        started=started,
        outcome=str(outcome),
        outcome_class=outcome_class,
        retryable=retryable,
        idempotent_replay=_find_replay_marker(result),
    )
    return result


def _log_operation(
    context: RequestContext,
    *,
    kind: str,
    identifier: str,
    request_id: str | None,
    started_at: str,
    started: float,
    outcome: str,
    outcome_class: str,
    retryable: bool,
    idempotent_replay: bool | None,
) -> None:
    """Emit one secret-safe operation record."""
    LOGGER.info(
        "workstream_mcp_operation",
        extra={
            "transport": context.transport,
            "mcp_kind": kind,
            "mcp_identifier": identifier,
            "correlation_id": context.correlation_id,
            "request_id": request_id,
            "started_at": started_at,
            "outcome": outcome,
            "outcome_class": outcome_class,
            "retryable": retryable,
            "idempotent_replay": idempotent_replay,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )


def _error_outcome_class(code: str) -> str:
    """Classify a stable MCP error without inspecting request or response bodies."""
    if code in {"workstream_temporarily_unavailable", "unexpected_server_error"}:
        return "infrastructure_error"
    if code in {"authentication_required", "invalid_token"}:
        return "authentication_error"
    if code in {"project_access_denied", "capability_not_granted"}:
        return "authorization_error"
    return "domain_error"


def _find_replay_marker(value: Any) -> bool | None:
    """Read an explicit backend replay marker without inferring hidden state."""
    if isinstance(value, dict):
        marker = value.get("idempotent_replay")
        if isinstance(marker, bool):
            return marker
        for nested in value.values():
            found = _find_replay_marker(nested)
            if found is not None:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_replay_marker(nested)
            if found is not None:
                return found
    return None
