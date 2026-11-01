from __future__ import annotations

import base64
import hashlib
from typing import Any
from unittest.mock import ANY

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import TASK_OPERATIONS, GatewayResult, WorkstreamGateway
from workstream_mcp.limits import TASK_IMPORT_SOURCE_MAX_BASE64_CHARS
from workstream_mcp.schemas import (
    TASK_OPERATION_CONTRACT_NAMES,
    task_operation_input_schema,
)
from workstream_mcp.tools import task_operations

PROJECT_ID = "019a2a00-0000-7000-8000-000000002001"
TASK_ID = "019a2a00-0000-7000-8000-000000002002"
BATCH_ID = "019a2a00-0000-7000-8000-000000002003"
SOURCE_ID = "019a2a00-0000-7000-8000-000000002004"
EFFECT_ID = "019a2a00-0000-7000-8000-000000002005"
ATTEMPT_ID = "019a2a00-0000-7000-8000-000000002006"
KEY = "019a2a00-0000-7000-8000-000000002007"
DIGEST = "sha256:" + "a" * 64
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]


def _arguments(name: str) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "projects_list": {"limit": 25, "cursor": "opaque"},
        "service_actor_create": {
            "body": {"service_identity": {"issuer": "flow", "subject": "worker"}},
            "idempotency_key": KEY,
        },
        "task_import_batch_create": {
            "project_id": PROJECT_ID,
            "body": {"source_id": SOURCE_ID},
            "idempotency_key": KEY,
        },
        "management_tasks_list": {"project_id": PROJECT_ID, "limit": 25},
        "management_task_create": {
            "project_id": PROJECT_ID,
            "body": {},
            "idempotency_key": KEY,
        },
        "operational_tasks_list": {"project_id": PROJECT_ID, "limit": 25},
        "task_import_batch_screen": {
            "project_id": PROJECT_ID,
            "batch_id": BATCH_ID,
            "body": {},
            "idempotency_key": KEY,
        },
        "task_import_batch_release": {
            "project_id": PROJECT_ID,
            "batch_id": BATCH_ID,
            "body": {},
            "idempotency_key": KEY,
        },
        "task_import_batch_get": {"project_id": PROJECT_ID, "batch_id": BATCH_ID},
        "management_task_get": {"project_id": PROJECT_ID, "task_id": TASK_ID},
        "management_task_locked_context_get": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
        },
        "operational_task_locked_context_get": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
        },
        "audit_task_locked_context_get": {"project_id": PROJECT_ID, "task_id": TASK_ID},
        "task_revision_context_repair": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
            "body": {},
            "idempotency_key": KEY,
        },
        "audit_task_evidence_get": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
            "limit": 25,
        },
        "operational_task_start_override": {
            "task_id": TASK_ID,
            "body": {},
            "idempotency_key": KEY,
        },
        "project_model_profile_provision": {
            "project_id": PROJECT_ID,
            "body": {"project_id": PROJECT_ID},
            "idempotency_key": KEY,
        },
        "project_model_budget_configure": {
            "project_id": PROJECT_ID,
            "body": {"project_id": PROJECT_ID},
            "idempotency_key": KEY,
        },
        "project_model_usage_effect_get": {
            "project_id": PROJECT_ID,
            "effect_id": EFFECT_ID,
        },
        "project_model_recovery_child_create": {
            "project_id": PROJECT_ID,
            "parent_attempt_id": ATTEMPT_ID,
            "body": {},
        },
        "task_import_source_declare": {
            "project_id": PROJECT_ID,
            "body": {"sha256": DIGEST, "byte_count": 2},
            "idempotency_key": KEY,
        },
        "task_import_source_content_upload": {
            "project_id": PROJECT_ID,
            "source_id": SOURCE_ID,
            "content_base64": base64.b64encode(b"{}").decode(),
        },
        "task_import_source_content_get": {
            "project_id": PROJECT_ID,
            "source_id": SOURCE_ID,
        },
        "task_import_source_get": {"project_id": PROJECT_ID, "source_id": SOURCE_ID},
    }
    return values[name]


