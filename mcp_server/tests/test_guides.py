from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from workstream_mcp.tools.guides import _valid_task_examples

PROJECT_ID = "019a2a00-0000-7000-8000-000000000301"
GUIDE_ID = "019a2a00-0000-7000-8000-000000000302"
DOCUMENT_ID = "019a2a00-0000-7000-8000-000000000303"
SETUP_ID = "019a2a00-0000-7000-8000-000000000304"
KEY = "019a2a00-0000-7000-8000-000000000305"
TOOLS = ("workstream_guides_create", "workstream_guides_update")
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _example() -> dict[str, Any]:
    return {"content": "Review a claim using the declared guide.", "labels": ["review"]}


def _create_arguments() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "body": {
            "version": "v1",
            "change_summary": "Initial guide declaration",
            "task_examples": [_example()],
            "documents": [{"label": "Guide", "media_type": "application/pdf"}],
        },
        "idempotency_key": KEY,
    }


def _guide(**overrides: Any) -> dict[str, Any]:
    value = {
        "contribution_policy_id": None,
        "contribution_policy_version_id": None,
        "activation_operation_id": None,
        "id": GUIDE_ID,
        "project_id": PROJECT_ID,
        "version": "v1",
        "status": "draft",
        "change_summary": "Initial guide declaration",
        "task_examples": [_example()],
        "task_examples_hash": "sha256:" + "a" * 64,
        "approved_by": None,
        "effective_at": None,
        "created_by": "019a2a00-0000-7000-8000-000000000399",
        "created_at": "2026-10-22T10:00:00Z",
        "updated_at": "2026-10-22T10:00:00Z",
        "superseded_at": None,
    }
    value.update(overrides)
    return value


def _created() -> dict[str, Any]:
    return _guide() | {
        "task_examples": [{**_example(), "title": None}],
        "documents": [
            {
                "document_id": DOCUMENT_ID,
                "label": "Guide",
                "media_type": "application/pdf",
                "order": 0,
            }
        ],
        "setup": {"id": SETUP_ID, "status": "awaiting_documents"},
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
def test_guide_tools_advertise_closed_keyed_mutation_contracts(
    adapter: Adapter, name: str
) -> None:
    client, received, _ = adapter
    tool = _catalogue(client)[name]
    Draft202012Validator.check_schema(tool["inputSchema"])
    Draft202012Validator.check_schema(tool["outputSchema"])
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["annotations"] == {
        "title": tool["annotations"]["title"],
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert received == []


@pytest.mark.parametrize(
    "name,arguments,status,response,path,method",
    [
        (
            "workstream_guides_create",
            _create_arguments(),
            201,
            _created(),
            f"/api/v1/projects/{PROJECT_ID}/guides",
            "POST",
        ),
        (
            "workstream_guides_update",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "body": {"change_summary": None},
                "idempotency_key": KEY,
            },
            200,
            _guide(change_summary=None),
            f"/api/v1/projects/{PROJECT_ID}/guides/{GUIDE_ID}",
            "PATCH",
        ),
    ],
)
def test_guide_mutations_forward_fixed_body_bearer_and_key_unchanged(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
    status: int,
    response: dict[str, Any],
    path: str,
    method: str,
) -> None:
    client, received, upstream = adapter
    upstream.update(status=status, json=response)
    result = call(
        client,
        name=name,
        arguments=arguments,
        token="project-manager",
        extra_headers={"Idempotency-Key": DOCUMENT_ID},
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == response
    assert len(received) == 1
    request = received[0]
    assert request.method == method
    assert request.url.path == path
    assert request.headers["authorization"] == 'Bearer api-project-manager'
    assert request.headers["idempotency-key"] == KEY
    assert json.loads(request.content) == arguments["body"]


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("workstream_guides_create", {}),
        ("workstream_guides_create", {**_create_arguments(), "project_id": "bad"}),
        (
            "workstream_guides_create",
            {
                **_create_arguments(),
                "body": {**_create_arguments()["body"], "content_markdown": "forbidden"},
            },
        ),
        (
            "workstream_guides_create",
            {
                **_create_arguments(),
                "body": {
                    **_create_arguments()["body"],
                    "task_examples": [{"content": " \n\t "}],
                },
            },
        ),
        (
            "workstream_guides_create",
            {
                **_create_arguments(),
                "body": {
                    **_create_arguments()["body"],
                    "documents": [{"label": "Guide", "media_type": "text/html"}],
                },
            },
        ),
        (
            "workstream_guides_update",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "body": {"version": "v2"},
                "idempotency_key": KEY,
            },
        ),
        (
            "workstream_guides_update",
            {"project_id": PROJECT_ID, "guide_id": GUIDE_ID, "body": {}},
        ),
    ],
)
def test_invalid_guide_input_never_dispatches(
    adapter: Adapter, call: Call, name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_mcp_headers_and_metadata_cannot_supply_guide_key(adapter: Adapter) -> None:
    client, received, _ = adapter
    arguments = _create_arguments()
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
                "name": "workstream_guides_create",
                "arguments": arguments,
                "_meta": {"idempotency_key": KEY},
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_guide_task_examples_enforce_the_backend_aggregate_utf8_byte_limit() -> None:
    arguments = _create_arguments()
    arguments["body"]["task_examples"] = [
        {"content": "x" * 65_536},
        {"content": "界" * 22_000},
    ]
    assert _valid_task_examples(arguments) is False


def test_guide_task_example_limit_includes_backend_defaults() -> None:
    arguments = _create_arguments()
    examples = [{"content": "x" * 1_280} for _ in range(100)]
    raw_size = len(
        json.dumps(examples, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    assert raw_size <= 128 * 1024
    arguments["body"]["task_examples"] = examples
    assert _valid_task_examples(arguments) is False


@pytest.mark.parametrize(
    "name,arguments,status,response",
    [
        (
            "workstream_guides_create",
            _create_arguments(),
            201,
            _created() | {"project_id": DOCUMENT_ID},
        ),
        (
            "workstream_guides_create",
            _create_arguments(),
            201,
            _created() | {"change_summary": "Substituted summary"},
        ),
        (
            "workstream_guides_update",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "body": {"change_summary": "Updated"},
                "idempotency_key": KEY,
            },
            200,
            _guide(id=DOCUMENT_ID, change_summary="Updated"),
        ),
    ],
)
def test_guide_mutations_reject_substituted_success_as_uncertain(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
    status: int,
    response: dict[str, Any],
) -> None:
    client, received, upstream = adapter
    upstream.update(status=status, json=response)
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 1


def test_guide_api_denial_is_safe(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    upstream.update(
        status=409,
        json={"error": {"code": "idempotency_mismatch", "message": "private guide"}},
    )
    result = call(
        client,
        name="workstream_guides_create",
        arguments=_create_arguments(),
        token="private-token",
    ).json()["result"]
    assert result["structuredContent"]["code"] == "idempotency_mismatch"
    serialized = json.dumps(result)
    assert "private guide" not in serialized
    assert "private-token" not in serialized
    assert len(received) == 1


def test_guide_create_accepts_backend_canonical_document_label(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    arguments = _create_arguments()
    arguments["body"]["documents"][0]["label"] = "  Guide   document  "
    response = _created()
    response["documents"][0]["label"] = "Guide document"
    upstream.update(status=201, json=response)
    result = call(
        client,
        name="workstream_guides_create",
        arguments=arguments,
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == response
    assert len(received) == 1
