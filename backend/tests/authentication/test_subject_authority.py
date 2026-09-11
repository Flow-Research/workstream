"""Nonhuman token identity is never human compatibility authority."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
import pytest

from app.adapters.auth.flow import FlowAuthVerifier
from app.db.session import get_db_session
from app.interfaces.auth import AuthVerificationError
from app.main import create_app
from tests.authentication.support import (
    issue_asymmetric_token,
    jwks_transport,
    production_verifier_settings,
)


@pytest.mark.parametrize(
    ("kind", "scope"),
    [
        ("service", "workstream:service"),
        ("agent", "agent:identity"),
        ("space", "space:identity"),
    ],
)
async def test_nonhuman_tokens_receive_no_legacy_authority(rsa_signing_material, kind, scope):
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(production_verifier_settings(), jwks_transport=jwks_transport(jwk))
    result = await verifier.verify(
        issue_asymmetric_token(private_key, subject_kind=kind, scope=scope)
    )
    assert result.legacy is None
    assert result.token.subject_kind == kind


async def test_agent_token_is_denied_by_actor_admission(rsa_signing_material):
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(production_verifier_settings(), jwks_transport=jwks_transport(jwk))
    agent_token = issue_asymmetric_token(private_key, subject_kind="agent", scope="agent:identity")
    app = create_app(production_verifier_settings())
    app.state.auth_verifier = verifier

    async def no_database_session() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_db_session] = no_database_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/actors/me", headers={"Authorization": f"Bearer {agent_token}"}
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Unsupported subject kind",
        "error": {
            "code": "unsupported_subject_kind",
            "message": "Unsupported subject kind",
            "details": {},
            "correlation_id": response.headers["x-correlation-id"],
            "retryable": False,
        },
    }


async def test_service_token_cannot_substitute_human_scope(rsa_signing_material):
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(production_verifier_settings(), jwks_transport=jwks_transport(jwk))
    with pytest.raises(AuthVerificationError, match="service scope"):
        await verifier.verify(
            issue_asymmetric_token(private_key, subject_kind="service", scope="workstream:access")
        )
