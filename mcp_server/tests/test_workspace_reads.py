from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.tools import workspace_reads

PROJECT_ID = "019a2a00-0000-7000-8000-000000000501"
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _catalogue(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": "Bearer fixture-token",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    return {tool["name"]: tool for tool in response.json()["result"]["tools"]}


def test_workspace_catalogue_has_closed_valid_contracts(adapter: Adapter) -> None:
    client, received, _ = adapter
    catalogue = _catalogue(client)
    for name in workspace_reads.TOOL_NAMES:
        tool = catalogue[name]
        Draft202012Validator.check_schema(tool["inputSchema"])
        Draft202012Validator.check_schema(tool["outputSchema"])
        assert tool["inputSchema"]["additionalProperties"] is False
        # Reads can still advance admission/audit state in Workstream.
        assert tool["annotations"]["readOnlyHint"] is False
    assert received == []


def test_actor_project_read_forwards_only_typed_query_and_bearer(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {"items": [], "next_cursor": None}
    result = call(
        client,
        name="workstream_actor_projects_list",
        arguments={"limit": 25, "cursor": "opaque+/="},
        token="workspace-caller",
        extra_headers={"Idempotency-Key": PROJECT_ID, "If-Match": '"ignored"'},
    ).json()["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"].startswith("Untrusted Workstream data")
    request = received[0]
    assert request.method == "GET"
    assert request.url.path == "/api/v1/actors/me/projects"
    assert dict(request.url.params) == {"limit": "25", "cursor": "opaque+/="}
    assert request.headers["authorization"] == 'Bearer api-workspace-caller'
    assert "idempotency-key" not in request.headers
    assert "if-match" not in request.headers


def test_contribution_export_is_json_only_and_binds_project(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {"exported_at": "2026-10-23T10:00:00Z", "items": [], "next_cursor": None}
    result = call(
        client,
        name="workstream_project_contributions_export",
        arguments={"project_id": PROJECT_ID, "contribution_type": "accepted_submission"},
    ).json()["result"]
    assert result["isError"] is False
    request = received[0]
    assert request.url.path == f"/api/v1/projects/{PROJECT_ID}/contributions/export"
    assert dict(request.url.params) == {
        "contribution_type": "accepted_submission",
        "format": "json",
    }


def test_workspace_project_binding_checks_response_and_list_items() -> None:
    other_project = "019a2a00-0000-7000-8000-000000000502"

    assert not WorkstreamGateway._workspace_project_matches(
        "project_contributions_export",
        {"project_id": other_project, "items": []},
        PROJECT_ID,
    )
    assert not WorkstreamGateway._workspace_project_matches(
        "project_submissions_list",
        {"project_id": PROJECT_ID, "items": [{"project_id": other_project}]},
        PROJECT_ID,
    )


def test_active_guide_binding_checks_nested_project_objects() -> None:
    other_project = "019a2a00-0000-7000-8000-000000000502"
    response = {
        "guide": {"project_id": PROJECT_ID},
        "guide_source_snapshot": {"project_id": other_project},
    }

    assert not WorkstreamGateway._workspace_project_matches(
        "active_guide_get", response, PROJECT_ID
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"format": "csv"},
        {"project_id": "not-a-uuid"},
        {
            "recorded_from": "2026-10-24T00:00:00Z",
            "recorded_before": "2026-10-23T00:00:00Z",
        },
    ],
)
def test_invalid_workspace_input_never_dispatches(
    adapter: Adapter, call: Call, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    result = call(
        client,
        name="workstream_contributions_list",
        arguments=arguments,
    ).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []
    assert "Bearer" not in json.dumps(result)
