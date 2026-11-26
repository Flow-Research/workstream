from __future__ import annotations

import base64
from typing import Any
from unittest.mock import ANY

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import TASK_EXECUTION_OPERATIONS, GatewayResult, WorkstreamGateway
from workstream_mcp.limits import SUBMISSION_BUNDLE_MAX_BASE64_CHARS
from workstream_mcp.schemas import TASK_EXECUTION_CONTRACT_NAMES, TASK_EXECUTION_INPUT_SCHEMAS
from workstream_mcp.tools import task_execution

TASK_ID = "019a2a00-0000-7000-8000-000000000701"
PROJECT_ID = "019a2a00-0000-7000-8000-000000000702"
ASSIGNMENT_ID = "019a2a00-0000-7000-8000-000000000703"
PREPARATION_ID = "019a2a00-0000-7000-8000-000000000704"
DOCUMENT_ID = "019a2a00-0000-7000-8000-000000000705"
SUBMISSION_ID = "019a2a00-0000-7000-8000-000000000706"
KEY = "019a2a00-0000-7000-8000-000000000708"
OPERATION_ID = "019a2a00-0000-7000-8000-000000000709"
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]


def _arguments(name: str) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "submission_operation_get": {"task_id": TASK_ID, "operation_id": OPERATION_ID},
        "submission_create": {
            "task_id": TASK_ID,
            "assignment_id": ASSIGNMENT_ID,
            "zip_base64": base64.b64encode(b"PK\x03\x04fixture").decode(),
            "idempotency_key": KEY,
            "feedback": "ready  for review",
        },
        "preparations_list": {"task_id": TASK_ID, "limit": 25, "cursor": "opaque"},
        "preparation_get": {"task_id": TASK_ID, "preparation_id": PREPARATION_ID},
        "task_get": {"task_id": TASK_ID},
        "task_submission_requirements_get": {"task_id": TASK_ID},
        "task_screen": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_release": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_claim": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_work_context_get": {"task_id": TASK_ID},
        "task_assignment_get": {"assignment_id": ASSIGNMENT_ID},
        "project_contributor_guide_get": {"project_id": PROJECT_ID},
        "project_contributor_guide_document_get": {
            "project_id": PROJECT_ID, "guide_id": PREPARATION_ID, "document_id": DOCUMENT_ID,
        },
        "task_guide_document_content_get": {
            "task_id": TASK_ID,
            "document_id": DOCUMENT_ID,
        },
        "task_submissions_list": {"task_id": TASK_ID, "limit": 25},
        "submission_get": {"submission_id": SUBMISSION_ID},
        "management_task_submissions_list": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
            "limit": 25,
        },
        "management_submission_get": {
            "project_id": PROJECT_ID,
            "submission_id": SUBMISSION_ID,
        },
        "management_task_work_context_get": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
        },
        "management_task_submission_requirements_get": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
        },
    }
    return values[name]


def _bound_response(name: str) -> dict[str, Any]:
    if name in {"preparations_list", "task_submissions_list", "management_task_submissions_list"}:
        return {"items": [], "next_cursor": None}
    if name == "preparation_get":
        return {"task_id": TASK_ID, "preparation_id": PREPARATION_ID}
    if name in {"task_get", "task_submission_requirements_get"}:
        return {"task_id": TASK_ID}
    if name in {"task_screen", "task_release"}:
        return {"id": TASK_ID}
    if name == "task_claim":
        return {
            "task": {"id": TASK_ID, "status": "in_progress"},
            "assignment": {"task_id": TASK_ID},
        }
    if name == "task_work_context_get":
        return {"task": {"task_id": TASK_ID}}
    if name == "task_assignment_get":
        return {"assignment": {"task_id": TASK_ID, "assignment_id": ASSIGNMENT_ID}}
    if name == "project_contributor_guide_get":
        return {"project_id": PROJECT_ID}
    if name in {"task_guide_document_content_get", "project_contributor_guide_document_get"}:
        return {
            "media_type": "text/markdown",
            "content_base64": "eA==",
            "byte_count": 1,
            "sha256": "sha256:" + "0" * 64,
        }
    if name == "submission_operation_get":
        return {"task_id": TASK_ID, "operation_id": OPERATION_ID, "idempotency_key": KEY}
    if name == "submission_create":
        return {"task_id": TASK_ID, "assignment_id": ASSIGNMENT_ID}
    if name in {"submission_get", "management_submission_get"}:
        return {"id": SUBMISSION_ID}
    if name == "management_task_work_context_get":
        return {
            "project": {"id": PROJECT_ID},
            "task": {"task_id": TASK_ID, "project_id": PROJECT_ID},
        }
    if name == "management_task_submission_requirements_get":
        return {"project_id": PROJECT_ID, "task_id": TASK_ID}
    raise AssertionError(name)


