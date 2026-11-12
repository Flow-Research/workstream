from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import httpx2
import jwt
import pytest
from conftest import profile_fixture
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from workstream_mcp.adapters.keycloak import KeycloakCredentials
from workstream_mcp.config import Settings
from workstream_mcp.oauth import OAuthSettings
from workstream_mcp.server import create_app

ISSUER = "https://identity.example/realms/flow"
RESOURCE = "https://workstream.example/mcp"


@pytest.fixture
def oauth_transport(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    provider_requests = []
    api_requests = []
    controls = {"status": 200}
    settings = Settings(
        api_url="http://127.0.0.1:8000",
        oauth=OAuthSettings(ISSUER, RESOURCE, Path("/run/secrets/not-read-by-fixture")),
    )

    def token(subject, *, api=False):
        now = int(time.time())
        return jwt.encode(
            dict(
                iss=ISSUER,
                sub=subject,
                aud="workstream-api" if api else [RESOURCE, "workstream-mcp"],
                iat=now,
                exp=now + (120 if api else 300),
                jti="fixture-token-id",
                azp="workstream-mcp" if api else "garden-client",
                typ="Bearer",
                subject_kind="human",
                scope="workstream:access",
            ),
            key,
            algorithm="RS256",
            headers={"kid": "fixture-key"},
        )

    def provider(request):
        provider_requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"keys": [{**public, "kid": "fixture-key", "use": "sig", "alg": "RS256"}]}
            )
        source = parse_qs(request.content.decode())["subject_token"][0]
        claims = jwt.decode(source, key.public_key(), algorithms=["RS256"], audience=RESOURCE)
        return httpx.Response(
            200,
            json={
                "access_token": token(claims["sub"], api=True),
                "token_type": "Bearer",
                "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
        )

    @asynccontextmanager
    async def credentials(config):
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            yield KeycloakCredentials(config, client, "fixture-secret")

    def api(request):
        api_requests.append(request)
        claims = jwt.decode(
            request.headers["authorization"][7:],
            key.public_key(),
            algorithms=["RS256"],
            audience="workstream-api",
            issuer=ISSUER,
        )
        assert claims["aud"] == "workstream-api"
        if controls["status"] != 200:
            return httpx2.Response(403, json={"error": {"code": "identity_link_revoked"}})
        return httpx2.Response(200, json=profile_fixture(display_name=claims["sub"]))

    monkeypatch.setattr("workstream_mcp.server.create_credentials", credentials)
    monkeypatch.setattr(
        "workstream_mcp.server.create_http_client",
        lambda _: httpx2.AsyncClient(
            base_url="http://127.0.0.1:8000", transport=httpx2.MockTransport(api)
        ),
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8080") as client:
        yield client, token, provider_requests, api_requests, controls


def call(client, token):
    return client.post(
        "/mcp",
        headers={
            "authorization": "Bearer " + token,
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "workstream_profile_get", "arguments": {}},
        },
    )


def test_discovery_and_missing_auth_never_contact_provider(oauth_transport):
    client, _, provider, api, _ = oauth_transport
    metadata = client.get("/.well-known/oauth-protected-resource/mcp")
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == RESOURCE
    assert metadata.json()["authorization_servers"] == [ISSUER]
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401
    assert (
        'resource_metadata="https://workstream.example/.well-known/oauth-protected-resource/mcp"'
        in response.headers["www-authenticate"]
    )
    assert provider == api == []


def test_request_identity_is_exchanged_and_never_shared(oauth_transport):
    client, token, provider, api, _ = oauth_transport
    for subject in ("first-user", "second-user", "first-user"):
        source = token(subject)
        response = call(client, source)
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["display_name"] == subject
        assert api[-1].headers["authorization"] != "Bearer " + source
    assert len(api) == 3
    assert len([r for r in provider if r.method == "POST"]) == 3


def test_product_revocation_remains_effective_after_exchange(oauth_transport):
    client, token, _, api, controls = oauth_transport
    source = token("revoked-user")
    controls["status"] = 403
    response = call(client, source)
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "identity_link_revoked"
    assert len(api) == 1


def test_duplicate_bearers_are_rejected_before_identity_io(oauth_transport):
    client, token, provider, api, _ = oauth_transport
    response = client.post(
        "/mcp",
        headers=[
            ("authorization", "Bearer " + token("one")),
            ("authorization", "Bearer " + token("two")),
        ],
        json={},
    )
    assert response.status_code == 401
    assert provider == api == []
