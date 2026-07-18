"""Read-only MCP resource handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from workstream_mcp.auth import RequestContext, redact_context_secrets
from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError, unexpected_server_error
from workstream_mcp.gateway import ContributorGateway
from workstream_mcp.schemas import normalize_stable_ref


async def read_my_projects(
    gateway: ContributorGateway,
    context: RequestContext,
) -> dict[str, Any]:
    """Read approved projects and contributor capabilities."""
    return await _safe_resource(lambda: gateway.get_my_projects(context), context)


async def read_my_contributions(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read current actor contribution records."""
    return await _safe_resource(
        lambda: gateway.get_my_contributions(
            context,
            project_id=_optional_resource_ref(project_id, "project_id", context),
        ),
        context,
    )


async def read_tasks(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read contributor task views without claiming work."""
    return await _safe_resource(
        lambda: gateway.list_tasks(
            context,
            project_id=_optional_resource_ref(project_id, "project_id", context),
        ),
        context,
    )


async def read_task_context(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
) -> dict[str, Any]:
    """Read locked task context for initial work or revision work."""
    return await _safe_resource(
        lambda: gateway.get_task_context(
            context,
            task_id=_resource_ref(task_id, "task_id", context),
        ),
        context,
    )


async def read_task_status(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
) -> dict[str, Any]:
    """Read poll-safe task status."""
    return await _safe_resource(
        lambda: gateway.get_task_status(
            context,
            task_id=_resource_ref(task_id, "task_id", context),
        ),
        context,
    )


async def read_current_review(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Read the one current review visible to a Reviewer."""
    return await _safe_resource(
        lambda: gateway.get_current_review(
            context,
            project_id=_resource_ref(project_id, "project_id", context),
        ),
        context,
    )


async def read_review_context(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    review_ref: str,
) -> dict[str, Any]:
    """Read context for a currently leased review."""
    return await _safe_resource(
        lambda: gateway.get_review_context(
            context,
            review_ref=_resource_ref(review_ref, "review_ref", context),
        ),
        context,
    )


async def _safe_resource(
    action: Callable[[], Awaitable[dict[str, Any]]],
    context: RequestContext,
) -> dict[str, Any]:
    """Convert WorkstreamMCPError into structured resource output."""
    try:
        return redact_context_secrets(await action(), context)
    except WorkstreamMCPError as exc:
        return redact_context_secrets(exc.to_result(), context)
    except Exception:
        return redact_context_secrets(
            unexpected_server_error(correlation_id=context.correlation_id).to_result(),
            context,
        )


def _optional_resource_ref(
    value: str | None,
    field_name: str,
    context: RequestContext,
) -> str | None:
    """Validate an optional resource URI path segment."""
    if value is None:
        return None
    return _resource_ref(value, field_name, context)


def _resource_ref(value: str, field_name: str, context: RequestContext) -> str:
    """Convert malformed resource references to the non-disclosing resource error."""
    try:
        return normalize_stable_ref(value, field_name)
    except ValueError as exc:
        raise WorkstreamMCPError(
            MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE,
            "The requested Workstream resource was not found or is not visible.",
            correlation_id=context.correlation_id,
        ) from exc
