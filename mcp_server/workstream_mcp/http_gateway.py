"""HTTP gateway for currently available Workstream APIs."""

from __future__ import annotations

from typing import Any

import httpx

from workstream_mcp.auth import RequestContext, authorization_headers
from workstream_mcp.errors import (
    MCPErrorCode,
    WorkstreamMCPError,
    map_http_error_response,
    map_http_status,
)
from workstream_mcp.gateway import ContributorGateway


class HTTPContributorGateway:
    """Contributor gateway backed by Workstream's public HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        fallback: ContributorGateway | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create an HTTP gateway.

        Args:
            base_url: Workstream API root without trailing slash.
            timeout_seconds: HTTP timeout for Workstream calls.
            fallback: Explicit temporary gateway for unavailable APIs. Defaults
                to fail-closed behavior so runtime HTTP mode never serves
                scenario data by accident.
            transport: Optional test transport.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._fallback = fallback
        self._transport = transport

    async def get_my_projects(self, context: RequestContext) -> dict[str, Any]:
        """Return project capabilities through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "my_projects")
        return await self._fallback.get_my_projects(context)

    async def get_my_contributions(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return contribution records through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "my_contributions")
        return await self._fallback.get_my_contributions(context, project_id=project_id)

    async def list_tasks(
        self,
        context: RequestContext,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Return contributor task views through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "tasks")
        return await self._fallback.list_tasks(context, project_id=project_id)

    async def get_task_context(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return task context by composing available Workstream task APIs."""
        task = await self._request(context, "GET", f"/api/v1/tasks/{task_id}")
        work_context = await self._request(context, "GET", f"/api/v1/tasks/{task_id}/work-context")
        requirements = await self._request(
            context,
            "GET",
            f"/api/v1/tasks/{task_id}/submission-requirements",
        )
        submissions = await self._request(context, "GET", f"/api/v1/tasks/{task_id}/submissions")
        return {
            "task": task,
            "work_context": work_context,
            "submission_requirements": requirements,
            "submissions": submissions,
        }

    async def get_task_status(self, context: RequestContext, *, task_id: str) -> dict[str, Any]:
        """Return actor-facing task status from available task and submission APIs."""
        task = await self._request(context, "GET", f"/api/v1/tasks/{task_id}")
        submissions = await self._request(context, "GET", f"/api/v1/tasks/{task_id}/submissions")
        latest_submission = (
            submissions[-1] if isinstance(submissions, list) and submissions else None
        )
        checker_runs: list[dict[str, Any]] = []
        if latest_submission and latest_submission.get("id"):
            checker_runs = await self._request(
                context,
                "GET",
                f"/api/v1/submissions/{latest_submission['id']}/checker-runs",
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
        if self._fallback is None:
            raise _missing_backend_api(context, "claim_task")
        return await self._fallback.claim_task(context, task_id=task_id, request_id=request_id)

    async def release_task(
        self,
        context: RequestContext,
        *,
        task_id: str,
        request_id: str,
        reason: str | None,
    ) -> dict[str, Any]:
        """Use a complete temporary adapter until contributor release is available."""
        if self._fallback is None:
            raise _missing_backend_api(context, "release_task")
        return await self._fallback.release_task(
            context,
            task_id=task_id,
            request_id=request_id,
            reason=reason,
        )

    async def run_pre_submit_check(
        self,
        context: RequestContext,
        *,
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        """Run non-authoritative pre-submit checks."""
        return await self._request(
            context,
            "POST",
            f"/api/v1/tasks/{task_id}/submission-precheck",
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
        if self._fallback is None:
            raise _missing_backend_api(context, "submit_task")
        return await self._fallback.submit_task(
            context,
            task_id=task_id,
            submission=submission,
            request_id=request_id,
        )

    async def get_current_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
    ) -> dict[str, Any]:
        """Return current review through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "current_review")
        return await self._fallback.get_current_review(context, project_id=project_id)

    async def get_review_context(
        self,
        context: RequestContext,
        *,
        review_ref: str,
    ) -> dict[str, Any]:
        """Return review context through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "review_context")
        return await self._fallback.get_review_context(context, review_ref=review_ref)

    async def claim_review(
        self,
        context: RequestContext,
        *,
        project_id: str,
        review_routing_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Claim current review through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "claim_review")
        return await self._fallback.claim_review(
            context,
            project_id=project_id,
            review_routing_ref=review_routing_ref,
            request_id=request_id,
        )

    async def release_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Release current review through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "release_review")
        return await self._fallback.release_review(
            context,
            review_ref=review_ref,
            request_id=request_id,
        )

    async def submit_review(
        self,
        context: RequestContext,
        *,
        review_ref: str,
        decision: str,
        findings: list[dict[str, Any]],
        request_id: str,
    ) -> dict[str, Any]:
        """Submit a review decision through an explicitly injected temporary gateway."""
        if self._fallback is None:
            raise _missing_backend_api(context, "submit_review")
        return await self._fallback.submit_review(
            context,
            review_ref=review_ref,
            decision=decision,
            findings=findings,
            request_id=request_id,
        )

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
        details={"surface": surface, "temporary_gateway_required": True},
    )
