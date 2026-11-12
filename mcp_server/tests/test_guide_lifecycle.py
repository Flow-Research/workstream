from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.limits import (
    GUIDE_DOCUMENT_MAX_BASE64_CHARS,
    GUIDE_DOCUMENT_MAX_BYTES,
    GUIDE_DOCUMENT_MEDIA_TYPES,
)
from workstream_mcp.schemas import guide_lifecycle_input_schema
from workstream_mcp.tools import guide_lifecycle

PROJECT_ID = "019a2a00-0000-7000-8000-000000000501"
GUIDE_ID = "019a2a00-0000-7000-8000-000000000502"
DOCUMENT_ID = "019a2a00-0000-7000-8000-000000000503"
COMPILATION_ID = "019a2a00-0000-7000-8000-000000000504"
CORRECTION_ID = "019a2a00-0000-7000-8000-000000000505"
IDEMPOTENCY_KEY = "019a2a00-0000-7000-8000-000000000506"
POLICY_ID = "019a2a00-0000-7000-8000-000000000507"
REPORT_ID = "019a2a00-0000-7000-8000-000000000508"
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _approval_arguments() -> dict[str, Any]:
    digest = "sha256:" + "a" * 64
    target = {
        "project_id": PROJECT_ID,
        "guide_id": GUIDE_ID,
        "compilation_id": COMPILATION_ID,
        "guide_version": "1",
        "source_snapshot_id": DOCUMENT_ID,
        "source_snapshot_hash": digest,
        "setup_run_id": REPORT_ID,
        "setup_generation": 1,
        "finalization_id": CORRECTION_ID,
        "finalization_facts_digest": digest,
        "result_hash": digest,
        "result_schema_version": "project_guide_check_specification.v1",
        "component_hashes": {
            "schema_version": "project_guide_check_specification_hashes.v1",
            **{
                name: digest
                for name in (
                    "sufficiency_hash",
                    "artifact_policy_hash",
                    "requirement_inventory_hash",
                    "pre_submit_hash",
                    "post_submit_hash",
                )
            },
        },
        "artifact_policy_id": POLICY_ID,
        "artifact_policy_hash": digest,
        "artifact_projection_operation_id": CORRECTION_ID,
        "artifact_projection_output_digest": digest,
    }
    return {
        "project_id": PROJECT_ID,
        "guide_id": GUIDE_ID,
        "compilation_id": COMPILATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "body": {
            "target": target,
            "pre_submit_attachments": [],
            "post_submit_attachments": [
                {
                    "requirement_id": "project.quality",
                    "registry_entry_id": POLICY_ID,
                    "registry_entry_digest": digest,
                    "configuration": {"rubric": "Check the guide's requirements", "limit": 3},
                }
            ],
        },
    }


def test_approval_forwards_human_image_attachments_unchanged(
    adapter: Adapter,
    call: Call,
) -> None:
    client, received, upstream = adapter
    # A backend conflict still proves the full input reached its authority boundary.
    upstream["status"] = 409
    upstream["json"] = {
        "error": {
            "code": "proposal_stale",
            "message": "Proposal changed",
            "retryable": False,
        }
    }
    arguments = _approval_arguments()
    result = call(
        client, name="workstream_guide_pre_submission_approve", arguments=arguments
    ).json()["result"]
    assert len(received) == 1
    assert json.loads(received[0].content) == arguments["body"]
    assert received[0].headers["idempotency-key"] == IDEMPOTENCY_KEY
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 409


@pytest.mark.parametrize("field", ["pre_submit_attachments", "post_submit_attachments"])
def test_approval_requires_explicit_phase_image_choice(
    adapter: Adapter,
    call: Call,
    field: str,
) -> None:
    client, received, _ = adapter
    arguments = _approval_arguments()
    del arguments["body"][field]
    result = call(
        client, name="workstream_guide_pre_submission_approve", arguments=arguments
    ).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


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


