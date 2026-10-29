from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import ANY

import httpx2 as httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.errors import SafeFailure
from workstream_mcp.http_gateway import GatewayResult, WorkstreamGateway
from workstream_mcp.schemas import (
    CHECKER_ARTIFACT_CONTRACT_NAMES,
    checker_artifact_input_schema,
)
from workstream_mcp.tools import checker_artifacts

PROJECT_ID = "019a2a00-0000-7000-8000-000000001001"
SUBMISSION_ID = "019a2a00-0000-7000-8000-000000001002"
CHECKER_RUN_ID = "019a2a00-0000-7000-8000-000000001003"
SOURCE_RUN_ID = "019a2a00-0000-7000-8000-000000001004"
EVENT_ID = "019a2a00-0000-7000-8000-000000001005"
REGISTRY_ID = "019a2a00-0000-7000-8000-000000001006"
CONTENT_ID = "019a2a00-0000-7000-8000-000000001007"
REPLICA_ID = "019a2a00-0000-7000-8000-000000001008"
JOB_ID = "019a2a00-0000-7000-8000-000000001009"
RECOVERY_ID = "019a2a00-0000-7000-8000-000000001010"
TASK_ID = "019a2a00-0000-7000-8000-000000001011"
KEY = "019a2a00-0000-7000-8000-000000001012"
DIGEST = "sha256:" + "a" * 64
Adapter = tuple[TestClient, list[httpx.Request], dict[str, Any]]
Call = Callable[..., httpx.Response]


def _registry_body() -> dict[str, Any]:
    schema = {
        "schema_id": "checker.schema",
        "schema_version": "v1",
        "document": {"type": "object"},
        "schema_sha256": DIGEST,
    }
    return {
        "capability_id": "checker.capability",
        "capability_version": "v1",
        "phase": "post_submit",
        "image_digest": DIGEST,
        "configuration_schema": schema,
        "input_schema": schema,
        "output_schema": schema,
        "resources": {
            "cpu_millis": 100,
            "memory_bytes": 16777216,
            "deadline_ms": 100,
            "maximum_output_bytes": 256,
        },
    }


def _arguments(name: str) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "submission_checker_runs_list": {"submission_id": SUBMISSION_ID, "limit": 10},
        "submission_checker_runs_get": {
            "submission_id": SUBMISSION_ID,
            "checker_run_id": CHECKER_RUN_ID,
        },
        "project_checker_runs_list": {
            "project_id": PROJECT_ID,
            "submission_id": SUBMISSION_ID,
            "cursor": "next",
        },
        "project_checker_runs_get": {
            "project_id": PROJECT_ID,
            "submission_id": SUBMISSION_ID,
            "checker_run_id": CHECKER_RUN_ID,
        },
        "checker_retry_sources_list": {"project_id": PROJECT_ID, "limit": 25},
        "checker_runs_retry": {
            "project_id": PROJECT_ID,
            "source_run_id": SOURCE_RUN_ID,
            "idempotency_key": KEY,
            "body": {"reason": "operator retry"},
        },
        "post_submit_deliveries_list": {"project_id": PROJECT_ID, "cursor": "next"},
        "post_submit_deliveries_reconcile": {
            "project_id": PROJECT_ID,
            "event_id": EVENT_ID,
            "idempotency_key": KEY,
            "body": {"reason": "operator reconciliation"},
        },
        "checker_registry_read": {"registry_entry_id": REGISTRY_ID},
        "checker_registry_register": {
            "idempotency_key": KEY,
            "body": _registry_body(),
        },
        "artifact_readiness_get": {},
        "artifact_bindings_list": {
            "resource_type": "submission",
            "resource_id": SUBMISSION_ID,
            "limit": 10,
        },
        "artifact_replicas_list": {"content_id": CONTENT_ID, "cursor": "next"},
        "artifact_receipts_list": {"replica_id": REPLICA_ID, "limit": 10},
        "artifact_verification_job_get": {"verification_job_id": JOB_ID},
        "artifact_verification_job_retry": {
            "verification_job_id": JOB_ID,
            "body": {
                "project_id": PROJECT_ID,
                "task_id": TASK_ID,
                "submission_id": SUBMISSION_ID,
                "reason": "operator retry",
                "client_idempotency_key": "artifact-retry-1",
                "expected_source_job_cas_version": 3,
            },
        },
        "artifact_recovery_attempt_get": {"recovery_attempt_id": RECOVERY_ID},
        "artifact_admission_usage_get": {
            "project_id": PROJECT_ID,
            "task_id": TASK_ID,
            "limit": 10,
        },
        "artifact_audit_events_list": {
            "resource_type": "artifact_replica",
            "resource_id": REPLICA_ID,
            "cursor": "next",
        },
    }
    return values[name]


