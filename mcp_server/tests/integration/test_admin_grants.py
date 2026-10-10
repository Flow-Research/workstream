"""Installed MCP/public-API proof for administrative grant mutations."""

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
from test_profile_flow import (
    _bootstrap_access_administrator,
    _call,
    _ready,
    _start_processes,
    _stop,
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)


async def _profile(client: httpx.AsyncClient, token: str) -> dict[str, Any]:
    response = await client.get("/api/v1/actors/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    return response.json()


async def _mcp(
    mcp_url: str,
    token: str,
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


def _restart_mcp(
    executable: str,
    scratch: str,
    environment: dict[str, str],
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
async def test_installed_mcp_preserves_admin_grant_authority_and_replay() -> None:
    env = api_environment()
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    issuer, audience, secret = flow_settings(env)
    run_id = uuid4().hex
    subjects = {
        "admin": "mcp-admin",
        "ordinary": f"mcp-grants-{run_id}-ordinary",
        "target": f"mcp-grants-{run_id}-target",
        "second_admin": f"mcp-grants-{run_id}-second-admin",
        "second_target": f"mcp-grants-{run_id}-second-target",
    }
    tokens = {
        name: issue_flow_token(subject, [], issuer=issuer, audience=audience, secret=secret)
        for name, subject in subjects.items()
    }
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-admin-grants-") as scratch:
        mcp_env = {
            key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}
        }
        mcp_env.update(
            WORKSTREAM_API_URL=api_url,
            WORKSTREAM_MCP_HOST="127.0.0.1",
            WORKSTREAM_MCP_PORT=str(mcp_port),
        )
        api, mcp, api_log, mcp_log = _start_processes(
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
                if "access_administrator" not in profiles["admin"]["admin_roles"]:
                    _bootstrap_access_administrator(profiles["admin"]["actor_profile_id"], env)

                issue_key = str(uuid4())
                issue = {
                    "body": {
                        "target_actor_profile_id": profiles["target"]["actor_profile_id"],
                        "role": "operator",
                        "scope_type": "system",
                        "reason": "Installed MCP administrative grant proof",
                    },
                    "idempotency_key": issue_key,
                }
                issued = await _mcp(
                    mcp_url, tokens["admin"], "workstream_admin_grants_issue", issue
                )
                assert (issued["http_status"], issued["version"]) == (201, 1)

                # Recreate the adapter before replay: replay authority belongs to Workstream.
                _stop(mcp)
                mcp_log.close()
                mcp, restart_log = _restart_mcp(executable, scratch, mcp_env)
                await _ready(mcp_url + "/mcp", mcp)
                assert (
                    await _mcp(mcp_url, tokens["admin"], "workstream_admin_grants_issue", issue)
                    == issued
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_issue",
                    {**issue, "body": {**issue["body"], "reason": "Changed request"}},
                    status=409,
                    code="idempotency_mismatch",
                )
                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_admin_grants_issue",
                    {**issue, "idempotency_key": str(uuid4())},
                    status=403,
                    code="permission_not_granted",
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_issue",
                    {
                        **issue,
                        "body": {
                            **issue["body"],
                            "target_actor_profile_id": profiles["admin"]["actor_profile_id"],
                        },
                        "idempotency_key": str(uuid4()),
                    },
                    status=403,
                    code="self_grant_forbidden",
                )

                revoke = {
                    "grant_id": issued["resource_id"],
                    "body": {"reason": "Installed MCP administrative revoke proof"},
                    "idempotency_key": str(uuid4()),
                }
                revoked = await _mcp(
                    mcp_url, tokens["admin"], "workstream_admin_grants_revoke", revoke
                )
                assert revoked == {
                    **issued,
                    "version": 2,
                    "http_status": 200,
                }
                assert (
                    await _mcp(mcp_url, tokens["admin"], "workstream_admin_grants_revoke", revoke)
                    == revoked
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_revoke",
                    {**revoke, "body": {"reason": "Changed request"}},
                    status=409,
                    code="idempotency_mismatch",
                )

                second_admin_issue = {
                    "body": {
                        "target_actor_profile_id": profiles["second_admin"]["actor_profile_id"],
                        "role": "access_administrator",
                        "scope_type": "system",
                        "reason": "Prove current authority through MCP",
                    },
                    "idempotency_key": str(uuid4()),
                }
                second_admin_grant = await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_issue",
                    second_admin_issue,
                )
                delegated_issue = {
                    "body": {
                        "target_actor_profile_id": profiles["second_target"]["actor_profile_id"],
                        "role": "operator",
                        "scope_type": "system",
                        "reason": "Current authority success",
                    },
                    "idempotency_key": str(uuid4()),
                }
                await _mcp(
                    mcp_url,
                    tokens["second_admin"],
                    "workstream_admin_grants_issue",
                    delegated_issue,
                )
                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_revoke",
                    {
                        "grant_id": second_admin_grant["resource_id"],
                        "body": {"reason": "End delegated administration"},
                        "idempotency_key": str(uuid4()),
                    },
                )
                await _mcp(
                    mcp_url,
                    tokens["second_admin"],
                    "workstream_admin_grants_issue",
                    {**delegated_issue, "idempotency_key": str(uuid4())},
                    status=403,
                    code="permission_not_granted",
                )
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            if not mcp_log.closed:
                mcp_log.close()
            if restart_log is not None:
                restart_log.close()