def test_guide_lifecycle_catalogue_has_26_closed_valid_contracts(adapter: Adapter) -> None:
    client, received, _ = adapter
    catalogue = _catalogue(client)
    assert len(guide_lifecycle.TOOL_NAMES) == 26
    for name in guide_lifecycle.TOOL_NAMES:
        tool = catalogue[name]
        Draft202012Validator.check_schema(tool["inputSchema"])
        Draft202012Validator.check_schema(tool["outputSchema"])
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["outputSchema"]["type"] == "object"
        assert tool["annotations"]["readOnlyHint"] is False
    assert received == []


def test_project_guide_list_forwards_only_typed_query_and_bearer(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {"items": [], "next_cursor": None}
    result = call(
        client,
        name="workstream_project_guides_list",
        arguments={"project_id": PROJECT_ID, "limit": 25, "cursor": "opaque+/="},
        token="guide-caller",
        extra_headers={"Idempotency-Key": IDEMPOTENCY_KEY, "If-Match": '"ignored"'},
    ).json()["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"].startswith("Untrusted Workstream data")
    request = received[0]
    assert request.method == "GET"
    assert request.url.path == f"/api/v1/projects/{PROJECT_ID}/guides"
    assert dict(request.url.params) == {"limit": "25", "cursor": "opaque+/="}
    assert request.headers["authorization"] == 'Bearer api-guide-caller'
    assert "idempotency-key" not in request.headers
    assert "if-match" not in request.headers


def test_saved_correction_dispatch_uses_only_fixed_selectors(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    upstream["status"] = 202
    upstream["json"] = {
        "correction_operation_id": CORRECTION_ID,
        "setup_run_id": "019a2a00-0000-7000-8000-000000000507",
        "setup_generation": 1,
        "status": "queued",
    }
    result = call(
        client,
        name="workstream_guide_correction_dispatch",
        arguments={
            "project_id": PROJECT_ID,
            "guide_id": GUIDE_ID,
            "compilation_id": COMPILATION_ID,
            "correction_operation_id": CORRECTION_ID,
        },
    ).json()["result"]
    assert result["isError"] is False
    request = received[0]
    assert request.method == "POST"
    assert request.url.path.endswith(f"/{CORRECTION_ID}/dispatch")
    assert "idempotency-key" not in request.headers


def test_document_upload_decodes_once_and_binds_receipt(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    content = b"# reviewed guide\n"
    digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
    upstream["status"] = 202
    upstream["json"] = {
        "document_id": DOCUMENT_ID,
        "sha256": digest,
        "byte_count": len(content),
        "status": "document_stored",
        "replayed": False,
    }
    result = call(
        client,
        name="workstream_guide_document_upload",
        arguments={
            "project_id": PROJECT_ID,
            "guide_id": GUIDE_ID,
            "document_id": DOCUMENT_ID,
            "media_type": "text/markdown",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "idempotency_key": IDEMPOTENCY_KEY,
        },
    ).json()["result"]
    assert result["isError"] is False
    request = received[0]
    assert request.content == content
    assert request.headers["content-type"] == "text/markdown"
    assert request.headers["idempotency-key"] == IDEMPOTENCY_KEY
    assert request.extensions["timeout"]["read"] == 120.0
    assert result["structuredContent"]["sha256"] == digest


def test_document_read_returns_bounded_base64_and_digest(adapter: Adapter, call: Call) -> None:
    client, received, upstream = adapter
    content = b"verified bytes"
    upstream["content"] = content
    upstream["headers"] = {"content-type": "text/markdown"}
    result = call(
        client,
        name="workstream_guide_document_content_get",
        arguments={
            "project_id": PROJECT_ID,
            "guide_id": GUIDE_ID,
            "document_id": DOCUMENT_ID,
        },
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == {
        "media_type": "text/markdown",
        "content_base64": base64.b64encode(content).decode("ascii"),
        "byte_count": len(content),
        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
    }
    assert received[0].url.path.endswith(f"/{DOCUMENT_ID}/content")
    assert received[0].extensions["timeout"]["read"] == 120.0


def test_document_contract_matches_supported_media_and_transport_bounds() -> None:
    schema = guide_lifecycle_input_schema("guide_document_upload")
    assert schema["properties"]["media_type"]["enum"] == list(GUIDE_DOCUMENT_MEDIA_TYPES)
    assert schema["properties"]["content_base64"]["maxLength"] == (GUIDE_DOCUMENT_MAX_BASE64_CHARS)
    settings = Settings(api_url="http://127.0.0.1:8000")
    assert settings.max_request_bytes > GUIDE_DOCUMENT_MAX_BASE64_CHARS
    assert settings.max_response_bytes == 65_536
    assert settings.max_document_bytes == GUIDE_DOCUMENT_MAX_BYTES
    assert settings.document_timeout_seconds == 120.0


@pytest.mark.asyncio
async def test_oversized_document_response_is_non_retryable() -> None:
    client = httpx.AsyncClient(
        base_url="http://api.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=b"x" * 1025,
                headers={"content-type": "text/markdown"},
            )
        ),
    )
    try:
        result = await WorkstreamGateway(
            Settings(
                api_url="http://127.0.0.1:8000",
                max_document_bytes=1024,
            ),
            client,
        ).guide_lifecycle(
            "guide_document_content_get",
            "Bearer opaque",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "document_id": DOCUMENT_ID,
            },
        )
    finally:
        await client.aclose()

    assert result.data is None
    assert result.failure is not None
    assert result.failure.payload() == {
        "error": "workstream_response_too_large",
        "retryable": False,
        "status": 502,
    }


@pytest.mark.asyncio
async def test_document_response_uses_its_dedicated_byte_bound() -> None:
    content = b"x" * 65_537
    client = httpx.AsyncClient(
        base_url="http://api.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=content,
                headers={"content-type": "text/markdown"},
            )
        ),
    )
    try:
        result = await WorkstreamGateway(
            Settings(
                api_url="http://127.0.0.1:8000",
                max_response_bytes=65_536,
                max_document_bytes=len(content),
            ),
            client,
        ).guide_lifecycle(
            "guide_document_content_get",
            "Bearer opaque",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "document_id": DOCUMENT_ID,
            },
        )
    finally:
        await client.aclose()

    assert result.failure is None
    assert result.data is not None
    assert result.data["byte_count"] == len(content)


