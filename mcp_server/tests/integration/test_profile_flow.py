from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
from api_contract_e2e import (  # noqa: E402
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def _ready(url: str, process: subprocess.Popen[str]) -> None:
    async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
        for _ in range(160):
            assert process.poll() is None, "subprocess exited before readiness"
            try:
                if (await client.head(url)).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise AssertionError("subprocess readiness timeout")


async def _call(mcp_url: str, token: str) -> tuple[dict[str, Any], bool]:
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
        trust_env=False,
        timeout=20,
    ) as client:
        async with streamable_http_client(mcp_url + "/mcp", http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.call_tool("workstream_profile_get", {})
    dump = result.model_dump()
    if "structuredContent" in dump and dump["structuredContent"] is not None:
        content = dump["structuredContent"]
    elif "structured_content" in dump and dump["structured_content"] is not None:
        content = dump["structured_content"]
    else:
        import json

        content = json.loads(dump["content"][0]["text"])

    is_error = dump.get("isError", dump.get("is_error", False))
    return content, bool(is_error)


def _bootstrap_access_administrator(actor_id: str, environment: dict[str, str]) -> None:
    """Run the documented local trust-root command; never seed authority by SQL."""
    completed = subprocess.run(  # noqa: S603 - fixed repository command and generated UUID
        [
            sys.executable,
            "scripts/bootstrap_access_administrator.py",
            "--actor-profile-id",
            actor_id,
            "--execute",
        ],
        cwd=BACKEND,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout


async def _admin_transition(
    client: httpx.AsyncClient,
    *,
    token: str,
    path: str,
) -> None:
    response = await client.post(
        path,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid4())},
        json={"reason": "MCP integration lifecycle proof"},
    )
    assert response.status_code == 200, response.text


def _start_processes(
    *,
    api_port: int,
    api_env: dict[str, str],
    mcp_port: int,
    mcp_env: dict[str, str],
    executable: str,
    scratch: str,
) -> tuple[subprocess.Popen[str], subprocess.Popen[str], IO[str], IO[str]]:
    api_log = open(Path(scratch) / "api.log", "w", encoding="utf-8")  # noqa: PTH123
    mcp_log = open(Path(scratch) / "mcp.log", "w", encoding="utf-8")  # noqa: PTH123
    api = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--log-level",
            "error",
            "--no-access-log",
        ],
        cwd=BACKEND,
        env=api_env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    mcp = subprocess.Popen(  # noqa: S603
        [executable],
        cwd=scratch,
        env=mcp_env,
        stdout=mcp_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return api, mcp, api_log, mcp_log


@pytest.mark.asyncio
async def test_installed_mcp_preserves_profile_and_lifecycle_parity() -> None:
    env = api_environment()
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    tokens = {
        name: issue_flow_token(name, [], issuer=issuer, audience=audience, secret=secret)
        for name in (
            "mcp-first-a",
            "mcp-first-b",
            "mcp-admin",
            "mcp-suspended",
            "mcp-revoked",
            "mcp-deactivated",
        )
    }
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-integration-") as scratch:
        clean_mcp_env = {
            key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}
        }
        clean_mcp_env.update(
            WORKSTREAM_API_URL=api_url,
            WORKSTREAM_MCP_HOST="127.0.0.1",
            WORKSTREAM_MCP_PORT=str(mcp_port),
        )
        api, mcp, api_log, mcp_log = _start_processes(
            api_port=api_port,
            api_env=env,
            mcp_port=mcp_port,
            mcp_env=clean_mcp_env,
            executable=executable,
            scratch=scratch,
        )
        try:
            await _ready(api_url + "/api/v1/health", api)
            await _ready(mcp_url + "/mcp", mcp)
            async with httpx.AsyncClient(base_url=api_url, trust_env=False, timeout=10) as direct:
                first: dict[str, dict[str, Any]] = {}
                names = list(tokens.keys())
                
                # Prove overlapping concurrency: start all requests in parallel
                tasks = [asyncio.create_task(_call(mcp_url, tokens[name])) for name in names]
                results = await asyncio.gather(*tasks)
                
                for name, (profile, failed) in zip(names, results, strict=True):
                    assert not failed
                    assert profile["display_name"] is None and profile["contact_email"] is None
                    assert profile["admin_roles"] == [] and profile["project_role_grants"] == []
                    first[name] = profile
                    response = await direct.get(
                        "/api/v1/actors/me",
                        headers={"Authorization": f"Bearer {tokens[name]}"},
                    )
                    assert response.status_code == 200
                    assert response.json()["actor_profile_id"] == profile["actor_profile_id"]

                profile_ids = {profile["actor_profile_id"] for profile in first.values()}
                assert len(profile_ids) == len(first)

                _bootstrap_access_administrator(first["mcp-admin"]["actor_profile_id"], env)
                admin_token = tokens["mcp-admin"]
                await _admin_transition(
                    direct,
                    token=admin_token,
                    path=f"/api/v1/actors/{first['mcp-suspended']['actor_profile_id']}/suspend",
                )
                suspended, failed = await _call(mcp_url, tokens["mcp-suspended"])
                assert not failed and suspended["status"] == "suspended"

                revoked_link = await direct.get(
                    f"/api/v1/actors/{first['mcp-revoked']['actor_profile_id']}/identity-links",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert revoked_link.status_code == 200, revoked_link.text
                await _admin_transition(
                    direct,
                    token=admin_token,
                    path=(
                        "/api/v1/actor-identity-links/"
                        f"{revoked_link.json()['identity_link_id']}/revoke"
                    ),
                )
                await _admin_transition(
                    direct,
                    token=admin_token,
                    path=f"/api/v1/actors/{first['mcp-deactivated']['actor_profile_id']}/deactivate",
                )

                for name, code in (
                    ("mcp-revoked", "identity_link_revoked"),
                    ("mcp-deactivated", "actor_deactivated"),
                ):
                    direct_response = await direct.get(
                        "/api/v1/actors/me",
                        headers={"Authorization": f"Bearer {tokens[name]}"},
                    )
                    assert direct_response.status_code == 403
                    assert direct_response.json()["error"]["code"] == code
                    failure, failed = await _call(mcp_url, tokens[name])
                    assert failed
                    assert failure["status"] == 403 and failure["code"] == code
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            mcp_log.close()
