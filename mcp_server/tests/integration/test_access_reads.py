"""Installed MCP/public-API parity for the six administrative read projections.

Requires the installed wheel, backend dependencies, and an already migrated isolated
PostgreSQL database configured as for test_profile_flow. No infrastructure is started
at collection time. The test starts only its API and installed adapter processes.

Run on a fresh database, or after test_profile_flow on the same database: its stable
``mcp-admin`` subject may already own the one-time bootstrap grant. Do not run these
stateful journeys concurrently or run profile_flow's bootstrap after this test on
the same database. All other subjects/projects are unique to this run. Authority is
created through public HTTP mutations, except the documented bootstrap CLI helper;
there is no SQL setup, backend model import, or authority teardown/reset.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from test_profile_flow import (
    _admin_transition,
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

_PATHS = {
    "workstream_permissions_list": "/api/v1/authorization/permissions",
    "workstream_admin_roles_list": "/api/v1/authorization/admin-role-definitions",
    "workstream_admin_grants_list": "/api/v1/admin-role-grants",
    "workstream_actor_admin_grants_list": "/api/v1/actors/{actor_profile_id}/admin-role-grants",
    "workstream_actor_get": "/api/v1/actors/{actor_profile_id}",
    "workstream_actor_identity_link_get": "/api/v1/actors/{actor_profile_id}/identity-links",
}
_PROFILE_FIELDS = {
    "actor_profile_id",
    "actor_kind",
    "status",
    "provisioning_method",
    "service_identity",
    "display_name",
    "created_at",
    "updated_at",
    "last_seen_at",
    "suspended_at",
    "reactivated_at",
    "deactivated_at",
}
_LINK_FIELDS = {
    "identity_link_id",
    "actor_profile_id",
    "subject_kind",
    "status",
    "linked_at",
    "last_verified_at",
    "revoked_at",
    "reactivated_at",
}


async def _parity(
    direct: httpx.AsyncClient,
    mcp_url: str,
    token: str,
    name: str,
    arguments: dict[str, Any],
    *,
    private_values: tuple[str, ...],
    status: int = 200,
    code: str | None = None,
) -> dict[str, Any]:
    path = _PATHS[name].format(**arguments)
    query = {key: value for key, value in arguments.items() if key != "actor_profile_id"}
    response = await direct.get(path, params=query, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status, (name, response.status_code, response.text)
    body, failed = await _call(mcp_url, token, name=name, arguments=arguments)
    assert failed is (status != 200), (name, body)
    if status == 200:
        # Targets never act during paired reads, so observation timestamps also match.
        assert body == response.json(), name
    else:
        assert body["status"] == status
        assert body["code"] == response.json()["error"]["code"] == code
        assert not {"items", "actor_profile_id", "identity_link_id"}.intersection(body)
    serialized = json.dumps(body, sort_keys=True)
    for value in private_values:
        assert value not in serialized, f"{name} disclosed a private fixture value"
    assert '"contact_email"' not in serialized
    assert '"subject"' not in serialized
    assert '"issuer"' not in serialized
    if status == 200 and name == "workstream_actor_get":
        assert set(body) == _PROFILE_FIELDS
        assert body["actor_profile_id"] == arguments["actor_profile_id"]
    if status == 200 and name == "workstream_actor_identity_link_get":
        assert set(body) == _LINK_FIELDS
        assert body["actor_profile_id"] == arguments["actor_profile_id"]
    return body


async def _grant(
    direct: httpx.AsyncClient,
    admin_token: str,
    actor_id: str,
    role: str,
    project_id: str | None = None,
) -> str:
    payload = {
        "target_actor_profile_id": actor_id,
        "role": role,
        "scope_type": "project" if project_id else "system",
        "reason": "Installed MCP access-read integration fixture",
    }
    if project_id is not None:
        payload["scope_project_id"] = project_id
    response = await direct.post(
        "/api/v1/admin-role-grants",
        headers={"Authorization": f"Bearer {admin_token}", "Idempotency-Key": str(uuid4())},
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()["resource_id"]


async def _exercise_access_reads(
    direct: httpx.AsyncClient, mcp_url: str, env: dict[str, str]
) -> None:
    issuer, audience, secret = flow_settings(env)
    run_id = uuid4().hex
    subjects = {
        name: f"mcp-access-{run_id}-{name}"
        for name in ("auditor", "ordinary", "operator", "manager", "project-auditor", "target")
    }
    subjects["admin"] = "mcp-admin"
    tokens = {
        name: issue_flow_token(subject, [], issuer=issuer, audience=audience, secret=secret)
        for name, subject in subjects.items()
    }
    profiles: dict[str, dict[str, Any]] = {}
    for name, token in tokens.items():
        response = await direct.get(
            "/api/v1/actors/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, response.text
        profiles[name] = response.json()
    ids = {name: profile["actor_profile_id"] for name, profile in profiles.items()}
    assert len(set(ids.values())) == len(ids)
    if "access_administrator" not in profiles["admin"]["admin_roles"]:
        _bootstrap_access_administrator(ids["admin"], env)
    admin = tokens["admin"]
    audit_grant = await _grant(direct, admin, ids["auditor"], "audit_authority")
    await _grant(direct, admin, ids["operator"], "operator")
    await _grant(direct, admin, ids["manager"], "project_manager")
    await _grant(direct, admin, ids["target"], "operator")
    await _grant(direct, admin, ids["target"], "finance_authority")

    contact = f"private-{run_id}@example.com"
    patched = await direct.patch(
        "/api/v1/actors/me",
        headers={"Authorization": f"Bearer {tokens['target']}"},
        json={"display_name": "Access read target", "contact_email": contact},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["contact_email"] == contact
    private_values = (contact, issuer, *subjects.values(), *tokens.values())

    reads: dict[str, dict[str, Any]] = {
        "workstream_permissions_list": {},
        "workstream_admin_roles_list": {},
        "workstream_admin_grants_list": {"scope_type": "system"},
        "workstream_actor_admin_grants_list": {
            "actor_profile_id": ids["target"],
            "scope_type": "system",
        },
        "workstream_actor_get": {"actor_profile_id": ids["target"]},
        "workstream_actor_identity_link_get": {"actor_profile_id": ids["target"]},
    }
    for caller in ("admin", "auditor", "ordinary", "operator"):
        allowed = caller in {"admin", "auditor"}
        for name, arguments in reads.items():
            body = await _parity(
                direct,
                mcp_url,
                tokens[caller],
                name,
                arguments,
                private_values=private_values,
                status=200 if allowed else 403,
                code=None if allowed else "permission_not_granted",
            )
            if allowed and "items" in body:
                assert body["items"] and body["total"] >= len(body["items"])
            if allowed and name == "workstream_actor_get":
                assert body["display_name"] == "Access read target"

    for name in ("workstream_actor_get", "workstream_actor_identity_link_get"):
        await _parity(
            direct,
            mcp_url,
            admin,
            name,
            {"actor_profile_id": str(uuid4())},
            private_values=private_values,
            status=404,
            code="actor_resource_not_found",
        )

    projects: list[str] = []
    for suffix in ("selected", "foreign"):
        response = await direct.post(
            "/api/v1/projects",
            headers={
                "Authorization": f"Bearer {tokens['manager']}",
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "name": f"MCP access {suffix}",
                "slug": f"mcp-access-{run_id}-{suffix}",
                "description": "Public API fixture for installed administrative read parity",
            },
        )
        assert response.status_code == 201, response.text
        projects.append(response.json()["id"])
    selected, foreign = projects
    target_grants = {
        await _grant(direct, admin, ids["target"], role, selected)
        for role in ("project_manager", "finance_authority")
    }
    scoped_audit_grant = await _grant(
        direct, admin, ids["project-auditor"], "audit_authority", selected
    )
    foreign_grant = await _grant(direct, admin, ids["target"], "project_manager", foreign)
    scoped = tokens["project-auditor"]
    first_cursors: dict[str, str] = {}
    grant_reads = ("workstream_admin_grants_list", "workstream_actor_admin_grants_list")
    for name in grant_reads:
        arguments = {
            **reads[name],
            "scope_type": "project",
            "scope_project_id": selected,
            "status": "all",
            "limit": 1,
        }
        expected = target_grants | ({scoped_audit_grant} if name == grant_reads[0] else set())
        seen: list[str] = []
        cursors: set[str] = set()
        for page_number in range(len(expected)):
            page = await _parity(
                direct, mcp_url, scoped, name, arguments, private_values=private_values
            )
            assert page["total"] == len(expected)
            assert len(page["items"]) == 1
            row = page["items"][0]
            assert row["scope_type"] == "project" and row["scope_project_id"] == selected
            assert row["grant_id"] not in seen and row["grant_id"] != foreign_grant
            seen.append(row["grant_id"])
            cursor = page["next_cursor"]
            if page_number == len(expected) - 1:
                assert cursor is None
                break
            assert isinstance(cursor, str) and 0 < len(cursor) <= 512
            assert cursor not in cursors
            cursors.add(cursor)
            first_cursors.setdefault(name, cursor)
            # Pass the returned token unchanged; never decode or reconstruct it.
            arguments = {**arguments, "cursor": cursor}
        assert set(seen) == expected

        await _parity(
            direct,
            mcp_url,
            scoped,
            name,
            {**arguments, "scope_project_id": foreign, "cursor": first_cursors[name]},
            private_values=private_values,
            status=403,
            code="scope_not_authorized",
        )
        await _parity(
            direct,
            mcp_url,
            scoped,
            name,
            {**reads[name], "cursor": first_cursors[name]},
            private_values=private_values,
            status=403,
            code="permission_not_granted",
        )
        await _parity(
            direct,
            mcp_url,
            admin,
            name,
            {**arguments, "cursor": "malformed$cursor"},
            private_values=private_values,
            status=400,
            code="invalid_request",
        )

    for name in ("workstream_actor_get", "workstream_actor_identity_link_get"):
        await _parity(
            direct,
            mcp_url,
            scoped,
            name,
            reads[name],
            private_values=private_values,
            status=403,
            code="permission_not_granted",
        )

    revoked_target_grant = sorted(target_grants)[0]
    await _admin_transition(
        direct, token=admin, path=f"/api/v1/admin-role-grants/{revoked_target_grant}/revoke"
    )
    for name in grant_reads:
        all_ids = target_grants | ({scoped_audit_grant} if name == grant_reads[0] else set())
        for grant_status, expected in (
            (None, all_ids - {revoked_target_grant}),
            ("active", all_ids - {revoked_target_grant}),
            ("revoked", {revoked_target_grant}),
            ("all", all_ids),
        ):
            arguments = {
                **reads[name],
                "scope_type": "project",
                "scope_project_id": selected,
                "limit": 100,
            }
            if grant_status is not None:
                arguments["status"] = grant_status
            page = await _parity(
                direct, mcp_url, scoped, name, arguments, private_values=private_values
            )
            assert {row["grant_id"] for row in page["items"]} == expected
            assert page["total"] == len(expected) and page["next_cursor"] is None
            if grant_status in {None, "active", "revoked"}:
                assert {row["status"] for row in page["items"]} == {grant_status or "active"}

    # The same adapter process and caller bearer must observe current stored authority.
    await _admin_transition(
        direct, token=admin, path=f"/api/v1/admin-role-grants/{audit_grant}/revoke"
    )
    for name, arguments in reads.items():
        await _parity(
            direct,
            mcp_url,
            tokens["auditor"],
            name,
            arguments,
            private_values=private_values,
            status=403,
            code="permission_not_granted",
        )
    await _admin_transition(
        direct, token=admin, path=f"/api/v1/admin-role-grants/{scoped_audit_grant}/revoke"
    )
    for name in grant_reads:
        await _parity(
            direct,
            mcp_url,
            scoped,
            name,
            {
                **reads[name],
                "scope_type": "project",
                "scope_project_id": selected,
                "status": "all",
                "limit": 1,
                "cursor": first_cursors[name],
            },
            private_values=private_values,
            status=403,
            code="permission_not_granted",
        )


@pytest.mark.asyncio
async def test_installed_mcp_preserves_access_read_parity() -> None:
    env = api_environment()
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"
    api_port, mcp_port = find_free_port(), find_free_port()
    while api_port == mcp_port:
        mcp_port = find_free_port()
    api_url, mcp_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"
    with tempfile.TemporaryDirectory(prefix="workstream-mcp-access-") as scratch:
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
        try:
            await _ready(api_url + "/api/v1/health", api)
            await _ready(mcp_url + "/mcp", mcp)
            async with httpx.AsyncClient(base_url=api_url, trust_env=False, timeout=20) as direct:
                await _exercise_access_reads(direct, mcp_url, env)
        finally:
            _stop(mcp)
            _stop(api)
            api_log.close()
            mcp_log.close()
