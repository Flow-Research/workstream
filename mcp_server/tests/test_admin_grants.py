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

ACTOR_ID = "019a2a00-0000-7000-8000-000000000001"
PROJECT_ID = "019a2a00-0000-7000-8000-000000000002"
GRANT_ID = "019a2a00-0000-7000-8000-000000000003"
FOREIGN_GRANT_ID = "019a2a00-0000-7000-8000-000000000099"
KEY = "019a2a00-0000-7000-8000-000000000004"
CORRELATION_ID = "019a2a00-0000-4000-8000-000000000005"
TOOLS = (
    "workstream_admin_grants_issue",
    "workstream_admin_grants_revoke",
)
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _issue_arguments(*, reason: str = "Appoint project manager") -> dict[str, Any]:
    return {
        "body": {
            "target_actor_profile_id": ACTOR_ID,
            "role": "project_manager",
            "scope_type": "project",
            "scope_project_id": PROJECT_ID,
            "reason": reason,
        },
        "idempotency_key": KEY,
    }


def _revoke_arguments(*, reason: str = "Remove administrative responsibility") -> dict[str, Any]:
    return {
        "grant_id": GRANT_ID,
        "body": {"reason": reason},
        "idempotency_key": KEY,
    }


def _receipt(name: str) -> dict[str, Any]:
    issue = name == "workstream_admin_grants_issue"
    return {
        "resource_type": "admin_role_grant",
        "resource_id": GRANT_ID,
        "version": 1 if issue else 2,
        "http_status": 201 if issue else 200,
    }


def _catalogue(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return {tool["name"]: tool for tool in response.json()["result"]["tools"]}


@pytest.mark.parametrize("name", TOOLS)
def test_admin_grant_tools_advertise_closed_current_contracts(adapter: Adapter, name: str) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    arguments = _issue_arguments() if name.endswith("issue") else _revoke_arguments()
    for key, value in (("inputSchema", arguments), ("outputSchema", _receipt(name))):
        schema = tool[key]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    assert tool["annotations"] == {
        "title": (
            "Issue administrative grant"
            if name.endswith("issue")
            else "Revoke administrative grant"
        ),
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert received == []


@pytest.mark.parametrize("name", TOOLS)
def test_admin_grant_mutations_forward_exact_fixed_request(
    adapter: Adapter, call: Call, name: str
) -> None:
    client, received, upstream = adapter
    arguments = _issue_arguments(reason="  Preserve this exact reason  ")
    expected_path = "/api/v1/admin-role-grants"
    if name.endswith("revoke"):
        arguments = _revoke_arguments(reason="  Preserve this exact reason  ")
        expected_path = f"/api/v1/admin-role-grants/{GRANT_ID}/revoke"
    upstream["status"] = _receipt(name)["http_status"]
    upstream["json"] = _receipt(name)
    upstream["headers"] = {
        "content-type": "application/json",
        "x-correlation-id": CORRELATION_ID,
    }

    response = call(
        client,
        name=name,
        arguments=arguments,
        token="admin-caller",
        extra_headers={
            "Idempotency-Key": "ffffffff-ffff-4fff-8fff-ffffffffffff",
            "If-Match": '"caller-header"',
        },
    )

    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == _receipt(name)
    assert json.loads(result["content"][0]["text"]) == _receipt(name)
    assert len(received) == 1
    request = received[0]
    assert request.method == "POST"
    assert request.url.path == expected_path
    assert request.url.query == b""
    assert request.headers["authorization"] == "Bearer admin-caller"
    assert request.headers["idempotency-key"] == KEY
    assert "if-match" not in request.headers
    assert json.loads(request.content) == arguments["body"]
    assert "idempotency_key" not in json.loads(request.content)


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("workstream_admin_grants_issue", {"body": _issue_arguments()["body"]}),
        ("workstream_admin_grants_issue", _issue_arguments() | {"idempotency_key": None}),
        ("workstream_admin_grants_issue", _issue_arguments() | {"idempotency_key": "bad"}),
        (
            "workstream_admin_grants_issue",
            _issue_arguments() | {"idempotency_key": KEY + "\r\nX-Evil: yes"},
        ),
        (
            "workstream_admin_grants_issue",
            _issue_arguments() | {"body": _issue_arguments()["body"] | {"reason": ""}},
        ),
        (
            "workstream_admin_grants_issue",
            _issue_arguments() | {"body": _issue_arguments()["body"] | {"reason": "a\x00b"}},
        ),
        (
            "workstream_admin_grants_issue",
            _issue_arguments(reason="a" * 501),
        ),
        (
            "workstream_admin_grants_issue",
            _issue_arguments(reason="é" * 251),
        ),
        (
            "workstream_admin_grants_issue",
            _issue_arguments()
            | {
                "body": {
                    **_issue_arguments()["body"],
                    "scope_type": "project",
                    "scope_project_id": None,
                }
            },
        ),
        (
            "workstream_admin_grants_issue",
            _issue_arguments()
            | {
                "body": {
                    **_issue_arguments()["body"],
                    "role": "operator",
                    "scope_type": "project",
                }
            },
        ),
        (
            "workstream_admin_grants_revoke",
            _revoke_arguments() | {"grant_id": "not-a-uuid"},
        ),
        (
            "workstream_admin_grants_revoke",
            _revoke_arguments() | {"unexpected": True},
        ),
    ],
)
def test_invalid_admin_grant_input_never_dispatches(
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


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("workstream_admin_grants_issue", _issue_arguments(reason="é" * 250)),
        ("workstream_admin_grants_revoke", _revoke_arguments(reason="a" * 500)),
    ],
)
def test_reason_accepts_exact_500_utf8_byte_boundary(
    adapter: Adapter, call: Call, name: str, arguments: dict[str, Any]
) -> None:
    client, received, upstream = adapter
    upstream["status"] = _receipt(name)["http_status"]
    upstream["json"] = _receipt(name)
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["isError"] is False
    assert len(received) == 1
    assert json.loads(received[0].content)["reason"] == arguments["body"]["reason"]


