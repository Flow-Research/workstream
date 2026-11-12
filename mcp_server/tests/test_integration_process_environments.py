"""Keep API-to-adapter proof in each component's independent dependency environment."""

from __future__ import annotations

import json
from types import SimpleNamespace

from integration import test_profile_flow as journey


def test_backend_environment_uses_backend_python_and_retains_shared_environment(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/adapter/environment")
    monkeypatch.setenv("MCP_ENVIRONMENT_PROBE", "retained")
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout=json.dumps({"WORKSTREAM_ENVIRONMENT": "local"}))

    monkeypatch.setattr(journey.subprocess, "run", run)
    environment = journey.api_environment()
    argv, kwargs = calls[0]
    backend_python = str(journey.BACKEND / ".venv" / "bin" / "python")
    assert argv[:2] == [backend_python, "-c"]
    assert kwargs["cwd"] == journey.BACKEND
    assert kwargs["check"] and kwargs["capture_output"]
    assert kwargs["env"]["VIRTUAL_ENV"] == str(journey.BACKEND / ".venv")
    assert environment["VIRTUAL_ENV"] == str(journey.BACKEND / ".venv")
    assert environment["MCP_ENVIRONMENT_PROBE"] == "retained"
    assert environment["WORKSTREAM_ENVIRONMENT"] == "local"
    assert "assert_isolated_database_url(env['WORKSTREAM_DATABASE_URL'])" in argv[2]
    assert "if before.get(key) != value" in argv[2]


def test_api_and_bootstrap_execute_with_backend_python(monkeypatch, tmp_path):
    commands = []

    def start(argv, **kwargs):
        commands.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(journey.subprocess, "run", start)
    monkeypatch.setattr(journey.subprocess, "Popen", start)
    environment = {"WORKSTREAM_ENVIRONMENT": "local"}
    identity_environments = []
    identity = SimpleNamespace(
        configure_processes=lambda api, mcp: identity_environments.append((api, mcp)),
    )
    journey._bootstrap_access_administrator("actor-probe", environment)
    _, _, api_log, mcp_log = journey._start_processes(
        identity=identity,
        api_port=12345, api_env=environment, mcp_port=12346,
        mcp_env={}, executable="/independent-wheel/workstream-mcp", scratch=str(tmp_path),
    )
    api_log.close()
    mcp_log.close()
    backend_python = str(journey.BACKEND / ".venv" / "bin" / "python")
    assert commands[0][0][:2] == [backend_python, "scripts/bootstrap_access_administrator.py"]
    assert commands[1][0][:3] == [backend_python, "-m", "uvicorn"]
    assert commands[0][1]["cwd"] == commands[1][1]["cwd"] == journey.BACKEND
    assert commands[0][1]["env"] == commands[1][1]["env"] == environment
    assert commands[2][0] == ["/independent-wheel/workstream-mcp"]
    assert identity_environments == [(environment, {})]
