"""PostgreSQL contention proof for service provisioning idempotency and binding."""

import pytest

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.repository import AuthorityIdempotencyRepository
from tests.authorization.admin_access.concurrency_support import ordered_owner_calls
from tests.authorization.admin_access.support import AdminAccess, authority_snapshot
from tests.authorization.service_actors.provisioning_support import (
    provision,
    provisioning_payload,
    service_records_for_identity,
    service_records_for_subject,
)


async def test_same_key_concurrent_identical_requests_replay_one_result(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_SCHEDULER
    payload = provisioning_payload(identity, "same-key-identical-service")
    key = str(new_record_id())

    first, second, custody = await ordered_owner_calls(
        lambda: provision(access, key, payload),
        lambda: provision(access, key, payload),
        boundary="reservation",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )

    assert custody.observed
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    [row] = await service_records_for_identity(identity)
    assert row.profile_id == first.json()["actor_profile_id"]
    snapshot = await authority_snapshot()
    reservations = [
        row
        for row in snapshot["authority_idempotency_records"]
        if str(row["idempotency_key"]) == key
    ]
    assert len(reservations) == 1 and reservations[0]["status"] == "committed"


async def test_same_key_concurrent_payload_drift_is_rejected(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_MATERIALIZER
    payload = provisioning_payload(identity, "same-key-drift-original")
    changed = payload | {"subject": "same-key-drift-changed"}
    key = str(new_record_id())

    first, second, custody = await ordered_owner_calls(
        lambda: provision(access, key, payload),
        lambda: provision(access, key, changed),
        boundary="reservation",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )

    assert custody.observed
    assert sorted((first.status_code, second.status_code)) == [201, 409]
    rejected = next(response for response in (first, second) if response.status_code == 409)
    assert rejected.json()["error"]["code"] == "idempotency_mismatch"
    snapshot = await authority_snapshot()
    reservations = [
        row
        for row in snapshot["authority_idempotency_records"]
        if str(row["idempotency_key"]) == key
    ]
    assert len(reservations) == 1 and reservations[0]["status"] == "committed"
    [row] = await service_records_for_identity(identity)
    assert row.subject in {payload["subject"], changed["subject"]}


async def test_distinct_identities_cannot_claim_same_subject(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    subject = "service-subject-shared-by-identities"
    first_identity = ServiceIdentity.ARTIFACT_BINDING
    second_identity = ServiceIdentity.ARTIFACT_GUIDE_READER
    first_payload = provisioning_payload(first_identity, subject)
    second_payload = provisioning_payload(second_identity, subject)

    first, second, custody = await ordered_owner_calls(
        lambda: provision(access, str(new_record_id()), first_payload),
        lambda: provision(access, str(new_record_id()), second_payload),
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )

    assert custody.observed
    assert sorted((first.status_code, second.status_code)) == [201, 409]
    rejected = next(response for response in (first, second) if response.status_code == 409)
    assert rejected.json()["error"]["code"] == "identity_subject_already_linked"
    [row] = await service_records_for_subject(subject)
    assert row.service_identity in {first_identity.value, second_identity.value}
    losing_identity = (
        second_identity if row.service_identity == first_identity.value else first_identity
    )
    assert await service_records_for_identity(losing_identity) == ()


async def test_same_key_race_proof_rejects_nonblocking_reservation(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    body = provisioning_payload(
        ServiceIdentity.ARTIFACT_SCHEDULER,
        "reservation-negative-control",
    )
    key = str(new_record_id())

    async def nonblocking_reservation(self, **kwargs):
        return None

    with monkeypatch.context() as patch:
        patch.setattr(AuthorityIdempotencyRepository, "reserve", nonblocking_reservation)
        with pytest.raises(AssertionError, match="actual owner lock observation failed") as failure:
            await ordered_owner_calls(
                lambda: provision(access, key, body),
                lambda: provision(access, key, body),
                boundary="reservation",
                database_url=auth_database_env,
                monkeypatch=monkeypatch,
            )

    assert isinstance(failure.value.__cause__, AssertionError)
    assert (
        str(failure.value.__cause__) == "ordered lifecycle request never reached the database lock"
    )