def _bound_response(name: str) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "submission_checker_runs_list": {
            "items": [{"id": CHECKER_RUN_ID, "submission_id": SUBMISSION_ID}]
        },
        "submission_checker_runs_get": {
            "id": CHECKER_RUN_ID,
            "submission_id": SUBMISSION_ID,
        },
        "project_checker_runs_list": {
            "items": [{"id": CHECKER_RUN_ID, "submission_id": SUBMISSION_ID}]
        },
        "project_checker_runs_get": {
            "id": CHECKER_RUN_ID,
            "submission_id": SUBMISSION_ID,
        },
        "checker_retry_sources_list": {
            "project_id": PROJECT_ID,
            "items": [{"source": {"project_id": PROJECT_ID, "source_run_id": SOURCE_RUN_ID}}],
        },
        "checker_runs_retry": {
            "source": {"project_id": PROJECT_ID, "source_run_id": SOURCE_RUN_ID}
        },
        "post_submit_deliveries_list": {
            "project_id": PROJECT_ID,
            "items": [{"project_id": PROJECT_ID, "event_id": EVENT_ID}],
        },
        "post_submit_deliveries_reconcile": {
            "source": {"project_id": PROJECT_ID, "event_id": EVENT_ID}
        },
        "checker_registry_read": {"registry_entry_id": REGISTRY_ID},
        "checker_registry_register": {
            **_registry_body(),
            "registration_operation_id": KEY,
        },
        "artifact_readiness_get": {},
        "artifact_bindings_list": {
            "items": [
                {
                    "id": CONTENT_ID,
                    "resource_type": "submission",
                    "resource_id": SUBMISSION_ID,
                }
            ]
        },
        "artifact_replicas_list": {
            "items": [{"id": REPLICA_ID, "content_id": CONTENT_ID}]
        },
        "artifact_receipts_list": {
            "items": [{"id": CONTENT_ID, "replica_id": REPLICA_ID}]
        },
        "artifact_verification_job_get": {"id": JOB_ID},
        "artifact_verification_job_retry": {"source_verification_job_id": JOB_ID},
        "artifact_recovery_attempt_get": {"id": RECOVERY_ID},
        "artifact_admission_usage_get": {
            "items": [
                {"scope_type": "project", "scope_id": PROJECT_ID},
                {"scope_type": "task", "scope_id": TASK_ID},
            ]
        },
        "artifact_audit_events_list": {
            "items": [
                {
                    "id": CONTENT_ID,
                    "entity_type": "artifact_replica",
                    "entity_id": REPLICA_ID,
                }
            ]
        },
    }
    return values[name]


def _catalogue(client: TestClient) -> list[dict[str, Any]]:
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return response.json()["result"]["tools"]


def test_checker_artifact_catalogue_is_exact_closed_and_does_not_dispatch(
    adapter: Adapter,
) -> None:
    client, received, _ = adapter
    catalogue = _catalogue(client)
    by_name = {tool["name"]: tool for tool in catalogue}
    selected = [by_name[name] for name in checker_artifacts.TOOL_NAMES]
    assert [tool["name"] for tool in selected] == list(checker_artifacts.TOOL_NAMES)
    for contract_name, tool in zip(CHECKER_ARTIFACT_CONTRACT_NAMES, selected, strict=True):
        assert tool["inputSchema"] == checker_artifact_input_schema(contract_name)
        Draft202012Validator.check_schema(tool["inputSchema"])
        Draft202012Validator.check_schema(tool["outputSchema"])
        Draft202012Validator(
            tool["inputSchema"], format_checker=FormatChecker()
        ).validate(_arguments(contract_name))
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["annotations"]["readOnlyHint"] is False
        assert tool["annotations"]["openWorldHint"] is False
    assert received == []


@pytest.mark.asyncio
async def test_nullable_checker_query_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        captured.update(kwargs)
        return GatewayResult(
            data={"items": [{"id": CHECKER_RUN_ID, "submission_id": SUBMISSION_ID}]}
        )

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).checker_artifact_operation(
            "submission_checker_runs_list",
            "Bearer token",
            {"submission_id": SUBMISSION_ID, "cursor": None},
        )

    assert result.failure is None
    assert captured["params"] is None