def _bound_response(name: str, upload: bytes | None = None) -> dict[str, Any]:
    if name in {"projects_list"}:
        return {"items": [], "next_cursor": None}
    if name == "service_actor_create":
        return {"service_identity": {"issuer": "flow", "subject": "worker"}}
    if name == "task_import_batch_create":
        return {"project_id": PROJECT_ID, "source_id": SOURCE_ID}
    if name in {"management_tasks_list", "operational_tasks_list"}:
        return {"project_id": PROJECT_ID, "items": [], "next_cursor": None}
    if name == "management_task_create":
        return {"project_id": PROJECT_ID}
    if name in {"task_import_batch_screen", "task_import_batch_release"}:
        return {"project_id": PROJECT_ID, "batch_id": BATCH_ID}
    if name == "task_import_batch_get":
        return {"creation": {"project_id": PROJECT_ID, "batch_id": BATCH_ID}}
    if name in {
        "management_task_get",
        "management_task_locked_context_get",
        "operational_task_locked_context_get",
        "audit_task_locked_context_get",
        "audit_task_evidence_get",
    }:
        return {"project_id": PROJECT_ID, "task_id": TASK_ID}
    if name == "task_revision_context_repair":
        return {}
    if name == "operational_task_start_override":
        return {"id": TASK_ID}
    if name in {"project_model_profile_provision", "project_model_budget_configure"}:
        return {"spec": {"project_id": PROJECT_ID}}
    if name == "project_model_usage_effect_get":
        return {"project_id": PROJECT_ID, "effect_id": EFFECT_ID}
    if name == "project_model_recovery_child_create":
        return {"slot_key": None, "request_sha256": None}
    if name == "task_import_source_declare":
        return {
            "project_id": PROJECT_ID,
            "sha256": DIGEST,
            "byte_count": 2,
        }
    if name == "task_import_source_content_upload":
        assert upload is not None
        return {
            "project_id": PROJECT_ID,
            "source_id": SOURCE_ID,
            "byte_count": len(upload),
            "sha256": "sha256:" + hashlib.sha256(upload).hexdigest(),
        }
    if name == "task_import_source_get":
        return {"project_id": PROJECT_ID, "source_id": SOURCE_ID}
    raise AssertionError(name)


def _catalogue(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return {tool["name"]: tool for tool in response.json()["result"]["tools"]}


def test_task_operation_catalogue_is_exact_closed_and_does_not_dispatch(
    adapter: Adapter,
) -> None:
    client, received, _ = adapter
    catalogue = _catalogue(client)
    assert len(task_operations.TOOL_NAMES) == 24
    for name, tool_name in zip(
        TASK_OPERATION_CONTRACT_NAMES, task_operations.TOOL_NAMES, strict=True
    ):
        tool = catalogue[tool_name]
        assert tool["inputSchema"] == task_operation_input_schema(name)
        Draft202012Validator.check_schema(tool["inputSchema"])
        Draft202012Validator.check_schema(tool["outputSchema"])
        assert tool["inputSchema"]["additionalProperties"] is False
    assert received == []


@pytest.mark.parametrize(
    "name",
    [name for name in TASK_OPERATION_CONTRACT_NAMES if name != "task_import_source_content_get"],
)
@pytest.mark.asyncio
async def test_every_json_operation_forwards_only_its_fixed_request(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    captured: dict[str, Any] = {}
    upload = b"{}" if name == "task_import_source_content_upload" else None

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        captured.update(args=args, kwargs=kwargs)
        return GatewayResult(data=_bound_response(name, upload))

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    arguments = _arguments(name)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_operation(
            name,
            "Bearer caller-token",
            arguments,
            "request-correlation",
            upload=upload,
        )

    method, path_template, status = TASK_OPERATIONS[name]
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


def test_source_upload_decodes_once_and_forwards_exact_json_bytes(adapter: Adapter) -> None:
    client, received, upstream = adapter
    content = b'{"tasks":[]}'
    upstream["json"] = {
        "source_id": SOURCE_ID,
        "project_id": PROJECT_ID,
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "byte_count": len(content),
        "media_type": "application/json",
        "status": "object_confirmed",
        "created_at": "2026-10-25T10:00:00Z",
    }
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer fixture-token", "accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_task_import_source_content_upload",
                "arguments": {
                    "project_id": PROJECT_ID,
                    "source_id": SOURCE_ID,
                    "content_base64": base64.b64encode(content).decode(),
                },
            },
        },
    )
    assert response.json()["result"]["isError"] is False
    assert received[0].content == content
    assert received[0].headers["content-type"] == "application/json"
    assert received[0].headers["authorization"] == "Bearer fixture-token"


def test_source_content_read_returns_only_bounded_integrity_projection(adapter: Adapter) -> None:
    client, _, upstream = adapter
    content = b'{"tasks":[]}'
    upstream.update(content=content, headers={"content-type": "application/json"})
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer fixture-token", "accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_task_import_source_content_get",
                "arguments": {"project_id": PROJECT_ID, "source_id": SOURCE_ID},
            },
        },
    )
    data = response.json()["result"]["structuredContent"]
    assert data == {
        "media_type": "application/json",
        "content_base64": base64.b64encode(content).decode(),
        "byte_count": len(content),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
    }
    assert "fixture-token" not in response.text


