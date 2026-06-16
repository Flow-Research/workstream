from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.auth.dev import DevelopmentAuthVerifier
from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import Settings, get_settings
from app.core.permissions import PermissionDenied, require_any_role
from app.interfaces.auth import AuthVerificationError
from app.main import create_app


def _application_paths(app) -> set[str]:
    """Return concrete application paths across FastAPI router representations."""
    paths = set(app.openapi()["paths"])
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        route_contexts = getattr(route, "effective_route_contexts", None)
        if route_contexts is not None:
            paths.update(context.path for context in route_contexts())
    return paths


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_missing_bearer_token_is_rejected() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_invalid_bearer_token_is_rejected() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid bearer token"


async def test_valid_dev_token_resolves_actor_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "local")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "local-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "flow-subject-1")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "flow-dev-issuer")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_EMAIL", "worker@example.test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_DISPLAY_NAME", "Worker One")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "worker,reviewer")
    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer local-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["actor_id"]
    assert body["external_subject"] == "flow-subject-1"
    assert body["external_issuer"] == "flow-dev-issuer"
    assert body["email"] == "worker@example.test"
    assert body["display_name"] == "Worker One"
    assert body["roles"] == ["worker", "reviewer"]
    assert body["auth_source"] == "dev_mock"
    assert body["is_dev_auth"] is True
    assert body["audit_context"]["actor_id"] == body["actor_id"]
    assert body["audit_context"]["external_subject"] == "flow-subject-1"
    assert body["audit_context"]["external_issuer"] == "flow-dev-issuer"
    assert body["audit_context"]["auth_source"] == "dev_mock"
    assert body["audit_context"]["is_dev_auth"] is True


async def test_actor_id_uses_subject_and_issuer_not_email() -> None:
    first = Settings(
        environment="local",
        auth_provider="dev",
        dev_auth_token="local-token",
        dev_auth_subject="same-subject",
        dev_auth_issuer="same-issuer",
        dev_auth_email="first@example.test",
    )
    second = Settings(
        environment="local",
        auth_provider="dev",
        dev_auth_token="local-token",
        dev_auth_subject="same-subject",
        dev_auth_issuer="same-issuer",
        dev_auth_email="second@example.test",
    )

    first_actor = await DevelopmentAuthVerifier(first).verify(first.dev_auth_token)
    second_actor = await DevelopmentAuthVerifier(second).verify(second.dev_auth_token)

    assert first_actor.actor_id == second_actor.actor_id
    assert first_actor.email != second_actor.email


@pytest.mark.parametrize("environment", ["production", "prod", "staging", "preview"])
def test_dev_auth_requires_explicit_development_environment(environment: str) -> None:
    settings = Settings(
        environment=environment,
        auth_provider="dev",
        dev_auth_token="local-token",
        dev_auth_subject="subject",
        dev_auth_issuer="issuer",
    )

    with pytest.raises(RuntimeError, match="development auth cannot run in production"):
        DevelopmentAuthVerifier(settings)


@pytest.mark.parametrize("environment", ["local", "dev", "development", "test"])
def test_dev_auth_allows_only_development_environments(environment: str) -> None:
    verifier = DevelopmentAuthVerifier(
        Settings(
            environment=environment,
            auth_provider="dev",
            dev_auth_token="local-token",
            dev_auth_subject="subject",
            dev_auth_issuer="issuer",
        )
    )

    assert verifier


@pytest.mark.parametrize(
    ("field_name", "error_message"),
    [
        ("dev_auth_token", "WORKSTREAM_DEV_AUTH_TOKEN must be set"),
        ("dev_auth_subject", "WORKSTREAM_DEV_AUTH_SUBJECT must be set"),
        ("dev_auth_issuer", "WORKSTREAM_DEV_AUTH_ISSUER must be set"),
    ],
)
def test_dev_auth_requires_explicit_identity_fields(
    field_name: str,
    error_message: str,
) -> None:
    values = {
        "environment": "local",
        "auth_provider": "dev",
        "dev_auth_token": "local-token",
        "dev_auth_subject": "subject",
        "dev_auth_issuer": "issuer",
    }
    values[field_name] = None
    settings = Settings(**values)

    with pytest.raises(RuntimeError, match=error_message):
        DevelopmentAuthVerifier(settings)


async def test_flow_auth_verifier_boundary_rejects_unconfigured_verification() -> None:
    verifier = FlowAuthVerifier(Settings(auth_provider="flow"))

    with pytest.raises(AuthVerificationError, match="Flow token verification is not configured"):
        await verifier.verify("flow-token")


async def test_permission_policy_allows_required_role() -> None:
    actor = await DevelopmentAuthVerifier(
        Settings(
            environment="local",
            auth_provider="dev",
            dev_auth_token="local-token",
            dev_auth_subject="subject",
            dev_auth_issuer="issuer",
            dev_auth_roles="worker,reviewer",
        )
    ).verify("local-token")

    require_any_role(actor, {"reviewer"})


async def test_permission_policy_rejects_missing_role() -> None:
    actor = await DevelopmentAuthVerifier(
        Settings(
            environment="local",
            auth_provider="dev",
            dev_auth_token="local-token",
            dev_auth_subject="subject",
            dev_auth_issuer="issuer",
            dev_auth_roles="worker",
        )
    ).verify("local-token")

    with pytest.raises(PermissionDenied, match="actor lacks required role"):
        require_any_role(actor, {"finance"})


async def test_no_local_login_password_or_session_routes() -> None:
    app = create_app()
    paths = {path.lower() for path in _application_paths(app)}
    forbidden_segments = {
        "login",
        "signup",
        "register",
        "password",
        "password-reset",
        "session",
        "sessions",
    }

    assert "/api/v1/auth/me" in paths
    assert not any(
        segment in forbidden_segments
        for path in paths
        for segment in path.strip("/").split("/")
    )
