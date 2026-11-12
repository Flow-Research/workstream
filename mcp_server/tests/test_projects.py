from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import WorkstreamGateway

PROJECT_ID = "019a2a00-0000-7000-8000-000000000101"
FOREIGN_PROJECT_ID = "019a2a00-0000-7000-8000-000000000199"
KEY = "019a2a00-0000-7000-8000-000000000102"
CORRELATION_ID = "019a2a00-0000-4000-8000-000000000103"
TOOLS = ("workstream_projects_create", "workstream_projects_get")
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _create_arguments() -> dict[str, Any]:
    return {
        "body": {
            "name": "Project shell",
            "slug": "project-shell",
            "description": "A bounded project shell",
        },
        "idempotency_key": KEY,
    }


def _full_project(**overrides: Any) -> dict[str, Any]:
    project = {
        "id": PROJECT_ID,
        "name": "Project shell",
        "slug": "project-shell",
        "description": "A bounded project shell",
        "status": "draft",
        "created_at": "2026-10-19T10:00:00Z",
        "updated_at": "2026-10-19T10:00:00Z",
    }
    project.update(overrides)
    return project


def _catalogue(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer fixture-token",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return {tool["name"]: tool for tool in response.json()["result"]["tools"]}


@pytest.mark.parametrize("name", TOOLS)
def test_project_tools_advertise_closed_current_contracts(adapter: Adapter, name: str) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    arguments = _create_arguments() if name.endswith("create") else {"project_id": PROJECT_ID}
    response = _full_project() if name.endswith("create") else {
        "id": PROJECT_ID,
        "name": "Project shell",
        "status": "draft",
    }
    for key, value in (("inputSchema", arguments), ("outputSchema", response)):
        Draft202012Validator.check_schema(tool[key])
        Draft202012Validator(tool[key], format_checker=FormatChecker()).validate(value)
    assert tool["annotations"] == {
        "title": "Create project shell" if name.endswith("create") else "Read project shell",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": name.endswith("create"),
        "openWorldHint": name.endswith("get"),
    }
    assert received == []


def test_project_create_forwards_exact_fixed_request(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    arguments = _create_arguments()
    arguments["body"]["description"] = "  Preserve exact project text  "
    upstream.update(
        status=201,
        json=_full_project(description=arguments["body"]["description"]),
        headers={"content-type": "application/json", "x-correlation-id": CORRELATION_ID},
    )

    result = call(
        client,
        name="workstream_projects_create",
        arguments=arguments,
        token="project-manager",
        extra_headers={"Idempotency-Key": FOREIGN_PROJECT_ID, "If-Match": '"ignored"'},
    ).json()["result"]

    assert result["isError"] is False
    assert result["structuredContent"] == upstream["json"]
    assert json.loads(result["content"][0]["text"]) == upstream["json"]
    assert len(received) == 1
    request = received[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/projects"
    assert request.url.query == b""
    assert request.headers["authorization"] == 'Bearer api-project-manager'
    assert request.headers["idempotency-key"] == KEY
    assert "if-match" not in request.headers
    assert json.loads(request.content) == arguments["body"]


@pytest.mark.parametrize(
    "projection",
    [
        _full_project(),
        {"id": PROJECT_ID, "name": "Project shell", "status": "draft"},
    ],
)
def test_project_get_accepts_only_current_authorized_projections(
    adapter: Adapter, call: Call, projection: dict[str, Any]
) -> None:
    client, received, upstream = adapter
    upstream["json"] = projection

    result = call(
        client,
        name="workstream_projects_get",
        arguments={"project_id": PROJECT_ID.upper()},
        token="authorized-reader",
    ).json()["result"]

    assert result["isError"] is False
    assert result["structuredContent"] == projection
    assert result["content"][0]["text"].startswith("Untrusted Workstream data follows")
    assert json.loads(result["content"][1]["text"]) == projection
    assert len(received) == 1
    request = received[0]
    assert request.method == "GET"
    assert request.url.path == f"/api/v1/projects/{PROJECT_ID.upper()}"
    assert request.url.query == b""
    assert request.headers["authorization"] == 'Bearer api-authorized-reader'
    assert "idempotency-key" not in request.headers


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("workstream_projects_create", {"body": _create_arguments()["body"]}),
        (
            "workstream_projects_create",
            _create_arguments() | {"idempotency_key": None},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"idempotency_key": "not-a-uuid"},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"idempotency_key": KEY + "\r\nX-Evil: yes"},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"body": {"slug": "missing-name"}},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"body": {"name": "n", "slug": "s", "extra": True}},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"body": {"name": "n\x00", "slug": "s"}},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"body": {"name": "n" * 201, "slug": "s"}},
        ),
        (
            "workstream_projects_create",
            _create_arguments() | {"body": {"name": "n", "slug": "s" * 121}},
        ),
        ("workstream_projects_get", {}),
        ("workstream_projects_get", {"project_id": "not-a-uuid"}),
        ("workstream_projects_get", {"project_id": PROJECT_ID, "extra": True}),
    ],
)
def test_invalid_project_input_never_dispatches(
    adapter: Adapter, call: Call, name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "error": "invalid_tool_input",
        "retryable": False,
        "status": 400,
    }
    assert received == []


