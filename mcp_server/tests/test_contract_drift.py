from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "mcp_server" / "contracts" / "profile_get.json"
BACKEND = ROOT / "backend"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _selected(openapi: dict[str, Any]) -> dict[str, Any]:
    operation = openapi["paths"]["/api/v1/actors/me"]["get"]
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


def _running_openapi() -> dict[str, Any]:
    command = os.environ.get("WORKSTREAM_MCP_OPENAPI_COMMAND")
    argv = (
        shlex.split(command)
        if command
        else [
            sys.executable,
            "-c",
            "import json; from app.main import app; print(json.dumps(app.openapi()))",
        ]
    )
    completed = subprocess.run(  # noqa: S603 - fixed local/configured contract probe
        argv,
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def test_profile_contract_has_a_tamper_evident_selected_fragment() -> None:
    snapshot = json.loads(CONTRACT.read_text(encoding="utf-8"))
    captured = {"operation": snapshot["operation"], "components": snapshot["components"]}
    assert hashlib.sha256(_canonical(captured)).hexdigest() == snapshot["canonical_sha256"]


def test_profile_contract_matches_current_backend_openapi_when_command_is_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if "WORKSTREAM_MCP_OPENAPI_COMMAND" not in os.environ:
        pytest.skip("backend OpenAPI comparison is run in the isolated backend environment")
    snapshot = json.loads(CONTRACT.read_text(encoding="utf-8"))
    captured = {"operation": snapshot["operation"], "components": snapshot["components"]}

    openapi = _running_openapi()
    assert snapshot["source"]["openapi_version"] == openapi["openapi"]
    assert captured == _selected(openapi)


def test_selected_fragment_follows_transitive_schema_references() -> None:
    openapi = {
        "paths": {
            "/api/v1/actors/me": {
                "get": {"responses": {"200": {"$ref": "#/components/schemas/Outer"}}}
            }
        },
        "components": {
            "schemas": {
                "Outer": {"properties": {"child": {"$ref": "#/components/schemas/Inner"}}},
                "Inner": {"type": "string"},
            }
        },
    }
    selected = _selected(openapi)
    assert set(selected["components"]["schemas"]) == {"Inner", "Outer"}
