"""HTTP gateway tests for available Workstream APIs."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.errors import (
    MCPErrorCode,
    WorkstreamMCPError,
    map_http_error_response,
    map_http_status,
)
from workstream_mcp.http_gateway import HTTPContributorGateway
from workstream_mcp.resources import read_task_context, read_task_status
from workstream_mcp.scenario_gateway import ScenarioContributorGateway
from workstream_mcp.tools import (
    claim_review,
    claim_task,
    release_review,
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
    return RequestContext("issuer-token", "corr-1", "test", "actor-submitter")


def reviewer_context() -> RequestContext:
    """Return a distinct reviewer identity for lifecycle tests."""
    return RequestContext("reviewer-token", "corr-2", "test", "actor-reviewer")


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
    assert [(method, path) for method, path, _headers in calls] == [
        ("GET", "/api/v1/auth/me")
    ]
    assert calls[0][2]["authorization"] == "Bearer issuer-token"


@pytest.mark.asyncio
async def test_default_http_gateway_fails_closed_for_missing_surfaces() -> None:
    """Runtime HTTP mode must not serve scenario data by default."""
    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"id": "actor-1"})),
    )

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
    scenario = ScenarioContributorGateway()
    await scenario.claim_task(context(), task_id="scenario-task-1", request_id=REQUEST_ID)
    await scenario.submit_task(
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )
    gateway = scenario

    result = await claim_review(
        gateway,
        reviewer_context(),
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
    path_task = await claim_task(gateway, context(), task_id="../auth/me", request_id=REQUEST_ID)

    assert invalid_decision["error"]["code"] == "invalid_tool_input"
    assert blank_request["error"]["code"] == "invalid_tool_input"
    assert blank_task["error"]["code"] == "invalid_tool_input"
    assert path_task["error"]["code"] == "invalid_tool_input"


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
            json={
                "task_id": "task-1",
                "authoritative": False,
                "status": "passed",
                "eligible_to_submit": True,
                "results": [],
                "echoed_authorization": request.headers["authorization"],
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

    assert "issuer-token" not in json.dumps(result)
    assert result["data"]["pre_submit_check"]["echoed_authorization"] == (
        "Bearer [REDACTED]"
    )


@pytest.mark.asyncio
async def test_bearer_material_never_reaches_identifier_paths() -> None:
    """Known bearer material is rejected in tool, resource, and direct gateway refs."""
    bearer = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    identifier = f"prefix:{bearer.lower()}:suffix"
    bearer_context = RequestContext(bearer, "corr-secret", "test", "actor-secret")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    tool_result = await run_pre_submit_check(
        gateway,
        bearer_context,
        task_id=identifier,
        submission=submission(),
        request_id="22222222-2222-4222-8222-222222222222",
    )
    resource_result = await read_task_context(
        gateway,
        bearer_context,
        task_id=identifier,
    )
    with pytest.raises(WorkstreamMCPError) as direct_error:
        await gateway.get_task_context(bearer_context, task_id=identifier)

    assert tool_result["error"]["code"] == "invalid_tool_input"
    assert resource_result["error"]["code"] == "resource_not_found_or_not_visible"
    assert direct_error.value.code == MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE
    assert calls == []


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
        seen["body"] = json.loads(request.content) if request.content else None
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

    assert seen == {"path": "/api/v1/auth/me", "body": None}
    assert result["error"]["code"] == "workstream_temporarily_unavailable"
    assert result["error"]["details"]["surface"] == "submit_task"


@pytest.mark.asyncio
async def test_release_task_fails_closed_without_contributor_backend_api() -> None:
    """The operator release endpoint must not be exposed as a contributor tool."""
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"id": "actor-1"})

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await release_task(
        gateway,
        context(),
        task_id="task-1",
        request_id=REQUEST_ID,
        reason="No longer available.",
    )

    assert result["error"]["code"] == "workstream_temporarily_unavailable"
    assert result["error"]["details"]["surface"] == "release_task"
    assert seen_paths == ["/api/v1/auth/me"]


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


@pytest.mark.asyncio
async def test_invalid_token_is_reported_before_missing_surface() -> None:
    """Unavailable APIs still authenticate through the existing Workstream Auth service."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/me"
        return httpx.Response(401, json={"error": {"code": "invalid_token"}})

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await claim_task(gateway, context(), task_id="task-1", request_id=REQUEST_ID)

    assert result["error"]["code"] == "invalid_token"
    assert result["error"]["details"] == {}


