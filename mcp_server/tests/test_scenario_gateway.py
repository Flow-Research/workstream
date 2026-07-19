"""Temporary scenario gateway tests."""

from __future__ import annotations

import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.errors import MCPErrorCode
from workstream_mcp.resources import read_review_context, read_task_context
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
    return RequestContext("issuer-token", "corr-1", "test", "actor-submitter")


def other_context() -> RequestContext:
    """Return a second actor context for idempotency isolation tests."""
    return RequestContext("other-issuer-token", "corr-2", "test", "actor-reviewer")


def third_context() -> RequestContext:
    """Return a third actor context for lease-visibility tests."""
    return RequestContext("third-issuer-token", "corr-3", "test", "actor-third")


def rotated_submitter_context() -> RequestContext:
    """Return the submitter under a rotated credential."""
    return RequestContext("rotated-token", "corr-4", "test", "actor-submitter")


def submission() -> dict[str, object]:
    """Return a valid contributor packet for the temporary conformance fixture."""
    return {
        "summary": "candidate",
        "package_hash": "sha256:abc",
        "artifact_hash_manifest": [{"artifact": "result.txt", "hash": "sha256:def"}],
        "worker_attestation": "I attest this packet is complete.",
    }


async def prepare_review(
    gateway: ScenarioContributorGateway,
    submitter: RequestContext | None = None,
) -> None:
    """Create the real submitted work required before a review can be offered."""
    actor = submitter or context()
    await claim_task(gateway, actor, task_id="scenario-task-1", request_id=REQUEST_ID)
    await submit_task(
        gateway,
        actor,
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )


@pytest.mark.asyncio
async def test_scenario_gateway_marks_temporary_surfaces() -> None:
    """Unavailable API surfaces are explicitly temporary and deterministic."""
    gateway = ScenarioContributorGateway()

    projects = await gateway.get_my_projects(context())
    contributions = await gateway.get_my_contributions(context())
    tasks = await gateway.list_tasks(context())
    review = await gateway.get_current_review(context(), project_id="scenario-project-1")
    premature_claim = await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )

    assert gateway.temporary is True
    assert projects["source"] == "temporary_scenario_gateway"
    assert contributions["contributions"] == []
    assert tasks["tasks"][0]["task_id"] == "scenario-task-1"
    assert review["state"] == "none_available"
    assert premature_claim["error"]["code"] == MCPErrorCode.REVIEW_NOT_AVAILABLE.value
    assert (await gateway.get_my_contributions(context()))["contributions"] == []


@pytest.mark.asyncio
async def test_scenario_resources_cover_required_v01_context() -> None:
    """The temporary fixture represents the complete v0.1 submitter/reviewer context."""
    gateway = ScenarioContributorGateway()

    contributions = await gateway.get_my_contributions(context())
    tasks = await gateway.list_tasks(context())
    task_context = await gateway.get_task_context(context(), task_id="scenario-task-1")
    task_status = await gateway.get_task_status(context(), task_id="scenario-task-1")
    await prepare_review(gateway)
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    review = await gateway.get_current_review(other_context(), project_id="scenario-project-1")
    review_context = await gateway.get_review_context(
        other_context(),
        review_ref="scenario-review-1",
    )

    assert contributions["contributions"] == []
    assert task_context["compensation"] == {
        "contribution_type": "accepted_submission",
        "compensation_mode": "unpaid",
        "policy_ref": "scenario-submitter-policy-1:v1",
        "summary": "The submitter contribution rule is explicitly unpaid.",
    }
    assert review_context["compensation"] == {
        "contribution_type": "completed_review",
        "compensation_mode": "unpaid",
        "policy_ref": "scenario-reviewer-policy-1:v1",
        "summary": "The reviewer contribution rule is explicitly unpaid.",
    }
    assert {"available_from", "claim_by"} <= tasks["tasks"][0].keys()
    assert {
        "locked_context",
        "expected_output",
        "acceptance_criteria",
        "artifact_requirements",
        "evidence_requirements",
        "pre_submit_checks",
        "review_criteria",
        "compensation",
        "cycle",
        "revision",
    } <= task_context.keys()
    assert {
        "actor_facing_state",
        "latest_submission",
        "latest_check_outcome",
        "latest_review_outcome",
        "action_required",
        "final_outcome",
    } <= task_status.keys()
    assert review["lease_started_at"] == SCENARIO_TIMESTAMP
    assert review["lease_expires_at"] is not None
    assert {
        "task_context",
        "submission",
        "checker_results",
        "revision_chain",
        "review_criteria",
        "compensation",
        "lease",
        "allowed_decisions",
    } <= review_context.keys()


