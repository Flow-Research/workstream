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
ADMISSION_ID = "019a2a00-0000-7000-8000-000000000707"
KEY = "019a2a00-0000-7000-8000-000000000708"
PUT_ATTEMPT_ID = "019a2a00-0000-7000-8000-000000000709"
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]


def _arguments(name: str) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "preparation_create": {
            "task_id": TASK_ID,
            "assignment_id": ASSIGNMENT_ID,
            "zip_base64": base64.b64encode(b"PK\x03\x04fixture").decode(),
            "idempotency_key": KEY,
            "summary": "ready",
            "contributor_attestation": "reviewed",
        },
        "preparations_list": {"task_id": TASK_ID, "limit": 25, "cursor": "opaque"},
        "preparation_get": {"task_id": TASK_ID, "preparation_id": PREPARATION_ID},
        "task_get": {"task_id": TASK_ID},
        "task_submission_requirements_get": {"task_id": TASK_ID},
        "task_screen": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_release": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_claim": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_start": {"task_id": TASK_ID, "idempotency_key": KEY},
        "task_work_context_get": {"task_id": TASK_ID},
        "task_guide_document_content_get": {
            "task_id": TASK_ID,
            "document_id": DOCUMENT_ID,
        },
        "submission_create": {
            "task_id": TASK_ID,
            "body": {"admission_id": ADMISSION_ID, "assignment_id": ASSIGNMENT_ID},
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
    if name == "preparation_create":
        return {"put_attempt_id": PUT_ATTEMPT_ID}
    if name in {"preparations_list", "task_submissions_list", "management_task_submissions_list"}:
        return {"items": [], "next_cursor": None}
    if name == "preparation_get":
        return {"task_id": TASK_ID, "preparation_id": PREPARATION_ID}
    if name in {"task_get", "task_submission_requirements_get"}:
        return {"task_id": TASK_ID}
    if name in {"task_screen", "task_release", "task_start"}:
        return {"id": TASK_ID}
    if name == "task_claim":
        return {"task": {"id": TASK_ID}, "assignment": {"task_id": TASK_ID}}
    if name == "task_work_context_get":
        return {"task": {"task_id": TASK_ID}}
    if name == "task_guide_document_content_get":
        return {
            "media_type": "text/markdown",
            "content_base64": "eA==",
            "byte_count": 1,
            "sha256": "sha256:" + "0" * 64,
        }
    if name == "submission_create":
        return {"admission_id": ADMISSION_ID}
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


def _catalogue(client: TestClient) -> list[dict[str, Any]]:
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
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
    assert received == []


@pytest.mark.parametrize(
    "name",
    [name for name in TASK_EXECUTION_CONTRACT_NAMES if name != "task_guide_document_content_get"],
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
    upload = b"PK\x03\x04fixture" if name == "preparation_create" else None
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
async def test_claim_dispatches_only_claim_and_never_start(
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


def test_preparation_upload_decodes_once_and_forwards_only_reviewed_headers(
    adapter: Adapter,
) -> None:
    client, received, upstream = adapter
    content = b"PK\x03\x04fixture"
    upstream["status"] = 202
    upstream["json"] = {
        "put_attempt_id": PUT_ATTEMPT_ID,
        "admission_id": None,
        "submission_bundle_preparation_status": "put_in_flight",
        "replayed": False,
        "pre_submission_results": [],
    }
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
                "name": "workstream_preparation_create",
                "arguments": _arguments("preparation_create"),
            },
        },
    )
    assert response.json()["result"]["isError"] is False
    request = received[0]
    assert request.content == content
    assert request.headers["authorization"] == "Bearer fixture-token"
    assert request.headers["content-type"] == "application/zip"
    assert request.headers["idempotency-key"] == KEY
    assert request.headers["x-task-assignment-id"] == ASSIGNMENT_ID
    assert request.headers["x-submission-summary"] == "ready"
    assert request.headers["x-contributor-attestation"] == "reviewed"


def test_preparation_bundle_contract_fits_inside_mcp_ingress() -> None:
    schema = TASK_EXECUTION_INPUT_SCHEMAS["preparation_create"]
    assert schema["properties"]["zip_base64"]["maxLength"] == (
        SUBMISSION_BUNDLE_MAX_BASE64_CHARS
    )
    assert Settings(api_url="http://127.0.0.1:8000").max_request_bytes > (
        SUBMISSION_BUNDLE_MAX_BASE64_CHARS
    )


@pytest.mark.parametrize("field", ["summary", "contributor_attestation"])
def test_preparation_header_text_rejects_trailing_newline_before_dispatch(
    adapter: Adapter, field: str
) -> None:
    client, received, _ = adapter
    arguments = {**_arguments("preparation_create"), field: "ready\n"}
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
                "name": "workstream_preparation_create",
                "arguments": arguments,
            },
        },
    )

    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_incomplete_revision_preparation_selector_never_dispatches(adapter: Adapter) -> None:
    client, received, _ = adapter
    arguments = {
        **_arguments("preparation_create"),
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
                "name": "workstream_preparation_create",
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
            "details": {"eligible_to_submit": False},
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
                "name": "workstream_preparation_create",
                "arguments": _arguments("preparation_create"),
            },
        },
    )
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 422
    assert result["structuredContent"]["code"] == "pre_submission_checker_failed"
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
            "task_start", "Bearer opaque", _arguments("task_start")
        )

    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"
