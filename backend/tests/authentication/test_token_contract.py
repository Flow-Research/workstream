from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import (  # type: ignore[import-not-found]
    MockTransport,
    Request,
    Response,
)

from app.adapters.auth.flow import (
    FlowAuthVerifier,
)
from app.interfaces.auth import AuthVerificationError


from tests.authentication.support import (
    production_verifier_settings,
    issue_asymmetric_token,
    jwks_transport,
    replace_token_header,
)


async def test_asymmetric_token_returns_minimal_canonical_contract(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk),
    )

    result = await verifier.verify(issue_asymmetric_token(private_key))

    assert verifier.canonical_issuer() == result.token.issuer
    assert result.token.model_dump().keys() == {
        "issuer",
        "subject",
        "audience",
        "expires_at",
        "issued_at",
        "not_before",
        "token_id",
        "subject_kind",
        "scopes",
    }
    assert result.token.subject == "opaque-subject-1"
    assert not hasattr(result.token, "roles")
    assert not hasattr(result.token, "email")


@pytest.mark.parametrize(
    "header_changes",
    [
        {"alg": "none"},
        {"alg": "HS256"},
        {"kid": ""},
        {"jku": "https://attacker.test/jwks"},
        {"x5u": "https://attacker.test/certificate"},
        {"crit": ["unrecognized"]},
    ],
)
async def test_untrusted_or_remote_key_headers_fail_before_jwks(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    header_changes: dict[str, Any],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
    )
    token = replace_token_header(issue_asymmetric_token(private_key), **header_changes)

    with pytest.raises(AuthVerificationError):
        await verifier.verify(token)

    assert requests == []


async def test_missing_kid_fails_before_jwks(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
    )
    token = replace_token_header(
        issue_asymmetric_token(private_key),
        remove_headers={"kid"},
    )

    with pytest.raises(AuthVerificationError, match="key identifier"):
        await verifier.verify(token)

    assert requests == []


@pytest.mark.parametrize(
    ("claims", "message"),
    [
        ({"aud": "other"}, "signature or claims"),
        ({"iss": "https://other.example.test"}, "signature or claims"),
        ({"exp": 1}, "signature or claims"),
        ({"iat": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())}, "signature or claims"),
        ({"jti": ""}, "identifier"),
        ({"subject_kind": "Human"}, "subject kind"),
        ({"scope": "unrelated"}, "human scope"),
    ],
)
async def test_verified_token_claim_failures_are_closed(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    claims: dict[str, Any],
    message: str,
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk),
    )

    with pytest.raises(AuthVerificationError, match=message):
        await verifier.verify(issue_asymmetric_token(private_key, claims=claims))


@pytest.mark.parametrize(
    "missing_claim", ["iss", "sub", "aud", "exp", "iat", "jti", "subject_kind", "scope"]
)
async def test_missing_mandatory_claims_fail_closed(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    missing_claim: str,
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(issue_asymmetric_token(private_key, remove_claims={missing_claim}))


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "a.b.c",
        "eyJhbGciOiJSUzI1NiJ9.not-json.signature",
        "....",
    ],
)
async def test_malformed_tokens_fail_without_network(token: str) -> None:
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(lambda request: requests.append(request) or Response(500)),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(token)

    assert requests == []


@pytest.mark.parametrize("limit", ["total", "header", "payload"])
async def test_token_size_limits_fail_before_network(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    limit: str,
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    overrides: dict[str, int] = {
        "token_max_bytes": 4_096,
        "token_header_max_bytes": 512,
        "token_payload_max_bytes": 2_048,
    }
    token = issue_asymmetric_token(private_key)
    if limit == "total":
        overrides.update(
            token_max_bytes=512,
            token_header_max_bytes=128,
            token_payload_max_bytes=256,
        )
        token = "x" * 513
    elif limit == "header":
        overrides["token_header_max_bytes"] = 128
        token = replace_token_header(token, padding="x" * 200)
    else:
        overrides["token_payload_max_bytes"] = 256
        token = issue_asymmetric_token(private_key, claims={"padding": "x" * 400})
    verifier = FlowAuthVerifier(
        production_verifier_settings(**overrides),
        jwks_transport=jwks_transport(jwk, requests),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(token)

    assert requests == []


@pytest.mark.parametrize(
    ("claim", "within_delta", "beyond_delta"),
    [("exp", -10, -60), ("iat", 10, 60), ("nbf", 10, 60)],
)
async def test_temporal_claims_honor_configured_skew(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    claim: str,
    within_delta: int,
    beyond_delta: int,
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_clock_skew_seconds=30),
        jwks_transport=jwks_transport(jwk),
    )
    now = datetime.now(UTC)

    within_skew = issue_asymmetric_token(
        private_key,
        claims={claim: int((now + timedelta(seconds=within_delta)).timestamp())},
    )
    beyond_skew = issue_asymmetric_token(
        private_key,
        claims={claim: int((now + timedelta(seconds=beyond_delta)).timestamp())},
    )

    assert (await verifier.verify(within_skew)).token.token_id == "token-id-1"
    with pytest.raises(AuthVerificationError):
        await verifier.verify(beyond_skew)
