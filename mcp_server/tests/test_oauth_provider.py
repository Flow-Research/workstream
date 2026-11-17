from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from workstream_mcp.adapters.keycloak import KeycloakCredentials
from workstream_mcp.oauth import IdentityUnavailable, InvalidCredential, OAuthSettings

ISSUER = "https://identity.example/realms/flow"
RESOURCE = "https://workstream.example/mcp"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def issue(key, **changes):
    now = int(time.time())
    claims = dict(
        iss=ISSUER,
        sub="user-one",
        aud=[RESOURCE, "workstream-mcp"],
        iat=now,
        exp=now + 300,
        jti="request-id",
        azp="garden-workstream",
        typ="Bearer",
        subject_kind="human",
        scope="openid workstream:access",
    )
    claims.update(changes)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key-one"})


def jwks(key):
    value = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {"keys": [{**value, "kid": "key-one", "use": "sig", "alg": "RS256"}]}


def settings():
    return OAuthSettings(ISSUER, RESOURCE, Path("/run/secrets/exchange"))


@pytest.mark.asyncio
async def test_exchange_preserves_subject_and_uses_fixed_target(signing_key):
    calls = []
    source = issue(signing_key)
    target = issue(
        signing_key,
        aud="workstream-api",
        azp="workstream-mcp",
        exp=int(time.time()) + 120,
        scope="workstream:access",
    )

    def handle(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=jwks(signing_key))
        data = parse_qs(request.content.decode())
        assert data["subject_token"] == [source]
        assert data["audience"] == ["workstream-api"]
        assert data["scope"] == ["workstream:access"]
        assert "client_secret" not in data
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(
            200,
            json={
                "access_token": target,
                "token_type": "Bearer",
                "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = KeycloakCredentials(settings(), client, "fixture-secret")
        identity = await provider.verify(source)
        assert identity.subject == "user-one"
        assert source not in repr(identity)
        assert await provider.exchange(identity) == "Bearer " + target
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"aud": "workstream-api"},
        {"aud": [RESOURCE, "workstream-mcp", "workstream-api"]},
        {"iss": "https://foreign.example"},
        {"subject_kind": "service"},
        {"scope": "openid"},
        {"typ": "ID"},
        {"exp": 1},
        {"iat": True},
        {"exp": int(time.time()) + 900},
        {"azp": ""},
    ],
)
async def test_source_substitutions_never_exchange(signing_key, change):
    calls = []

    def handle(request):
        calls.append(request.method)
        assert request.method == "GET"
        return httpx.Response(200, json=jwks(signing_key))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = KeycloakCredentials(settings(), client, "fixture-secret")
        with pytest.raises(InvalidCredential):
            await provider.verify(issue(signing_key, **change))
    assert "POST" not in calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"sub": "user-two"},
        {"aud": ["workstream-api", RESOURCE]},
        {"azp": "another-client"},
        {"scope": "workstream:access admin"},
        {"exp": int(time.time()) + 900},
    ],
)
async def test_exchanged_substitutions_never_reach_api(signing_key, change):
    target_claims = dict(
        aud="workstream-api",
        azp="workstream-mcp",
        exp=int(time.time()) + 120,
        scope="workstream:access",
    )
    target_claims.update(change)

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=jwks(signing_key))
        return httpx.Response(
            200,
            json={
                "access_token": issue(signing_key, **target_claims),
                "token_type": "Bearer",
                "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = KeycloakCredentials(settings(), client, "fixture-secret")
        identity = await provider.verify(issue(signing_key))
        with pytest.raises(IdentityUnavailable):
            await provider.exchange(identity)


@pytest.mark.asyncio
async def test_provider_redirect_is_never_followed(signing_key):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://foreign.example/keys"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = KeycloakCredentials(settings(), client, "fixture-secret")
        with pytest.raises(IdentityUnavailable):
            await provider.verify(issue(signing_key))
    assert len(calls) == 1
