"""HTTP gateway tests for available Workstream APIs."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.http_gateway import HTTPContributorGateway
from workstream_mcp.scenario_gateway import ScenarioContributorGateway
from workstream_mcp.tools import (
    claim_review,
    claim_task,
    release_task,
    run_pre_submit_check,
    submit_review,
    submit_task,
)

REQUEST_ID = "11111111-1111-4111-8111-111111111111"


def submission() -> dict[str, Any]:
    """Return a valid current Workstream submission packet."""
    return {
        "summary": "candidate",
        "package_hash": "sha256:abc",
        "artifact_hash_manifest": [{"artifact": "result.txt", "hash": "sha256:def"}],
        "worker_attestation": "I attest this packet is complete.",
    }


def context() -> RequestContext:
    """Return a reusable safe test context."""
    return RequestContext("issuer-token", "corr-1", "test")


@pytest.mark.asyncio
async def test_claim_task_fails_closed_until_backend_claim_starts_work() -> None:
    """The legacy claim endpoint cannot back the MCP's single claim operation."""
    calls: list[tuple[str, str, dict[str, str]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, dict(request.headers)))
        return httpx.Response(200, json={"task": {"id": "task-1"}, "assignment": {"id": "a-1"}})

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await claim_task(gateway, context(), task_id="task-1", request_id=REQUEST_ID)

    assert result["error"]["code"] == "workstream_temporarily_unavailable"
    assert result["error"]["details"]["surface"] == "claim_task"
    assert calls == []


@pytest.mark.asyncio
async def test_default_http_gateway_fails_closed_for_missing_surfaces() -> None:
    """Runtime HTTP mode must not serve scenario data by default."""
    gateway = HTTPContributorGateway(base_url="http://workstream.test")

    result = await claim_review(
        gateway,
        context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )

    assert result["error"]["code"] == "workstream_temporarily_unavailable"
    assert result["error"]["details"]["surface"] == "claim_review"


@pytest.mark.asyncio
async def test_temporary_gateway_is_explicitly_injected() -> None:
    """Scenario data is available only when tests/dev inject the temporary gateway."""
    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        fallback=ScenarioContributorGateway(),
    )

    result = await claim_review(
        gateway,
        context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )

    assert result["outcome"] == "leased_to_actor"


@pytest.mark.asyncio
async def test_tool_validation_rejects_invalid_review_decision_and_blank_request_id() -> None:
    """Tool schemas are enforced before gateway calls."""
    gateway = ScenarioContributorGateway()

    invalid_decision = await submit_review(
        gateway,
        context(),
        review_ref="scenario-review-1",
        decision="approve_anything",
        findings=[],
        request_id=REQUEST_ID,
    )
    blank_request = await claim_task(gateway, context(), task_id="task-1", request_id=" ")
    blank_task = await claim_task(gateway, context(), task_id=" ", request_id=REQUEST_ID)

    assert invalid_decision["error"]["code"] == "invalid_tool_input"
    assert blank_request["error"]["code"] == "invalid_tool_input"
    assert blank_task["error"]["code"] == "invalid_tool_input"


@pytest.mark.asyncio
async def test_tool_validation_rejects_invalid_input_shapes() -> None:
    """Tool schemas reject malformed structured input before gateway calls."""
    gateway = ScenarioContributorGateway()

    invalid_submission = await run_pre_submit_check(
        gateway,
        context(),
        task_id="task-1",
        submission=["not", "a", "dict"],  # type: ignore[arg-type]
        request_id=REQUEST_ID,
    )
    invalid_findings = await submit_review(
        gateway,
        context(),
        review_ref="review-1",
        decision="accept",
        findings=["not-a-finding"],  # type: ignore[list-item]
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert invalid_submission["error"]["code"] == "invalid_tool_input"
    assert invalid_findings["error"]["code"] == "invalid_tool_input"


@pytest.mark.asyncio
async def test_tool_results_redact_echoed_bearer_token() -> None:
    """Gateway echo bugs must not leak bearer material into MCP results."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"echoed_authorization": request.headers["authorization"]},
        )

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await run_pre_submit_check(
        gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    assert "issuer-token" not in json.dumps(result)
    assert result["data"]["pre_submit_check"]["echoed_authorization"] == "Bearer [REDACTED]"


@pytest.mark.asyncio
async def test_pre_submit_failure_is_valid_tool_outcome() -> None:
    """Checker failures are domain feedback, not MCP server crashes."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tasks/task-1/submission-precheck"
        assert request.headers["authorization"] == "Bearer issuer-token"
        assert request.headers["x-request-id"] == REQUEST_ID
        body = json.loads(request.content)
        assert body == {"submission": {**submission(), "evidence_items": []}}
        return httpx.Response(
            200,
            json={
                "task_id": "task-1",
                "authoritative": False,
                "status": "failed",
                "eligible_to_submit": False,
                "results": [],
            },
        )

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await run_pre_submit_check(
        gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    assert result["outcome"] == "pre_submit_check_failed"
    assert result["data"]["pre_submit_check"]["eligible_to_submit"] is False


@pytest.mark.asyncio
async def test_submit_task_fails_closed_until_backend_supports_idempotency() -> None:
    """The legacy submit endpoint cannot satisfy the MCP retry contract."""
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "submission-1", "task_id": "task-1"})

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await submit_task(
        gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    assert seen == {}
    assert result["error"]["code"] == "workstream_temporarily_unavailable"
    assert result["error"]["details"]["surface"] == "submit_task"


@pytest.mark.asyncio
async def test_release_task_fails_closed_without_contributor_backend_api() -> None:
    """The operator release endpoint must not be exposed as a contributor tool."""
    gateway = HTTPContributorGateway(base_url="http://workstream.test")

    result = await release_task(
        gateway,
        context(),
        task_id="task-1",
        request_id=REQUEST_ID,
        reason="No longer available.",
    )

    assert result["error"]["code"] == "workstream_temporarily_unavailable"
    assert result["error"]["details"]["surface"] == "release_task"


@pytest.mark.asyncio
async def test_invalid_upstream_json_becomes_safe_mcp_error() -> None:
    """Malformed upstream data must not escape as an MCP stack trace."""

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json")),
    )

    result = await run_pre_submit_check(
        gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    assert result["error"]["code"] == "unexpected_server_error"
