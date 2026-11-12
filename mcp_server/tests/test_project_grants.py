from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

PROJECT_ID = "019a2a00-0000-7000-8000-000000000201"
FOREIGN_PROJECT_ID = "019a2a00-0000-7000-8000-000000000299"
ACTOR_ID = "019a2a00-0000-7000-8000-000000000202"
GRANT_ID = "019a2a00-0000-7000-8000-000000000203"
SNAPSHOT_ID = "019a2a00-0000-7000-8000-000000000204"
ADMIN_ID = "019a2a00-0000-7000-8000-000000000205"
ADMIN_GRANT_ID = "019a2a00-0000-7000-8000-000000000206"
KEY = "019a2a00-0000-7000-8000-000000000207"
TOOLS = (
    "workstream_contributor_candidates_list",
    "workstream_project_grants_issue",
    "workstream_project_grants_list",
    "workstream_project_grants_get",
    "workstream_project_grants_revoke",
)
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _unavailable() -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    }


def _qualification() -> dict[str, Any]:
    return {
        "skills_snapshot": _unavailable(),
        "reputation_snapshot": _unavailable(),
        "prior_project_work_refs": [],
        "external_expertise_refs": [],
    }


def _issue_arguments() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "body": {
            "target_actor_profile_id": ACTOR_ID,
            "role": "submitter",
            "qualification": _qualification(),
            "reason": "Qualified for project participation",
        },
        "idempotency_key": KEY,
    }


def _receipt(*, status: str = "active", version: int = 1) -> dict[str, Any]:
    return {
        "id": GRANT_ID,
        "qualification_snapshot_id": SNAPSHOT_ID,
        "project_id": PROJECT_ID,
        "actor_profile_id": ACTOR_ID,
        "role": "submitter",
        "status": status,
        "version": version,
    }


def _grant(**overrides: Any) -> dict[str, Any]:
    value = {
        "id": GRANT_ID,
        "project_id": PROJECT_ID,
        "actor_profile_id": ACTOR_ID,
        "role": "submitter",
        "status": "active",
        "version": 1,
        "grant_method": "manual",
        "qualification_snapshot": {
            "id": SNAPSHOT_ID,
            "requested_role": "submitter",
            **_qualification(),
            "captured_by_actor_profile_id": ADMIN_ID,
            "captured_by_admin_role_grant_id": ADMIN_GRANT_ID,
            "captured_at": "2026-10-21T10:00:00Z",
        },
        "granted_by_actor_profile_id": ADMIN_ID,
        "granted_by_admin_role_grant_id": ADMIN_GRANT_ID,
        "granted_at": "2026-10-21T10:00:00Z",
        "grant_reason": "Qualified for project participation",
        "revoked_by_actor_profile_id": None,
        "revoked_at": None,
        "revoked_reason": None,
    }
    value.update(overrides)
    return value


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
def test_project_participation_tools_advertise_closed_contracts(
    adapter: Adapter, name: str
) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    Draft202012Validator.check_schema(tool["inputSchema"])
    Draft202012Validator.check_schema(tool["outputSchema"])
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["annotations"]["readOnlyHint"] is False
    mutation = name.endswith(("issue", "revoke"))
    assert tool["annotations"]["destructiveHint"] is mutation
    assert tool["annotations"]["idempotentHint"] is mutation
    assert tool["annotations"]["openWorldHint"] is not mutation
    assert received == []


@pytest.mark.parametrize(
    "name,arguments,response,path,query",
    [
        (
            "workstream_contributor_candidates_list",
            {"project_id": PROJECT_ID, "limit": 2, "cursor": "opaque"},
            {"items": [{"actor_profile_id": ACTOR_ID, "display_name": "Candidate"}],
             "next_cursor": "next"},
            f"/api/v1/projects/{PROJECT_ID}/contributor-candidates",
            b"limit=2&cursor=opaque",
        ),
        (
            "workstream_project_grants_list",
            {"project_id": PROJECT_ID, "status": "active", "role": "submitter", "limit": 1},
            {"items": [_grant()], "next_cursor": None},
            f"/api/v1/projects/{PROJECT_ID}/role-grants",
            b"status=active&role=submitter&limit=1",
        ),
        (
            "workstream_project_grants_get",
            {"project_id": PROJECT_ID, "grant_id": GRANT_ID},
            _grant(),
            f"/api/v1/projects/{PROJECT_ID}/role-grants/{GRANT_ID}",
            b"",
        ),
    ],
)
def test_project_participation_reads_forward_fixed_requests(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
    response: dict[str, Any],
    path: str,
    query: bytes,
) -> None:
    client, received, upstream = adapter
    upstream["json"] = response
    result = call(client, name=name, arguments=arguments, token="project-manager").json()[
        "result"
    ]
    assert result["isError"] is False
    assert result["structuredContent"] == response
    assert result["content"][0]["text"].startswith("Untrusted Workstream data follows")
    assert len(received) == 1
    request = received[0]
    assert request.method == "GET"
    assert request.url.path == path
    assert request.url.query == query
    assert request.headers["authorization"] == 'Bearer api-project-manager'
    assert "idempotency-key" not in request.headers


