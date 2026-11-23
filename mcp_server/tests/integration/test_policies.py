"""Installed MCP/public-API proof for draft review and revision policies."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from integration.oauth_fixture import IdentityFixture
from test_guides import _guide_input
from test_profile_flow import (
    _bootstrap_access_administrator,
    _ready,
    _start_processes,
    _stop,
    api_environment,
    find_free_port,
)
from test_projects import _mcp, _profile, _restart_mcp


def _selector(policy: dict[str, Any]) -> str:
    return (
        f'"{policy["id"]}.{policy["policy_generation"]}.'
        f'{policy["policy_hash"].removeprefix("sha256:")}"'
    )


def _review_arguments(project_id: str, guide_id: str, key: str, selector: str) -> dict:
    return {
        "project_id": project_id,
        "guide_id": guide_id,
        "body": {
            "human_review_required": False,
            "review_preference_window_seconds": 3600,
            "review_lease_duration_seconds": 1800,
        },
        "idempotency_key": key,
        "if_match": selector,
    }


@pytest.mark.asyncio
async def test_installed_mcp_preserves_policy_lineage_authority_and_replay(
    identity: IdentityFixture,
) -> None:
    env = api_environment()
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    run_id = uuid4().hex
    subjects = {
        "admin": "mcp-admin",
        "manager": f"mcp-policies-{run_id}-manager",
        "ordinary": f"mcp-policies-{run_id}-ordinary",
    }
    tokens = {name: identity.issue(subject) for name, subject in subjects.items()}
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-policies-") as scratch:
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
                            "reason": "Authorize installed MCP policy proof",
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
                            "name": "Installed MCP policy project",
                            "slug": f"mcp-policy-{run_id}",
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
                            "name": "Other installed MCP policy project",
                            "slug": f"mcp-policy-other-{run_id}",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )
                guide = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_guides_create",
                    _guide_input(project["id"], str(uuid4())),
                )

                review_input = _review_arguments(
                    project["id"], guide["id"], str(uuid4()), '"no-current-policy"'
                )
                review = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_review_policy_put",
                    review_input,
                )
                assert review["policy_generation"] == 1
                assert review["supersedes_policy_id"] is None
                assert review["human_review_required"] is False

                revision_input = {
                    "project_id": project["id"],
                    "guide_id": guide["id"],
                    "body": {"max_revision_rounds": 4, "revision_deadline_hours": 72},
                    "idempotency_key": str(uuid4()),
                    "if_match": '"no-current-policy"',
                }
                revision = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_revision_policy_put",
                    revision_input,
                )
                assert revision["policy_generation"] == 1
                assert revision["supersedes_policy_id"] is None

                _stop(mcp)
                mcp_log.close()
                mcp, restart_log = _restart_mcp(executable, scratch, mcp_env)
                await _ready(mcp_url + "/mcp", mcp)
                assert (
                    await _mcp(
                        mcp_url,
                        tokens["manager"],
                        "workstream_review_policy_put",
                        review_input,
                    )
                    == review
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_review_policy_put",
                    {
                        **review_input,
                        "body": {
                            **review_input["body"],
                            "human_review_required": True,
                        },
                    },
                    status=409,
                    code="idempotency_mismatch",
                )

                inherited_input = {
                    **review_input,
                    "body": {
                        "review_preference_window_seconds": 4200,
                        "review_lease_duration_seconds": 2100,
                    },
                    "idempotency_key": str(uuid4()),
                    "if_match": _selector(review),
                }
                inherited = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_review_policy_put",
                    inherited_input,
                )
                assert inherited["policy_generation"] == 2
                assert inherited["supersedes_policy_id"] == review["id"]
                assert inherited["human_review_required"] is False

                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_review_policy_put",
                    {
                        **inherited_input,
                        "idempotency_key": str(uuid4()),
                        "if_match": _selector(review),
                    },
                    status=409,
                    code="policy_precondition_failed",
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_review_policy_put",
                    {
                        **inherited_input,
                        "idempotency_key": str(uuid4()),
                        "if_match": '"malformed"',
                    },
                    status=409,
                    code="policy_precondition_invalid",
                )
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_review_policy_put",
                    {
                        **inherited_input,
                        "project_id": other_project["id"],
                        "idempotency_key": str(uuid4()),
                        "if_match": _selector(inherited),
                    },
                    status=404,
                    code="resource_not_found",
                )
                await _mcp(
                    mcp_url,
                    tokens["ordinary"],
                    "workstream_revision_policy_put",
                    {
                        **revision_input,
                        "idempotency_key": str(uuid4()),
                        "if_match": _selector(revision),
                    },
                    status=403,
                    code="permission_not_granted",
                )

                await _mcp(
                    mcp_url,
                    tokens["admin"],
                    "workstream_admin_grants_issue",
                    {
                        "body": {
                            "target_actor_profile_id": profiles["manager"]["actor_profile_id"],
                            "role": "finance_authority",
                            "scope_type": "project",
                            "scope_project_id": project["id"],
                            "reason": "Authorize contribution policy MCP proof",
                        },
                        "idempotency_key": str(uuid4()),
                    },
                )
                contribution_create = {
                    "project_id": project["id"],
                    "body": {"name": "Installed MCP contribution policy"},
                    "idempotency_key": str(uuid4()),
                }
                contribution_policy = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policy_create",
                    contribution_create,
                )
                policy_id = contribution_policy["contribution_policy_id"]
                version_id = contribution_policy["contribution_policy_version_id"]
                assert await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policy_current_get",
                    {"project_id": project["id"]},
                ) == {
                    "project_id": project["id"],
                    "contribution_policy_id": policy_id,
                    "current_published_version_id": None,
                    "open_draft_version_id": version_id,
                }
                listed = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policies_list",
                    {"project_id": project["id"], "limit": 10},
                )
                assert [item["contribution_policy_version_id"] for item in listed["items"]] == [
                    version_id
                ]
                rules = {
                    "rules": [
                        {
                            "contribution_type": contribution_type,
                            "compensation_mode": "unpaid",
                            "definitions": [],
                        }
                        for contribution_type in (
                            "accepted_submission",
                            "completed_review",
                        )
                    ]
                }
                base = {
                    "project_id": project["id"],
                    "policy_id": policy_id,
                    "version_id": version_id,
                }
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policy_update",
                    {**base, "body": rules, "idempotency_key": str(uuid4())},
                )
                published = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policy_publish",
                    {**base, "body": {}, "idempotency_key": str(uuid4())},
                )
                assert published["to_version_status"] == "published"
                exact = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policy_get",
                    {**base},
                )
                assert exact["contribution_policy_version_id"] == version_id
                retired = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_contribution_policy_retire",
                    {**base, "body": {}, "idempotency_key": str(uuid4())},
                )
                assert retired["to_version_status"] == "retired"

                actor_projects = await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_actor_projects_list",
                    {"limit": 100},
                )
                assert project["id"] in {item["project_id"] for item in actor_projects["items"]}
                assert (
                    await _mcp(
                        mcp_url,
                        tokens["manager"],
                        "workstream_actor_submissions_list",
                        {},
                    )
                )["items"] == []
                await _mcp(
                    mcp_url,
                    tokens["manager"],
                    "workstream_actor_submissions_list",
                    {"project_id": project["id"]},
                    status=404,
                    code="project_authorization_resource_not_found",
                )
                assert (
                    await _mcp(
                        mcp_url,
                        tokens["manager"],
                        "workstream_project_submissions_list",
                        {"project_id": project["id"]},
                    )
                )["items"] == []
                assert (
                    await _mcp(
                        mcp_url,
                        tokens["manager"],
                        "workstream_contributions_list",
                        {"project_id": project["id"]},
                    )
                )["items"] == []
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            if not mcp_log.closed:
                mcp_log.close()
            if restart_log is not None:
                restart_log.close()
