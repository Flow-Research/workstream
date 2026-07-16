"""Read-only MCP resource handlers."""

from __future__ import annotations

from typing import Any

from workstream_mcp.auth import RequestContext, redact_context_secrets
from workstream_mcp.errors import WorkstreamMCPError
from workstream_mcp.gateway import ContributorGateway


async def read_my_projects(
    gateway: ContributorGateway,
    context: RequestContext,
) -> dict[str, Any]:
    """Read approved projects and contributor capabilities."""
    return await _safe_resource(gateway.get_my_projects(context), context)


async def read_my_contributions(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read current actor contribution records."""
    return await _safe_resource(
        gateway.get_my_contributions(context, project_id=project_id), context
    )


async def read_tasks(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read contributor task views without claiming work."""
    return await _safe_resource(gateway.list_tasks(context, project_id=project_id), context)


async def read_task_context(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
) -> dict[str, Any]:
    """Read locked task context for initial work or revision work."""
    return await _safe_resource(gateway.get_task_context(context, task_id=task_id), context)


async def read_task_status(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    task_id: str,
) -> dict[str, Any]:
    """Read poll-safe task status."""
    return await _safe_resource(gateway.get_task_status(context, task_id=task_id), context)


async def read_current_review(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Read the one current review visible to a Reviewer."""
    return await _safe_resource(gateway.get_current_review(context, project_id=project_id), context)


async def read_review_context(
    gateway: ContributorGateway,
    context: RequestContext,
    *,
    review_ref: str,
) -> dict[str, Any]:
    """Read context for a currently leased review."""
    return await _safe_resource(gateway.get_review_context(context, review_ref=review_ref), context)


async def _safe_resource(awaitable: Any, context: RequestContext) -> dict[str, Any]:
    """Convert WorkstreamMCPError into structured resource output."""
    try:
        return redact_context_secrets(await awaitable, context)
    except WorkstreamMCPError as exc:
        return redact_context_secrets(exc.to_result(), context)
