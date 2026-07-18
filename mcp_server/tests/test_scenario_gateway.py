"""Temporary scenario gateway tests."""

from __future__ import annotations

import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.errors import MCPErrorCode
from workstream_mcp.scenario_gateway import SCENARIO_TIMESTAMP, ScenarioContributorGateway
from workstream_mcp.tools import (
    claim_review,
    claim_task,
    release_task,
    run_pre_submit_check,
    submit_review,
    submit_task,
)

REQUEST_ID = "11111111-1111-4111-8111-111111111111"


def context() -> RequestContext:
    """Return a reusable safe test context."""
    return RequestContext("issuer-token", "corr-1", "test")


def submission() -> dict[str, object]:
    """Return a valid contributor packet for the temporary conformance fixture."""
    return {
        "summary": "candidate",
        "package_hash": "sha256:abc",
        "artifact_hash_manifest": [{"artifact": "result.txt", "hash": "sha256:def"}],
        "worker_attestation": "I attest this packet is complete.",
    }


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
        request_id=REQUEST_ID,
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
        request_id="22222222-2222-4222-8222-222222222222",
    )
    accepted = await submit_review(
        gateway,
        context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="33333333-3333-4333-8333-333333333333",
    )
    accepted_retry = await submit_review(
        gateway,
        context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="33333333-3333-4333-8333-333333333333",
    )

    assert claimed["outcome"] == "leased_to_actor"
    assert context_result["review_ref"] == "scenario-review-1"
    assert missing_findings["error"]["code"] == MCPErrorCode.FINDINGS_REQUIRED.value
    assert accepted["outcome"] == "accept"
    assert accepted_retry == accepted


@pytest.mark.asyncio
async def test_temporary_submitter_flow_is_complete_and_idempotent() -> None:
    """The injected fixture supports the full missing-API conformance journey."""
    gateway = ScenarioContributorGateway()

    claimed = await claim_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )
    checked = await run_pre_submit_check(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )
    submitted = await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="33333333-3333-4333-8333-333333333333",
    )
    submitted_retry = await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="33333333-3333-4333-8333-333333333333",
    )
    status = await gateway.get_task_status(context(), task_id="scenario-task-1")

    assert claimed["outcome"] == "claimed"
    assert checked["outcome"] == "passed"
    assert submitted["outcome"] == "submitted"
    assert submitted_retry == submitted
    assert status["task"]["actor_facing_state"] == "review_pending"
    assert status["latest_submission"]["id"] == "scenario-submission-1"


@pytest.mark.asyncio
async def test_temporary_task_release_retries_after_state_changes() -> None:
    """A retry returns the original release result after the task is available again."""
    gateway = ScenarioContributorGateway()
    await claim_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )

    released = await release_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id="22222222-2222-4222-8222-222222222222",
    )
    released_retry = await release_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert released["outcome"] == "released"
    assert released_retry == released
