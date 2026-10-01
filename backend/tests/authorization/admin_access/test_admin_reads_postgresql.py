"""Administrative read projections, provenance and observations through real routes."""

from datetime import datetime
import json
import logging
from uuid import UUID, uuid4

import pytest

from tests.authorization.admin_access.read_support import (
    LINK_FIELDS,
    PROFILE_FIELDS,
    READ_ACTIONS,
    read_path,
    seed_read_target,
)
from tests.authorization.admin_access.support import (
    AdminAccess,
    actor_observation,
    authority_events,
    authority_snapshot,
    concealed_error,
    seed_old_observation,
)


@pytest.mark.parametrize(
    "kind,surface",
    [
        ("human", "profile"),
        ("human", "link"),
        ("service", "profile"),
        ("service", "link"),
        ("suspended", "profile"),
        ("revoked_link", "link"),
    ],
)
async def test_admin_read_projects_only_public_fields(
    admin_access: AdminAccess,
    kind: str,
    surface: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = await seed_read_target(admin_access, kind)
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="app")
    response = await admin_access.signed.client.get(
        read_path(target.id, surface), headers=admin_access.admin.headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == (PROFILE_FIELDS if surface == "profile" else LINK_FIELDS)
    assert body["actor_profile_id"] == str(target.id)
    if surface == "profile":
        assert body["actor_kind"] == ("service" if kind == "service" else "human")
        assert body["service_identity"] == (
            "workstream.artifact.verifier" if kind == "service" else None
        )
    if kind == "service":
        assert body["last_seen_at" if surface == "profile" else "last_verified_at"] is None
    assert (
        body["status"]
        == {
            "human": "active",
            "service": "active",
            "suspended": "suspended",
            "revoked_link": "revoked",
        }[kind]
    )
    serialized = json.dumps(body, sort_keys=True)
    for value in target.private_values:
        assert value not in serialized
        assert value not in caplog.text


@pytest.mark.parametrize("surface", ["profile", "link"])
async def test_admin_read_touches_caller_not_target(
    admin_access: AdminAccess, surface: str
) -> None:
    access = admin_access
    caller_before = await seed_old_observation(access.admin.id)
    target_before = await seed_old_observation(access.target.id)
    response = await access.signed.client.get(
        read_path(access.target.id, surface), headers=access.admin.headers
    )
    assert response.status_code == 200, response.text
    assert await actor_observation(access.target.id) == target_before
    caller_after = await actor_observation(access.admin.id)
    assert caller_after.last_seen_at > caller_before.last_seen_at
    assert caller_after.last_verified_at > caller_before.last_verified_at


@pytest.mark.parametrize("surface", ["profile", "link"])
async def test_admin_read_records_exact_authorization_provenance(
    admin_access: AdminAccess,
    surface: str,
) -> None:
    access = admin_access
    response = await access.signed.client.get(
        read_path(access.target.id, surface), headers=access.admin.headers
    )
    assert response.status_code == 200, response.text
    action, permission = READ_ACTIONS[surface]
    events = await authority_events(action=action, event_type="SensitiveAuthorizationAllowed")
    assert len(events) == 1
    event = events[0]
    assert event.permission_id == permission
    assert event.actor_id == str(access.admin.id)
    assert event.resource_id == str(access.target.id)
    assert event.target_actor_ref == str(access.target.id)
    assert event.target_ref_id == str(access.target.id)
    assert event.matched_grant_id == access.bootstrap_grant_id
    assert event.project_id is None
    assert event.after_facts == {"allowed": True}
    assert UUID(str(event.request_id)) == UUID(response.headers["x-request-id"])
    assert UUID(str(event.correlation_id)) == UUID(response.headers["x-correlation-id"])


async def test_self_admin_profile_read_returns_committed_observation(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    before = await seed_old_observation(access.admin.id)
    authority_before = await authority_snapshot()
    response = await access.signed.client.get(
        read_path(access.admin.id, "profile"), headers=access.admin.headers
    )
    assert response.status_code == 200, response.text
    after = await actor_observation(access.admin.id)
    assert after.updated_at > before.updated_at
    assert after.last_seen_at > before.last_seen_at
    assert after.last_verified_at > before.last_verified_at
    assert datetime.fromisoformat(response.json()["updated_at"]) == after.updated_at
    assert datetime.fromisoformat(response.json()["last_seen_at"]) == after.last_seen_at
    authority_after = await authority_snapshot()
    assert authority_after["admin_role_grants"] == authority_before["admin_role_grants"]
    assert (
        authority_after["authority_idempotency_records"]
        == authority_before["authority_idempotency_records"]
    )
    assert len(authority_after["audit_events"]) == len(authority_before["audit_events"]) + 1


async def test_self_admin_link_read_returns_committed_observation(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    before = await seed_old_observation(access.admin.id)
    authority_before = await authority_snapshot()
    response = await access.signed.client.get(
        read_path(access.admin.id, "link"), headers=access.admin.headers
    )
    assert response.status_code == 200, response.text
    after = await actor_observation(access.admin.id)
    assert after.updated_at > before.updated_at
    assert after.last_seen_at > before.last_seen_at
    assert after.last_verified_at > before.last_verified_at
    assert datetime.fromisoformat(response.json()["last_verified_at"]) == after.last_verified_at
    authority_after = await authority_snapshot()
    assert authority_after["admin_role_grants"] == authority_before["admin_role_grants"]
    assert (
        authority_after["authority_idempotency_records"]
        == authority_before["authority_idempotency_records"]
    )
    assert len(authority_after["audit_events"]) == len(authority_before["audit_events"]) + 1


async def test_missing_admin_target_has_concealed_response_and_no_success_effect(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    observed = await actor_observation(access.admin.id)
    before = await authority_snapshot()
    absent = uuid4()
    profile = await access.signed.client.get(
        read_path(absent, "profile"), headers=access.admin.headers
    )
    link = await access.signed.client.get(read_path(absent, "link"), headers=access.admin.headers)
    assert profile.status_code == link.status_code == 404
    assert concealed_error(profile) == concealed_error(link)
    assert profile.json()["error"]["code"] == "actor_resource_not_found"
    assert await actor_observation(access.admin.id) == observed
    assert await authority_snapshot() == before


@pytest.mark.parametrize("surface,total", [("permissions", 77), ("admin-role-definitions", 5)])
async def test_admin_catalogue_read_returns_public_definitions(
    admin_access: AdminAccess,
    surface: str,
    total: int,
) -> None:
    access = admin_access
    before = await seed_old_observation(access.admin.id)
    response = await access.signed.client.get(
        f"/api/v1/authorization/{surface}", headers=access.admin.headers
    )
    assert response.status_code == 200, response.text
    assert (response.json()["total"], len(response.json()["items"])) == (total, total)
    if surface == "admin-role-definitions":
        assert [item["role"] for item in response.json()["items"]] == [
            "access_administrator",
            "operator",
            "project_manager",
            "finance_authority",
            "audit_authority",
        ]
    after = await actor_observation(access.admin.id)
    assert after.last_seen_at > before.last_seen_at
    assert after.last_verified_at > before.last_verified_at


async def test_admin_self_patch_commits_requested_observation(admin_access: AdminAccess) -> None:
    access = admin_access
    before = await seed_old_observation(access.admin.id)
    response = await access.signed.client.patch(
        "/api/v1/actors/me",
        headers=access.admin.headers,
        json={"display_name": "Administrator observation"},
    )
    assert response.status_code == 200, response.text
    after = await actor_observation(access.admin.id)
    assert after.display_name == "Administrator observation"
    assert after.last_seen_at > before.last_seen_at
    assert after.last_verified_at > before.last_verified_at