def _acceptance() -> dict[str, Any]:
    return {
        "operation_id": OPERATION_ID,
        "task_id": TASK_ID,
        "assignment_id": ASSIGNMENT_ID,
        "status": "accepted",
        "accepted_at": "2026-11-16T12:00:00Z",
        "task_status_at_acceptance": "evaluation_pending",
        "processing_stage_at_acceptance": "finalization_pending",
        "replayed": False,
        "pre_submission_results": [],
    }


def _catalogue(client: TestClient) -> list[dict[str, Any]]:
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer fixture-token",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return response.json()["result"]["tools"]


def test_task_execution_catalogue_is_exact_closed_and_does_not_dispatch(
    adapter: Adapter,
) -> None:
    client, received, _ = adapter
    catalogue = {tool["name"]: tool for tool in _catalogue(client)}
    selected = [catalogue[name] for name in task_execution.TOOL_NAMES]
    assert [tool["name"] for tool in selected] == list(task_execution.TOOL_NAMES)
    for name, tool in zip(TASK_EXECUTION_CONTRACT_NAMES, selected, strict=True):
        assert tool["inputSchema"] == TASK_EXECUTION_INPUT_SCHEMAS[name]
        Draft202012Validator.check_schema(tool["inputSchema"])
        Draft202012Validator.check_schema(tool["outputSchema"])
        Draft202012Validator(
            tool["inputSchema"], format_checker=FormatChecker()
        ).validate(_arguments(name))
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["annotations"]["readOnlyHint"] is False
    assert "workstream_preparation_create" not in catalogue
    assert received == []


