from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from jsonschema.exceptions import ValidationError

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import TASK_EXECUTION_OPERATIONS, WorkstreamGateway
from workstream_mcp.schemas import TASK_EXECUTION_CONTRACT_NAMES, task_execution_output_validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "mcp_server" / "contracts"
BACKEND = ROOT / "backend"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _selected(openapi: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    operation = openapi["paths"][path][method.lower()]
    names: set[str] = set()
    pending: list[Any] = [operation]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
                name = reference.rsplit("/", 1)[-1]
                if name not in names:
                    names.add(name)
                    pending.append(openapi["components"]["schemas"][name])
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return {
        "operation": operation,
        "components": {
            "schemas": {name: openapi["components"]["schemas"][name] for name in sorted(names)}
        },
    }


@pytest.mark.parametrize("name", TASK_EXECUTION_CONTRACT_NAMES)
def test_task_execution_contract_is_tamper_evident_and_matches_fixed_route(
    name: str,
) -> None:
    snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
    captured = {"operation": snapshot["operation"], "components": snapshot["components"]}
    method, path, status = TASK_EXECUTION_OPERATIONS[name]
    success_codes = {
        int(code) for code in snapshot["operation"]["responses"] if code.startswith("2")
    }
    assert snapshot["schema_version"] == 1
    assert snapshot["source"]["method"] == method
    assert snapshot["source"]["path"] == path
    assert status in success_codes
    assert hashlib.sha256(_canonical(captured)).hexdigest() == snapshot["canonical_sha256"]


def test_exact_task_execution_contract_set_is_reviewed() -> None:
    assert len(TASK_EXECUTION_CONTRACT_NAMES) == 17
    assert set(TASK_EXECUTION_CONTRACT_NAMES) == set(TASK_EXECUTION_OPERATIONS)


def test_task_execution_contracts_match_backend_openapi_when_configured() -> None:
    command = os.environ.get("WORKSTREAM_MCP_OPENAPI_COMMAND")
    if command is None:
        pytest.skip("backend OpenAPI comparison is run in the isolated backend environment")
    completed = subprocess.run(  # noqa: S603 - configured local contract probe
        shlex.split(command),
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    openapi = json.loads(completed.stdout)
    for name, (method, path, _) in TASK_EXECUTION_OPERATIONS.items():
        snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
        assert snapshot["source"]["openapi_version"] == openapi["openapi"]
        assert {
            "operation": snapshot["operation"],
            "components": snapshot["components"],
        } == _selected(openapi, path, method)


def test_current_claim_http_json_passes_mcp_validation_when_configured() -> None:
    """The actual route's fresh/replayed bytes satisfy the closed MCP contract."""
    command = os.environ.get("WORKSTREAM_MCP_OPENAPI_COMMAND")
    if command is None:
        pytest.skip("backend HTTP projection proof runs in the isolated backend environment")
    probe = shlex.split(command)
    assert probe[-2] == "-c", "the configured backend probe must run an inline Python command"
    probe[-1] = """
import asyncio,json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient
from app.modules.tasks.api.authorization import TaskAuthorityOperation
from app.modules.tasks.command_replay import TaskCommandReplay
from app.modules.tasks.router import router,get_task_commands
from tests.tasks.test_payment_policy_removal import _command_receipt,MANAGEMENT_ONLY
async def observe():
    receipt,facts,task,assignment,fresh=_command_receipt(TaskAuthorityOperation.CLAIM,'in_progress')
    stored=deepcopy(receipt.response)
    replay=await TaskCommandReplay(AsyncMock()).recover(
        receipt,receipt.request_digest,facts,task,assignment,reserved=False)
    private={key:'PRIVATE_'+key for key in MANAGEMENT_ONLY}
    fresh=fresh.model_copy(update={'task':fresh.task.model_copy(update=private)})
    app=FastAPI()
    app.include_router(router,prefix='/api/v1')
    commands=SimpleNamespace(claim=AsyncMock(side_effect=[fresh,replay]))
    app.dependency_overrides[get_task_commands]=lambda:commands
    responses=[]
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver') as client:
        for _ in range(2):
            response=await client.post(
                f'/api/v1/tasks/{task.id}/claim',
                headers={'Idempotency-Key':str(receipt.idempotency_key)},
            )
            assert response.status_code==200,response.text
            assert receipt.response==stored
            responses.append(response.json())
    print(json.dumps({'responses':responses,'task_id':task.id,'key':str(receipt.idempotency_key)}))
asyncio.run(observe())
"""
    completed = subprocess.run(  # noqa: S603 - same configured local backend interpreter
        probe,
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    observed = json.loads(completed.stdout)
    fresh, replay = observed["responses"]
    assert fresh == replay
    validator = task_execution_output_validator("task_claim")
    for body in (fresh, replay):
        validator.validate(body)
        assert body["task"]["task_type"] is None
        assert body["assignment"]["released_at"] is None
        assert "PRIVATE_" not in json.dumps(body)
    for field in ("source_ref", "locked_guide_source_snapshot_id"):
        poisoned = deepcopy(fresh)
        poisoned["task"][field] = None
        with pytest.raises(ValidationError):
            validator.validate(poisoned)
    missing = deepcopy(fresh)
    del missing["task"]["task_type"]
    with pytest.raises(ValidationError):
        validator.validate(missing)

    async def dispatch() -> None:
        responses = iter((fresh, replay))
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=next(responses))

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://workstream.test"
        ) as client:
            gateway = WorkstreamGateway(Settings(api_url="http://127.0.0.1:8000"), client)
            arguments = {"task_id": observed["task_id"], "idempotency_key": observed["key"]}
            for expected in (fresh, replay):
                result = await gateway.task_execution_operation(
                    "task_claim", "Bearer caller-token", arguments
                )
                assert result.failure is None
                assert result.data == expected
        assert len(requests) == 2
        assert all(request.headers["idempotency-key"] == observed["key"] for request in requests)

    asyncio.run(dispatch())
