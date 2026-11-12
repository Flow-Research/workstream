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
LINK_ID = "019a2a00-0000-7000-8000-000000000002"
FOREIGN_ID = "019a2a00-0000-7000-8000-000000000099"
KEY = "019a2a00-0000-7000-8000-000000000003"
CORRELATION_ID = "019a2a00-0000-4000-8000-000000000004"
TOOLS = (
    "workstream_actor_suspend",
    "workstream_actor_reactivate",
    "workstream_actor_deactivate",
    "workstream_identity_link_revoke",
    "workstream_identity_link_reactivate",
)
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _contract_name(tool_name: str) -> str:
    return tool_name.removeprefix("workstream_")


def _arguments(name: str, *, reason: str = "Lifecycle administration") -> dict[str, Any]:
    resource_key = "actor_profile_id" if "identity_link" not in name else "identity_link_id"
    resource_id = ACTOR_ID if resource_key == "actor_profile_id" else LINK_ID
    return {
        resource_key: resource_id,
        "body": {"reason": reason},
        "idempotency_key": KEY,
    }


def _receipt(name: str, *, resource_id: str | None = None) -> dict[str, Any]:
    link = "identity_link" in name
    return {
        "resource_type": "actor_identity_link" if link else "actor_profile",
        "resource_id": resource_id or (LINK_ID if link else ACTOR_ID),
        "version": None,
        "http_status": 200,
    }


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
def test_lifecycle_tools_advertise_closed_current_contracts(adapter: Adapter, name: str) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    for key, value in (("inputSchema", _arguments(name)), ("outputSchema", _receipt(name))):
        schema = tool[key]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
        assert schema.get("additionalProperties") is False
    assert tool["annotations"] == {
        "title": {
            "workstream_actor_suspend": "Suspend actor",
            "workstream_actor_reactivate": "Reactivate actor",
            "workstream_actor_deactivate": "Deactivate actor",
            "workstream_identity_link_revoke": "Revoke identity link",
            "workstream_identity_link_reactivate": "Reactivate identity link",
        }[name],
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert received == []


@pytest.mark.parametrize(
    "name,path",
    [
        ("workstream_actor_suspend", f"/api/v1/actors/{ACTOR_ID}/suspend"),
        ("workstream_actor_reactivate", f"/api/v1/actors/{ACTOR_ID}/reactivate"),
        ("workstream_actor_deactivate", f"/api/v1/actors/{ACTOR_ID}/deactivate"),
        (
            "workstream_identity_link_revoke",
            f"/api/v1/actor-identity-links/{LINK_ID}/revoke",
        ),
        (
            "workstream_identity_link_reactivate",
            f"/api/v1/actor-identity-links/{LINK_ID}/reactivate",
        ),
    ],
)
def test_lifecycle_tools_forward_one_exact_fixed_request(
    adapter: Adapter, call: Call, name: str, path: str
) -> None:
    client, received, upstream = adapter
    arguments = _arguments(name, reason="  Preserve this exact reason  ")
    upstream.update(
        status=200,
        json=_receipt(name),
        headers={"content-type": "application/json", "x-correlation-id": CORRELATION_ID},
    )

    result = call(
        client,
        name=name,
        arguments=arguments,
        token="admin-caller",
        extra_headers={
            "Idempotency-Key": "ffffffff-ffff-4fff-8fff-ffffffffffff",
            "If-Match": '"caller-header"',
        },
    ).json()["result"]

    assert result["isError"] is False
    assert result["structuredContent"] == _receipt(name)
    assert json.loads(result["content"][0]["text"]) == _receipt(name)
    assert len(received) == 1
    request = received[0]
    assert request.method == "POST"
    assert request.url.path == path
    assert request.url.query == b""
    assert request.headers["authorization"] == 'Bearer api-admin-caller'
    assert request.headers["idempotency-key"] == KEY
    assert "if-match" not in request.headers
    assert json.loads(request.content) == arguments["body"]


@pytest.mark.parametrize("name", TOOLS)
@pytest.mark.parametrize("mutation", ("missing_key", "bad_key", "bad_target", "extra", "nul"))
def test_invalid_lifecycle_input_never_dispatches(
    adapter: Adapter, call: Call, name: str, mutation: str
) -> None:
    client, received, _ = adapter
    arguments = _arguments(name)
    resource_key = "identity_link_id" if "identity_link" in name else "actor_profile_id"
    if mutation == "missing_key":
        arguments.pop("idempotency_key")
    elif mutation == "bad_key":
        arguments["idempotency_key"] = "not-a-uuid"
    elif mutation == "bad_target":
        arguments[resource_key] = "not-a-uuid"
    elif mutation == "extra":
        arguments["route"] = "/api/v1/health"
    else:
        arguments["body"]["reason"] = "bad\x00reason"

    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"] == {
        "error": "invalid_tool_input",
        "retryable": False,
        "status": 400,
    }
    assert received == []