@pytest.mark.parametrize(
    "name,arguments,status,response,path",
    [
        (
            "workstream_project_grants_issue",
            _issue_arguments(),
            201,
            _receipt(),
            f"/api/v1/projects/{PROJECT_ID}/role-grants",
        ),
        (
            "workstream_project_grants_revoke",
            {
                "project_id": PROJECT_ID,
                "grant_id": GRANT_ID,
                "body": {"reason": "Participation ended"},
                "idempotency_key": KEY,
            },
            200,
            _receipt(status="revoked", version=2),
            f"/api/v1/projects/{PROJECT_ID}/role-grants/{GRANT_ID}/revoke",
        ),
    ],
)
def test_project_grant_mutations_forward_body_and_key_unchanged(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
    status: int,
    response: dict[str, Any],
    path: str,
) -> None:
    client, received, upstream = adapter
    upstream.update(status=status, json=response)
    result = call(
        client,
        name=name,
        arguments=arguments,
        token="project-manager",
        extra_headers={"Idempotency-Key": FOREIGN_PROJECT_ID},
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == response
    assert len(received) == 1
    request = received[0]
    assert request.method == "POST"
    assert request.url.path == path
    assert request.headers["authorization"] == 'Bearer api-project-manager'
    assert request.headers["idempotency-key"] == KEY
    assert json.loads(request.content) == arguments["body"]


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("workstream_contributor_candidates_list", {}),
        ("workstream_contributor_candidates_list", {"project_id": "not-a-uuid"}),
        ("workstream_project_grants_list", {"project_id": PROJECT_ID, "limit": 101}),
        ("workstream_project_grants_list", {"project_id": PROJECT_ID, "status": "all"}),
        ("workstream_project_grants_get", {"project_id": PROJECT_ID}),
        ("workstream_project_grants_issue", {**_issue_arguments(), "idempotency_key": None}),
        (
            "workstream_project_grants_issue",
            {**_issue_arguments(), "body": {**_issue_arguments()["body"], "reason": " padded "}},
        ),
        (
            "workstream_project_grants_issue",
            {
                **_issue_arguments(),
                "body": {
                    **_issue_arguments()["body"],
                    "qualification": {
                        **_qualification(),
                        "skills_snapshot": {
                            "availability": "available",
                            "reference_ids": [],
                            "unavailable_reason": None,
                        },
                    },
                },
            },
        ),
        (
            "workstream_project_grants_issue",
            {
                **_issue_arguments(),
                "body": {
                    **_issue_arguments()["body"],
                    "qualification": {
                        **_qualification(),
                        "external_expertise_refs": ["https://secret.example"],
                    },
                },
            },
        ),
        (
            "workstream_project_grants_revoke",
            {"project_id": PROJECT_ID, "grant_id": GRANT_ID, "body": {"reason": "x"}},
        ),
    ],
)
def test_invalid_project_participation_input_never_dispatches(
    adapter: Adapter, call: Call, name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"] == {
        "error": "invalid_tool_input",
        "retryable": False,
        "status": 400,
    }
    assert received == []


def test_mcp_headers_and_metadata_cannot_supply_project_grant_key(adapter: Adapter) -> None:
    client, received, _ = adapter
    arguments = _issue_arguments()
    arguments.pop("idempotency_key")
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
                "name": "workstream_project_grants_issue",
                "arguments": arguments,
                "_meta": {"idempotency_key": KEY},
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize(
    "name,arguments,response",
    [
        (
            "workstream_project_grants_list",
            {"project_id": PROJECT_ID},
            {"items": [_grant(project_id=FOREIGN_PROJECT_ID)], "next_cursor": None},
        ),
        (
            "workstream_project_grants_get",
            {"project_id": PROJECT_ID, "grant_id": GRANT_ID},
            _grant(id=ACTOR_ID),
        ),
    ],
)
def test_reads_reject_schema_valid_cross_resource_substitution(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
    response: dict[str, Any],
) -> None:
    client, received, upstream = adapter
    upstream["json"] = response
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_api_response"
    assert len(received) == 1


@pytest.mark.parametrize(
    "name,arguments,response",
    [
        (
            "workstream_contributor_candidates_list",
            {"project_id": PROJECT_ID},
            {
                "items": [
                    {"actor_profile_id": ACTOR_ID, "display_name": "One"},
                    {"actor_profile_id": ACTOR_ID.upper(), "display_name": "Duplicate"},
                ],
                "next_cursor": None,
            },
        ),
        (
            "workstream_project_grants_get",
            {"project_id": PROJECT_ID, "grant_id": GRANT_ID},
            _grant(
                qualification_snapshot={
                    **_grant()["qualification_snapshot"],
                    "requested_role": "reviewer",
                }
            ),
        ),
        (
            "workstream_project_grants_get",
            {"project_id": PROJECT_ID, "grant_id": GRANT_ID},
            _grant(
                qualification_snapshot={
                    **_grant()["qualification_snapshot"],
                    "external_expertise_refs": ["https://private.example"],
                }
            ),
        ),
    ],
)
def test_reads_reject_semantically_invalid_authority_data(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
    response: dict[str, Any],
) -> None:
    client, received, upstream = adapter
    upstream["json"] = response
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_api_response"
    assert len(received) == 1


def test_issue_rejects_schema_valid_target_substitution_as_uncertain(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream.update(status=201, json=_receipt() | {"actor_profile_id": ADMIN_ID})
    result = call(
        client, name="workstream_project_grants_issue", arguments=_issue_arguments()
    ).json()["result"]
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


def test_project_grant_public_denial_is_safe(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    upstream.update(
        status=409,
        json={
            "error": {
                "code": "project_role_grant_exists",
                "message": "private candidate and qualification details",
            }
        },
    )
    result = call(
        client,
        name="workstream_project_grants_issue",
        arguments=_issue_arguments(),
        token="private-token",
    ).json()["result"]
    assert result["structuredContent"]["code"] == "project_role_grant_exists"
    serialized = json.dumps(result)
    assert "private candidate" not in serialized
    assert "private-token" not in serialized
    assert len(received) == 1
