from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import WorkstreamGateway

PROJECT_ID = "019a2a00-0000-7000-8000-000000000401"
GUIDE_ID = "019a2a00-0000-7000-8000-000000000402"
POLICY_ID = "019a2a00-0000-7000-8000-000000000403"
PREDECESSOR_ID = "019a2a00-0000-7000-8000-000000000404"
KEY = "019a2a00-0000-7000-8000-000000000405"
DIGEST = "sha256:" + "a" * 64
INITIAL = '"no-current-policy"'
CURRENT = f'"{PREDECESSOR_ID}.1.{DIGEST.removeprefix("sha256:")}"'
TOOLS = ("workstream_review_policy_put", "workstream_revision_policy_put")
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _review_body(**overrides: Any) -> dict[str, Any]:
    value = {
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
    }
    value.update(overrides)
    return value


def _revision_body(**overrides: Any) -> dict[str, Any]:
    value = {"max_revision_rounds": 3, "revision_deadline_hours": 48}
    value.update(overrides)
    return value


def _arguments(name: str, *, current: bool = False) -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "guide_id": GUIDE_ID,
        "body": _review_body() if name == "review_policy_put" else _revision_body(),
        "idempotency_key": KEY,
        "if_match": CURRENT if current else INITIAL,
    }


def _review_response(*, current: bool = False, mode: bool = True) -> dict[str, Any]:
    return {
        "id": POLICY_ID,
        "project_id": PROJECT_ID,
        "guide_version": "v1",
        "policy_generation": 2 if current else 1,
        "policy_hash": DIGEST,
        "human_review_required": mode,
        "semantics_format": "v2",
        "semantics_status": "complete",
        "supersedes_policy_id": PREDECESSOR_ID if current else None,
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
        "max_active_review_leases_per_reviewer": 1,
        "self_review_allowed": False,
        "reject_policy": "close_task",
        "finding_evidence_requirement": "optional",
        "requires_second_review": False,
        "allowed_decisions": ["accept", "needs_revision", "reject"],
        "minimum_finding_fields": [],
        "created_at": "2026-10-23T01:00:00Z",
    }


