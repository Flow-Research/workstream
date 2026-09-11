from __future__ import annotations


import pytest  # type: ignore[import-not-found]
from httpx import (  # type: ignore[import-not-found]
    ASGITransport,
    AsyncClient,
)

from app.core.config import Settings
from app.main import create_app


async def test_missing_bearer_token_is_rejected() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/actors/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"] == {
        "code": "missing_token",
        "message": "Missing bearer token",
        "details": {},
        "correlation_id": response.headers["x-correlation-id"],
        "retryable": False,
    }


async def test_invalid_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "expected-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "issuer")
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/actors/me",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid bearer token"
    assert response.json()["error"]["code"] == "invalid_token"
    assert response.json()["error"]["retryable"] is False


async def test_invalid_production_verifier_configuration_is_service_unavailable() -> None:
    app = create_app(Settings(
        _env_file=None,
        environment="production",
        auth_provider="flow",
        flow_auth_local_hmac_secret=None,
        token_issuer=None,
    ))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/actors/me",
            headers={"Authorization": "Bearer opaque-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Identity verification unavailable"
    assert response.json()["error"]["code"] == "identity_verification_unavailable"
    assert response.json()["error"]["retryable"] is True
