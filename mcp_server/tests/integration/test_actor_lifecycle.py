"""Installed MCP/public-API proof for actor and identity-link lifecycle."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from integration.oauth_fixture import IdentityFixture, IdentityTokens
from test_profile_flow import (
    _bootstrap_access_administrator,
    _call,
    _ready,
    _start_processes,
    _stop,
    api_environment,
    find_free_port,
)


async def _profile(client: httpx.AsyncClient, token: IdentityTokens) -> dict[str, Any]:
    response = await client.get(
        "/api/v1/actors/me", headers={"Authorization": f"Bearer {token.api}"}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _identity_link(
    client: httpx.AsyncClient, admin_token: IdentityTokens, actor_profile_id: str
) -> str:
    response = await client.get(
        f"/api/v1/actors/{actor_profile_id}/identity-links",
        headers={"Authorization": f"Bearer {admin_token.api}"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["identity_link_id"])


async def _mcp(
    mcp_url: str,
    token: IdentityTokens,
    name: str,
    arguments: dict[str, Any],
    *,
    status: int | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    body, failed = await _call(mcp_url, token, name=name, arguments=arguments)
    assert failed is (status is not None), (name, body)
    if status is not None:
        assert body["status"] == status
        assert body.get("code") == code
    return body


def _arguments(resource_key: str, resource_id: str, reason: str) -> dict[str, Any]:
    return {
        resource_key: resource_id,
        "body": {"reason": reason},
        "idempotency_key": str(uuid4()),
    }


def _restart_mcp(
    executable: str, scratch: str, environment: dict[str, str]
) -> tuple[subprocess.Popen[str], IO[str]]:
    log = open(Path(scratch) / "mcp-restart.log", "w", encoding="utf-8")  # noqa: PTH123
    process = subprocess.Popen(  # noqa: S603
        [executable],
        cwd=scratch,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, log


@pytest.mark.asyncio
async def test_installed_mcp_preserves_lifecycle_authority_replay_and_terminal_state(
    identity: IdentityFixture,
) -> None:
    env = api_environment()
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    run_id = uuid4().hex
    tokens = {
        name: identity.issue(f"mcp-lifecycle-{run_id}-{name}")
        for name in ("admin", "ordinary", "target", "terminal")
    }
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-lifecycle-") as scratch:
        mcp_env = {
            key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}
        }
        mcp_env.update(
            WORKSTREAM_API_URL=api_url,
            WORKSTREAM_MCP_HOST="127.0.0.1",
            WORKSTREAM_MCP_PORT=str(mcp_port),
        )
        api, mcp, api_log, mcp_log = _start_processes(
            identity=identity,
            api_port=api_port,
            api_env=env,
            mcp_port=mcp_port,
            mcp_env=mcp_env,
            executable=executable,
            scratch=scratch,
        )
        restart_log = None
        try:
            await _ready(api_url + "/api/v1/health", api)
            await _ready(mcp_url + "/mcp", mcp)
            async with httpx.AsyncClient(base_url=api_url, trust_env=False, timeout=20) as direct:
                profiles = {name: await _profile(direct, token) for name, token in tokens.items()}
                admin_id = profiles["admin"]["actor_profile_id"]
                _bootstrap_access_administrator(admin_id, env)
                links = {
                    name: await _identity_link(direct, tokens["admin"], profile["actor_profile_id"])
                    for name, profile in profiles.items()
                }

                suspend = _arguments(
                    "actor_profile_id",
                    profiles["target"]["actor_profile_id"],
                    "Installed MCP actor suspension proof",
                )
                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_actor_suspend",
                    {**suspend, "idempotency_key": str(uuid4())},
                    status=403,
                    code="permission_not_granted",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_actor_suspend",
                    _arguments("actor_profile_id", admin_id, "Self suspension denial proof"),
                    status=403,
                    code="resource_guard_denied",
                )
                suspended = await _mcp(
                    mcp_url, tokens["admin"], "workstream_actor_suspend", suspend
                )
                assert suspended == {
                    "resource_type": "actor_profile",
                    "resource_id": profiles["target"]["actor_profile_id"],
                    "version": None,
                    "http_status": 200,
                }

                _stop(mcp)
                mcp_log.close()
                mcp, restart_log = _restart_mcp(executable, scratch, mcp_env)
                await _ready(mcp_url + "/mcp", mcp)
                assert (
                    await _mcp(mcp_url, tokens["admin"], "workstream_actor_suspend", suspend)
                    == suspended
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_actor_suspend",
                    {**suspend, "body": {"reason": "Changed request"}},
                    status=409,
                    code="idempotency_mismatch",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_actor_suspend",
                    {**suspend, "idempotency_key": str(uuid4())},
                    status=409,
                    code="actor_already_suspended",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_actor_reactivate",
                    _arguments(
                        "actor_profile_id",
                        profiles["target"]["actor_profile_id"],
                        "Installed MCP actor reactivation proof",
                    ),
                )

                revoke = _arguments(
                    "identity_link_id",
                    links["target"],
                    "Installed MCP identity-link revoke proof",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_identity_link_revoke",
                    _arguments("identity_link_id", links["admin"], "Self link revoke denial proof"),
                    status=403,
                    code="resource_guard_denied",
                )
                revoked = await _mcp(
                    mcp_url, tokens["admin"], "workstream_identity_link_revoke", revoke
                )
                assert revoked["resource_id"] == links["target"]
                assert (
                    await _mcp(mcp_url, tokens["admin"], "workstream_identity_link_revoke", revoke)
                    == revoked
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_identity_link_revoke",
                    {**revoke, "body": {"reason": "Changed link request"}},
                    status=409,
                    code="idempotency_mismatch",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_identity_link_reactivate",
                    _arguments(
                        "identity_link_id",
                        links["target"],
                        "Installed MCP identity-link reactivation proof",
                    ),
                )

                terminal_id = profiles["terminal"]["actor_profile_id"]
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_actor_deactivate",
                    _arguments("actor_profile_id", terminal_id, "Terminal lifecycle proof"),
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_actor_reactivate",
                    _arguments("actor_profile_id", terminal_id, "Must remain terminal"),
                    status=409,
                    code="actor_deactivated_terminal",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_identity_link_revoke",
                    _arguments(
                        "identity_link_id", links["terminal"], "Terminal link mutation denial"
                    ),
                    status=409,
                    code="actor_deactivated_terminal",
                )
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            if not mcp_log.closed:
                mcp_log.close()
            if restart_log is not None:
                restart_log.close()