@pytest.mark.parametrize(
    "name",
    [name for name in TASK_EXECUTION_CONTRACT_NAMES
     if name not in {"task_guide_document_content_get", "project_contributor_guide_document_get"}],
)
@pytest.mark.asyncio
async def test_every_json_operation_forwards_only_its_fixed_request(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    captured: dict[str, Any] = {}

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        captured.update(args=args, kwargs=kwargs)
        return GatewayResult(data=_bound_response(name))

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    arguments = _arguments(name)
    upload = b"PK\x03\x04fixture" if name == "submission_create" else None
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_execution_operation(
            name,
            "Bearer caller-token",
            arguments,
            "request-correlation",
            upload=upload,
        )

    method, path_template, status = TASK_EXECUTION_OPERATIONS[name]
    expected_path = path_template
    for key, value in arguments.items():
        expected_path = expected_path.replace("{" + key + "}", str(value))
    assert result.failure is None
    assert captured["args"][:5] == (
        method,
        expected_path,
        "Bearer caller-token",
        ANY,
        "request-correlation",
    )
    assert captured["kwargs"]["expected_status"] == status
    assert captured["kwargs"]["json_body"] == arguments.get("body")
    assert captured["kwargs"]["idempotency_key"] == arguments.get("idempotency_key")


@pytest.mark.asyncio
async def test_assignment_feedback_uses_one_selector_and_rejects_substitution(monkeypatch):
    name = "task_assignment_get"
    args = {"assignment_id": ASSIGNMENT_ID, "limit": 2, "cursor": "next"}
    validator = Draft202012Validator(TASK_EXECUTION_INPUT_SCHEMAS[name])
    assert validator.is_valid(args)
    assert not validator.is_valid(args | {"task_id": TASK_ID})
    assert not validator.is_valid({"task_id": TASK_ID})
    assert not validator.is_valid(args | {"cursor": "x" * 513})

    async def request(_gateway, method, path, bearer, _validator, _correlation, **kwargs):
        assert (method, path, bearer) == (
            "GET", f"/api/v1/actors/me/assignments/{ASSIGNMENT_ID}", "Bearer caller",
        )
        assert kwargs["params"] == {"limit": "2", "cursor": "next"}
        return GatewayResult(data={
            "assignment": {"assignment_id": SUBMISSION_ID, "task_id": TASK_ID},
        })

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        gateway = WorkstreamGateway(Settings(api_url="http://127.0.0.1:8000"), client)
        result = await gateway.task_execution_operation(name, "Bearer caller", args)
    assert result.failure is not None and result.failure.error == "invalid_api_response"


@pytest.mark.asyncio
async def test_claim_dispatches_one_atomic_claim_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[str] = []

    async def request(
        _gateway: WorkstreamGateway,
        _method: str,
        path: str,
        *args: Any,
        **kwargs: Any,
    ) -> GatewayResult:
        del args, kwargs
        paths.append(path)
        return GatewayResult(data=_bound_response("task_claim"))

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_execution_operation(
            "task_claim", "Bearer opaque", _arguments("task_claim")
        )

    assert result.failure is None
    assert paths == [f"/api/v1/tasks/{TASK_ID}/claim"]
    assert result.data is not None
    assert result.data["task"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_assigned_guide_document_uses_only_the_fixed_binary_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def request_binary(
        _: WorkstreamGateway,
        path: str,
        bearer: str,
        correlation_id: str | None,
    ) -> GatewayResult:
        captured.update(path=path, bearer=bearer, correlation_id=correlation_id)
        return GatewayResult(data=_bound_response("task_guide_document_content_get"))

    monkeypatch.setattr(WorkstreamGateway, "_request_binary", request_binary)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_execution_operation(
            "task_guide_document_content_get",
            "Bearer caller-token",
            _arguments("task_guide_document_content_get"),
            "request-correlation",
        )

    assert result.failure is None
    assert captured == {
        "path": f"/api/v1/tasks/{TASK_ID}/guide/documents/{DOCUMENT_ID}/content",
        "bearer": "Bearer caller-token",
        "correlation_id": "request-correlation",
    }


def test_submission_upload_decodes_once_and_forwards_only_reviewed_headers(
    adapter: Adapter,
) -> None:
    client, received, upstream = adapter
    content = b"PK\x03\x04fixture"
    upstream["status"] = 202
    upstream["json"] = _acceptance()
    response = client.post(
        "/mcp",
        headers={
            "authorization": "Bearer fixture-token",
            "accept": "application/json, text/event-stream",
            "idempotency-key": "019a2a00-0000-7000-8000-000000009999",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_submission_create",
                "arguments": _arguments("submission_create"),
            },
        },
    )
    assert response.json()["result"]["isError"] is False
    request = received[0]
    assert request.content == content
    assert request.headers["authorization"] == 'Bearer api-fixture-token'
    assert request.headers["content-type"] == "application/zip"
    assert request.headers["idempotency-key"] == KEY
    assert request.headers["x-task-assignment-id"] == ASSIGNMENT_ID
    assert request.headers["x-submission-feedback"] == "ready  for review"
    assert "x-submission-summary" not in request.headers


def test_submission_bundle_contract_fits_inside_mcp_ingress() -> None:
    schema = TASK_EXECUTION_INPUT_SCHEMAS["submission_create"]
    assert schema["properties"]["zip_base64"]["maxLength"] == (
        SUBMISSION_BUNDLE_MAX_BASE64_CHARS
    )
    assert Settings(api_url="http://127.0.0.1:8000").max_request_bytes > (
        SUBMISSION_BUNDLE_MAX_BASE64_CHARS
    )


@pytest.mark.parametrize("text", ["ready\n", " edge", "café", "x" * 4097])
def test_submission_feedback_rejects_non_wire_text(
    adapter: Adapter, text: str,
) -> None:
    client, received, _ = adapter
    arguments = {**_arguments("submission_create"), "feedback": text}
    response = client.post(
        "/mcp",
        headers={
            "authorization": "Bearer fixture-token",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_submission_create",
                "arguments": arguments,
            },
        },
    )

    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_retired_revision_selector_never_dispatches(adapter: Adapter) -> None:
    client, received, _ = adapter
    arguments = {
        **_arguments("submission_create"),
        "revision_preparation_id": PREPARATION_ID,
    }
    response = client.post(
        "/mcp",
        headers={
            "authorization": "Bearer fixture-token",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_submission_create",
                "arguments": arguments,
            },
        },
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_pre_submit_checker_failure_is_a_safe_tool_outcome(adapter: Adapter) -> None:
    client, received, upstream = adapter
    upstream["status"] = 422
    upstream["json"] = {
        "error": {
            "code": "pre_submission_checker_failed",
            "message": "Pre-submission checks failed",
            "details": {
                "eligible_to_submit": False, "status": "failed", "results": [{
                    "source": "workstream_default", "check_id": "archive_safe", "status": "failed",
                    "failure_code": "submission_archive_malformed", "finding_count": 1,
                }],
            },
            "correlation_id": KEY,
            "retryable": False,
        }
    }
    response = client.post(
        "/mcp",
        headers={
            "authorization": "Bearer fixture-token",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_submission_create",
                "arguments": _arguments("submission_create"),
            },
        },
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 422
    assert result["structuredContent"]["code"] == "pre_submission_checker_failed"
    assert result["structuredContent"]["details"] == upstream["json"]["error"]["details"]
    assert len(received) == 1


