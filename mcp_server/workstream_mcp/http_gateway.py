"""HTTP gateway for currently available Workstream APIs."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from workstream_mcp.auth import (
    RequestContext,
    authorization_headers,
    contains_context_secret,
)
from workstream_mcp.errors import (
    MCPErrorCode,
    WorkstreamMCPError,
    map_http_error_response,
    map_http_status,
)
from workstream_mcp.schemas import normalize_stable_ref


class HTTPContributorGateway:
    """Contributor gateway backed by Workstream's public HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create an HTTP gateway.

        Args:
            base_url: Workstream API root without trailing slash.
            timeout_seconds: HTTP timeout for Workstream calls.
            transport: Optional test transport.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    async def get_my_projects(self, context: RequestContext) -> dict[str, Any]:
        """Return project capabilities through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "my_projects")

    async def get_my_contributions(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return contribution records through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "my_contributions")

    async def list_tasks(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return contributor task views through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "tasks")

    async def get_task_context(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return task context by composing available Workstream task APIs."""
        task_segment = _path_segment(task_id, context)
        task = await self._request(context, "GET", f"/api/v1/tasks/{task_segment}")
        work_context = await self._request(
            context,
            "GET",
            f"/api/v1/tasks/{task_segment}/work-context",
        )
        requirements = await self._request(
            context,
            "GET",
            f"/api/v1/tasks/{task_segment}/submission-requirements",
        )
        submissions = await self._request(
            context,
            "GET",
            f"/api/v1/tasks/{task_segment}/submissions",
        )
        return {
            "task": task,
            "work_context": work_context,
            "submission_requirements": requirements,
            "submissions": submissions,
        }

    async def get_task_status(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return actor-facing task status from available task and submission APIs."""
        task_segment = _path_segment(task_id, context)
        task = await self._request(context, "GET", f"/api/v1/tasks/{task_segment}")
        submissions = await self._request(
            context,
            "GET",
            f"/api/v1/tasks/{task_segment}/submissions",
        )
        latest_submission = (
            submissions[-1] if isinstance(submissions, list) and submissions else None
        )
        checker_runs: list[dict[str, Any]] = []
        if latest_submission and latest_submission.get("id"):
            checker_runs = await self._request(
                context,
                "GET",
                f"/api/v1/submissions/{_path_segment(str(latest_submission['id']), context)}/checker-runs",
            )
        return {
            "task_id": task_id,
            "task": task,
            "latest_submission": latest_submission,
            "checker_runs": checker_runs,
            "next_resource": f"workstream://tasks/{task_id}/context"
            if task.get("status") == "needs_revision"
            else None,
        }

    async def claim_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Use a complete temporary adapter until Workstream merges claim and start."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "claim_task")

    async def release_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
        reason: str | None,
    ) -> dict[str, Any]:
        """Use a complete temporary adapter until contributor release is available."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "release_task")

    async def run_pre_submit_check(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Run non-authoritative pre-submit checks."""
        task_segment = _path_segment(task_id, context)
        return await self._request(
            context,
            "POST",
            f"/api/v1/tasks/{task_segment}/submission-precheck",
            request_id=request_id,
            json={"submission": submission},
        )

    async def submit_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Use a complete temporary adapter until submissions have durable request idempotency."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "submit_task")

    async def get_current_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
    ) -> dict[str, Any]:
        """Return current review through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "current_review")

    async def get_review_context(
        self,
        context: RequestContext,
        *,
        review_ref: str,
    ) -> dict[str, Any]:
        """Return review context through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "review_context")

    async def claim_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
        review_routing_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Claim current review through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "claim_review")

    async def release_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Release current review through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "release_review")

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
        """Submit a review decision through an explicitly injected temporary gateway."""
        await self._require_authoritative_identity(context)
        raise _missing_backend_api(context, "submit_review")

    async def _require_authoritative_identity(self, context: RequestContext) -> None:
        """Ask Workstream Auth to validate identity before a fail-closed response."""
        await self._request(context, "GET", "/api/v1/auth/me")

    async def _request(
        self,
        context: RequestContext,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Send one Workstream HTTP request and return decoded JSON."""
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
            trust_env=False,
        ) as client:
            try:
                response = await client.request(
                    method,
                    path,
                    headers=authorization_headers(context, request_id=request_id),
                    json=json,
                )
            except httpx.HTTPError as exc:
                raise WorkstreamMCPError(
                    map_http_status(503, correlation_id=context.correlation_id).code,
                    "Workstream is temporarily unavailable.",
                    retryable=True,
                    correlation_id=context.correlation_id,
                ) from exc
        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = None
            raise map_http_error_response(
                response.status_code,
                error_payload,
                correlation_id=context.correlation_id,
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise WorkstreamMCPError(
                MCPErrorCode.UNEXPECTED_SERVER_ERROR,
                "Workstream returned an invalid response.",
                correlation_id=context.correlation_id,
            ) from exc


def _missing_backend_api(context: RequestContext, surface: str) -> WorkstreamMCPError:
    """Fail closed when a WS-MCP surface has no current Workstream API."""
    return WorkstreamMCPError(
        MCPErrorCode.WORKSTREAM_TEMPORARILY_UNAVAILABLE,
        "This MCP surface is waiting on a Workstream backend API.",
        retryable=False,
        correlation_id=context.correlation_id,
        details={"surface": surface, "backend_api_required": True},
    )


def _path_segment(value: str, context: RequestContext) -> str:
    """Encode one opaque Workstream reference without allowing path traversal."""
    if contains_context_secret(value, context):
        raise WorkstreamMCPError(
            MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE,
            "The requested Workstream resource was not found or is not visible.",
            correlation_id=context.correlation_id,
        )
    return quote(normalize_stable_ref(value, "reference"), safe="")