@pytest.mark.asyncio
async def test_current_review_claim_context_and_decision_flow() -> None:
    """Reviewer flow exposes one review and requires findings for revision."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)

    claimed = await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    context_result = await gateway.get_review_context(
        other_context(),
        review_ref="scenario-review-1",
    )
    missing_findings = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )
    advisory_only_revision = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[{"summary": "Optional polish.", "finding_kind": "advisory"}],
        request_id="88888888-8888-4888-8888-888888888888",
    )
    blocking_accept = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[{"summary": "Unresolved requirement.", "finding_kind": "blocking"}],
        request_id="99999999-9999-4999-8999-999999999999",
    )
    blank_blocking_finding = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[{"summary": "   ", "finding_kind": "blocking"}],
        request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    missing_rejection_reason = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="reject",
        findings=[],
        request_id="44444444-4444-4444-8444-444444444444",
    )
    blank_rejection_reason = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="reject",
        findings=[],
        request_id="55555555-5555-4555-8555-555555555555",
        reason="   ",
    )
    misplaced_accept_reason = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="66666666-6666-4666-8666-666666666666",
        reason="This field is valid only for rejection.",
    )
    misplaced_revision_reason = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[{"summary": "Correct the manifest.", "finding_kind": "blocking"}],
        request_id="77777777-7777-4777-8777-777777777777",
        reason="This field is valid only for rejection.",
    )
    accepted = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="33333333-3333-4333-8333-333333333333",
    )
    accepted_retry = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="33333333-3333-4333-8333-333333333333",
    )
    contributions = await gateway.get_my_contributions(other_context())
    submitter_contributions = await gateway.get_my_contributions(context())
    task_status = await gateway.get_task_status(context(), task_id="scenario-task-1")

    assert claimed["outcome"] == "leased_to_actor"
    assert context_result["review_ref"] == "scenario-review-1"
    assert context_result["checker_results"]["checker_run_ref"] == (
        "scenario-checker-run-1"
    )
    assert context_result["checker_results"]["submission_ref"] == (
        "scenario-submission-1"
    )
    assert context_result["checker_results"]["status"] == "final"
    assert context_result["checker_results"]["outcome"] == "allow_review"
    assert missing_findings["error"]["code"] == MCPErrorCode.FINDINGS_REQUIRED.value
    assert advisory_only_revision["error"]["code"] == MCPErrorCode.FINDINGS_REQUIRED.value
    assert blocking_accept["error"]["code"] == "invalid_tool_input"
    assert blank_blocking_finding["error"]["code"] == "invalid_tool_input"
    assert missing_rejection_reason["error"]["code"] == "invalid_tool_input"
    assert blank_rejection_reason["error"]["code"] == "invalid_tool_input"
    assert misplaced_accept_reason["error"]["code"] == "invalid_tool_input"
    assert misplaced_revision_reason["error"]["code"] == "invalid_tool_input"
    assert accepted["outcome"] == "accept"
    assert accepted_retry["data"]["review_decision"]["idempotent_replay"] is True
    assert "idempotent_replay" not in accepted["data"]["review_decision"]
    assert [
        (record["contribution_type"], record["outcome"])
        for record in contributions["contributions"]
    ] == [("completed_review", "accept")]
    assert contributions["contributions"][0]["source_ref"] == "scenario-review-1"
    assert [
        record["contribution_type"]
        for record in submitter_contributions["contributions"]
    ] == ["accepted_submission"]
    assert submitter_contributions["contributions"][0]["source_ref"] == (
        "scenario-final-acceptance-1"
    )
    assert task_status["latest_review_outcome"]["review_lease_ref"] == (
        "scenario-review-lease-1"
    )
    assert task_status["latest_review_outcome"]["checker_run_ref"] == (
        "scenario-checker-run-1"
    )
    assert gateway._reviews[0]["review_lease_ref"] == (  # noqa: SLF001
        "scenario-review-lease-1"
    )
    assert gateway._final_acceptances[0]["review_ref"] == (  # noqa: SLF001
        gateway._reviews[0]["review_ref"]  # noqa: SLF001
    )
    assert await gateway.get_my_contributions(rotated_submitter_context()) == (
        submitter_contributions
    )
    assert await gateway.get_current_review(
        other_context(), project_id="scenario-project-1"
    ) == {
        "source": "temporary_scenario_gateway",
        "project_id": "scenario-project-1",
        "state": "none_available",
    }


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
    assert submitted_retry["data"]["submission"]["idempotent_replay"] is True
    assert "idempotent_replay" not in submitted["data"]["submission"]
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
    assert released_retry["data"]["task_release"]["idempotent_replay"] is True
    assert "idempotent_replay" not in released["data"]["task_release"]


@pytest.mark.asyncio
async def test_idempotency_is_scoped_to_actor_tool_and_request_id() -> None:
    """One actor cannot receive another actor's stored temporary result."""
    gateway = ScenarioContributorGateway()

    first = await claim_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )
    other_actor = await claim_task(
        gateway,
        other_context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )
    conflicting_retry = await claim_task(
        gateway,
        context(),
        task_id="different-task",
        request_id=REQUEST_ID,
    )

    assert first["outcome"] == "claimed"
    assert other_actor["error"]["code"] == "task_not_claimable"
    assert conflicting_retry["error"]["code"] == "idempotency_conflict"


