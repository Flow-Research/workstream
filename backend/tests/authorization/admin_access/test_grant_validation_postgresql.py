"""Each original malformed selector reaches the real API validation boundary."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile

from tests.authorization.admin_access.support import AdminAccess, authority_snapshot, grant_body


async def service_subject_state():
    """Observe provisioning outputs as well as the canonical authority tables."""
    state = await authority_snapshot()
    async with db_session.get_session_factory()() as session:
        for model in (ActorProfile, ActorIdentityLink):
            rows = await session.execute(select(model.__table__).order_by(model.id))
            state[model.__tablename__] = [dict(row) for row in rows.mappings()]
    return state


@pytest.mark.parametrize("subject", ["service\x00subject", "\x00", "é" * 101],
                         ids=["embedded_nul", "nul_only", "utf8_overflow"])
async def test_service_subject_rejection_preserves_state_and_key(
    admin_access: AdminAccess, subject: str,
) -> None:
    access = admin_access
    key = str(uuid4())
    headers = access.admin.headers | {"Idempotency-Key": key}
    payload = {"service_identity": "workstream.review.projection", "subject": subject,
               "reason": "é" * 250}
    before = await service_subject_state()
    rejected = await access.signed.client.post("/api/v1/service-actors", headers=headers, json=payload)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "invalid_request"
    assert rejected.json()["error"]["retryable"] is False
    assert await service_subject_state() == before

    payload["subject"] = "é" * 100
    recovered = await access.signed.client.post("/api/v1/service-actors", headers=headers, json=payload)
    assert recovered.status_code == 201, recovered.text
    after = await service_subject_state()
    actor_id = recovered.json()["actor_profile_id"]
    links = [row for row in after["actor_identity_links"] if row["actor_profile_id"] == actor_id]
    assert len(links) == 1 and links[0]["subject"] == payload["subject"]
    assert links[0]["status"] == "active" and links[0]["subject_kind"] == "service"
    profiles = [row for row in after["actor_profiles"] if row["id"] == actor_id]
    assert len(profiles) == 1 and profiles[0]["service_identity"] == payload["service_identity"]
    assert profiles[0]["actor_kind"] == "service" and profiles[0]["status"] == "active"
    records = [row for row in after["authority_idempotency_records"] if str(row["idempotency_key"]) == key]
    assert len(records) == 1 and records[0]["status"] == "committed"
    assert records[0]["operation"] == "service_actor.create"
    replay = await access.signed.client.post("/api/v1/service-actors", headers=headers, json=payload)
    assert replay.status_code == 201 and replay.json() == recovered.json()
    replayed = await service_subject_state()
    assert replayed["authority_idempotency_records"] == after["authority_idempotency_records"]
    assert [row for row in replayed["actor_profiles"] if row["id"] == actor_id] == profiles
    assert [row for row in replayed["actor_identity_links"] if row["actor_profile_id"] == actor_id] == links


@pytest.mark.parametrize("operation", ["issue", "revoke"])
@pytest.mark.parametrize("reason", ["bad\x00reason", "é" * 251], ids=["nul", "utf8_overflow"])
async def test_admin_reason_rejection_preserves_state_and_key(
    admin_access: AdminAccess, operation: str, reason: str,
) -> None:
    access = admin_access
    body = grant_body(access.target.id)
    grant_id = await access.signed.grant(access.admin, access.target) if operation == "revoke" else None
    key = str(uuid4())
    path = "/api/v1/admin-role-grants" + (f"/{grant_id}/revoke" if grant_id else "")
    before = await authority_snapshot()
    payload = {"reason": reason} if grant_id else body | {"reason": reason}
    headers = access.admin.headers | {"Idempotency-Key": key}
    rejected = await access.signed.client.post(path, headers=headers, json=payload)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "invalid_request"
    assert rejected.json()["error"]["retryable"] is False
    assert await authority_snapshot() == before

    valid_reason = "é" * 250
    payload["reason"] = valid_reason
    recovered = await access.signed.client.post(path, headers=headers, json=payload)
    assert recovered.status_code == (200 if grant_id else 201), recovered.text
    after = await authority_snapshot()
    stored = next(row for row in after["admin_role_grants"]
                  if str(row["id"]) == recovered.json()["resource_id"])
    assert stored["version"] == (2 if grant_id else 1)
    assert stored["status"] == ("revoked" if grant_id else "active")
    assert stored["revoked_reason" if grant_id else "grant_reason"] == valid_reason
    if grant_id:
        original = next(row for row in before["admin_role_grants"] if str(row["id"]) == grant_id)
        assert stored["grant_reason"] == original["grant_reason"]
    records = [row for row in after["authority_idempotency_records"] if str(row["idempotency_key"]) == key]
    assert len(records) == 1
    assert records[0]["status"] == "committed"
    assert records[0]["operation"] == f"admin_role_grant.{operation}"
    replay = await access.signed.client.post(path, headers=headers, json=payload)
    assert replay.status_code == recovered.status_code
    assert replay.json() == recovered.json()
    replayed = await authority_snapshot()
    for table in ("admin_role_grants", "authority_idempotency_records"):
        assert replayed[table] == after[table]


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("pending_status", 422, "invalid_request"),
        ("zero_limit", 422, "invalid_request"),
        ("excessive_limit", 422, "invalid_request"),
        ("malformed_actor", 422, "invalid_request"),
        ("unknown_role", 422, "invalid_request"),
        ("unknown_scope", 422, "invalid_request"),
        ("malformed_grant", 422, "invalid_request"),
        ("operator_project", 422, "invalid_role_scope"),
        ("oversized_utf8_reason", 422, "invalid_request"),
        ("absent_project", 404, "resource_not_found"),
        ("system_with_project", 400, "invalid_request"),
        ("missing_project", 400, "invalid_request"),
        ("invalid_cursor", 400, "invalid_request"),
    ],
)
async def test_invalid_admin_request_is_bounded(
    admin_access: AdminAccess,
    case: str,
    status: int,
    code: str,
) -> None:
    access = admin_access
    path = "/api/v1/admin-role-grants"
    params = {"scope_type": "system"}
    body = grant_body(access.target.id)
    method = "get"
    if case in {"pending_status", "zero_limit", "excessive_limit"}:
        params |= {
            "pending_status": {"status": "pending"},
            "zero_limit": {"limit": 0},
            "excessive_limit": {"limit": 101},
        }[case]
    elif case == "malformed_actor":
        path = "/api/v1/actors/not-a-uuid/admin-role-grants"
    elif case == "system_with_project":
        params["scope_project_id"] = str(uuid4())
    elif case == "missing_project":
        params["scope_type"] = "project"
    elif case == "invalid_cursor":
        params["cursor"] = "not-a-cursor"
    else:
        method = "post"
        if case == "malformed_grant":
            path, body = (
                "/api/v1/admin-role-grants/not-a-uuid/revoke",
                {"reason": "Invalid selector"},
            )
        elif case == "unknown_role":
            body["role"] = "administrator"
        elif case == "unknown_scope":
            body |= {"role": "project_manager", "scope_type": "organization"}
        elif case == "oversized_utf8_reason":
            body["reason"] = "é" * 251
        else:
            assert case in {"operator_project", "absent_project"}
            body |= {
                "role": "operator" if case == "operator_project" else "project_manager",
                "scope_type": "project",
                "scope_project_id": str(uuid4()),
            }
    before = await authority_snapshot()
    if method == "get":
        response = await access.signed.client.get(path, headers=access.admin.headers, params=params)
    else:
        response = await access.signed.client.post(
            path,
            headers=access.admin.headers | {"Idempotency-Key": str(uuid4())},
            json=body,
        )
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]
