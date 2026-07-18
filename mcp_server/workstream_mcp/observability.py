"""Secret-safe MCP boundary observability helpers."""

from __future__ import annotations

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
    started = time.perf_counter()
    result = await action()
    error = result.get("error") if isinstance(result, dict) else None
    outcome = error.get("code") if isinstance(error, dict) else result.get("outcome", "read")
    LOGGER.info(
        "workstream_mcp_operation",
        extra={
            "transport": context.transport,
            "mcp_kind": kind,
            "mcp_identifier": identifier,
            "correlation_id": context.correlation_id,
            "request_id": request_id,
            "outcome": outcome,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return result
