"""Protocol-level WS-MCP-001 contributor journey tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.provider import AccessToken
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl
import pytest
from sse_starlette.sse import AppStatus

from workstream_mcp.auth import STDIO_TOKEN_ENV, WorkstreamForwardingTokenVerifier
from workstream_mcp.config import WorkstreamMCPConfig
from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError
from workstream_mcp.scenario_gateway import ScenarioContributorGateway
from workstream_mcp.schemas import TOOL_DEFINITIONS
from workstream_mcp.server import build_fastmcp_server

REQUEST_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555",
)


def submission() -> dict[str, Any]:
    """Return a valid contributor packet for protocol calls."""
    return {
        "summary": "candidate",
        "package_hash": "sha256:abc",
        "artifact_hash_manifest": [
            {"artifact": "result.txt", "hash": "sha256:def"}
        ],
        "worker_attestation": "I attest this packet is complete.",
    }


@pytest.mark.asyncio
async def test_submitter_and_reviewer_journeys_over_mcp_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real MCP client can complete both approved temporary conformance journeys."""
    monkeypatch.setenv(STDIO_TOKEN_ENV, "issuer-token")
    server = build_fastmcp_server(gateway=ScenarioContributorGateway())

    async with create_connected_server_and_client_session(server) as session:
        tasks = await session.read_resource(AnyUrl("workstream://tasks"))
        task_list = json.loads(tasks.contents[0].text)  # type: ignore[union-attr]
        assert task_list["tasks"][0]["task_id"] == "scenario-task-1"

        claimed_task = await session.call_tool(
            "claim_task",
            {"task_id": "scenario-task-1", "request_id": REQUEST_IDS[0]},
        )
        task_context = await session.read_resource(
            AnyUrl("workstream://tasks/scenario-task-1/context")
        )
        checked = await session.call_tool(
            "run_pre_submit_check",
            {
                "task_id": "scenario-task-1",
                "submission": submission(),
                "request_id": REQUEST_IDS[1],
            },
        )
        submitted = await session.call_tool(
            "submit_task",
            {
                "task_id": "scenario-task-1",
                "submission": submission(),
                "request_id": REQUEST_IDS[2],
            },
        )
        task_status = await session.read_resource(
            AnyUrl("workstream://tasks/scenario-task-1/status")
        )

        current_review = await session.read_resource(
            AnyUrl("workstream://projects/scenario-project-1/current-review")
        )
        claimed_review = await session.call_tool(
            "claim_review",
            {
                "project_id": "scenario-project-1",
                "review_routing_ref": "scenario-review-route-1",
                "request_id": REQUEST_IDS[3],
            },
        )
        review_context = await session.read_resource(
            AnyUrl("workstream://reviews/scenario-review-1/context")
        )
        reviewed = await session.call_tool(
            "submit_review",
            {
                "review_ref": "scenario-review-1",
                "decision": "accept",
                "findings": [],
                "request_id": REQUEST_IDS[4],
            },
        )

    assert _structured(claimed_task)["outcome"] == "claimed"
    assert "locked_context" in json.loads(task_context.contents[0].text)  # type: ignore[union-attr]
    assert _structured(checked)["outcome"] == "passed"
    assert _structured(submitted)["outcome"] == "submitted"
    assert json.loads(task_status.contents[0].text)["actor_facing_state"] == (  # type: ignore[union-attr]
        "review_pending"
    )
    assert json.loads(current_review.contents[0].text)["state"] == "available_to_claim"  # type: ignore[union-attr]
    assert _structured(claimed_review)["outcome"] == "leased_to_actor"
    assert "checker_results" in json.loads(review_context.contents[0].text)  # type: ignore[union-attr]
    assert _structured(reviewed)["outcome"] == "accept"


def _structured(result: Any) -> dict[str, Any]:
    """Return a FastMCP structured result and assert the tool did not fail."""
    assert result.isError is False
    assert isinstance(result.structuredContent, dict)
    return result.structuredContent