@pytest.mark.asyncio
async def test_substituted_mutation_response_fails_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        return GatewayResult(data={"id": PROJECT_ID})

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_execution_operation(
            "task_release", "Bearer opaque", _arguments("task_release")
        )

    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"


@pytest.mark.parametrize("change", [
    {"task_id": PROJECT_ID},
    {"assignment_id": PROJECT_ID},
    {"operation_id": "not-a-uuid"},
    {"accepted_at": "not-a-timestamp"},
    {"status": "completed"},
    {"processing_stage_at_acceptance": "post_pending"},
    {"replayed": None},
    {"submission_id": SUBMISSION_ID},
])
def test_submission_acceptance_refuses_substitution_and_invalid_snapshots(
    adapter: Adapter, change: dict[str, Any]
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 202
    upstream["json"] = _acceptance() | change
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer fixture-token",
                 "accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "workstream_submission_create",
                         "arguments": _arguments("submission_create")}},
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


@pytest.mark.parametrize("fields", [
    {"predecessor_submission_id": SUBMISSION_ID},
    {"revision_preparation_id": PREPARATION_ID,
     "revision_preparation_sha256": "sha256:" + "a" * 64},
])
def test_submission_has_no_revision_acknowledgement_inputs(
    fields: dict[str, Any],
) -> None:
    validator = Draft202012Validator(
        TASK_EXECUTION_INPUT_SCHEMAS["submission_create"], format_checker=FormatChecker()
    )
    assert not validator.is_valid(_arguments("submission_create") | fields)
    assert validator.is_valid({
        key: value for key, value in _arguments("submission_create").items() if key != "feedback"
    })


def _operation_progress() -> dict[str, Any]:
    return {
        "operation_id": OPERATION_ID,
        "task_id": TASK_ID,
        "assignment_id": ASSIGNMENT_ID,
        "idempotency_key": KEY,
        "operation_state": "finalization_pending",
        "processing_stage": "finalization_pending",
        "accepted_at": "2026-11-16T12:00:00Z",
        "task_status_at_acceptance": "evaluation_pending",
        "current_task_status": None,
        "submission_id": None,
        "submission_version": None,
        "evaluation_request_id": None,
        "pre_submission_results": [],
        "failure_code": None,
        "operationally_stalled": False,
        "next_action": "wait",
    }


@pytest.mark.parametrize(
    "selector,value", [("operation_id", OPERATION_ID), ("idempotency_key", KEY)]
)
def test_operation_progress_uses_one_get_and_binds_selector(
    adapter: Adapter, selector, value
) -> None:
    client, received, upstream = adapter
    upstream["json"] = _operation_progress()
    arguments = {"task_id": TASK_ID, selector: value}

    def read():
        return client.post(
            "/mcp",
            headers={
                "authorization": "Bearer fixture-token",
                "accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "workstream_submission_operation_get", "arguments": arguments},
            },
        ).json()["result"]

    assert read()["isError"] is False
    assert len(received) == 1
    assert received[0].method == "GET"
    assert received[0].url.path == f"/api/v1/tasks/{TASK_ID}/submission-operations"
    assert dict(received[0].url.params) == {selector: value}
    assert "idempotency-key" not in received[0].headers
    upstream["json"][selector] = ASSIGNMENT_ID
    assert read()["isError"] is True


@pytest.mark.parametrize(
    "selectors",
    [
        {},
        {"operation_id": OPERATION_ID, "idempotency_key": KEY},
        {"operation_id": "bad"},
        {"idempotency_key": KEY, "actor_id": ASSIGNMENT_ID},
    ],
)
def test_operation_progress_invalid_selectors_never_dispatch(adapter: Adapter, selectors) -> None:
    client, received, _ = adapter
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer fixture-token",
                 "accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_submission_operation_get",
                "arguments": {"task_id": TASK_ID, **selectors},
            },
        },
    )
    assert response.json()["result"]["isError"] is True
    assert received == []


