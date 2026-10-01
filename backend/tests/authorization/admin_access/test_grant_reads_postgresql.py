"""Grant query disclosure follows actual system or exact-project authority."""

import json

import pytest

from tests.authorization.admin_access.read_support import read_path
from tests.authorization.admin_access.support import (
    AdminAccess,
    authority_snapshot,
    create_project,
    grant_body,
)


@pytest.mark.parametrize("surface", ["list", "history", "foreign", "profile", "link"])
async def test_project_auditor_reads_only_granted_project(
    admin_access: AdminAccess, surface: str
) -> None:
    access = admin_access
    auditor = await access.signed.actor("project-auditor")
    project = await create_project("Authorized project")
    foreign = await create_project("Foreign project")
    target_grant = await access.signed.grant(
        access.admin, access.target, role="project_manager", project_id=project
    )
    audit_grant = await access.signed.grant(
        access.admin, auditor, role="audit_authority", project_id=project
    )
    await access.signed.grant(
        access.admin, access.target, role="project_manager", project_id=foreign
    )
    path = "/api/v1/admin-role-grants"
    params = {"scope_type": "project", "scope_project_id": str(project)}
    if surface == "history":
        path = f"/api/v1/actors/{access.target.id}/admin-role-grants"
    elif surface == "foreign":
        params["scope_project_id"] = str(foreign)
    elif surface in {"profile", "link"}:
        path, params = read_path(access.target.id, surface), {}
    response = await access.signed.client.get(path, headers=auditor.headers, params=params)
    if surface in {"list", "history"}:
        assert response.status_code == 200, response.text
        expected = {target_grant, audit_grant} if surface == "list" else {target_grant}
        assert response.json()["total"] == len(expected)
        assert {r["grant_id"] for r in response.json()["items"]} == expected
        assert {r["scope_project_id"] for r in response.json()["items"]} == {str(project)}
        if surface == "history":
            assert response.json()["items"][0]["target_actor_profile_id"] == str(access.target.id)
    else:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == (
            "scope_not_authorized" if surface == "foreign" else "permission_not_granted"
        )


async def test_audit_authority_cannot_issue_grant(admin_access: AdminAccess) -> None:
    access = admin_access
    auditor = await access.signed.actor("read-only-auditor")
    project = await create_project("Audited project")
    await access.signed.grant(access.admin, auditor, role="audit_authority", project_id=project)
    before = await authority_snapshot()
    response = await access.signed.issue(auditor, grant_body(auditor.id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_not_granted"
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]


@pytest.mark.parametrize(
    "surface", ["permissions", "definitions", "list", "history", "profile", "link"]
)
async def test_system_auditor_has_exact_read_surface(
    admin_access: AdminAccess, surface: str
) -> None:
    access = admin_access
    auditor = await access.signed.actor("system-auditor")
    grant_id = await access.signed.grant(access.admin, auditor, role="audit_authority")
    paths = {
        "permissions": "/api/v1/authorization/permissions",
        "definitions": "/api/v1/authorization/admin-role-definitions",
        "list": "/api/v1/admin-role-grants",
        "history": f"/api/v1/actors/{auditor.id}/admin-role-grants",
        "profile": read_path(access.target.id, "profile"),
        "link": read_path(access.target.id, "link"),
    }
    params = {"scope_type": "system", "status": "all"} if surface in {"list", "history"} else {}
    response = await access.signed.client.get(
        paths[surface], headers=auditor.headers, params=params
    )
    assert response.status_code == 200, response.text
    body = response.json()
    if surface in {"permissions", "definitions"}:
        assert body["total"] == len(body["items"]) == (77 if surface == "permissions" else 5)
    elif surface in {"list", "history"}:
        expected = {grant_id, access.bootstrap_grant_id} if surface == "list" else {grant_id}
        assert body["total"] == len(expected)
        assert {r["grant_id"] for r in body["items"]} == expected
        assert {r["scope_project_id"] for r in body["items"]} == {None}
    else:
        assert body["actor_profile_id"] == str(access.target.id)


@pytest.mark.parametrize("scope", ["system", "project"])
async def test_admin_grant_list_returns_exact_scope_and_count(
    admin_access: AdminAccess, scope: str
) -> None:
    access = admin_access
    project = await create_project("Selected scope")
    system = await access.signed.grant(access.admin, access.target)
    auditor = await access.signed.actor("list-auditor")
    audit_grant = await access.signed.grant(access.admin, auditor, role="audit_authority")
    scoped = await access.signed.grant(
        access.admin, access.target, role="project_manager", project_id=project
    )
    params = {"scope_type": scope, "status": "all"}
    if scope == "project":
        params["scope_project_id"] = str(project)
    response = await access.signed.client.get(
        "/api/v1/admin-role-grants",
        headers=access.admin.headers,
        params=params,
    )
    assert response.status_code == 200
    expected = {access.bootstrap_grant_id, system, audit_grant} if scope == "system" else {scoped}
    assert response.json()["total"] == len(expected)
    assert {r["grant_id"] for r in response.json()["items"]} == expected
    assert {r["scope_project_id"] for r in response.json()["items"]} == {
        None if scope == "system" else str(project)
    }


async def test_admin_grant_history_has_bounded_payload(admin_access: AdminAccess) -> None:
    access = admin_access
    body = grant_body(access.target.id)
    issued = await access.signed.issue(access.admin, body)
    assert issued.status_code == 201
    response = await access.signed.client.get(
        f"/api/v1/actors/{access.target.id}/admin-role-grants",
        headers=access.admin.headers,
        params={"scope_type": "system", "status": "all"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    row = response.json()["items"][0]
    assert row["grant_id"] == issued.json()["resource_id"]
    assert row["target_actor_profile_id"] == str(access.target.id)
    assert row["grant_reason"] == body["reason"]
    serialized = json.dumps(response.json(), sort_keys=True)
    assert access.target.subject not in serialized
    assert access.target.token not in serialized


async def test_admin_grant_first_page_has_bounded_cursor(admin_access: AdminAccess) -> None:
    access = admin_access
    grant_id = await access.signed.grant(access.admin, access.target)
    params = {"scope_type": "system", "status": "all", "limit": 1}
    first = await access.signed.client.get(
        "/api/v1/admin-role-grants",
        headers=access.admin.headers,
        params=params,
    )
    assert first.status_code == 200
    assert first.json()["total"] == 2
    assert [r["grant_id"] for r in first.json()["items"]] == [access.bootstrap_grant_id]
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str) and cursor
    second = await access.signed.client.get(
        "/api/v1/admin-role-grants",
        headers=access.admin.headers,
        params=params | {"cursor": cursor},
    )
    assert second.status_code == 200
    assert [r["grant_id"] for r in second.json()["items"]] == [grant_id]
    assert second.json()["next_cursor"] is None


async def test_admin_grant_rejects_malformed_derivative_cursor(admin_access: AdminAccess) -> None:
    access = admin_access
    await access.signed.grant(access.admin, access.target)
    first = await access.signed.client.get(
        "/api/v1/admin-role-grants",
        headers=access.admin.headers,
        params={"scope_type": "system", "status": "all", "limit": 1},
    )
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str) and cursor
    before = await authority_snapshot()
    response = await access.signed.client.get(
        "/api/v1/admin-role-grants",
        headers=access.admin.headers,
        params={"scope_type": "system", "cursor": cursor + "$"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert await authority_snapshot() == before