def test_http_header_and_mcp_meta_cannot_supply_project_key(adapter: Adapter) -> None:
    client, received, _ = adapter
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer project-manager",
            "idempotency-key": KEY,
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_projects_create",
                "arguments": {"body": _create_arguments()["body"]},
                "_meta": {"idempotency_key": KEY},
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize(
    "status,payload",
    [
        (200, _full_project()),
        (503, {"error": {"code": "service_unavailable", "message": "private"}}),
    ],
)
def test_unexpected_project_create_outcome_is_execution_uncertain(
    adapter: Adapter, call: Call, status: int, payload: dict[str, Any]
) -> None:
    client, received, upstream = adapter
    upstream.update(status=status, json=payload)
    result = call(
        client, name="workstream_projects_create", arguments=_create_arguments()
    ).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


def test_project_get_rejects_a_schema_valid_foreign_project(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    upstream["json"] = {
        "id": FOREIGN_PROJECT_ID,
        "name": "Foreign project",
        "status": "draft",
    }
    result = call(
        client,
        name="workstream_projects_get",
        arguments={"project_id": PROJECT_ID},
        extra_headers={"X-Request-ID": CORRELATION_ID},
    ).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "error": "invalid_api_response",
        "retryable": False,
        "status": 502,
        "correlation_id": CORRELATION_ID,
    }
    assert len(received) == 1


@pytest.mark.parametrize(
    "name,status,code,retryable",
    [
        ("workstream_projects_create", 409, "project_slug_conflict", False),
        ("workstream_projects_create", 409, "idempotency_mismatch", False),
        ("workstream_projects_create", 409, "idempotency_pending", True),
        (
            "workstream_projects_get",
            404,
            "project_authorization_resource_not_found",
            False,
        ),
    ],
)
def test_project_api_denials_preserve_only_safe_status_code_and_correlation(
    adapter: Adapter,
    call: Call,
    name: str,
    status: int,
    code: str,
    retryable: bool,
) -> None:
    client, received, upstream = adapter
    upstream.update(
        status=status,
        json={"error": {"code": code, "message": "private detail", "details": {"secret": 1}}},
        headers={"content-type": "application/json", "x-request-id": CORRELATION_ID},
    )
    arguments = _create_arguments() if name.endswith("create") else {"project_id": PROJECT_ID}
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "error": "workstream_request_failed",
        "retryable": retryable,
        "status": status,
        "code": code,
        "correlation_id": CORRELATION_ID,
    }
    assert "private" not in json.dumps(result)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_project_create_transport_failure_is_uncertain_and_not_retried() -> None:
    attempts = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("private transport failure", request=request)

    client = httpx.AsyncClient(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(fail),
    )
    try:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).project_create("Bearer opaque", _create_arguments(), CORRELATION_ID)
    finally:
        await client.aclose()
    assert attempts == 1
    assert result.data is None
    assert result.failure is not None
    assert result.failure.payload() == {
        "error": "workstream_execution_uncertain",
        "retryable": False,
        "status": 502,
        "correlation_id": CORRELATION_ID,
    }