@pytest.mark.parametrize(
    "change", ["foreign_task", "private_field", "missing_nullable", "unknown_stage"]
)
def test_operation_progress_rejects_unbound_or_noncontract_response(
    adapter: Adapter, change
) -> None:
    client, received, upstream = adapter
    progress = _operation_progress()
    if change == "foreign_task":
        progress["task_id"] = ASSIGNMENT_ID
    elif change == "private_field":
        progress["provider_key"] = "private"
    elif change == "missing_nullable":
        del progress["evaluation_request_id"]
    else:
        progress["processing_stage"] = "invented"
    upstream["json"] = progress
    response = client.post("/mcp", headers={"authorization": "Bearer fixture-token",
                 "accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "workstream_submission_operation_get",
            "arguments": {"task_id": TASK_ID, "operation_id": OPERATION_ID}}})
    assert response.json()["result"]["isError"] is True
    assert len(received) == 1


@pytest.mark.parametrize("valid", [True, False])
def test_submission_pre_timeout_requires_closed_terminal_envelope(
    adapter: Adapter, valid: bool,
) -> None:
    """Forward known timeout guidance while leaving a malformed 504 uncertain."""
    client, received, upstream = adapter
    action = {"next_action": "retry_new_key_after_terminal"}
    upstream["status"] = 504
    upstream["json"] = {"error": {
        "code": "submission_pre_timeout",
        "message": "private runner diagnostic",
        "details": action if valid else action | {"private": "opaque value"},
        "correlation_id": "a92cd489-0aef-4e95-97c9-e10b4ae52b68",
        "retryable": True,
    }}
    response = client.post("/mcp", headers={"authorization": "Bearer fixture-token",
                 "accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "workstream_submission_create", "arguments": _arguments("submission_create")}})
    result = response.json()["result"]
    assert result["isError"] is True and len(received) == 1
    error = result["structuredContent"]
    if valid:
        assert error["error"] == "workstream_request_failed"
        assert error["code"] == "submission_pre_timeout" and error["details"] == action
        assert error["retryable"] is True and "new idempotency key" in error["message"]
    else:
        assert error["error"] == "workstream_execution_uncertain" and error["retryable"] is False
        assert "code" not in error and "details" not in error
    assert "private runner diagnostic" not in response.text and "opaque value" not in response.text


@pytest.mark.parametrize("private_message", [False, True])
@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "submission_outcome_unknown",
            "Check the original submission operation or retry with the same idempotency key",
        ),
        (
            "submission_infrastructure_unavailable",
            "Submission processing is temporarily unavailable",
        ),
    ],
)
def test_submission_transport_failure_preserves_safe_recovery_guidance(
    adapter: Adapter,
    code: str,
    message: str,
    private_message: bool,
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 503
    supplied_message = (
        "https://private-provider.invalid?token=private-token" if private_message else message
    )
    upstream["json"] = {
        "error": {
            "code": code,
            "message": supplied_message,
            "details": {"private_provider_diagnostic": "must not escape"},
        }
    }
    response = client.post(
        "/mcp",
        headers={
            "authorization": "Bearer fixture-token",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_submission_create",
                "arguments": _arguments("submission_create"),
            },
        },
    )
    result = response.json()["result"]
    assert result["isError"] is True
    error = result["structuredContent"]
    assert (error["status"], error.get("code"), error.get("message"), error["retryable"]) == (
        503,
        code,
        message,
        False,
    )
    assert error["error"] == "workstream_execution_uncertain"
    assert "details" not in error
    assert "must not escape" not in response.text
    assert "private-provider" not in response.text
    assert "private-token" not in response.text
    assert len(received) == 1


@pytest.mark.parametrize(
    "malformed_code",
    [None, 17, ["submission_outcome_unknown"], {"code": "submission_outcome_unknown"}],
)
def test_submission_transport_failure_rejects_nonstring_error_code(
    adapter: Adapter, malformed_code: object
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 503
    upstream["json"] = {
        "error": {
            "code": malformed_code,
            "message": "private-provider-token",
            "details": {"private_provider_diagnostic": "must not escape"},
        }
    }
    response = client.post(
        "/mcp",
        headers={
            "authorization": "Bearer fixture-token",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "workstream_submission_create",
                "arguments": _arguments("submission_create"),
            },
        },
    )
    result = response.json()["result"]
    assert result["isError"] is True
    error = result["structuredContent"]
    assert error["status"] == 503 and error.get("code") is None
    assert error["error"] == "workstream_execution_uncertain"
    assert "private-provider-token" not in response.text
    assert "must not escape" not in response.text
    assert len(received) == 1
