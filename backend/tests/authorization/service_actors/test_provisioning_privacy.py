"""Confidentiality of service-provisioning inputs across observable evidence."""

import logging

from httpx import Response
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from tests.authentication.support import issue_asymmetric_token
from tests.authorization.admin_access.support import AdminAccess
from tests.authorization.service_actors.provisioning_support import (
    provision,
    provisioning_payload,
    signed_subject_headers,
)


async def _create_with_private_admin_credentials(
    access: AdminAccess, service_subject: str, reason: str
) -> tuple[Response, tuple[str, ...]]:
    key = str(new_record_id())
    email = "private-admin@example.test"
    token_id = "private-admin-token-id"
    token = issue_asymmetric_token(
        access.signed.private_key,
        claims={"sub": access.admin.subject, "email": email, "jti": token_id},
    )
    response = await access.signed.client.post(
        "/api/v1/service-actors",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json=provisioning_payload(ServiceIdentity.ARTIFACT_VERIFIER, service_subject, reason),
    )
    assert response.status_code == 201, response.text
    return response, (token, email, token_id, key)


async def _exercise_private_requests(
    access: AdminAccess,
) -> tuple[list[Response], tuple[str, ...]]:
    service_subject = "private-service-subject-for-privacy"
    service_token = signed_subject_headers(access, service_subject)["Authorization"].removeprefix(
        "Bearer "
    )
    reason = "private-provisioning-reason-for-privacy"
    created, admin_private = await _create_with_private_admin_credentials(
        access,
        service_subject,
        reason,
    )

    ordinary_subject = "private-ordinary-provisioner-subject"
    ordinary_jti = "private-ordinary-provisioner-token-id"
    private_email = "private-provisioner@example.test"
    ordinary_token = issue_asymmetric_token(
        access.signed.private_key,
        claims={"sub": ordinary_subject, "email": private_email, "jti": ordinary_jti},
    )
    ordinary_denial = await access.signed.client.post(
        "/api/v1/service-actors",
        headers={
            "Authorization": f"Bearer {ordinary_token}",
            "Idempotency-Key": str(new_record_id()),
        },
        json=provisioning_payload(ServiceIdentity.ARTIFACT_PUT_RESOLVER, "private-denied-subject"),
    )
    assert ordinary_denial.status_code == 403

    nonhuman_headers = {
        kind: signed_subject_headers(
            access,
            f"private-{kind}-provisioner-subject",
            subject_kind=kind,
            scope=f"{kind}:identity",
        )
        for kind in ("agent", "space")
    }
    nonhuman_denials = [
        await access.signed.client.post(
            "/api/v1/service-actors",
            headers=headers | {"Idempotency-Key": str(new_record_id())},
            json=provisioning_payload(
                ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                "private-denied-subject",
            ),
        )
        for headers in nonhuman_headers.values()
    ]
    assert [response.status_code for response in nonhuman_denials] == [403, 403]

    conflict = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(ServiceIdentity.ARTIFACT_PUT_RESOLVER, service_subject, reason),
    )
    assert conflict.status_code == 409
    malformed_subject = "private-" + "x" * 220
    malformed_reason = "private-" + "y" * 520
    malformed = await provision(
        access,
        str(new_record_id()),
        provisioning_payload(
            ServiceIdentity.ARTIFACT_CHECKER_OUTPUT, malformed_subject, malformed_reason
        ),
    )
    assert malformed.status_code == 422
    denied_subject = "private-service-denial-subject"
    denied = await access.signed.client.get(
        "/api/v1/actors/me",
        headers=signed_subject_headers(access, denied_subject),
    )
    assert denied.status_code == 403

    tokens = tuple(
        headers["Authorization"].removeprefix("Bearer ") for headers in nonhuman_headers.values()
    )
    private_values = (
        access.admin.token,
        *admin_private,
        service_token,
        ordinary_token,
        *tokens,
        access.signed.issuer,
        access.admin.subject,
        ordinary_subject,
        ordinary_jti,
        private_email,
        service_subject,
        denied_subject,
        reason,
        malformed_subject,
        malformed_reason,
    )
    responses = [created, ordinary_denial, *nonhuman_denials, conflict, malformed, denied]
    return responses, private_values


async def _serialized_audit_evidence() -> str:
    async with db_session.get_session_factory()() as session:
        rows = (
            await session.scalars(text("select row_to_json(audit_events)::text from audit_events"))
        ).all()
    return "\n".join(rows)


async def test_provisioning_secrets_are_not_exposed_in_responses_logs_or_audit(
    admin_access: AdminAccess,
    caplog,
) -> None:
    caplog.set_level(logging.DEBUG, logger="app")
    responses, sensitive = await _exercise_private_requests(admin_access)
    response_text = "\n".join(response.text for response in responses)
    audit_text = await _serialized_audit_evidence()
    assert all(value not in response_text for value in sensitive)
    assert all(value not in caplog.text for value in sensitive)
    assert all(value not in audit_text for value in sensitive)
