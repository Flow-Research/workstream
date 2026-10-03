from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from starlette.testclient import TestClient

ACTOR_ID = "019a2a00-0000-7000-8000-000000000001"
PROJECT_ID = "019a2a00-0000-7000-8000-000000000002"
GRANT_ID = "019a2a00-0000-7000-8000-000000000003"
LINK_ID = "019a2a00-0000-7000-8000-000000000004"
TIMESTAMP = "2026-09-15T10:00:00Z"
GRANT_TOOLS = ("workstream_admin_grants_list", "workstream_actor_admin_grants_list")
ACTOR_TOOLS = (
    "workstream_actor_admin_grants_list",
    "workstream_actor_get",
    "workstream_actor_identity_link_get",
)
PATHS = {
    "workstream_permissions_list": "/api/v1/authorization/permissions",
    "workstream_admin_roles_list": "/api/v1/authorization/admin-role-definitions",
    "workstream_admin_grants_list": "/api/v1/admin-role-grants",
    "workstream_actor_admin_grants_list": f"/api/v1/actors/{ACTOR_ID}/admin-role-grants",
    "workstream_actor_get": f"/api/v1/actors/{ACTOR_ID}",
    "workstream_actor_identity_link_get": f"/api/v1/actors/{ACTOR_ID}/identity-links",
}
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _arguments(name: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    if name in ACTOR_TOOLS:
        arguments["actor_profile_id"] = ACTOR_ID
    if name in GRANT_TOOLS:
        arguments["scope_type"] = "system"
    return arguments


def _response(name: str) -> dict[str, Any]:
    # Representative entries use the backend's frozen catalogue totals.
    if name == "workstream_permissions_list":
        return {"items": [{"permission_id": "actor.profile.read_any"}], "total": 78}
    if name == "workstream_admin_roles_list":
        return {
            "items": [
                {
                    "role": "access_administrator",
                    "allowed_scopes": ["system"],
                    "permission_ids": ["admin_role.read", "admin_role.grant"],
                },
                {
                    "role": "audit_authority",
                    "allowed_scopes": ["system", "project"],
                    "permission_ids": ["audit.read"],
                },
            ],
            "total": 5,
        }
    if name in GRANT_TOOLS:
        return {
            "items": [
                {
                    "grant_id": GRANT_ID,
                    "target_actor_profile_id": ACTOR_ID,
                    "role": "audit_authority",
                    "scope_type": "system",
                    "scope_project_id": None,
                    "status": "active",
                    "version": 1,
                    "granted_by_ref_kind": "system_principal",
                    "granted_by_ref": "bootstrap",
                    "granted_by_admin_role_grant_id": None,
                    "grant_reason": "Authorized audit access",
                    "granted_at": TIMESTAMP,
                    "revoked_by_actor_profile_id": None,
                    "revoked_by_admin_role_grant_id": None,
                    "revoked_reason": None,
                    "revoked_at": None,
                }
            ],
            "total": 1,
            "next_cursor": None,
        }
    if name == "workstream_actor_get":
        return {
            "actor_profile_id": ACTOR_ID,
            "actor_kind": "human",
            "status": "active",
            "provisioning_method": "automatic_first_access",
            "service_identity": None,
            "display_name": "Audit subject",
            "created_at": TIMESTAMP,
            "updated_at": TIMESTAMP,
            "last_seen_at": None,
            "suspended_at": None,
            "reactivated_at": None,
            "deactivated_at": None,
        }
    assert name == "workstream_actor_identity_link_get"
    return {
        "identity_link_id": LINK_ID,
        "actor_profile_id": ACTOR_ID,
        "subject_kind": "human",
        "status": "active",
        "linked_at": TIMESTAMP,
        "last_verified_at": None,
        "revoked_at": None,
        "reactivated_at": None,
    }


def _catalogue(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return {tool["name"]: tool for tool in response.json()["result"]["tools"]}


def _object_schemas(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield value
        for child in value.values():
            yield from _object_schemas(child)
    elif isinstance(value, list):
        for child in value:
            yield from _object_schemas(child)


@pytest.mark.parametrize("name", PATHS)
def test_access_read_advertises_closed_valid_schemas(adapter: Adapter, name: str) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    expected_properties = set(_arguments(name))
    if name in GRANT_TOOLS:
        expected_properties.update({"scope_project_id", "status", "limit", "cursor"})
    assert set(tool["inputSchema"]["properties"]) == expected_properties
    assert set(tool["inputSchema"].get("required", [])) == set(_arguments(name))
    for key in ("inputSchema", "outputSchema"):
        schema = tool[key]
        Draft202012Validator.check_schema(schema)
        assert schema["type"] == "object"
        assert all(node.get("additionalProperties") is False for node in _object_schemas(schema))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(_arguments(name) if key == "inputSchema" else _response(name))
    for field in ("actor_profile_id", "scope_project_id"):
        if field in expected_properties:
            assert tool["inputSchema"]["properties"][field]["format"] == "uuid"
    assert received == []


@pytest.mark.parametrize("name", PATHS)
def test_access_read_exact_get_wire_and_projection(adapter: Adapter, call: Call, name: str) -> None:
    client, received, upstream = adapter
    upstream["json"] = _response(name)
    response = call(
        client,
        name=name,
        arguments=_arguments(name),
        token="read-caller",
        extra_headers={
            "Idempotency-Key": GRANT_ID,
            "If-Match": '"version-1"',
            "X-Actor-ID": PROJECT_ID,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == upstream["json"]
    assert json.loads(result["content"][0]["text"]) == upstream["json"]
    assert len(received) == 1
    request = received[0]
    assert request.method == "GET"
    assert request.url.scheme == "http"
    assert request.url.host == "workstream.test"
    assert request.url.path == PATHS[name]
    assert request.url.fragment == ""
    assert list(request.url.params.multi_items()) == (
        [("scope_type", "system")] if name in GRANT_TOOLS else []
    )
    assert request.content == b""
    assert request.headers["authorization"] == "Bearer read-caller"
    assert request.headers["accept"] == "application/json"
    for header in ("idempotency-key", "if-match", "if-none-match", "x-actor-id", "content-type"):
        assert header not in request.headers


@pytest.mark.parametrize("name", GRANT_TOOLS)
@pytest.mark.parametrize(
    ("status", "limit", "cursor"),
    [("active", 1, ""), ("revoked", 100, "x" * 512), ("all", 50, "  a+/=%2F?&b=c._-  ")],
)
def test_grant_queries_preserve_bounds_and_opaque_cursor(
    adapter: Adapter, call: Call, name: str, status: str, limit: int, cursor: str
) -> None:
    client, received, upstream = adapter
    upstream["json"] = _response(name)
    upstream["json"]["next_cursor"] = "next+/=%2F?&page=2"
    query = {
        "scope_type": "project",
        "scope_project_id": PROJECT_ID,
        "status": status,
        "limit": limit,
        "cursor": cursor,
    }
    response = call(client, name=name, arguments={**_arguments(name), **query})
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == upstream["json"]
    assert len(received) == 1
    assert received[0].url.path == PATHS[name]
    assert sorted(received[0].url.params.multi_items()) == sorted(
        (key, str(value)) for key, value in query.items()
    )


@pytest.mark.parametrize("name", GRANT_TOOLS)
@pytest.mark.parametrize("limit", [1.0, 100.0])
def test_integral_numeric_limit_matches_advertised_schema(
    adapter: Adapter, call: Call, name: str, limit: float
) -> None:
    client, received, upstream = adapter
    upstream["json"] = _response(name)
    arguments = {**_arguments(name), "limit": limit}
    schema = _catalogue(client)[name]["inputSchema"]
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(arguments)

    result = call(client, name=name, arguments=arguments).json()["result"]

    assert result["isError"] is False
    assert result["structuredContent"] == upstream["json"]
    assert len(received) == 1
    assert received[0].url.params["limit"] == str(int(limit))


def _invalid_inputs() -> Iterator[Any]:
    for name in PATHS:
        for field in ("url", "authorization", "headers", "idempotency_key", "contact_email"):
            yield pytest.param(name, {**_arguments(name), field: "injected"}, id=f"{name}-{field}")
        for field in _arguments(name):
            arguments = _arguments(name)
            del arguments[field]
            yield pytest.param(name, arguments, id=f"{name}-missing-{field}")
    for name in ACTOR_TOOLS:
        for index, value in enumerate((None, 7, "", "not-a-uuid", "../me", ACTOR_ID + "/other")):
            yield pytest.param(
                name, {**_arguments(name), "actor_profile_id": value}, id=f"{name}-uuid-{index}"
            )
    invalid_queries = {
        "scope_type": [None, 1, "", "organization", "SYSTEM"],
        "scope_project_id": [None, 1, "", "not-a-uuid", PROJECT_ID + "?status=all"],
        "status": [None, 1, "", "pending", "ACTIVE"],
        "limit": [None, 0, -1, 101, 1.5, True, "10"],
        "cursor": [None, 1, [], {}, "x" * 513],
    }
    for name in GRANT_TOOLS:
        for field, values in invalid_queries.items():
            for index, value in enumerate(values):
                yield pytest.param(
                    name, {**_arguments(name), field: value}, id=f"{name}-{field}-{index}"
                )


@pytest.mark.parametrize(("name", "arguments"), list(_invalid_inputs()))
def test_invalid_access_read_input_rejected_before_dispatch(
    adapter: Adapter, call: Call, name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    schema = _catalogue(client)[name]["inputSchema"]
    assert not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(arguments)
    response = call(client, name=name, arguments=arguments)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize("name", PATHS)
def test_missing_bearer_prevents_access_read_dispatch(
    adapter: Adapter, call: Call, name: str
) -> None:
    client, received, _ = adapter
    response = call(client, name=name, arguments=_arguments(name), token=None)
    assert response.json()["result"]["isError"] is True
    assert received == []


@pytest.mark.parametrize("name", PATHS)
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "invalid_token"),
        (403, "permission_not_granted"),
        (404, "actor_resource_not_found"),
        (400, "invalid_request"),
        (422, "validation_error"),
        (503, "service_unavailable"),
    ],
)
def test_access_read_api_failures_are_safe_and_not_retried(
    adapter: Adapter, call: Call, name: str, status: int, code: str
) -> None:
    client, received, upstream = adapter
    upstream.update(
        status=status,
        json={
            "error": {
                "code": code,
                "message": "private backend diagnostic",
                "details": {"contact_email": "private@example.test", "subject": "private-subject"},
            }
        },
    )
    response = call(client, name=name, arguments=_arguments(name), token="private-caller-token")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "workstream_request_failed"
    assert result["structuredContent"]["status"] == status
    assert result["structuredContent"]["code"] == code
    for secret in (
        "private backend diagnostic",
        "private@example.test",
        "private-subject",
        "private-caller-token",
        "contact_email",
        "subject",
    ):
        assert secret not in response.text
    assert len(received) == 1


@pytest.mark.parametrize("name", PATHS)
@pytest.mark.parametrize("field", ["contact_email", "subject"])
def test_extra_sensitive_output_fields_fail_closed(
    adapter: Adapter, call: Call, name: str, field: str
) -> None:
    client, received, upstream = adapter
    upstream["json"] = _response(name)
    target = upstream["json"]
    if "items" in target:
        target = target["items"][0]
    target[field] = "private-projection-value"
    response = call(client, name=name, arguments=_arguments(name))
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_api_response"
    assert result["structuredContent"]["status"] == 502
    assert "private-projection-value" not in response.text
    assert len(received) == 1


@pytest.mark.parametrize("name", PATHS)
@pytest.mark.parametrize("malformation", ["missing", "type", "extra"])
def test_malformed_access_read_response_rejected(
    adapter: Adapter, call: Call, name: str, malformation: str
) -> None:
    client, received, upstream = adapter
    payload = _response(name)
    required_field = "items" if "items" in payload else "actor_profile_id"
    if malformation == "missing":
        del payload[required_field]
    elif malformation == "type":
        payload[required_field] = 42
    else:
        payload["contact_email"] = "private@example.test"
    upstream["json"] = payload
    result = call(client, name=name, arguments=_arguments(name)).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_api_response"
    assert result["structuredContent"]["status"] == 502
    assert "private@example.test" not in json.dumps(result)
    assert len(received) == 1


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("workstream_permissions_list", "total", 77),
        ("workstream_admin_roles_list", "total", 4),
        ("workstream_admin_grants_list", "total", -1),
        ("workstream_actor_admin_grants_list", "next_cursor", 42),
        ("workstream_actor_get", "actor_profile_id", "not-a-uuid"),
        ("workstream_actor_get", "created_at", "not-a-timestamp"),
        ("workstream_actor_get", "actor_kind", "administrator"),
        ("workstream_actor_identity_link_get", "identity_link_id", "not-a-uuid"),
        ("workstream_actor_identity_link_get", "linked_at", "not-a-timestamp"),
        ("workstream_actor_identity_link_get", "status", "deleted"),
    ],
)
def test_output_formats_enums_and_bounds_are_enforced(
    adapter: Adapter, call: Call, name: str, field: str, value: Any
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {**_response(name), field: value}
    result = call(client, name=name, arguments=_arguments(name)).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "invalid_api_response"
    assert result["structuredContent"]["status"] == 502
    assert len(received) == 1


@pytest.mark.parametrize("name", GRANT_TOOLS)
@pytest.mark.parametrize("empty", [False, True])
def test_grant_empty_pages_and_revoked_history_are_preserved(
    adapter: Adapter, call: Call, name: str, empty: bool
) -> None:
    client, received, upstream = adapter
    payload = _response(name)
    if empty:
        payload.update(items=[], total=0)
    else:
        payload["items"][0].update(
            status="revoked",
            version=2,
            scope_type="project",
            scope_project_id=PROJECT_ID,
            granted_by_ref_kind="actor_profile",
            granted_by_ref=ACTOR_ID,
            granted_by_admin_role_grant_id=GRANT_ID,
            revoked_by_actor_profile_id=ACTOR_ID,
            revoked_by_admin_role_grant_id=GRANT_ID,
            revoked_reason="Audit complete",
            revoked_at=TIMESTAMP,
        )
    upstream["json"] = payload
    arguments = {
        **_arguments(name),
        "scope_type": "project",
        "scope_project_id": PROJECT_ID,
        "status": "revoked",
    }
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == payload
    assert len(received) == 1
    assert dict(received[0].url.params) == {
        "scope_type": "project",
        "scope_project_id": PROJECT_ID,
        "status": "revoked",
    }


def test_service_actor_projection_preserves_closed_local_identity(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    name = "workstream_actor_get"
    upstream["json"] = {
        **_response(name),
        "actor_kind": "service",
        "provisioning_method": "manual_service_provisioning",
        "service_identity": "workstream.artifact.verifier",
        "display_name": None,
        "status": "suspended",
        "suspended_at": TIMESTAMP,
    }
    result = call(client, name=name, arguments=_arguments(name)).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == upstream["json"]
    assert len(received) == 1


@pytest.mark.parametrize("name", PATHS)
def test_access_read_success_is_not_reused_after_authority_revocation(
    adapter: Adapter, call: Call, name: str
) -> None:
    client, received, upstream = adapter
    upstream["json"] = _response(name)
    first = call(client, name=name, arguments=_arguments(name), token="first-caller")
    assert first.json()["result"]["isError"] is False
    upstream.update(status=403, json={"error": {"code": "permission_not_granted"}})
    for token in ("first-caller", "second-caller"):
        response = call(client, name=name, arguments=_arguments(name), token=token)
        result = response.json()["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["status"] == 403
        assert "items" not in result["structuredContent"]
        assert "actor_profile_id" not in result["structuredContent"]
    assert [request.headers["authorization"] for request in received] == [
        "Bearer first-caller",
        "Bearer first-caller",
        "Bearer second-caller",
    ]
