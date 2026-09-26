from __future__ import annotations

from datetime import UTC, datetime

import pytest  # type: ignore[import-not-found]

from app.adapters.auth.flow import (
    FlowAuthVerifier,
)
from app.core.config import Settings
from app.interfaces.auth import AuthVerificationError


from tests.authentication.support import issue_local_hmac_token


async def test_local_hmac_fixture_uses_final_claim_shape() -> None:
    secret = "local-test-secret"
    now = int(datetime.now(UTC).timestamp())
    verifier = FlowAuthVerifier(
        Settings(
            environment="test",
            auth_provider="flow",
            flow_auth_issuer="https://issuer.local.test",
            flow_auth_audience="workstream",
            flow_auth_local_hmac_secret=secret,
        )
    )
    token = issue_local_hmac_token(
        secret,
        {
            "iss": "https://issuer.local.test",
            "sub": "local-subject",
            "aud": "workstream",
            "exp": now + 300,
            "iat": now,
            "jti": "local-token-id",
            "subject_kind": "human",
            "scope": "workstream:access",
            "roles": ["reviewer"],
        },
    )

    result = await verifier.verify(token)

    assert verifier.canonical_issuer() == result.token.issuer
    assert result.token.token_id == "local-token-id"


async def test_flow_auth_rejects_subject_above_persisted_identity_bound() -> None:
    secret = "local-test-secret"
    now = int(datetime.now(UTC).timestamp())
    verifier = FlowAuthVerifier(
        Settings(
            environment="test",
            auth_provider="flow",
            flow_auth_issuer="https://issuer.local.test",
            flow_auth_audience="workstream",
            flow_auth_local_hmac_secret=secret,
        )
    )
    token = issue_local_hmac_token(
        secret,
        {
            "iss": "https://issuer.local.test",
            "sub": "s" * 201,
            "aud": "workstream",
            "exp": now + 300,
            "iat": now,
            "jti": "oversized-subject",
            "subject_kind": "human",
            "scope": "workstream:access",
        },
    )

    with pytest.raises(AuthVerificationError, match="token subject is required"):
        await verifier.verify(token)


@pytest.mark.parametrize("subject", ["   ", " padded-subject "])
async def test_flow_auth_rejects_subject_whitespace_before_persistence(subject: str) -> None:
    secret = "local-test-secret"
    now = int(datetime.now(UTC).timestamp())
    verifier = FlowAuthVerifier(
        Settings(
            environment="test",
            auth_provider="flow",
            flow_auth_issuer="https://issuer.local.test",
            flow_auth_audience="workstream",
            flow_auth_local_hmac_secret=secret,
        )
    )
    token = issue_local_hmac_token(
        secret,
        {
            "iss": "https://issuer.local.test",
            "sub": subject,
            "aud": "workstream",
            "exp": now + 300,
            "iat": now,
            "jti": "whitespace-subject",
            "subject_kind": "human",
            "scope": "workstream:access",
        },
    )

    with pytest.raises(AuthVerificationError, match="token subject is required"):
        await verifier.verify(token)


@pytest.mark.parametrize("environment", ["staging", "preview", "prod", "production"])
def test_local_hmac_fixture_is_impossible_in_production(environment: str) -> None:
    with pytest.raises(RuntimeError, match="cannot run outside local/test"):
        FlowAuthVerifier(
            Settings(
                environment=environment,
                auth_provider="flow",
                flow_auth_local_hmac_secret="forbidden-secret",
            )
        )
