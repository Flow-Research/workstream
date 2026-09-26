"""Success, replay, and persisted privilege boundaries for service actors."""

import pytest

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.audit.schemas import AuthorityEventType
from tests.authorization.admin_access.support import (
    AdminAccess,
    actor_observation,
    assert_unavailable,
    authority_snapshot,
)
from tests.authorization.service_actors.provisioning_support import (
    provision,
    provisioning_payload,
    service_actor_authority_counts,
    service_records,
    service_records_for_identity,
)


async def test_service_actor_provisioning_binds_exact_identity(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    subject = "Opaque-Service-Subject/Verifier:01"
    key = str(new_record_id())

    response = await provision(access, key, provisioning_payload(identity, subject))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {
        "actor_profile_id",
        "service_identity",
        "actor_status",
        "identity_link_status",
        "provisioning_method",
        "created_at",
        "linked_at",
    }
    assert body["service_identity"] == identity.value
    assert body["actor_status"] == body["identity_link_status"] == "active"
    assert body["provisioning_method"] == "manual_service_provisioning"

    [row] = await service_records_for_identity(identity)
    assert row.profile_id == body["actor_profile_id"]
    assert row.actor_kind == row.subject_kind == "service"
    assert row.profile_status == row.link_status == "active"
    assert row.service_identity == identity.value
    assert row.provisioning_method == "manual_service_provisioning"
    assert row.created_by == row.linked_by == str(access.admin.id)
    assert row.profile_last_seen_at is None
    assert (row.issuer, row.subject, row.link_last_verified_at) == (
        access.signed.issuer,
        subject,
        None,
    )


async def test_project_setup_identity_is_provisioned(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.PROJECT_SETUP
    subject = "Opaque-Service-Subject/ProjectSetup:01"

    response = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(identity, subject),
    )

    assert response.status_code == 201, response.text
    assert response.json()["service_identity"] == identity.value
    [row] = await service_records_for_identity(identity)
    assert row.actor_kind == row.subject_kind == "service"
    assert row.profile_status == row.link_status == "active"
    assert row.provisioning_method == "manual_service_provisioning"
    assert (row.issuer, row.subject) == (access.signed.issuer, subject)
    assert row.created_by == row.linked_by == str(access.admin.id)
    assert row.profile_last_seen_at is row.link_last_verified_at is None


async def test_exact_replay_returns_original_provisioning_response(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    subject = "service-actor-exact-replay"
    payload = provisioning_payload(identity, subject)
    key = str(new_record_id())
    before_create = await actor_observation(access.admin.id)
    created = await provision(access, key, payload)
    assert created.status_code == 201, created.text
    original = created.json()
    after_create = await actor_observation(access.admin.id)
    assert after_create.last_seen_at > before_create.last_seen_at
    assert after_create.last_verified_at > before_create.last_verified_at
    before_replay = await actor_observation(access.admin.id)
    before_service = await service_records_for_identity(identity)

    replay = await provision(access, key, payload)

    assert replay.status_code == 201
    assert replay.json() == original
    assert await service_records_for_identity(identity) == before_service
    after_replay = await actor_observation(access.admin.id)
    assert after_replay.last_seen_at > before_replay.last_seen_at
    assert after_replay.last_verified_at > before_replay.last_verified_at
    records = await authority_snapshot()
    reservations = [
        row
        for row in records["authority_idempotency_records"]
        if str(row["idempotency_key"]) == key
    ]
    assert len(reservations) == 1 and reservations[0]["status"] == "committed"


async def test_unavailable_replay_does_not_touch_actor_or_service_state(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    payload = provisioning_payload(identity, "service-actor-unavailable-replay")
    key = str(new_record_id())
    created = await provision(access, key, payload)
    assert created.status_code == 201, created.text
    before_actor = await actor_observation(access.admin.id)
    before_service = await service_records_for_identity(identity)

    from app.modules.authorization.service_actor_service import (
        ServiceActorProvisioningService,
        ServiceActorProvisioningUnavailable,
    )

    async def unavailable_replay(self, **kwargs):
        raise ServiceActorProvisioningUnavailable("forced unavailable replay")

    with monkeypatch.context() as patch:
        patch.setattr(ServiceActorProvisioningService, "replay_response", unavailable_replay)
        response = await provision(access, key, payload)

    assert_unavailable(response)
    assert await actor_observation(access.admin.id) == before_actor
    assert await service_records_for_identity(identity) == before_service


async def test_mismatched_replay_does_not_touch_actor_or_service_state(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    payload = provisioning_payload(identity, "service-actor-mismatched-replay")
    key = str(new_record_id())
    created = await provision(access, key, payload)
    assert created.status_code == 201, created.text
    before_actor = await actor_observation(access.admin.id)
    before_service = await service_records_for_identity(identity)

    mismatch = await provision(
        access,
        key,
        payload | {"reason": "A different bounded reason"},
    )

    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_mismatch"
    assert await actor_observation(access.admin.id) == before_actor
    assert await service_records_for_identity(identity) == before_service


async def test_service_provisioning_persists_only_scoped_audit_and_no_grants(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identities = (ServiceIdentity.ARTIFACT_VERIFIER, ServiceIdentity.PROJECT_SETUP)
    subjects = ("service-actor-audit-verifier", "service-actor-audit-project-setup")

    for identity, subject in zip(identities, subjects, strict=True):
        response = await provision(
            access,
            str(new_record_id()),
            provisioning_payload(identity, subject),
        )
        assert response.status_code == 201, response.text

    services = await service_records()
    assert {row.service_identity for row in services} == {identity.value for identity in identities}
    assert all(row.profile_last_seen_at is None for row in services)
    assert await service_actor_authority_counts(services) == (0, 0, 0)

    snapshot = await authority_snapshot()
    events = [
        row
        for row in snapshot["audit_events"]
        if row["event_type"] == AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value
    ]
    assert len(events) == len(identities)
    assert {row["entity_id"] for row in events} == {row.profile_id for row in services}
    assert all(row["action_id"] is None for row in events)
    assert all(row["permission_id"] == "actor.service.provision" for row in events)