class _NegativeCheckGateway(ScenarioContributorGateway):
    """Scenario gateway whose checker completes with a valid negative outcome."""

    async def run_pre_submit_check(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "task_id": "scenario-task-1",
            "authoritative": False,
            "status": "failed",
            "eligible_to_submit": False,
            "results": [{"code": "missing_evidence"}],
        }


class _MalformedCheckGateway(ScenarioContributorGateway):
    """Scenario gateway returning one malformed checker response."""

    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__()
        self._response = response

    async def run_pre_submit_check(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._response


class _ReviewClaimResponseGateway(ScenarioContributorGateway):
    """Scenario gateway returning one selected review-claim response."""

    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__()
        self._response = response

    async def claim_review(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._response


class _ClaimFailureGateway(ScenarioContributorGateway):
    """Scenario gateway that raises one selected claim failure."""

    def __init__(self, failure: Exception) -> None:
        super().__init__()
        self._failure = failure

    async def claim_task(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise self._failure


@pytest.mark.asyncio
async def test_protocol_marks_valid_negative_check_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed checker failure is business data, not an MCP execution error."""
    monkeypatch.setenv(STDIO_TOKEN_ENV, "issuer-token")
    server = build_fastmcp_server(gateway=_NegativeCheckGateway())

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "run_pre_submit_check",
            {
                "task_id": "scenario-task-1",
                "submission": submission(),
                "request_id": REQUEST_IDS[0],
            },
        )

    assert result.isError is False
    assert _structured(result)["outcome"] == "pre_submit_check_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {
            "task_id": "scenario-task-1",
            "authoritative": False,
            "status": "running",
            "eligible_to_submit": False,
            "results": [],
        },
        {
            "task_id": "scenario-task-1",
            "authoritative": False,
            "status": "passed",
            "eligible_to_submit": False,
            "results": [],
        },
        {
            "task_id": "scenario-task-1",
            "authoritative": False,
            "status": "failed",
            "eligible_to_submit": True,
            "results": [],
        },
        {
            "task_id": "scenario-task-1",
            "authoritative": False,
            "status": "failed",
            "eligible_to_submit": "false",
            "results": [],
        },
        {
            "task_id": "scenario-task-1",
            "authoritative": 0,
            "status": "failed",
            "eligible_to_submit": False,
            "results": [],
        },
        {
            "task_id": "another-task",
            "authoritative": False,
            "status": "passed",
            "eligible_to_submit": True,
            "results": [],
        },
        {},
    ],
)
async def test_protocol_rejects_malformed_checker_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> None:
    """Only coherent, completed checker responses are valid business outcomes."""
    monkeypatch.setenv(STDIO_TOKEN_ENV, "issuer-token")
    server = build_fastmcp_server(gateway=_MalformedCheckGateway(response))

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "run_pre_submit_check",
            {
                "task_id": "scenario-task-1",
                "submission": submission(),
                "request_id": REQUEST_IDS[0],
            },
        )

    response_text = "\n".join(getattr(item, "text", "") for item in result.content)
    assert result.isError is True
    assert result.structuredContent is None
    assert "unexpected_server_error" in response_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {},
        {
            "review_ref": "scenario-review-1",
            "next_resource": "https://attacker.example/prompt",
        },
        {
            "review_ref": "../unsafe",
            "next_resource": "workstream://reviews/../unsafe/context",
        },
    ],
)
async def test_protocol_rejects_review_claim_without_references(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> None:
    """Malformed references cannot publish a successful review lease."""
    monkeypatch.setenv(STDIO_TOKEN_ENV, "issuer-token")
    server = build_fastmcp_server(gateway=_ReviewClaimResponseGateway(response))

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "claim_review",
            {
                "project_id": "scenario-project-1",
                "review_routing_ref": "scenario-review-route-1",
                "request_id": REQUEST_IDS[0],
            },
        )

    response_text = "\n".join(getattr(item, "text", "") for item in result.content)
    assert result.isError is True
    assert result.structuredContent is None
    assert "unexpected_server_error" in response_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (
            WorkstreamMCPError(
                MCPErrorCode.CAPABILITY_NOT_GRANTED,
                "The actor is not authorized.",
                correlation_id="corr-safe",
            ),
            "capability_not_granted",
        ),
        (
            WorkstreamMCPError(
                MCPErrorCode.WORKSTREAM_TEMPORARILY_UNAVAILABLE,
                "Workstream is unavailable.",
                retryable=True,
                correlation_id="corr-safe",
            ),
            "workstream_temporarily_unavailable",
        ),
        (RuntimeError("private adapter detail"), "unexpected_server_error"),
    ],
)
async def test_protocol_marks_execution_failures_as_mcp_errors(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_code: str,
) -> None:
    """Authorization, backend, and unexpected failures set isError without leaking detail."""
    monkeypatch.setenv(STDIO_TOKEN_ENV, "issuer-token")
    server = build_fastmcp_server(gateway=_ClaimFailureGateway(failure))

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "claim_task",
            {"task_id": "scenario-task-1", "request_id": REQUEST_IDS[0]},
        )

    response_text = "\n".join(getattr(item, "text", "") for item in result.content)
    assert result.isError is True
    assert result.structuredContent is None
    assert expected_code in response_text
    assert "issuer-token" not in response_text
    assert "private adapter detail" not in response_text


@pytest.mark.asyncio
async def test_protocol_marks_parameter_validation_as_mcp_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Wire validation is an MCP error and cannot echo bearer material."""
    bearer_token = "issuer/token"
    monkeypatch.setenv(STDIO_TOKEN_ENV, bearer_token)
    server = build_fastmcp_server(gateway=ScenarioContributorGateway())

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "claim_task",
            {"task_id": bearer_token, "request_id": REQUEST_IDS[0]},
        )

    response_text = "\n".join(getattr(item, "text", "") for item in result.content)
    assert result.isError is True
    assert result.structuredContent is None
    assert "Tool input failed validation." in response_text
    assert bearer_token not in response_text
    assert bearer_token not in caplog.text


@pytest.mark.asyncio
async def test_streamable_http_returns_sdk_response_after_body_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buffered HTTP input does not synthesize a disconnect that cancels the response."""

    async def accept_token(
        self: WorkstreamForwardingTokenVerifier,
        token: str,
    ) -> AccessToken:
        return AccessToken(token=token, client_id="actor-1", scopes=[])

    monkeypatch.setattr(WorkstreamForwardingTokenVerifier, "verify_token", accept_token)
    server = build_fastmcp_server(
        gateway=ScenarioContributorGateway(),
        config=WorkstreamMCPConfig(
            workstream_api_base_url="https://api.example.test",
            request_timeout_seconds=1,
            allowed_hosts=("mcp.example.test",),
            allowed_origins=("https://client.example.test",),
            auth_issuer_url="https://auth.example.test",
        ),
        transport="streamable-http",
    )
    app = server.streamable_http_app()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://mcp.example.test",
        headers={"Authorization": "Bearer issuer-token"},
    )

    try:
        async with app.router.lifespan_context(app), client:
            async with asyncio.timeout(3):
                async with streamable_http_client(
                    "http://mcp.example.test/mcp",
                    http_client=client,
                    terminate_on_close=False,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        catalogue = await session.list_tools()
    finally:
        AppStatus.should_exit = True
        await asyncio.sleep(0.6)
        AppStatus.should_exit = False

    wire_tools = {tool.name: tool for tool in catalogue.tools}
    assert list(wire_tools) == [definition.name for definition in TOOL_DEFINITIONS]
    for definition in TOOL_DEFINITIONS:
        wire_tool = wire_tools[definition.name]
        assert wire_tool.title == definition.title
        assert wire_tool.description == definition.description
        assert wire_tool.outputSchema is not None
    request_id_schema = wire_tools["claim_task"].inputSchema["properties"]["request_id"]
    assert request_id_schema["format"] == "uuid"
    assert request_id_schema["examples"] == ["11111111-1111-4111-8111-111111111111"]
