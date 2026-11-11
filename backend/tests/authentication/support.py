from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import (  # type: ignore[import-not-found]
    MockTransport,
    Request,
    Response,
)

from app.core.config import Settings


def _base64url_int(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(size, "big")).rstrip(b"=").decode()


def rsa_public_jwk(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
) -> dict[str, Any]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "RS256",
        "n": _base64url_int(numbers.n),
        "e": _base64url_int(numbers.e),
    }


def production_verifier_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "auth_provider": "flow",
        "token_issuer": "https://issuer.example.test",
        "token_audience": "workstream",
        "token_jwks_url": "https://issuer.example.test/.well-known/jwks.json",
        "token_algorithms": "RS256",
        "token_introspection_mode": "disabled",
        "token_introspection_disabled_reason": "issuer uses short-lived final tokens",
    }
    values.update(overrides)
    return Settings(**values)


def introspection_settings(**overrides: Any) -> Settings:
    """Configure the one separate, credential-bound test introspection endpoint."""
    values = {
        "token_introspection_mode": "required",
        "token_introspection_disabled_reason": None,
        "token_introspection_url": "https://introspection.example.test/oauth/introspect",
        "token_introspection_client_id": "workstream-client",
        "token_introspection_client_secret": "client-secret",
    }
    values.update(overrides)
    return production_verifier_settings(**values)


def issue_asymmetric_token(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str = "issuer-key-1",
    subject_kind: str = "human",
    scope: str = "workstream:access",
    claims: dict[str, Any] | None = None,
    remove_claims: set[str] | None = None,
    algorithm: str = "RS256",
) -> str:
    """Sign controlled issuer claims, including explicit omissions and malformed-value probes."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": "https://issuer.example.test",
        "sub": "opaque-subject-1",
        "aud": "workstream",
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "iat": int(now.timestamp()),
        "nbf": int((now - timedelta(seconds=1)).timestamp()),
        "jti": "token-id-1",
        "subject_kind": subject_kind,
        "scope": scope,
        "roles": ["admin", "reviewer"],
        "email": "issuer-profile@example.test",
        "name": "Issuer Profile",
    }
    if claims:
        payload.update(claims)
    for claim in remove_claims or ():
        payload.pop(claim, None)
    return jwt.encode(payload, private_key, algorithm=algorithm, headers={"kid": kid, "typ": "JWT"})


def issue_human_token_matrix(
    private_key: rsa.RSAPrivateKey,
    *,
    prefix: str,
    names: tuple[str, ...],
    email_prefix: str | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Issue related human tokens and bearer headers for auth matrix tests."""
    tokens = {
        name: issue_asymmetric_token(
            private_key,
            claims={
                "sub": f"{prefix}-{name}",
                "jti": f"{prefix}-{name}-token",
                **({"email": f"{email_prefix}{name}@example.test"} if email_prefix else {}),
            },
        )
        for name in names
    }
    return tokens, {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}


def jwks_transport(jwk: dict[str, Any], requests: list[Request] | None = None) -> MockTransport:
    def handler(request: Request) -> Response:
        if requests is not None:
            requests.append(request)
        return Response(200, json={"keys": [jwk]})

    return MockTransport(handler)


def issue_local_hmac_token(secret: str, claims: dict[str, Any]) -> str:
    def segment(value: dict[str, Any]) -> str:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode()

    header = segment({"alg": "HS256", "typ": "JWT"})
    payload = segment(claims)
    content = f"{header}.{payload}".encode()
    signature = (
        base64.urlsafe_b64encode(hmac.new(secret.encode(), content, hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.{signature}"


def replace_token_header(
    token: str,
    *,
    remove_headers: set[str] | None = None,
    **changes: Any,
) -> str:
    header_segment, payload_segment, signature_segment = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_segment + "=" * (-len(header_segment) % 4)))
    header.update(changes)
    for name in remove_headers or ():
        header.pop(name, None)
    replacement = (
        base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{replacement}.{payload_segment}.{signature_segment}"