@pytest.mark.asyncio
async def test_review_claim_conflicting_retry_precedes_fixture_validation() -> None:
    """A reused review request ID reports conflict even when new input is unavailable."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )

    conflicting_retry = await claim_review(
        gateway,
        other_context(),
        project_id="different-project",
        review_routing_ref="different-route",
        request_id=REQUEST_ID,
    )

    assert conflicting_retry["error"]["code"] == "idempotency_conflict"


@pytest.mark.asyncio
async def test_needs_revision_persists_findings_and_allows_revised_submission() -> None:
    """A review revision decision drives the submitter back through task context."""
    gateway = ScenarioContributorGateway()
    finding = {
        "summary": "Correct the declared artifact hash.",
        "finding_kind": "blocking",
        "category": "evidence",
    }
    await claim_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )
    await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="33333333-3333-4333-8333-333333333333",
    )

    decision = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[finding],
        request_id="44444444-4444-4444-8444-444444444444",
    )
    decision_retry = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="needs_revision",
        findings=[finding],
        request_id="44444444-4444-4444-8444-444444444444",
    )
    status = await gateway.get_task_status(context(), task_id="scenario-task-1")
    contributions = await gateway.get_my_contributions(other_context())
    submitter_contributions = await gateway.get_my_contributions(context())
    task_context = await gateway.get_task_context(context(), task_id="scenario-task-1")
    revised = await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="55555555-5555-4555-8555-555555555555",
    )
    revised_context = await gateway.get_task_context(context(), task_id="scenario-task-1")
    next_review = await gateway.get_current_review(
        other_context(), project_id="scenario-project-1"
    )

    assert decision["outcome"] == "needs_revision"
    assert decision_retry["data"]["review_decision"]["idempotent_replay"] is True
    assert [record["contribution_type"] for record in contributions["contributions"]] == [
        "completed_review"
    ]
    assert submitter_contributions["contributions"] == []
    assert status["actor_facing_state"] == "needs_revision"
    assert status["action_required"] == "read_task_context"
    persisted_finding = {**finding, "evidence_refs": []}
    assert status["latest_review_outcome"]["findings"] == [persisted_finding]
    assert task_context["revision"] == {
        "required": True,
        "findings": [persisted_finding],
        "submission_ref": "scenario-submission-1",
        "submission_version": 1,
    }
    assert revised["outcome"] == "submitted"
    assert revised_context["revision"] == {"required": False, "findings": []}
    assert next_review["state"] == "available_to_claim"
    assert next_review["review_ref"] == "scenario-review-2"
    assert next_review["review_routing_ref"] == "scenario-review-route-2"


@pytest.mark.asyncio
async def test_reject_records_only_one_replay_safe_reviewer_contribution() -> None:
    """Reject completes the task without creating a submitter contribution."""
    gateway = ScenarioContributorGateway()
    await claim_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )
    await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="33333333-3333-4333-8333-333333333333",
    )

    rejected = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="reject",
        findings=[],
        request_id="44444444-4444-4444-8444-444444444444",
        reason="The submission does not satisfy the governing acceptance criteria.",
    )
    rejected_retry = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="reject",
        findings=[],
        request_id="44444444-4444-4444-8444-444444444444",
        reason="The submission does not satisfy the governing acceptance criteria.",
    )
    status = await gateway.get_task_status(context(), task_id="scenario-task-1")
    contributions = await gateway.get_my_contributions(other_context())
    submitter_contributions = await gateway.get_my_contributions(context())

    assert rejected["outcome"] == "reject"
    assert rejected_retry["data"]["review_decision"]["idempotent_replay"] is True
    assert status["actor_facing_state"] == "rejected"
    assert status["final_outcome"] == "rejected"
    assert [record["contribution_type"] for record in contributions["contributions"]] == [
        "completed_review"
    ]
    assert submitter_contributions["contributions"] == []


@pytest.mark.asyncio
async def test_submitter_cannot_discover_or_claim_own_review() -> None:
    """The temporary service enforces Workstream's no-self-review boundary."""
    gateway = ScenarioContributorGateway()
    await claim_task(gateway, context(), task_id="scenario-task-1", request_id=REQUEST_ID)
    await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )

    submitter_view = await gateway.get_current_review(
        context(), project_id="scenario-project-1"
    )
    self_claim = await claim_review(
        gateway,
        context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="33333333-3333-4333-8333-333333333333",
    )
    reviewer_view = await gateway.get_current_review(
        other_context(), project_id="scenario-project-1"
    )
    rotated_submitter_view = await gateway.get_current_review(
        rotated_submitter_context(), project_id="scenario-project-1"
    )

    assert submitter_view["state"] == "none_available"
    assert self_claim["error"]["code"] == MCPErrorCode.REVIEW_NOT_AVAILABLE.value
    assert reviewer_view["state"] == "available_to_claim"
    assert rotated_submitter_view["state"] == "none_available"


