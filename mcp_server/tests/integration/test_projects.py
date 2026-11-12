"""Installed MCP/public-API proof for project-shell creation and reads."""

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
from oauth_fixture import IdentityFixture, IdentityTokens
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


def _qualification() -> dict[str, Any]:
    unavailable = {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    }
    return {
        "skills_snapshot": unavailable,
        "reputation_snapshot": unavailable,
        "prior_project_work_refs": [],
        "external_expertise_refs": [],
    }


@pytest.mark.asyncio
async def test_installed_mcp_preserves_project_authority_projection_and_replay(
    identity: IdentityFixture,
) -> None:
    env = api_environment()
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    run_id = uuid4().hex
    subjects = {
        "admin": "mcp-admin",
        "manager": f"mcp-projects-{run_id}-manager",
        "contributor": f"mcp-projects-{run_id}-contributor",
        "ordinary": f"mcp-projects-{run_id}-ordinary",
    }
    tokens = {name: identity.issue(subject) for name, subject in subjects.items()}
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-projects-") as scratch:
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
                if "access_administrator" not in profiles["admin"]["admin_roles"]:
                    _bootstrap_access_administrator(profiles["admin"]["actor_profile_id"], env)

                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_issue",
                    {
                        "body": {
                            "target_actor_profile_id": profiles["manager"]["actor_profile_id"],
                            "role": "project_manager",
                            "scope_type": "system",
                            "reason": "Authorize installed MCP project-shell proof",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )

                slug = f"mcp-project-shell-{run_id}"
                create = {
                    "body": {
                        "name": "Installed MCP project shell",
                        "slug": slug,
                        "description": "Project-shell projection and replay proof",
                    },
                    "idempotency_key": str(uuid4()),
                }
                created = await _mcp(
                    mcp_url, tokens["manager"], "workstream_projects_create", create
                )
                assert created["slug"] == slug
                assert created["status"] == "draft"

                _stop(mcp)
                mcp_log.close()
                mcp, restart_log = _restart_mcp(executable, scratch, mcp_env)
                await _ready(mcp_url + "/mcp", mcp)
                assert (
                    await _mcp(mcp_url, tokens["manager"], "workstream_projects_create", create)
                    == created
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_projects_create",
                    {**create, "body": {**create["body"], "name": "Changed replay"}},
                    status=409,
                    code="idempotency_mismatch",
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_projects_create",
                    {**create, "idempotency_key": str(uuid4())},
                    status=409,
                    code="project_slug_conflict",
                )
                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_projects_create",
                    {
                        "body": {"name": "Denied", "slug": f"denied-{run_id}"},
                        "idempotency_key": str(uuid4()),
                    },
                    status=403,
                    code="permission_not_granted",
                )

                assert (
                    await _mcp(
                        mcp_url,
                        tokens["manager"],
                        "workstream_projects_get",
                        {"project_id": created["id"]},
                    )
                    == created
                )
                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_projects_get",
                    {"project_id": created["id"]},
                    status=404,
                    code="project_authorization_resource_not_found",
                )

                grant_response = await direct.post(
                    f"/api/v1/projects/{created['id']}/role-grants",
                    headers={
                        "Authorization": f"Bearer {tokens['manager'].api}",
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "target_actor_profile_id": profiles["contributor"]["actor_profile_id"],
                        "role": "submitter",
                        "qualification": _qualification(),
                        "reason": "Public-API fixture for contributor projection proof",
                    },
                )
                assert grant_response.status_code == 201, grant_response.text
                grant = grant_response.json()
                contributor_view = await _mcp(
                    mcp_url,
                    tokens["contributor"],
                    "workstream_projects_get",
                    {"project_id": created["id"]},
                )
                assert contributor_view == {
                    "id": created["id"],
                    "name": created["name"],
                    "status": created["status"],
                }

                revoked = await direct.post(
                    f"/api/v1/projects/{created['id']}/role-grants/{grant['id']}/revoke",
                    headers={
                        "Authorization": f"Bearer {tokens['manager'].api}",
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={"reason": "End contributor projection proof"},
                )
                assert revoked.status_code == 200, revoked.text
                await _mcp(
                    mcp_url,
                    tokens["contributor"],
                    "workstream_projects_get",
                    {"project_id": created["id"]},
                    status=404,
                    code="project_authorization_resource_not_found",
                )
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            if not mcp_log.closed:
                mcp_log.close()
            if restart_log is not None:
                restart_log.close()