@pytest.mark.asyncio
async def test_resource_identifier_cannot_escape_http_path_segment() -> None:
    """Hostile resource references are rejected before any Workstream HTTP call."""
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    result = await read_task_context(gateway, context(), task_id="../auth/me")

    assert result["error"]["code"] == "resource_not_found_or_not_visible"
    assert calls == []


def test_safe_backend_error_codes_are_preserved() -> None:
    """Known authorization classifications survive the HTTP adapter boundary."""
    denied = map_http_error_response(
        403,
        {"error": {"code": "project_access_denied"}},
        correlation_id="corr-1",
    )

    assert denied.code.value == "project_access_denied"
    assert denied.correlation_id == "corr-1"


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, MCPErrorCode.INVALID_TOKEN, False),
        (403, MCPErrorCode.CAPABILITY_NOT_GRANTED, False),
        (404, MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE, False),
        (409, MCPErrorCode.IDEMPOTENCY_CONFLICT, False),
        (400, MCPErrorCode.SUBMISSION_NOT_ALLOWED, False),
        (503, MCPErrorCode.WORKSTREAM_TEMPORARILY_UNAVAILABLE, True),
        (418, MCPErrorCode.UNEXPECTED_SERVER_ERROR, False),
    ],
)
def test_http_statuses_map_to_safe_mcp_errors(
    status_code: int,
    expected_code: MCPErrorCode,
    retryable: bool,
) -> None:
    """Generic upstream statuses map to the closed MCP error catalogue."""
    error = map_http_status(status_code, correlation_id="corr-1")

    assert error.code is expected_code
    assert error.retryable is retryable
    assert error.correlation_id == "corr-1"


def test_backend_error_mapping_supports_top_level_and_unknown_envelopes() -> None:
    """Only recognized backend codes survive; unknown shapes use status mapping."""
    known = map_http_error_response(
        409,
        {"code": "idempotency_mismatch"},
        correlation_id="corr-1",
    )
    unknown = map_http_error_response(404, ["not", "an", "envelope"])

    assert known.code is MCPErrorCode.IDEMPOTENCY_CONFLICT
    assert unknown.code is MCPErrorCode.RESOURCE_NOT_FOUND_OR_NOT_VISIBLE


def test_invalid_locked_task_context_is_not_blamed_on_a_submission() -> None:
    """Invalid authoritative task setup maps to an infrastructure-safe error."""
    error = map_http_error_response(
        422,
        {"error": {"code": "task_locked_context_invalid"}},
        correlation_id="corr-1",
    )

    assert error.code is MCPErrorCode.UNEXPECTED_SERVER_ERROR
    assert "submitted payload" not in error.message