@pytest.mark.asyncio
async def test_submit_review_rechecks_self_review_before_mutation() -> None:
    """The decision boundary independently rejects a newly conflicting owner."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    gateway._task_owner = other_context().actor_id  # noqa: SLF001 - invariant probe

    result = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert result["error"]["code"] == MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR.value
    assert gateway._review["state"] == "leased_to_actor"  # noqa: SLF001
    assert (await gateway.get_my_contributions(other_context()))["contributions"] == []


@pytest.mark.asyncio
async def test_review_fails_closed_when_submission_state_is_missing() -> None:
    """A corrupted temporary fixture never fabricates reviewed work."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    submission_record = gateway._submissions.pop()  # noqa: SLF001 - corrupted-state probe

    review_context = await read_review_context(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
    )
    decision = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert review_context["error"]["code"] == MCPErrorCode.REVIEW_NOT_AVAILABLE.value
    assert decision["error"]["code"] == MCPErrorCode.REVIEW_NOT_AVAILABLE.value
    assert gateway._review["state"] == "leased_to_actor"  # noqa: SLF001
    assert (await gateway.get_my_contributions(other_context()))["contributions"] == []

    gateway._submissions.append(submission_record)  # noqa: SLF001
    retry = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert retry["outcome"] == "accept"


@pytest.mark.asyncio
async def test_review_fails_closed_without_checker_admission() -> None:
    """A review cannot proceed without its current final checker fact."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    gateway._checker_runs.clear()  # noqa: SLF001 - corrupted-state probe

    review_context = await read_review_context(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
    )
    decision = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert review_context["error"]["code"] == MCPErrorCode.REVIEW_NOT_AVAILABLE.value
    assert decision["error"]["code"] == MCPErrorCode.REVIEW_NOT_AVAILABLE.value
    assert gateway._review["state"] == "leased_to_actor"  # noqa: SLF001
    assert (await gateway.get_my_contributions(other_context()))["contributions"] == []


@pytest.mark.asyncio
async def test_review_consumes_frozen_submission_and_checker_anchors() -> None:
    """Contradictory later fixture state cannot change the admitted review packet."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)
    gateway._submissions.append(  # noqa: SLF001 - contradictory-state probe
        {"id": "scenario-submission-2", "task_id": "scenario-task-1", "version": 2}
    )
    gateway._checker_runs.append(  # noqa: SLF001 - contradictory-state probe
        {
            "checker_run_ref": "scenario-checker-run-2",
            "submission_ref": "scenario-submission-2",
            "submission_version": 2,
            "status": "final",
            "outcome": "allow_review",
            "current": True,
            "results": [],
        }
    )
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )

    review_context = await gateway.get_review_context(
        other_context(), review_ref="scenario-review-1"
    )
    decision = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert review_context["submission"]["submission_id"] == "scenario-submission-1"
    assert review_context["checker_results"]["checker_run_ref"] == (
        "scenario-checker-run-1"
    )
    assert decision["outcome"] == "accept"
    assert gateway._final_acceptances[0]["submission_ref"] == (  # noqa: SLF001
        "scenario-submission-1"
    )