def test_http_header_and_mcp_meta_cannot_supply_or_override_key(adapter: Adapter) -> None:
    client, received, _ = adapter
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer admin-caller",
            "idempotency-key": KEY,
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_admin_grants_issue",
                "arguments": {"body": _issue_arguments()["body"]},
                "_meta": {"idempotency_key": KEY},
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize(
    "name,status,payload",
    [
        (
            "workstream_admin_grants_issue",
            200,
            {
                "resource_type": "admin_role_grant",
                "resource_id": GRANT_ID,
                "version": 1,
                "http_status": 200,
            },
        ),
        (
            "workstream_admin_grants_revoke",
            200,
            {
                "resource_type": "admin_role_grant",
                "resource_id": GRANT_ID,
                "version": 1,
                "http_status": 200,
            },
        ),
        (
            "workstream_admin_grants_issue",
            503,
            {"error": {"code": "service_unavailable", "message": "private"}},
        ),
    ],
)
def test_unexpected_mutation_success_is_execution_uncertain(
    adapter: Adapter,
    call: Call,
    name: str,
    status: int,
    payload: dict[str, Any],
) -> None:
    client, received, upstream = adapter
    upstream["status"] = status
    upstream["json"] = payload
    arguments = _issue_arguments() if name.endswith("issue") else _revoke_arguments()
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


@pytest.mark.parametrize(
    ("receipt_grant_id", "is_error"),
    [
        (FOREIGN_GRANT_ID, True),
        (GRANT_ID.upper(), False),
    ],
)
def test_revoke_receipt_is_bound_to_requested_grant_uuid(
    adapter: Adapter,
    call: Call,
    receipt_grant_id: str,
    is_error: bool,
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 200
    upstream["json"] = {
        **_receipt("workstream_admin_grants_revoke"),
        "resource_id": receipt_grant_id,
    }

    result = call(
        client,
        name="workstream_admin_grants_revoke",
        arguments=_revoke_arguments(),
        extra_headers={"X-Request-ID": CORRELATION_ID},
    ).json()["result"]

    assert result["isError"] is is_error
    assert len(received) == 1
    if is_error:
        assert result["structuredContent"] == {
            "error": "workstream_execution_uncertain",
            "retryable": False,
            "status": 502,
            "correlation_id": CORRELATION_ID,
        }
    else:
        assert result["structuredContent"]["resource_id"] == receipt_grant_id


@pytest.mark.parametrize(
    "name,code",
    [
        ("workstream_admin_grants_issue", "self_grant_forbidden"),
        ("workstream_admin_grants_revoke", "last_access_administrator"),
        ("workstream_admin_grants_issue", "idempotency_mismatch"),
    ],
)
def test_admin_grant_api_denials_preserve_only_safe_status_code_and_correlation(
    adapter: Adapter, call: Call, name: str, code: str
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 409 if code != "self_grant_forbidden" else 403
    upstream["json"] = {
        "error": {"code": code, "message": "private backend detail", "details": {"secret": 1}}
    }
    upstream["headers"] = {
        "content-type": "application/json",
        "x-request-id": CORRELATION_ID,
    }
    arguments = _issue_arguments() if name.endswith("issue") else _revoke_arguments()
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "error": "workstream_request_failed",
        "retryable": False,
        "status": upstream["status"],
        "code": code,
        "correlation_id": CORRELATION_ID,
    }
    assert "private" not in json.dumps(result)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_admin_grant_transport_failure_is_uncertain_and_not_retried() -> None:
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
        ).admin_grant_mutation(
            "admin_grants_issue",
            "Bearer opaque",
            _issue_arguments(),
            CORRELATION_ID,
        )
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
