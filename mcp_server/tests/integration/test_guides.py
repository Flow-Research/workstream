"""Installed MCP/public-API proof for draft guide metadata mutations."""

from __future__ import annotations

import os
import shutil
import tempfile
from uuid import uuid4

import httpx2 as httpx
import pytest
from oauth_fixture import IdentityFixture
from test_profile_flow import (
    _bootstrap_access_administrator,
    _ready,
    _start_processes,
    _stop,
    api_environment,
    find_free_port,
)
from test_projects import _mcp, _profile, _restart_mcp


def _guide_input(project_id: str, key: str) -> dict[str, object]:
    return {
        "project_id": project_id,
        "body": {
            "version": "v1",
            "change_summary": "Initial installed MCP guide",
            "task_examples": [
                {
                    "content": "Review a claim using the project guide.",
                }
            ],
            "documents": [
                {"label": "Guide", "media_type": "application/pdf"},
                {"label": "Rubric", "media_type": "text/markdown"},
            ],
        },
        "idempotency_key": key,
    }


@pytest.mark.asyncio
async def test_installed_mcp_preserves_guide_authority_declarations_and_replay(
    identity: IdentityFixture,
) -> None:
    env = api_environment()
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    run_id = uuid4().hex
    subjects = {
        "admin": "mcp-admin",
        "manager": f"mcp-guides-{run_id}-manager",
        "ordinary": f"mcp-guides-{run_id}-ordinary",
    }
    tokens = {name: identity.issue(subject) for name, subject in subjects.items()}
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-guides-") as scratch:
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
                            "reason": "Authorize installed MCP guide proof",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )
                project = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_projects_create",
                    {
                        "body": {
                            "name": "Installed MCP guide project",
                            "slug": f"mcp-guide-{run_id}",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )
                other_project = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_projects_create",
                    {
                        "body": {
                            "name": "Other installed MCP guide project",
                            "slug": f"mcp-guide-other-{run_id}",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )

                create = _guide_input(project["id"], str(uuid4()))
                guide = await _mcp(mcp_url, tokens["manager"], "workstream_guides_create", create)
                assert guide["project_id"] == project["id"]
                assert guide["status"] == "draft"
                assert guide["task_examples"] == [
                    {
                        "content": "Review a claim using the project guide.",
                        "title": None,
                        "labels": [],
                    }
                ]
                assert guide["setup"]["status"] == "awaiting_documents"
                assert [
                    (item["label"], item["media_type"], item["order"])
                    for item in guide["documents"]
                ] == [
                    ("Guide", "application/pdf", 0),
                    ("Rubric", "text/markdown", 1),
                ]

                _stop(mcp)
                mcp_log.close()
                mcp, restart_log = _restart_mcp(executable, scratch, mcp_env)
                await _ready(mcp_url + "/mcp", mcp)
                assert (
                    await _mcp(mcp_url, tokens["manager"], "workstream_guides_create", create)
                    == guide
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_guides_create",
                    {
                        **create,
                        "body": {**create["body"], "change_summary": "Changed replay"},
                    },
                    status=409,
                    code="idempotency_mismatch",
                )

                update = {
                    "project_id": project["id"],
                    "guide_id": guide["id"],
                    "body": {"change_summary": "Updated installed MCP guide"},
                    "idempotency_key": str(uuid4()),
                }
                updated = await _mcp(mcp_url, tokens["manager"], "workstream_guides_update", update)
                assert updated["change_summary"] == "Updated installed MCP guide"
                assert (
                    await _mcp(mcp_url, tokens["manager"], "workstream_guides_update", update)
                    == updated
                )
                cleared = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_guides_update",
                    {
                        **update,
                        "body": {"change_summary": None},
                        "idempotency_key": str(uuid4()),
                    },
                )
                assert cleared["change_summary"] is None

                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_guides_update",
                    {
                        **update,
                        "project_id": other_project["id"],
                        "idempotency_key": str(uuid4()),
                    },
                    status=404,
                    code="resource_not_found",
                )
                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_guides_create",
                    _guide_input(project["id"], str(uuid4())),
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