@pytest.mark.asyncio
async def test_review_context_preserves_exact_immutable_submission_packet() -> None:
    """Reviewers receive the exact packet submitted by the contributor."""
    gateway = ScenarioContributorGateway()
    packet = {
        **submission(),
        "summary": "Unique submitted summary",
        "package_uri": "flow://packages/unique",
        "evidence_items": [{"type": "test_result", "label": "Unique evidence"}],
    }
    await claim_task(gateway, context(), task_id="scenario-task-1", request_id=REQUEST_ID)
    await submit_task(
        gateway,
        context(),
        task_id="scenario-task-1",
        submission=packet,
        request_id="22222222-2222-4222-8222-222222222222",
    )
    packet["summary"] = "mutated caller value"
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="33333333-3333-4333-8333-333333333333",
    )

    review_context = await gateway.get_review_context(
        other_context(), review_ref="scenario-review-1"
    )

    assert review_context["submission"]["packet"]["summary"] == (
        "Unique submitted summary"
    )
    assert review_context["submission"]["packet"]["package_uri"] == (
        "flow://packages/unique"
    )
    assert review_context["submission"]["packet"]["evidence_items"] == [
        {"type": "test_result", "label": "Unique evidence", "metadata": {}}
    ]
    assert review_context["submission"]["packet_digest"] == (
        review_context["checker_results"]["submission_digest"]
    )


@pytest.mark.asyncio
async def test_review_decision_rejects_corrupted_lease_anchor_without_mutation() -> None:
    """A changed lease reference cannot produce authoritative review facts."""
    gateway = ScenarioContributorGateway()
    await prepare_review(gateway)
    await claim_review(
        gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    original_lease_ref = gateway._review["review_lease_ref"]  # noqa: SLF001
    gateway._review["review_lease_ref"] = "corrupted-lease"  # noqa: SLF001

    rejected = await submit_review(
        gateway,
        other_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="22222222-2222-4222-8222-222222222222",
    )

    assert rejected["error"]["code"] == MCPErrorCode.REVIEW_NOT_LEASED_TO_ACTOR.value
    assert gateway._review["state"] == "leased_to_actor"  # noqa: SLF001
    assert gateway._reviews == []  # noqa: SLF001
    assert gateway._final_acceptances == []  # noqa: SLF001
    assert (await gateway.get_my_contributions(other_context()))["contributions"] == []
    gateway._review["review_lease_ref"] = original_lease_ref  # noqa: SLF001


@pytest.mark.asyncio
async def test_temporary_task_and_review_leases_are_actor_scoped() -> None:
    """A second test actor cannot read or mutate another actor's leased work."""
    task_gateway = ScenarioContributorGateway()
    await claim_task(
        task_gateway,
        context(),
        task_id="scenario-task-1",
        request_id=REQUEST_ID,
    )

    hidden_task = await read_task_context(
        task_gateway,
        other_context(),
        task_id="scenario-task-1",
    )
    hidden_task_list = await task_gateway.list_tasks(other_context())
    other_submit = await submit_task(
        task_gateway,
        other_context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )

    review_gateway = ScenarioContributorGateway()
    await prepare_review(review_gateway)
    await claim_review(
        review_gateway,
        other_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id=REQUEST_ID,
    )
    hidden_review = await review_gateway.get_current_review(
        third_context(),
        project_id="scenario-project-1",
    )
    other_review_context = await read_review_context(
        review_gateway,
        third_context(),
        review_ref="scenario-review-1",
    )

    assert hidden_task["error"]["code"] == "resource_not_found_or_not_visible"
    assert hidden_task_list["tasks"] == []
    assert other_submit["error"]["code"] == "submission_not_allowed"
    assert hidden_review["state"] == "none_available"
    assert other_review_context["error"]["code"] == "review_not_leased_to_actor"
