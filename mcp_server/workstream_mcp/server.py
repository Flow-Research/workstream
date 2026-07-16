"""MCP server registration for the Workstream contributor surface."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from uuid import uuid4

from workstream_mcp.auth import (
    RequestContext,
    WorkstreamForwardingTokenVerifier,
    context_from_mcp_access_token,
    context_from_stdio_environment,
)
from workstream_mcp.config import WorkstreamMCPConfig
from workstream_mcp.gateway import ContributorGateway
from workstream_mcp.http_gateway import HTTPContributorGateway
from workstream_mcp.scenario_gateway import ScenarioContributorGateway
import workstream_mcp.resources as resources
import workstream_mcp.tools as tools
from workstream_mcp.schemas import MCP_PROMPTS, RESOURCE_DEFINITIONS, TOOL_DEFINITIONS


@dataclass(frozen=True, slots=True)
class WorkstreamMCPApplication:
    """Testable application object for the contributor MCP surface."""

    gateway: ContributorGateway

    @property
    def resources(self) -> tuple[Any, ...]:
        """Return the closed resource catalogue."""
        return RESOURCE_DEFINITIONS

    @property
    def tools(self) -> tuple[Any, ...]:
        """Return the closed tool catalogue."""
        return TOOL_DEFINITIONS

    @property
    def prompts(self) -> tuple[str, ...]:
        """Return the closed prompt catalogue."""
        return MCP_PROMPTS


def create_mcp_application(
    gateway: ContributorGateway | None = None,
    *,
    config: WorkstreamMCPConfig | None = None,
) -> WorkstreamMCPApplication:
    """Create the testable MCP application surface."""
    resolved_config = config or WorkstreamMCPConfig.from_environment()
    if gateway is not None:
        resolved_gateway = gateway
    elif resolved_config.gateway_mode == "scenario":
        resolved_gateway = ScenarioContributorGateway()
    else:
        resolved_gateway = HTTPContributorGateway(
            base_url=resolved_config.workstream_api_base_url,
            timeout_seconds=resolved_config.request_timeout_seconds,
        )
    return WorkstreamMCPApplication(gateway=resolved_gateway)


def build_fastmcp_server(
    gateway: ContributorGateway | None = None,
    *,
    config: WorkstreamMCPConfig | None = None,
) -> Any:
    """Build a FastMCP server when the official MCP SDK is installed."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.auth.middleware.auth_context import get_access_token
        from mcp.server.auth.settings import AuthSettings
    except ImportError as exc:
        raise RuntimeError("Install the mcp package to run the Workstream MCP server") from exc

    app = create_mcp_application(gateway, config=config)
    server = FastMCP(
        "workstream-contributor",
        auth=AuthSettings(
            issuer_url=os.environ.get(
                "WORKSTREAM_MCP_AUTH_ISSUER_URL",
                "http://workstream.local",
            ),
            resource_server_url=None,
        ),
        token_verifier=WorkstreamForwardingTokenVerifier(),
    )

    def context() -> RequestContext:
        access_token = get_access_token()
        if access_token is not None:
            return context_from_mcp_access_token(
                access_token,
                correlation_id=str(uuid4()),
            )
        return context_from_stdio_environment(correlation_id=str(uuid4()))

    @server.resource("workstream://me/projects")
    async def my_projects() -> dict[str, Any]:
        return await resources.read_my_projects(app.gateway, context())

    @server.resource("workstream://me/contributions")
    async def my_contributions() -> dict[str, Any]:
        return await resources.read_my_contributions(app.gateway, context())

    @server.resource("workstream://me/contributions/projects/{project_id}")
    async def project_contributions(project_id: str) -> dict[str, Any]:
        return await resources.read_my_contributions(app.gateway, context(), project_id=project_id)

    @server.resource("workstream://tasks")
    async def task_list() -> dict[str, Any]:
        return await resources.read_tasks(app.gateway, context())

    @server.resource("workstream://projects/{project_id}/tasks")
    async def project_task_list(project_id: str) -> dict[str, Any]:
        return await resources.read_tasks(app.gateway, context(), project_id=project_id)

    @server.resource("workstream://tasks/{task_id}/context")
    async def task_context(task_id: str) -> dict[str, Any]:
        return await resources.read_task_context(app.gateway, context(), task_id=task_id)

    @server.resource("workstream://tasks/{task_id}/status")
    async def task_status(task_id: str) -> dict[str, Any]:
        return await resources.read_task_status(app.gateway, context(), task_id=task_id)

    @server.resource("workstream://projects/{project_id}/current-review")
    async def current_review(project_id: str) -> dict[str, Any]:
        return await resources.read_current_review(app.gateway, context(), project_id=project_id)

    @server.resource("workstream://reviews/{review_ref}/context")
    async def review_context(review_ref: str) -> dict[str, Any]:
        return await resources.read_review_context(app.gateway, context(), review_ref=review_ref)

    @server.tool()
    async def claim_task(task_id: str, request_id: str) -> dict[str, Any]:
        return await tools.claim_task(
            app.gateway,
            context(),
            task_id=task_id,
            request_id=request_id,
        )

    @server.tool()
    async def release_task(
        task_id: str,
        request_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return await tools.release_task(
            app.gateway,
            context(),
            task_id=task_id,
            request_id=request_id,
            reason=reason,
        )

    @server.tool()
    async def run_pre_submit_check(
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        return await tools.run_pre_submit_check(
            app.gateway,
            context(),
            task_id=task_id,
            submission=submission,
            request_id=request_id,
        )

    @server.tool()
    async def submit_task(
        task_id: str,
        submission: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        return await tools.submit_task(
            app.gateway,
            context(),
            task_id=task_id,
            submission=submission,
            request_id=request_id,
        )

    @server.tool()
    async def claim_review(
        project_id: str,
        review_routing_ref: str,
        request_id: str,
    ) -> dict[str, Any]:
        return await tools.claim_review(
            app.gateway,
            context(),
            project_id=project_id,
            review_routing_ref=review_routing_ref,
            request_id=request_id,
        )

    @server.tool()
    async def release_review(review_ref: str, request_id: str) -> dict[str, Any]:
        return await tools.release_review(
            app.gateway,
            context(),
            review_ref=review_ref,
            request_id=request_id,
        )

    @server.tool()
    async def submit_review(
        review_ref: str,
        decision: str,
        findings: list[dict[str, Any]],
        request_id: str,
    ) -> dict[str, Any]:
        return await tools.submit_review(
            app.gateway,
            context(),
            review_ref=review_ref,
            decision=decision,
            findings=findings,
            request_id=request_id,
        )

    return server


def main() -> None:
    """Run the Workstream contributor MCP server."""
    transport = os.environ.get("WORKSTREAM_MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise RuntimeError("WORKSTREAM_MCP_TRANSPORT must be stdio, sse, or streamable-http")
    build_fastmcp_server().run(transport=transport)  # type: ignore[arg-type]