def _revision_response(*, current: bool = False) -> dict[str, Any]:
    return {
        "id": POLICY_ID,
        "project_id": PROJECT_ID,
        "guide_version": "v1",
        "policy_generation": 2 if current else 1,
        "policy_hash": DIGEST,
        "semantics_status": "complete",
        "supersedes_policy_id": PREDECESSOR_ID if current else None,
        "max_revision_rounds": 3,
        "revision_deadline_hours": 48,
        "allowed_resubmission_states": ["needs_revision"],
        "reviewer_reassignment_rule": None,
        "created_at": "2026-10-23T01:00:00Z",
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
def test_policy_tools_advertise_closed_keyed_precondition_contracts(
    adapter: Adapter, name: str
) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    Draft202012Validator.check_schema(tool["inputSchema"])
    Draft202012Validator.check_schema(tool["outputSchema"])
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["annotations"]["idempotentHint"] is True
    assert tool["annotations"]["openWorldHint"] is False
    assert received == []


@pytest.mark.parametrize("contract_name", ["review_policy_put", "revision_policy_put"])
@pytest.mark.parametrize("current", [False, True])
def test_policy_mutations_forward_fixed_body_bearer_key_and_selector_unchanged(
    adapter: Adapter,
    call: Call,
    contract_name: str,
    current: bool,
) -> None:
    client, received, upstream = adapter
    response = (
        _review_response(current=current)
        if contract_name == "review_policy_put"
        else _revision_response(current=current)
    )
    arguments = _arguments(contract_name, current=current)
    upstream.update(status=200, json=response)
    result = call(
        client,
        name=f"workstream_{contract_name}",
        arguments=arguments,
        token="project-manager",
        extra_headers={"Idempotency-Key": POLICY_ID, "If-Match": '"ignored"'},
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == response
    assert len(received) == 1
    request = received[0]
    kind = "review" if contract_name == "review_policy_put" else "revision"
    assert request.method == "PUT"
    assert request.url.path == (
        f"/api/v1/projects/{PROJECT_ID}/guides/{GUIDE_ID}/{kind}-policy"
    )
    assert request.headers["authorization"] == 'Bearer api-project-manager'
    assert request.headers["idempotency-key"] == KEY
    assert request.headers["if-match"] == arguments["if_match"]
    assert json.loads(request.content) == arguments["body"]


def test_review_mode_omission_accepts_backend_inherited_false_value(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream.update(status=200, json=_review_response(current=True, mode=False))
    result = call(
        client,
        name="workstream_review_policy_put",
        arguments=_arguments("review_policy_put", current=True),
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["human_review_required"] is False
    assert len(received) == 1


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("workstream_review_policy_put", {}),
        (
            "workstream_review_policy_put",
            {**_arguments("review_policy_put"), "project_id": "bad"},
        ),
        (
            "workstream_review_policy_put",
            {
                **_arguments("review_policy_put"),
                "body": _review_body(requires_second_review=True),
            },
        ),
        (
            "workstream_review_policy_put",
            {**_arguments("review_policy_put"), "if_match": '"bad\nvalue"'},
        ),
        (
            "workstream_review_policy_put",
            {**_arguments("review_policy_put"), "if_match": f"{INITIAL}\n"},
        ),
        (
            "workstream_revision_policy_put",
            {
                **_arguments("revision_policy_put"),
                "body": _revision_body(max_revision_rounds=-1),
            },
        ),
        (
            "workstream_revision_policy_put",
            {
                **_arguments("revision_policy_put"),
                "body": _revision_body(max_revision_rounds=1.0),
            },
        ),
        (
            "workstream_revision_policy_put",
            {
                **_arguments("revision_policy_put"),
                "body": _revision_body(extra="forbidden"),
            },
        ),
        (
            "workstream_revision_policy_put",
            {**_arguments("revision_policy_put"), "idempotency_key": "bad"},
        ),
    ],
)
def test_invalid_policy_input_never_dispatches(
    adapter: Adapter, call: Call, name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_mcp_headers_and_metadata_cannot_supply_policy_mutation_values(
    adapter: Adapter,
) -> None:
    client, received, _ = adapter
    arguments = _arguments("review_policy_put")
    arguments.pop("idempotency_key")
    arguments.pop("if_match")
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer project-manager",
            "idempotency-key": KEY,
            "if-match": INITIAL,
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_review_policy_put",
                "arguments": arguments,
                "_meta": {"idempotency_key": KEY, "if_match": INITIAL},
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize(
    "response",
    [
        _review_response() | {"project_id": GUIDE_ID},
        _review_response() | {"policy_generation": 2},
        _review_response(current=True) | {"supersedes_policy_id": POLICY_ID},
        _review_response() | {"review_lease_duration_seconds": 900},
    ],
)
def test_policy_mutations_reject_substituted_success_as_uncertain(
    adapter: Adapter, call: Call, response: dict[str, Any]
) -> None:
    client, received, upstream = adapter
    current = response.get("policy_generation") == 2 and response.get(
        "supersedes_policy_id"
    ) is not None
    upstream.update(status=200, json=response)
    result = call(
        client,
        name="workstream_review_policy_put",
        arguments=_arguments("review_policy_put", current=current),
    ).json()["result"]
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


@pytest.mark.parametrize("code", ["policy_precondition_invalid", "policy_precondition_failed"])
def test_policy_conflicts_are_preserved_without_message_or_token_leakage(
    adapter: Adapter, call: Call, code: str
) -> None:
    client, received, upstream = adapter
    upstream.update(status=409, json={"error": {"code": code, "message": "private"}})
    result = call(
        client,
        name="workstream_review_policy_put",
        arguments=_arguments("review_policy_put"),
        token="private-token",
    ).json()["result"]
    assert result["structuredContent"]["code"] == code
    serialized = json.dumps(result)
    assert "private-token" not in serialized
    assert "private" not in serialized
    assert len(received) == 1


@pytest.mark.asyncio
async def test_policy_transport_failure_is_uncertain_and_not_retried() -> None:
    calls = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadError("private transport failure", request=request)

    async with httpx.AsyncClient(
        base_url="http://workstream.test",
        transport=httpx.MockTransport(fail),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).policy_mutation(
            "review_policy_put",
            "Bearer opaque",
            _arguments("review_policy_put"),
        )
    assert calls == 1
    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"
    assert result.failure.retryable is False
