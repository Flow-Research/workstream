"""Installed MCP/public-API proof for project participation."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from integration.oauth_fixture import IdentityFixture
from test_profile_flow import (
    _bootstrap_access_administrator,
    _call,
    _ready,
    _start_processes,
    _stop,
    api_environment,
    find_free_port,
)
from test_projects import _mcp, _profile, _qualification


def _issue(project_id: str, actor_id: str, role: str, key: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "body": {
            "target_actor_profile_id": actor_id,
            "role": role,
            "qualification": _qualification(),
            "reason": f"Authorize {role} participation",
        },
        "idempotency_key": key,
    }


@pytest.mark.asyncio
async def test_installed_mcp_preserves_project_participation_authority_and_replay(
    identity: IdentityFixture,
) -> None:
    env = api_environment()
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    run_id = uuid4().hex
    subjects = {
        "admin": "mcp-admin",
        "manager": f"mcp-grants-{run_id}-manager",
        "submitter": f"mcp-grants-{run_id}-submitter",
        "reviewer": f"mcp-grants-{run_id}-reviewer",
        "concurrent": f"mcp-grants-{run_id}-concurrent",
        "ordinary": f"mcp-grants-{run_id}-ordinary",
    }
    tokens = {name: identity.issue(subject) for name, subject in subjects.items()}
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-project-grants-") as scratch:
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
                            "reason": "Authorize project participation proof",
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
                            "name": "MCP participation project",
                            "slug": f"mcp-participation-{run_id}",
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
                            "name": "Other MCP project",
                            "slug": f"mcp-participation-other-{run_id}",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )

                first_page = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contributor_candidates_list",
                    {"project_id": project["id"], "limit": 1},
                )
                assert len(first_page["items"]) == 1
                assert first_page["next_cursor"]
                second_page = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contributor_candidates_list",
                    {
                        "project_id": project["id"],
                        "limit": 1,
                        "cursor": first_page["next_cursor"],
                    },
                )
                assert len(second_page["items"]) == 1
                assert second_page["items"][0] != first_page["items"][0]

                submitter_key = str(uuid4())
                submitter_input = _issue(
                    project["id"],
                    profiles["submitter"]["actor_profile_id"],
                    "submitter",
                    submitter_key,
                )
                submitter_grant = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_issue",
                    submitter_input,
                )
                assert submitter_grant == await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_issue",
                    submitter_input,
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_issue",
                    {
                        **submitter_input,
                        "body": {**submitter_input["body"], "reason": "Changed replay"},
                    },
                    status=409,
                    code="idempotency_mismatch",
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_issue",
                    {**submitter_input, "idempotency_key": str(uuid4())},
                    status=409,
                    code="project_role_grant_exists",
                )

                reviewer_grant = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_issue",
                    _issue(
                        project["id"],
                        profiles["reviewer"]["actor_profile_id"],
                        "reviewer",
                        str(uuid4()),
                    ),
                )
                page = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_list",
                    {"project_id": project["id"], "role": "reviewer", "limit": 1},
                )
                assert [item["id"] for item in page["items"]] == [reviewer_grant["id"]]
                observed = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_get",
                    {"project_id": project["id"], "grant_id": submitter_grant["id"]},
                )
                assert observed["qualification_snapshot"]["requested_role"] == "submitter"
                assert observed["qualification_snapshot"]["skills_snapshot"] == _unavailable()
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_get",
                    {"project_id": other_project["id"], "grant_id": submitter_grant["id"]},
                    status=404,
                    code="resource_not_found",
                )

                concurrent_inputs = [
                    _issue(
                        project["id"],
                        profiles["concurrent"]["actor_profile_id"],
                        "submitter",
                        str(uuid4()),
                    )
                    for _ in range(2)
                ]
                concurrent_results = await asyncio.gather(
                    *(
                        _call(
                            mcp_url,
                            tokens["manager"],
                            name="workstream_project_grants_issue",
                            arguments=value,
                        )
                        for value in concurrent_inputs
                    )
                )
                assert sorted(failed for _, failed in concurrent_results) == [False, True]
                failure = next(body for body, failed in concurrent_results if failed)
                assert failure["status"] == 409
                assert failure["code"] == "project_role_grant_exists"

                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_project_grants_issue",
                    _issue(
                        project["id"],
                        profiles["ordinary"]["actor_profile_id"],
                        "submitter",
                        str(uuid4()),
                    ),
                    status=404,
                    code="resource_not_found",
                )

                revoke_input = {
                    "project_id": project["id"],
                    "grant_id": submitter_grant["id"],
                    "body": {"reason": "End installed participation proof"},
                    "idempotency_key": str(uuid4()),
                }
                revoked = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_revoke",
                    revoke_input,
                )
                assert revoked["status"] == "revoked"
                assert revoked == await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_project_grants_revoke",
                    revoke_input,
                )
                await _mcp(
                    mcp_url,
                    tokens["submitter"],
                    "workstream_projects_get",
                    {"project_id": project["id"]},
                    status=404,
                    code="project_authorization_resource_not_found",
                )
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            mcp_log.close()


def _unavailable() -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    }