@pytest.mark.asyncio
async def test_available_task_resources_compose_current_workstream_apis() -> None:
    """Task context and status compose only the semantically compatible APIs."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path == "/api/v1/tasks/task-1":
            return httpx.Response(200, json={"id": "task-1", "status": "needs_revision"})
        if path.endswith("/work-context"):
            return httpx.Response(200, json={"guide_ref": "guide-1:v1"})
        if path.endswith("/submission-requirements"):
            return httpx.Response(200, json={"required": ["summary"]})
        if path.endswith("/submissions"):
            return httpx.Response(200, json=[{"id": "submission-1", "version": 1}])
        if path == "/api/v1/submissions/submission-1/checker-runs":
            return httpx.Response(200, json=[{"status": "passed"}])
        raise AssertionError(f"Unexpected path: {path}")

    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(handler),
    )

    task_context = await read_task_context(gateway, context(), task_id="task-1")
    task_status = await read_task_status(gateway, context(), task_id="task-1")

    assert task_context["work_context"] == {"guide_ref": "guide-1:v1"}
    assert task_context["submission_requirements"] == {"required": ["summary"]}
    assert task_status["latest_submission"]["id"] == "submission-1"
    assert task_status["checker_runs"] == [{"status": "passed"}]
    assert task_status["next_resource"] == "workstream://tasks/task-1/context"
    assert calls.count("/api/v1/tasks/task-1") == 2


@pytest.mark.asyncio
async def test_http_gateway_handles_empty_error_and_network_responses() -> None:
    """Empty success, non-JSON error, and transport failures remain safe outcomes."""
    empty_gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(204)),
    )
    empty = await run_pre_submit_check(
        empty_gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    denied_gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(403, text="denied")),
    )
    denied = await run_pre_submit_check(
        denied_gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    unavailable_gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(unavailable),
    )
    unavailable_result = await run_pre_submit_check(
        unavailable_gateway,
        context(),
        task_id="task-1",
        submission=submission(),
        request_id=REQUEST_ID,
    )

    assert empty["error"]["code"] == "unexpected_server_error"
    assert denied["error"]["code"] == "capability_not_granted"
    assert unavailable_result["error"]["code"] == "workstream_temporarily_unavailable"
    assert unavailable_result["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_explicit_scenario_gateway_covers_all_temporary_surfaces() -> None:
    """Temporary APIs are exercised through one explicitly injected scenario gateway."""
    scenario = ScenarioContributorGateway()
    gateway = scenario

    projects = await gateway.get_my_projects(context())
    contributions = await gateway.get_my_contributions(
        context(), project_id="scenario-project-1"
    )
    tasks = await gateway.list_tasks(context(), project_id="scenario-project-1")
    claimed_task = await gateway.claim_task(
        context(), task_id="scenario-task-1", request_id=REQUEST_ID
    )
    released_task = await gateway.release_task(
        context(),
        task_id="scenario-task-1",
        request_id="22222222-2222-4222-8222-222222222222",
        reason=None,
    )
    await gateway.claim_task(
        context(),
        task_id="scenario-task-1",
        request_id="33333333-3333-4333-8333-333333333333",
    )
    submitted_task = await gateway.submit_task(
        context(),
        task_id="scenario-task-1",
        submission=submission(),
        request_id="44444444-4444-4444-8444-444444444444",
    )
    submitter_review = await gateway.get_current_review(
        context(), project_id="scenario-project-1"
    )
    current_review = await gateway.get_current_review(
        reviewer_context(), project_id="scenario-project-1"
    )
    claimed_review = await gateway.claim_review(
        reviewer_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="55555555-5555-4555-8555-555555555555",
    )
    review_context = await gateway.get_review_context(
        reviewer_context(), review_ref="scenario-review-1"
    )
    released_review = await gateway.release_review(
        reviewer_context(),
        review_ref="scenario-review-1",
        request_id="66666666-6666-4666-8666-666666666666",
    )
    await gateway.claim_review(
        reviewer_context(),
        project_id="scenario-project-1",
        review_routing_ref="scenario-review-route-1",
        request_id="77777777-7777-4777-8777-777777777777",
    )
    submitted_review = await gateway.submit_review(
        reviewer_context(),
        review_ref="scenario-review-1",
        decision="accept",
        findings=[],
        request_id="88888888-8888-4888-8888-888888888888",
    )
    reviewer_contributions = await gateway.get_my_contributions(
        reviewer_context(), project_id="scenario-project-1"
    )
    submitter_contributions = await gateway.get_my_contributions(
        context(), project_id="scenario-project-1"
    )

    assert projects["source"] == "temporary_scenario_gateway"
    assert contributions["contributions"] == []
    assert len(tasks["tasks"]) == 1
    assert claimed_task["assignment"]["id"] == "scenario-assignment-1"
    assert released_task["task"]["actor_facing_state"] == "available"
    assert submitted_task["status"] == "submitted"
    assert submitter_review["state"] == "none_available"
    assert current_review["state"] == "available_to_claim"
    assert claimed_review["outcome"] == "leased_to_actor"
    assert review_context["review_ref"] == "scenario-review-1"
    assert released_review["outcome"] == "released"
    assert submitted_review["outcome"] == "accept"
    assert [
        record["contribution_type"]
        for record in reviewer_contributions["contributions"]
    ] == ["completed_review"]
    assert [
        record["contribution_type"]
        for record in submitter_contributions["contributions"]
    ] == ["accepted_submission"]


@pytest.mark.asyncio
async def test_default_gateway_fails_closed_across_unavailable_resource_surfaces() -> None:
    """Production never substitutes temporary data for any unavailable resource."""
    gateway = HTTPContributorGateway(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"id": "actor-1"})
        ),
    )
    calls = [
        gateway.get_my_projects(context()),
        gateway.get_my_contributions(context(), project_id=None),
        gateway.list_tasks(context(), project_id=None),
        gateway.get_current_review(context(), project_id="project-1"),
        gateway.get_review_context(context(), review_ref="review-1"),
        gateway.release_review(context(), review_ref="review-1", request_id=REQUEST_ID),
        gateway.submit_review(
            context(),
            review_ref="review-1",
            decision="accept",
            findings=[],
            request_id=REQUEST_ID,
        ),
    ]

    surfaces: list[str] = []
    for call in calls:
        with pytest.raises(WorkstreamMCPError) as unavailable:
            await call
        surfaces.append(unavailable.value.details["surface"])

    assert surfaces == [
        "my_projects",
        "my_contributions",
        "tasks",
        "current_review",
        "review_context",
        "release_review",
        "submit_review",
    ]


class _FailingGateway:
    """Gateway double that raises the same failure from every operation."""

    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def __getattr__(self, _name: str) -> Any:
        async def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise self._failure

        return fail


@pytest.mark.asyncio
@pytest.mark.parametrize("unexpected", [False, True])
async def test_all_tool_handlers_map_gateway_failures_safely(unexpected: bool) -> None:
    """Every lifecycle tool converts gateway failures to the closed error envelope."""
    failure: Exception
    if unexpected:
        failure = RuntimeError("adapter detail must not escape")
        expected_code = "unexpected_server_error"
    else:
        failure = WorkstreamMCPError(
            MCPErrorCode.WORKSTREAM_TEMPORARILY_UNAVAILABLE,
            "Workstream is unavailable.",
            correlation_id="corr-1",
        )
        expected_code = "workstream_temporarily_unavailable"
    gateway = _FailingGateway(failure)

    results = [
        await claim_task(gateway, context(), task_id="task-1", request_id=REQUEST_ID),
        await release_task(
            gateway,
            context(),
            task_id="task-1",
            request_id=REQUEST_ID,
            reason=None,
        ),
        await run_pre_submit_check(
            gateway,
            context(),
            task_id="task-1",
            submission=submission(),
            request_id=REQUEST_ID,
        ),
        await submit_task(
            gateway,
            context(),
            task_id="task-1",
            submission=submission(),
            request_id=REQUEST_ID,
        ),
        await claim_review(
            gateway,
            context(),
            project_id="project-1",
            review_routing_ref="route-1",
            request_id=REQUEST_ID,
        ),
        await release_review(
            gateway,
            context(),
            review_ref="review-1",
            request_id=REQUEST_ID,
        ),
        await submit_review(
            gateway,
            context(),
            review_ref="review-1",
            decision="accept",
            findings=[],
            request_id=REQUEST_ID,
        ),
    ]

    assert {result["error"]["code"] for result in results} == {expected_code}