@pytest.mark.parametrize("name", TOOLS)
@pytest.mark.parametrize("reason", ("", "é" * 251))
def test_invalid_reason_byte_bounds_never_dispatch(
    adapter: Adapter, call: Call, name: str, reason: str
) -> None:
    client, received, _ = adapter
    result = call(client, name=name, arguments=_arguments(name, reason=reason)).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize("name,reason", [(TOOLS[0], "é" * 250), (TOOLS[3], "a" * 500)])
def test_reason_accepts_exact_500_utf8_byte_boundary(
    adapter: Adapter, call: Call, name: str, reason: str
) -> None:
    client, received, upstream = adapter
    upstream.update(status=200, json=_receipt(name))
    result = call(client, name=name, arguments=_arguments(name, reason=reason)).json()["result"]
    assert result["isError"] is False
    assert len(received) == 1
    assert json.loads(received[0].content)["reason"] == reason


def test_http_header_and_mcp_meta_cannot_supply_key(adapter: Adapter) -> None:
    client, received, _ = adapter
    arguments = _arguments(TOOLS[0])
    arguments.pop("idempotency_key")
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
                "name": TOOLS[0],
                "arguments": arguments,
                "_meta": {"idempotency_key": KEY},
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize("name", TOOLS)
@pytest.mark.parametrize(
    "fault", ("foreign", "resource_type", "version", "http_status", "malformed")
)
def test_invalid_success_receipt_is_execution_uncertain(
    adapter: Adapter, call: Call, name: str, fault: str
) -> None:
    client, received, upstream = adapter
    receipt: Any = _receipt(name)
    if fault == "foreign":
        receipt["resource_id"] = FOREIGN_ID
    elif fault == "resource_type":
        receipt["resource_type"] = (
            "actor_profile" if "identity_link" in name else "actor_identity_link"
        )
    elif fault == "version":
        receipt["version"] = 1
    elif fault == "http_status":
        receipt["http_status"] = 201
    else:
        receipt = {"private": "diagnostic"}
    upstream.update(status=200, json=receipt)

    result = call(
        client,
        name=name,
        arguments=_arguments(name),
        extra_headers={"X-Request-ID": CORRELATION_ID},
    ).json()["result"]
    assert result["structuredContent"] == {
        "error": "workstream_execution_uncertain",
        "retryable": False,
        "status": 502,
        "correlation_id": CORRELATION_ID,
    }
    assert "private" not in json.dumps(result)
    assert len(received) == 1


@pytest.mark.parametrize("name", (TOOLS[0], TOOLS[3]))
def test_equivalent_uppercase_receipt_uuid_is_accepted(
    adapter: Adapter, call: Call, name: str
) -> None:
    client, received, upstream = adapter
    expected_id = LINK_ID if "identity_link" in name else ACTOR_ID
    upstream.update(status=200, json=_receipt(name, resource_id=expected_id.upper()))
    result = call(client, name=name, arguments=_arguments(name)).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["resource_id"] == expected_id.upper()
    assert len(received) == 1


@pytest.mark.parametrize(
    "name,status,code",
    [
        ("workstream_actor_suspend", 409, "actor_already_suspended"),
        ("workstream_actor_reactivate", 409, "actor_not_suspended"),
        ("workstream_actor_deactivate", 409, "actor_deactivated_terminal"),
        ("workstream_identity_link_revoke", 409, "identity_link_already_revoked"),
        ("workstream_identity_link_reactivate", 409, "identity_link_not_revoked"),
        ("workstream_actor_suspend", 403, "last_access_administrator"),
        ("workstream_identity_link_revoke", 403, "resource_guard_denied"),
    ],
)
def test_lifecycle_denials_preserve_only_safe_status_code_and_correlation(
    adapter: Adapter, call: Call, name: str, status: int, code: str
) -> None:
    client, received, upstream = adapter
    upstream.update(
        status=status,
        json={"error": {"code": code, "message": "private detail", "details": {"secret": 1}}},
        headers={"content-type": "application/json", "x-request-id": CORRELATION_ID},
    )
    result = call(client, name=name, arguments=_arguments(name)).json()["result"]
    assert result["structuredContent"] == {
        "error": "workstream_request_failed",
        "retryable": False,
        "status": status,
        "code": code,
        "correlation_id": CORRELATION_ID,
    }
    assert "private" not in json.dumps(result)
    assert len(received) == 1


@pytest.mark.parametrize("status", (201, 503))
def test_unexpected_status_after_dispatch_is_execution_uncertain(
    adapter: Adapter, call: Call, status: int
) -> None:
    client, received, upstream = adapter
    upstream.update(status=status, json=_receipt(TOOLS[0]))
    result = call(client, name=TOOLS[0], arguments=_arguments(TOOLS[0])).json()["result"]
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


@pytest.mark.asyncio
async def test_lifecycle_transport_failure_is_uncertain_and_not_retried() -> None:
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
        ).actor_lifecycle_mutation(
            _contract_name(TOOLS[0]),
            "Bearer opaque",
            _arguments(TOOLS[0]),
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