def test_upload_binding_failure_preserves_upstream_correlation(
    adapter: Adapter, call: Call
) -> None:
    client, _, upstream = adapter
    content = b"reviewed guide"
    response_id = "123e4567-e89b-42d3-a456-426614174000"
    upstream["status"] = 202
    upstream["headers"] = {
        "content-type": "application/json",
        "x-request-id": response_id,
    }
    upstream["json"] = {
        "document_id": "019a2a00-0000-7000-8000-000000000599",
        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
        "byte_count": len(content),
        "status": "document_stored",
        "replayed": False,
    }
    result = call(
        client,
        name="workstream_guide_document_upload",
        arguments={
            "project_id": PROJECT_ID,
            "guide_id": GUIDE_ID,
            "document_id": DOCUMENT_ID,
            "media_type": "text/markdown",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "idempotency_key": IDEMPOTENCY_KEY,
        },
    ).json()["result"]

    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert result["structuredContent"]["correlation_id"] == response_id


@pytest.mark.parametrize(
    ("name", "data", "arguments"),
    [
        (
            "guide_activate",
            {
                "operation_id": "019a2a00-0000-7000-8000-000000000510",
                "command": {
                    "target": {
                        "proposal": {
                            "project_id": PROJECT_ID,
                            "guide_id": GUIDE_ID,
                        }
                    }
                },
            },
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
            },
        ),
        (
            "project_guide_get",
            {"guide": {"project_id": PROJECT_ID, "guide_id": GUIDE_ID}},
            {"project_id": PROJECT_ID, "guide_id": GUIDE_ID},
        ),
        (
            "guide_proposal_get",
            {
                "target": {
                    "project_id": PROJECT_ID,
                    "guide_id": GUIDE_ID,
                    "compilation_id": COMPILATION_ID,
                }
            },
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "compilation_id": COMPILATION_ID,
            },
        ),
        (
            "guide_proposal_correct",
            {"operation_id": "019a2a00-0000-7000-8000-000000000511"},
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "compilation_id": COMPILATION_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
            },
        ),
        (
            "guide_post_policy_approve",
            {
                "operation_id": "019a2a00-0000-7000-8000-000000000512",
                "target": {
                    "policy_id": POLICY_ID,
                    "proposal": {
                        "project_id": PROJECT_ID,
                        "guide_id": GUIDE_ID,
                        "compilation_id": COMPILATION_ID,
                    },
                },
            },
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "compilation_id": COMPILATION_ID,
                "policy_id": POLICY_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
            },
        ),
        (
            "guide_submission_artifact_policies_list",
            {
                "items": [
                    {
                        "project_id": PROJECT_ID,
                        "guide_id": GUIDE_ID,
                        "id": POLICY_ID,
                    }
                ]
            },
            {"project_id": PROJECT_ID, "guide_id": GUIDE_ID},
        ),
        (
            "guide_submission_artifact_policy_get",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "id": POLICY_ID,
            },
            {"project_id": PROJECT_ID, "guide_id": GUIDE_ID, "policy_id": POLICY_ID},
        ),
        (
            "guide_submission_artifact_policy_update",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "id": "019a2a00-0000-7000-8000-000000000513",
                "supersedes_policy_id": POLICY_ID,
            },
            {"project_id": PROJECT_ID, "guide_id": GUIDE_ID, "policy_id": POLICY_ID},
        ),
        (
            "guide_sufficiency_report_get",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "id": REPORT_ID,
            },
            {"project_id": PROJECT_ID, "guide_id": GUIDE_ID, "report_id": REPORT_ID},
        ),
    ],
)
def test_guide_response_binding_accepts_authoritative_selectors(
    name: str, data: dict[str, Any], arguments: dict[str, Any]
) -> None:
    assert WorkstreamGateway._guide_lifecycle_response_matches(name, data, arguments)


