from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.audit.schemas import AuthorityEventType
from app.modules.audit.service import AuditService
from app.modules.authorization.repository import AuthorityIdempotencyRepository
from tests.authorization.admin_access.concurrency_support import ordered_owner_calls
from tests.authorization.admin_access.support import (
    AdminAccess,
    actor_observation,
    assert_unavailable,
    authority_snapshot,
)


async def _service_binding(
    identity: ServiceIdentity, subject: str
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    async with db_session.get_session_factory()() as session:
        profile_ids = tuple(
            str(value)
            for value in (
                await session.scalars(
                    select(ActorProfile.id).where(
                        ActorProfile.service_identity == identity.value,
                        ActorProfile.actor_kind == "service",
                    )
                )
            ).all()
        )
        links = tuple(
            (str(row.id), str(row.actor_profile_id))
            for row in (
                await session.execute(
                    select(ActorIdentityLink.id, ActorIdentityLink.actor_profile_id).where(
                        ActorIdentityLink.subject == subject,
                        ActorIdentityLink.subject_kind == "service",
                    )
                )
            ).all()
        )
        return profile_ids, links


async def _provision(access: AdminAccess, key: str, body: dict[str, str]):
    return await access.signed.client.post(
        "/api/v1/service-actors",
        headers=access.admin.headers | {"Idempotency-Key": key},
        json=body,
    )


@pytest.mark.parametrize(
    ("failure", "event_type"),
    [
        ("decision", AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED),
        ("invalidation", AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED),
        ("reservation", None),
    ],
)
async def test_authority_write_failure_rolls_back_provision_and_allows_retry(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    event_type: AuthorityEventType | None,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    subject = f"service-actor-failure-{failure}"
    key = str(new_record_id())
    body = {
        "service_identity": identity.value,
        "subject": subject,
        "reason": "Prove service provisioning transaction rollback",
    }
    before_authority = await authority_snapshot()
    before_actor = await actor_observation(access.admin.id)
    original_event = AuditService.add_authority_event

    async def fail_event(self, event):
        if event.event_type is event_type:
            raise SQLAlchemyError("injected service provisioning evidence failure")
        return await original_event(self, event)

    async def fail_completion(self, claim, response):
        raise SQLAlchemyError("injected idempotency completion failure")

    with monkeypatch.context() as patch:
        if failure == "reservation":
            patch.setattr(AuthorityIdempotencyRepository, "complete", fail_completion)
        else:
            patch.setattr(AuditService, "add_authority_event", fail_event)
        failed = await _provision(access, key, body)

    assert_unavailable(failed)
    assert await authority_snapshot() == before_authority
    assert await actor_observation(access.admin.id) == before_actor
    assert await _service_binding(identity, subject) == ((), ())

    retried = await _provision(access, key, body)
    assert retried.status_code == 201, retried.text
    profile_ids, links = await _service_binding(identity, subject)
    profile_id = retried.json()["actor_profile_id"]
    assert profile_ids == (profile_id,)
    assert len(links) == 1 and links[0][1] == profile_id
    committed = await authority_snapshot()
    rows = [
        row
        for row in committed["authority_idempotency_records"]
        if str(row["idempotency_key"]) == key
    ]
    assert len(rows) == 1 and rows[0]["status"] == "committed"
    events = [row for row in committed["audit_events"] if row["resource_id"] == profile_id]
    assert {row["event_type"] for row in events} == {
        AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value,
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
    }
    assert len(events) == 2


async def test_distinct_keys_cannot_duplicate_service_actor_after_authority_serialization(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_SCHEDULER
    subject = "service-actor-distinct-key-contention"
    body = {
        "service_identity": identity.value,
        "subject": subject,
        "reason": "Prove one fixed service identity has one owner",
    }
    keys = (str(new_record_id()), str(new_record_id()))

    winner, loser, custody = await ordered_owner_calls(
        lambda: _provision(access, keys[0], body),
        lambda: _provision(access, keys[1], body),
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    assert winner.status_code == 201, winner.text
    assert loser.status_code == 409
    assert loser.json()["error"]["code"] == "service_identity_already_provisioned"
    profile_ids, links = await _service_binding(identity, subject)
    profile_id = winner.json()["actor_profile_id"]
    assert profile_ids == (profile_id,)
    assert len(links) == 1 and links[0][1] == profile_id

    snapshot = await authority_snapshot()
    records = [
        row
        for row in snapshot["authority_idempotency_records"]
        if str(row["idempotency_key"]) in keys
    ]
    assert len(records) == 1 and records[0]["status"] == "committed"
    events = [row for row in snapshot["audit_events"] if row["resource_id"] == profile_id]
    assert len(events) == 2
    assert {row["event_type"] for row in events} == {
        AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value,
        AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
    }


@pytest.mark.parametrize("first_operation", ["provision", "revoke"])
async def test_authority_revocation_serializes_with_service_provisioning(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    first_operation: str,
) -> None:
    access = admin_access
    second_admin = await access.signed.actor("service-provisioning-revoker")
    grant = await access.signed.issue(
        access.admin,
        {
            "target_actor_profile_id": str(second_admin.id),
            "role": "access_administrator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "Set up independent revocation authority",
        },
    )
    assert grant.status_code == 201, grant.text
    key = str(new_record_id())
    identity = ServiceIdentity.ARTIFACT_MATERIALIZER
    subject = f"service-actor-revocation-{first_operation}"
    body = {
        "service_identity": identity.value,
        "subject": subject,
        "reason": "Prove provisioning observes serialized current authority",
    }

    async def revoke():
        return await access.signed.revoke(second_admin, str(access.bootstrap_grant_id))

    async def provision():
        return await _provision(access, key, body)

    first, second, custody = await ordered_owner_calls(
        provision if first_operation == "provision" else revoke,
        revoke if first_operation == "provision" else provision,
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    provisioned, revoked = (first, second) if first_operation == "provision" else (second, first)
    assert revoked.status_code == 200, revoked.text
    succeeded = first_operation == "provision"
    assert provisioned.status_code == (201 if succeeded else 403), provisioned.text
    if not succeeded:
        assert provisioned.json()["error"]["code"] == "permission_not_granted"

    state_before_replay = await _service_binding(identity, subject)
    replay = await _provision(access, key, body)
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "permission_not_granted"
    profile_ids, links = await _service_binding(identity, subject)
    assert (profile_ids, links) == state_before_replay
    profile_id = provisioned.json()["actor_profile_id"] if succeeded else None
    assert profile_ids == ((profile_id,) if succeeded else ())
    assert len(links) == int(succeeded)
    if succeeded:
        assert links[0][1] == profile_id
    snapshot = await authority_snapshot()
    bootstrap = [
        row
        for row in snapshot["admin_role_grants"]
        if str(row["id"]) == str(access.bootstrap_grant_id)
    ]
    assert len(bootstrap) == 1 and bootstrap[0]["status"] == "revoked"
    pending = [
        row for row in snapshot["authority_idempotency_records"] if row["status"] == "pending"
    ]
    assert pending == []
    request_ids = {replay.headers["x-request-id"]}
    if not succeeded:
        request_ids.add(provisioned.headers["x-request-id"])
    denials = [
        row
        for row in snapshot["audit_events"]
        if row["action_id"] == "actor.service.provision" and str(row["request_id"]) in request_ids
    ]
    assert len(denials) == len(request_ids)
    assert all(
        row["event_type"] == AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED.value
        and row["denial_code"] == "permission_not_granted"
        for row in denials
    )
    revoked_events = [
        row
        for row in snapshot["audit_events"]
        if row["event_type"] == AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED.value
        and str(row["entity_id"]) == str(access.bootstrap_grant_id)
    ]
    assert len(revoked_events) == 1
    revoke_invalidations = [
        row
        for row in snapshot["audit_events"]
        if row["event_type"] == AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value
        and row["invalidation_cause_event_id"] == revoked_events[0]["id"]
    ]
    assert len(revoke_invalidations) == 1
    service_records = [
        row
        for row in snapshot["authority_idempotency_records"]
        if str(row["idempotency_key"]) == key
    ]
    assert len(service_records) == int(succeeded)
    assert all(row["status"] == "committed" for row in service_records)
    successes = [
        row
        for row in snapshot["audit_events"]
        if profile_id is not None and row["resource_id"] == profile_id
    ]
    assert len(successes) == (2 if succeeded else 0)
    assert {row["event_type"] for row in successes} == (
        {
            AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value,
            AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
        }
        if succeeded
        else set()
    )
