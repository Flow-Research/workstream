"""Service-actor provisioning admission, conflict and input rejections."""

from typing import Any

import pytest
from app.core.identifiers import new_record_id
from app.interfaces.auth import AuthVerificationUnavailableError
from app.modules.actors.api import ServiceIdentity
from app.modules.audit.schemas import AuthorityEventType
from tests.authorization.admin_access.support import AdminAccess, authority_snapshot
from tests.authorization.service_actors.provisioning_support import (
    provision,
    provisioning_payload,
    service_records_for_identity,
    service_records_for_subject,
    signed_subject_headers,
)


async def test_unprovisioned_service_cannot_provision_itself(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    subject = "unprovisioned-service-subject"
    response = await access.signed.client.post(
        "/api/v1/service-actors",
        headers=signed_subject_headers(access, subject) | {"Idempotency-Key": str(new_record_id())},
        json=provisioning_payload(identity, subject),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "service_actor_not_provisioned"
    assert await service_records_for_identity(identity) == ()
    assert await service_records_for_subject(subject) == ()


async def test_provisioned_service_cannot_use_human_provisioning_route(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    subject = "provisioned-service-cannot-provision"
    payload = provisioning_payload(identity, subject)
    created = await provision(access, str(new_record_id()), payload)
    assert created.status_code == 201, created.text
    before = await service_records_for_identity(identity)

    response = await access.signed.client.post(
        "/api/v1/service-actors",
        headers=signed_subject_headers(access, subject) | {"Idempotency-Key": str(new_record_id())},
        json=payload,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_not_granted"
    assert await service_records_for_identity(identity) == before


async def test_provisioned_service_cannot_read_human_self_profile(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    subject = "provisioned-service-cannot-read-human-profile"
    created = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(identity, subject),
    )
    assert created.status_code == 201, created.text
    before = await service_records_for_identity(identity)

    response = await access.signed.client.get(
        "/api/v1/actors/me",
        headers=signed_subject_headers(access, subject),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_not_granted"
    assert await service_records_for_identity(identity) == before


async def test_fixed_identity_cannot_be_rebound(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_VERIFIER
    original_subject = "fixed-service-identity-original-subject"
    created = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(identity, original_subject),
    )
    assert created.status_code == 201, created.text
    before = await service_records_for_identity(identity)

    conflict = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(identity, "another-service-subject"),
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "service_identity_already_provisioned"
    assert await service_records_for_identity(identity) == before


async def test_subject_cannot_be_linked_to_second_identity(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    subject = "one-service-subject-has-one-owner"
    first_identity = ServiceIdentity.ARTIFACT_VERIFIER
    second_identity = ServiceIdentity.ARTIFACT_PUT_RESOLVER
    created = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(first_identity, subject),
    )
    assert created.status_code == 201, created.text
    original = await service_records_for_subject(subject)

    conflict = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(second_identity, subject),
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "identity_subject_already_linked"
    assert await service_records_for_subject(subject) == original
    assert await service_records_for_identity(second_identity) == ()
    snapshot = await authority_snapshot()
    denials = [
        row
        for row in snapshot["audit_events"]
        if row["event_type"] == AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED.value
        and row["denial_code"] == "identity_link_conflict"
    ]
    assert len(denials) == 1
    assert denials[0]["action_id"] == "actor.service.provision"


async def test_only_authorized_human_can_provision_service_actor(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_PUT_RESOLVER
    subject = "denied-service-actor-subject"
    payload = provisioning_payload(identity, subject)
    ordinary = await access.signed.actor("ordinary-service-provisioner")
    responses = [
        await access.signed.client.post(
            "/api/v1/service-actors",
            headers=ordinary.headers | {"Idempotency-Key": str(new_record_id())},
            json=payload,
        )
    ]
    for kind in ("agent", "space"):
        responses.append(
            await access.signed.client.post(
                "/api/v1/service-actors",
                headers=signed_subject_headers(
                    access,
                    f"nonhuman-{kind}-service-provisioner",
                    subject_kind=kind,
                    scope=f"{kind}:identity",
                )
                | {"Idempotency-Key": str(new_record_id())},
                json=payload,
            )
        )

    assert [response.status_code for response in responses] == [403, 403, 403]
    assert responses[0].json()["error"]["code"] == "permission_not_granted"
    assert [response.json()["error"]["code"] for response in responses[1:]] == [
        "unsupported_subject_kind",
        "unsupported_subject_kind",
    ]
    assert await service_records_for_identity(identity) == ()
    assert await service_records_for_subject(subject) == ()


@pytest.mark.parametrize(
    ("case", "body_changes", "key", "private_values"),
    [
        (
            "oversized",
            {"subject": "private-" + "x" * 220, "reason": "private-" + "y" * 520},
            None,
            ("private-" + "x" * 220, "private-" + "y" * 520),
        ),
        (
            "whitespace-subject",
            {"subject": " private-service-subject "},
            None,
            (" private-service-subject ",),
        ),
        (
            "unknown-identity",
            {"service_identity": "private-unknown-service-identity"},
            None,
            ("private-unknown-service-identity",),
        ),
        (
            "malformed-idempotency-key",
            {},
            "private-invalid-idempotency-key",
            (
                "private-invalid-idempotency-key",
                "private-valid-service-subject",
                "private-valid-provisioning-reason",
            ),
        ),
    ],
)
async def test_invalid_provisioning_inputs_are_rejected_without_echo(
    admin_access: AdminAccess,
    case: str,
    body_changes: dict[str, Any],
    key: str | None,
    private_values: tuple[str, ...],
) -> None:
    access = admin_access
    identity = ServiceIdentity.ARTIFACT_PUT_RESOLVER
    payload = (
        provisioning_payload(
            identity,
            "private-valid-service-subject",
            "private-valid-provisioning-reason",
        )
        | body_changes
    )
    request_key = key or str(new_record_id())
    response = await access.signed.client.post(
        "/api/v1/service-actors",
        headers=access.admin.headers | {"Idempotency-Key": request_key},
        json=payload,
    )

    assert response.status_code == 422, case
    assert all(value not in response.text for value in private_values)
    if case == "malformed-idempotency-key":
        assert payload["subject"] not in response.text
        assert payload["reason"] not in response.text
    assert await service_records_for_identity(identity) == ()


async def test_canonical_issuer_unavailable_fails_closed(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    verifier = access.signed.app.state.auth_verifier

    class UnavailableCanonicalIssuer:
        async def verify(self, token: str):
            return await verifier.verify(token)

        def canonical_issuer(self) -> str:
            raise AuthVerificationUnavailableError("issuer unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(access.signed.app.state, "auth_verifier", UnavailableCanonicalIssuer())
        response = await access.signed.client.post(
            "/api/v1/service-actors",
            headers=access.admin.headers | {"Idempotency-Key": str(new_record_id())},
            json=provisioning_payload(
                ServiceIdentity.ARTIFACT_VERIFIER,
                "canonical-issuer-failure-subject",
            ),
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "identity_verification_unavailable"
    assert await service_records_for_identity(ServiceIdentity.ARTIFACT_VERIFIER) == ()