def test_model_path_and_body_project_mismatch_never_dispatches(adapter: Adapter) -> None:
    client, received, _ = adapter
    schema = task_operation_input_schema("project_model_profile_provision")
    body = {
        property_name: _minimal_value(property_schema)
        for property_name, property_schema in schema["properties"]["body"]["properties"].items()
        if property_name in schema["properties"]["body"].get("required", [])
    }
    body["project_id"] = TASK_ID
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer fixture-token", "accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_project_model_profile_provision",
                "arguments": {
                    "project_id": PROJECT_ID,
                    "body": body,
                    "idempotency_key": KEY,
                },
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


def test_invalid_source_base64_never_dispatches(adapter: Adapter) -> None:
    client, received, _ = adapter
    response = client.post(
        "/mcp",
        headers={"authorization": "Bearer fixture-token", "accept": "application/json"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workstream_task_import_source_content_upload",
                "arguments": {
                    "project_id": PROJECT_ID,
                    "source_id": SOURCE_ID,
                    "content_base64": "not-base64!",
                },
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.asyncio
async def test_substituted_mutation_response_fails_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        return GatewayResult(data={"project_id": PROJECT_ID, "batch_id": TASK_ID})

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_operation(
            "task_import_batch_release",
            "Bearer opaque",
            _arguments("task_import_batch_release"),
        )
    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"


@pytest.mark.asyncio
async def test_substituted_read_response_fails_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        return GatewayResult(data={"project_id": TASK_ID, "task_id": TASK_ID})

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_operation(
            "management_task_get",
            "Bearer opaque",
            _arguments("management_task_get"),
        )
    assert result.failure is not None
    assert result.failure.error == "invalid_api_response"


@pytest.mark.asyncio
async def test_revision_repair_binds_predecessor_without_confusing_new_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_id = "019a2a00-0000-7000-8000-000000002099"
    arguments = {
        **_arguments("task_revision_context_repair"),
        "body": {
            "reason": "restore context",
            "parent_preparation_id": parent_id,
            "parent_preparation_sha256": DIGEST,
        },
    }

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        return GatewayResult(
            data={
                "predecessor_preparation_id": parent_id,
                "preparation_sha256": "sha256:" + "b" * 64,
            }
        )

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_operation(
            "task_revision_context_repair",
            "Bearer opaque",
            arguments,
        )
    assert result.failure is None


@pytest.mark.asyncio
async def test_recovery_child_accepts_server_filled_slot_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_schema = task_operation_input_schema("project_model_recovery_child_create")
    body_schema = input_schema["properties"]["body"]
    body = _minimal_value(body_schema)
    body["slot"].pop("slot_index", None)

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        assert kwargs["json_body"]["slot"] == body["slot"]
        assert "slot_index" not in kwargs["json_body"]["slot"]
        slot_key = {**body["slot"], "slot_index": 0}
        return GatewayResult(
            data={"slot_key": slot_key, "request_sha256": body["request_sha256"]}
        )

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    arguments = {
        **_arguments("project_model_recovery_child_create"),
        "body": body,
    }
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).task_operation(
            "project_model_recovery_child_create",
            "Bearer opaque",
            arguments,
        )
    assert result.failure is None


def _minimal_value(schema: dict[str, Any]) -> Any:
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if schema.get("format") == "uuid":
        return TASK_ID
    if schema.get("type") == "string":
        return "x"
    if schema.get("type") == "integer":
        return max(1, int(schema.get("minimum", 1)))
    if schema.get("type") == "array":
        return []
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        return {
            key: _minimal_value(properties[key])
            for key in schema.get("required", [])
        }
    raise AssertionError(schema)


def test_source_and_cursor_bounds_are_explicit() -> None:
    upload = task_operation_input_schema("task_import_source_content_upload")
    assert upload["properties"]["content_base64"]["maxLength"] == (
        TASK_IMPORT_SOURCE_MAX_BASE64_CHARS
    )
    audit = task_operation_input_schema("audit_task_evidence_get")
    assert audit["properties"]["cursor"]["anyOf"][0]["maxLength"] == 512
    Draft202012Validator(
        audit, format_checker=FormatChecker()
    ).validate({"project_id": PROJECT_ID, "task_id": TASK_ID, "cursor": "x" * 512})