def test_guide_response_binding_rejects_route_substitution() -> None:
    other_project = "019a2a00-0000-7000-8000-000000000599"
    arguments = {
        "project_id": PROJECT_ID,
        "guide_id": GUIDE_ID,
        "compilation_id": COMPILATION_ID,
        "policy_id": POLICY_ID,
    }
    data = {
        "target": {
            "policy_id": POLICY_ID,
            "proposal": {
                "project_id": other_project,
                "guide_id": GUIDE_ID,
                "compilation_id": COMPILATION_ID,
            },
        }
    }

    assert not WorkstreamGateway._guide_lifecycle_response_matches(
        "guide_post_policy_get", data, arguments
    )


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("workstream_project_guide_get", {"project_id": "not-a-uuid"}),
        (
            "workstream_guide_document_upload",
            {
                "project_id": PROJECT_ID,
                "guide_id": GUIDE_ID,
                "document_id": DOCUMENT_ID,
                "media_type": "text/markdown",
                "content_base64": "not base64!",
                "idempotency_key": IDEMPOTENCY_KEY,
            },
        ),
    ],
)
def test_invalid_guide_input_never_dispatches(
    adapter: Adapter,
    call: Call,
    name: str,
    arguments: dict[str, Any],
) -> None:
    client, received, _ = adapter
    result = call(client, name=name, arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []
    assert "Bearer" not in json.dumps(result)


_INITIAL_DISPATCH_ROUTES = (
    ("guide_assistance_request", "setup"),
    ("guide_requirements_compile", "requirements/compile"),
)


def _initial_dispatch_arguments() -> dict[str, Any]:
    return {"project_id": PROJECT_ID, "guide_id": GUIDE_ID, "idempotency_key": IDEMPOTENCY_KEY}


def _initial_dispatch_receipt() -> dict[str, Any]:
    return {
        "operation_id": CORRECTION_ID,
        "setup_run_id": REPORT_ID,
        "setup_generation": 1,
        "status": "dispatch_pending",
    }


@pytest.mark.parametrize(("name", "suffix"), _INITIAL_DISPATCH_ROUTES)
def test_initial_dispatch_forwards_exact_key_and_caller_without_body(
    adapter: Adapter, call: Call, name: str, suffix: str
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 202
    upstream["json"] = _initial_dispatch_receipt()
    result = call(
        client, name=f"workstream_{name}", arguments=_initial_dispatch_arguments(),
        token="explicit-guide-caller",
    ).json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == upstream["json"]
    assert len(received) == 1
    request = received[0]
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/projects/{PROJECT_ID}/guides/{GUIDE_ID}/{suffix}"
    assert not request.url.query
    assert request.content == b""
    assert request.headers["authorization"] == 'Bearer api-explicit-guide-caller'
    assert request.headers["idempotency-key"] == IDEMPOTENCY_KEY
    annotations = _catalogue(client)[f"workstream_{name}"]["annotations"]
    assert annotations["destructiveHint"] is True
    assert annotations["idempotentHint"] is True


@pytest.mark.parametrize(("name", "_suffix"), _INITIAL_DISPATCH_ROUTES)
@pytest.mark.parametrize("change", (
    {"idempotency_key": None}, {"idempotency_key": "not-a-uuid"},
    {"project_id": "foreign/path"}, {"guide_id": "not-a-uuid"},
    {"body": {"inference_required": True}}, {"token": "caller-override"},
))
def test_initial_dispatch_rejects_invalid_selectors_keys_and_behavior_overrides(
    adapter: Adapter, call: Call, name: str, _suffix: str, change: dict[str, Any]
) -> None:
    client, received, _ = adapter
    arguments = {**_initial_dispatch_arguments(), **change}
    if change.get("idempotency_key", "present") is None:
        arguments.pop("idempotency_key")
    result = call(client, name=f"workstream_{name}", arguments=arguments).json()["result"]
    assert result["structuredContent"]["error"] == "invalid_tool_input"
    assert received == []


@pytest.mark.parametrize(("name", "_suffix"), _INITIAL_DISPATCH_ROUTES)
@pytest.mark.parametrize(("status", "response"), (
    (200, _initial_dispatch_receipt()),
    (202, {**_initial_dispatch_receipt(), "setup_run_id": "invalid"}),
    (202, {**_initial_dispatch_receipt(), "setup_generation": 0}),
    (202, {**_initial_dispatch_receipt(), "project_id": PROJECT_ID}),
))
def test_initial_dispatch_rejects_uncertain_success_without_retry(
    adapter: Adapter, call: Call, name: str, _suffix: str, status: int, response: dict[str, Any]
) -> None:
    client, received, upstream = adapter
    upstream["status"] = status
    upstream["json"] = response
    result = call(
        client, name=f"workstream_{name}", arguments=_initial_dispatch_arguments()
    ).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert result["structuredContent"]["retryable"] is False
    assert len(received) == 1


@pytest.mark.parametrize(("name", "_suffix"), _INITIAL_DISPATCH_ROUTES)
@pytest.mark.parametrize(("status", "code"), (
    (404, "proposal_unavailable"), (409, "operation_conflict"),
    (503, "storage_unavailable"), (503, "authorization_service_unavailable"),
))
def test_initial_dispatch_preserves_safe_public_failures(
    adapter: Adapter, call: Call, name: str, _suffix: str, status: int, code: str
) -> None:
    client, received, upstream = adapter
    upstream["status"] = status
    upstream["json"] = {
        "error": {"code": code, "message": "Private detail", "retryable": status == 503}
    }
    result = call(
        client, name=f"workstream_{name}", arguments=_initial_dispatch_arguments()
    ).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == status
    assert result["structuredContent"]["code"] == code
    assert result["structuredContent"]["retryable"] is False
    if status == 503:
        assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert "Private detail" not in json.dumps(result)
    assert len(received) == 1


@pytest.mark.parametrize(("name", "_suffix"), _INITIAL_DISPATCH_ROUTES)
@pytest.mark.asyncio
async def test_initial_dispatch_transport_failure_is_uncertain_and_not_retried(
    name: str, _suffix: str
) -> None:
    attempts = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("private transport detail", request=request)

    async with httpx.AsyncClient(
        base_url="http://api.test", transport=httpx.MockTransport(fail)
    ) as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).guide_lifecycle(name, "Bearer explicit-caller", _initial_dispatch_arguments())
    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"
    assert result.failure.retryable is False
    assert attempts == 1
