"""Temporary scenario gateway tests."""

from __future__ import annotations

import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.errors import MCPErrorCode
from workstream_mcp.scenario_gateway import SCENARIO_TIMESTAMP, ScenarioContributorGateway
from workstream_mcp.tools import claim_review, submit_review


def context() -> RequestContext:
    """Return a reusable safe test context."""
    return RequestContext("issuer-token", "corr-1", "test")


@pytest.mark.asyncio
async def test_scenario_gateway_marks_temporary_surfaces() -> None:
    """Unavailable API surfaces are explicitly temporary and deterministic."""
    gateway = ScenarioContributorGateway()

    projects = await gateway.get_my_projects(context())
    contributions = await gateway.get_my_contributions(context())
    tasks = await gateway.list_tasks(context())
    review = await gateway.get_current_review(context(), project_id="scenario-project-1")

    assert gateway.temporary is True
    assert projects["source"] == "temporary_scenario_gateway"
    assert contributions["contributions"][0]["contribution_ref"] == "scenario-contribution-1"
    assert contributions["contributions"][0]["recorded_at"] == SCENARIO_TIMESTAMP
    assert tasks["tasks"][0]["task_id"] == "scenario-task-1"
    assert review["state"] == "available_to_claim"


@pytest.mark.asyncio
async def test_current_review_claim_context_and_decision_flow() -> None:
    """Reviewer flow exposes one review and requires findings for revision."""
    gateway = ScenarioContributorGateway()

    claimed = await claim_review(
        gateway,
        context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="req-1",
    )
    context_result = await gateway.get_review_context(
        context(),
        review_ref="scenario-review-1",
    )
    missing_findings = await submit_review(
        gateway,
        context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[],
        request_id="req-2",
    )
    accepted = await submit_review(
        gateway,
        context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="req-3",
    )

    assert claimed["outcome"] == "leased_to_actor"
    assert context_result["review_ref"] == "scenario-review-1"
    assert missing_findings["error"]["code"] == MCPErrorCode.FINDINGS_REQUIRED.value
    assert accepted["outcome"] == "accept"