@pytest.mark.parametrize("name", CHECKER_ARTIFACT_CONTRACT_NAMES)
@pytest.mark.asyncio
async def test_every_checker_artifact_operation_forwards_only_its_fixed_request(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    captured: dict[str, Any] = {}

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        captured.update(args=args, kwargs=kwargs)
        return GatewayResult(data=_bound_response(name))

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    client = httpx.AsyncClient(base_url="http://workstream.test")
    try:
        result = await WorkstreamGateway(
            Settings(api_url="http://127.0.0.1:8000"), client
        ).checker_artifact_operation(
            name, "Bearer caller-token", _arguments(name), "request-correlation"
        )
    finally:
        await client.aclose()

    method, path_template, status = __import__(
        "workstream_mcp.http_gateway", fromlist=["CHECKER_ARTIFACT_OPERATIONS"]
    ).CHECKER_ARTIFACT_OPERATIONS[name]
    expected_path = path_template
    for key, value in _arguments(name).items():
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
    assert captured["kwargs"]["json_body"] == _arguments(name).get("body")
    assert captured["kwargs"]["idempotency_key"] == _arguments(name).get("idempotency_key")
    path_keys = {key for key in _arguments(name) if "{" + key + "}" in path_template}
    expected_params = {
        key: str(value)
        for key, value in _arguments(name).items()
        if key not in path_keys and key not in {"body", "idempotency_key"}
    }
    assert captured["kwargs"]["params"] == (expected_params or None)


@pytest.mark.parametrize("name", CHECKER_ARTIFACT_CONTRACT_NAMES)
@pytest.mark.asyncio
async def test_invalid_checker_artifact_input_never_dispatches(name: str) -> None:
    class Gateway:
        called = False

        async def checker_artifact_operation(self, *_: Any) -> GatewayResult:
            self.called = True
            return GatewayResult(data={})

    arguments = _arguments(name)
    required = checker_artifact_input_schema(name).get("required", [])
    if required:
        arguments.pop(required[0])
    else:
        arguments["unexpected"] = True
    gateway = Gateway()
    result = await checker_artifacts.invoke(
        gateway,  # type: ignore[arg-type]
        f"workstream_{name}",
        "Bearer token",
        None,
        arguments,
    )
    assert result.is_error is True
    assert gateway.called is False


def test_caller_token_is_forwarded_and_mcp_headers_cannot_supply_arguments(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {
        "backend": "s3",
        "provider_profile": "hosted",
        "configured": True,
        "active": True,
        "status": "ready",
        "prerequisites": {"bucket": True},
    }
    result = call(
        client,
        name="workstream_artifact_readiness_get",
        token="operator-token",
        extra_headers={"Idempotency-Key": KEY, "If-Match": '"ignored"'},
    ).json()["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"].startswith("Untrusted Workstream data")
    assert len(received) == 1
    assert received[0].headers["authorization"] == "Bearer operator-token"
    assert "idempotency-key" not in received[0].headers
    assert "if-match" not in received[0].headers


def test_checker_artifact_upstream_error_is_safely_forwarded(
    adapter: Adapter, call: Call
) -> None:
    client, received, upstream = adapter
    upstream.update(
        status=403,
        json={
            "error": {
                "code": "permission_not_granted",
                "message": "private authority detail",
                "details": {"private": "value"},
            }
        },
    )
    result = call(
        client,
        name="workstream_artifact_readiness_get",
        token="operator-token",
    ).json()["result"]
    assert len(received) == 1
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "error": "workstream_request_failed",
        "retryable": False,
        "status": 403,
        "code": "permission_not_granted",
        "correlation_id": ANY,
    }
    assert "private" not in str(result)


@pytest.mark.parametrize("name", CHECKER_ARTIFACT_CONTRACT_NAMES)
def test_success_responses_are_bound_to_requested_selectors_and_receipts(name: str) -> None:
    arguments = _arguments(name)
    response = _bound_response(name)
    assert WorkstreamGateway._checker_artifact_response_matches(name, response, arguments)
    if name == "artifact_readiness_get":
        return
    foreign = "019a2a00-0000-7000-8000-000000001099"
    if name.endswith("_list") and isinstance(response.get("items"), list):
        response["items"].append(response["items"][0].copy())
    elif name == "checker_registry_register":
        response["registration_operation_id"] = foreign
    elif name in {"checker_runs_retry", "post_submit_deliveries_reconcile"}:
        response["source"] = {**response["source"], "project_id": foreign}
    elif name == "artifact_verification_job_retry":
        response["source_verification_job_id"] = foreign
    else:
        response[next(iter(response))] = foreign
    assert not WorkstreamGateway._checker_artifact_response_matches(name, response, arguments)


def test_registry_receipt_allows_backend_defaults_but_binds_supplied_fields() -> None:
    arguments = _arguments("checker_registry_register")
    response = _bound_response("checker_registry_register")
    response["resources"] = {**response["resources"], "network_disabled": True}

    assert WorkstreamGateway._checker_artifact_response_matches(
        "checker_registry_register", response, arguments
    )


@pytest.mark.asyncio
async def test_mutation_binding_failure_is_uncertain_and_upstream_failure_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = iter(
        [
            GatewayResult(
                data={"source": {"project_id": PROJECT_ID, "source_run_id": EVENT_ID}},
                correlation_id="123e4567-e89b-42d3-a456-426614174000",
            ),
            GatewayResult(failure=SafeFailure("workstream_request_failed", status=409)),
        ]
    )

    async def request(_: WorkstreamGateway, *args: Any, **kwargs: Any) -> GatewayResult:
        return next(outcomes)

    monkeypatch.setattr(WorkstreamGateway, "_request", request)
    async with httpx.AsyncClient(base_url="http://workstream.test") as client:
        gateway = WorkstreamGateway(Settings(api_url="http://127.0.0.1:8000"), client)
        mismatch = await gateway.checker_artifact_operation(
            "checker_runs_retry", "Bearer token", _arguments("checker_runs_retry")
        )
        rejected = await gateway.checker_artifact_operation(
            "checker_runs_retry", "Bearer token", _arguments("checker_runs_retry")
        )
    assert mismatch.failure is not None
    assert mismatch.failure.error == "workstream_execution_uncertain"
    assert mismatch.failure.correlation_id == "123e4567-e89b-42d3-a456-426614174000"
    assert rejected.failure is not None
    assert rejected.failure.status == 409
