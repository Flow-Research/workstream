"""Contributor gateway interface used by MCP resources and tools."""

from __future__ import annotations

from typing import Any, Protocol

from workstream_mcp.auth import RequestContext


class ContributorGateway(Protocol):
    """Typed contributor operations required by WS-MCP-001."""

    async def get_my_projects(self, context: RequestContext) -> dict[str, Any]:
        """Return projects visible to the current contributor."""

    async def get_my_contributions(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return contribution records visible to the current contributor."""

    async def list_tasks(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return task views visible to a Submitter."""

    async def get_task_context(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return locked task context and submission requirements."""

    async def get_task_status(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return current actor-facing task status."""

    async def claim_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Claim an available task."""

    async def release_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
        reason: str | None,
    ) -> dict[str, Any]:
        """Release a task when Workstream permits it."""

    async def run_pre_submit_check(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Evaluate a candidate submission packet."""

    async def submit_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Submit an initial or revised task packet."""

    async def get_current_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
    ) -> dict[str, Any]:
        """Return the current review view for one project."""

    async def get_review_context(
        self,
        context: RequestContext,
        *,
        review_ref: str,
    ) -> dict[str, Any]:
        """Return context for the actor's leased review."""

    async def claim_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
        review_routing_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Claim the currently offered review."""

    async def release_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Release the actor's current review."""

    async def submit_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        decision: str,
        findings: list[dict[str, Any]],
        request_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Submit a human review decision."""
