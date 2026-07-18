"""Protocol-level WS-MCP-001 contributor journey tests."""

from __future__ import annotations

import json
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl
import pytest

from workstream_mcp.auth import STDIO_TOKEN_ENV
from workstream_mcp.scenario_gateway import ScenarioContributorGateway
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
