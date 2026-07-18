from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import hmac
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
import httpx
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from fastapi import HTTPException

from app.adapters.auth.dev import DevelopmentAuthVerifier
from app.adapters.auth.flow import (
    FlowAuthVerifier,
    _normalize_audience,
    _normalize_scopes,
    actor_id_from_flow_identity,
)
from app.adapters.auth.metrics import InProcessAuthVerifierMetrics
from app.api.deps.auth import get_registered_actor
from app.core.auth import clear_auth_verifier_cache
from app.core.config import Settings, get_settings
from app.core.permissions import PermissionDenied, require_any_role
from app.db import session as db_session
from app.db.session import get_db_session
from app.interfaces.auth import AuthVerificationError, AuthVerificationUnavailableError
from app.main import create_app
from app.modules.audit.schemas import AuthorityEventType
from app.modules.audit.service import AuditService
from app.modules.actors.service import ActorService
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.repository import ActorRepository
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.models import AdminRoleGrant, AuthorityIdempotencyRecord
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.repository import (
    AdminAuthorizationRepository,
    AuthorityIdempotencyRepository,
)
from app.modules.authorization.schemas import derive_reason_digest
from app.modules.authorization.service_actor_service import (
    ServiceActorProvisioningService,
    ServiceActorProvisioningUnavailable,
)
from app.modules.projects.models import Project
from app.modules.tasks.models import AuditEvent
from app.schemas.auth import normalize_legacy_roles
from scripts.bootstrap_access_administrator import (
    BOOTSTRAP_COMMAND_MANIFEST,
    _run as run_admin_bootstrap,
)
from scripts import bootstrap_access_administrator as bootstrap_command


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


def test_legacy_submitter_eligibility_adapter_has_a_shrinking_static_allowlist() -> None:
    """Confine the temporary bridge to its owner, lifecycle view, and intake gates."""
    app_root = Path(__file__).resolve().parents[1] / "app"
    compatibility_name = "LegacyWorkflowEligibilityCompatibility"
    consumers: set[str] = set()
    for path in app_root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        defines_compatibility = any(
            isinstance(node, ast.ClassDef) and node.name == compatibility_name
            for node in ast.walk(tree)
        )
        imports_compatibility = any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == compatibility_name for alias in node.names)
            for node in ast.walk(tree)
        )
        calls_compatibility = any(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id == compatibility_name
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == compatibility_name
            )
            for node in ast.walk(tree)
        )
        if defines_compatibility or imports_compatibility or calls_compatibility:
            consumers.add(path.relative_to(app_root).as_posix())

    task_service_tree = ast.parse(
        (app_root / "modules/tasks/service.py").read_text(),
        filename="modules/tasks/service.py",
    )
    compatibility_calls: list[tuple[str, str]] = []
    task_service_class = next(
        node
        for node in task_service_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TaskService"
    )
    for method in task_service_class.body:
        if not isinstance(method, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        compatibility_calls.extend(
            (method.name, node.func.attr)
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {
                "_require_legacy_submitter_eligibility",
                "get_active_submitter_eligibility",
            }
        )

    assert consumers == {
        "modules/actors/service.py",
        "modules/tasks/service.py",
    }
    assert sorted(compatibility_calls) == [
        (
            "_require_legacy_submitter_eligibility",
            "get_active_submitter_eligibility",
        ),
        ("claim_task", "_require_legacy_submitter_eligibility"),
        ("create_submission", "_require_legacy_submitter_eligibility"),
        ("get_task_work_context", "get_active_submitter_eligibility"),
        ("start_task", "_require_legacy_submitter_eligibility"),
    ]


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    clear_auth_verifier_cache()
    yield
    get_settings.cache_clear()
    clear_auth_verifier_cache()


@pytest.fixture
def auth_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
    reset_test_database_state,
) -> Iterator[str]:
    """Run auth route persistence tests against a migrated Postgres schema."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())

    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    try:
        with migration_lock():
            command.downgrade(config, "base")
            try:
                command.upgrade(config, "head")
                yield postgres_database_url
            finally:
                try:
                    asyncio.run(
                        reset_test_database_state(
                            postgres_database_url,
                            include_canonical_actors=True,
                        )
                    )
                finally:
                    try:
                        asyncio.run(db_session.dispose_engine())
                    finally:
                        command.downgrade(config, "base")
    finally:
        try:
            asyncio.run(db_session.dispose_engine())
        finally:
            get_settings.cache_clear()


def _base64url_int(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(size, "big")).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def rsa_signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    return private_key, rsa_public_jwk(private_key, kid="issuer-key-1")


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
        "email": "must-not-enter-canonical@example.test",
        "name": "Must Not Enter Canonical",
    }
    if claims:
        payload.update(claims)
    for claim in remove_claims or ():
        payload.pop(claim, None)
    return jwt.encode(payload, private_key, algorithm=algorithm, headers={"kid": kid, "typ": "JWT"})


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
    assert result.legacy is not None
    assert result.legacy.roles == ("reviewer",)


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


async def test_asymmetric_token_returns_minimal_canonical_contract(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
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
    assert result.legacy is not None
    assert result.legacy.roles == ("admin", "reviewer")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].headers.get("authorization") is None
    assert requests[0].content == b""


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


async def test_jwks_cache_hit_avoids_second_network_request(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    metrics = InProcessAuthVerifierMetrics()
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
        metrics=metrics,
    )

    await verifier.verify(issue_asymmetric_token(private_key))
    await verifier.verify(issue_asymmetric_token(private_key, claims={"jti": "token-id-2"}))

    assert len(requests) == 1
    assert any(
        name == "workstream_auth_jwks_cache_total" and ("result", "hit") in labels
        for name, labels in metrics.snapshot()
    )


def test_verifier_metrics_enforce_closed_labels_without_identity_values() -> None:
    metrics = InProcessAuthVerifierMetrics()
    for result in ("success", "invalid", "unsupported_kind", "unavailable"):
        metrics.verification(result)  # type: ignore[arg-type]
    for result in ("hit", "miss", "negative_hit", "expired"):
        metrics.jwks_cache(result)  # type: ignore[arg-type]
    for result in ("success", "failure"):
        metrics.jwks_refresh(result)  # type: ignore[arg-type]
    for mode in ("disabled", "required"):
        for result in ("success", "inactive", "invalid", "unavailable", "skipped"):
            metrics.introspection(mode, result)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not allowed"):
        metrics.verification("opaque-subject-token-id")  # type: ignore[arg-type]

    snapshot = repr(metrics.snapshot())
    for forbidden in ("opaque-subject", "token-id", "https://", "client-secret", "BEGIN"):
        assert forbidden not in snapshot


async def test_unknown_kid_refreshes_once_then_uses_bounded_negative_cache(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
    )
    token = issue_asymmetric_token(private_key, kid="unknown-key")

    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(token)
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(token)

    assert len(requests) == 1


async def test_unknown_kid_refresh_is_single_flight(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
    )
    token = issue_asymmetric_token(private_key, kid="concurrent-unknown-key")

    results = await asyncio.gather(
        verifier.verify(token),
        verifier.verify(token),
        return_exceptions=True,
    )

    assert all(isinstance(result, AuthVerificationError) for result in results)
    assert len(requests) == 1


async def test_distinct_unknown_kids_share_one_refresh_generation(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
    )

    results = await asyncio.gather(
        verifier.verify(issue_asymmetric_token(private_key, kid="unknown-a")),
        verifier.verify(issue_asymmetric_token(private_key, kid="unknown-b")),
        return_exceptions=True,
    )

    assert all(isinstance(result, AuthVerificationError) for result in results)
    assert len(requests) == 1


async def test_jwks_lock_wait_is_inside_total_deadline(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material

    async def slow_jwks(request: Request) -> Response:
        await asyncio.sleep(0.6)
        return Response(200, json={"keys": [jwk]})

    verifier = FlowAuthVerifier(
        production_verifier_settings(token_jwks_total_timeout_seconds=0.5),
        jwks_transport=MockTransport(slow_jwks),
    )

    with pytest.raises(AuthVerificationUnavailableError, match="unavailable|timed out"):
        await verifier.verify(issue_asymmetric_token(private_key))


async def test_rotation_clears_matching_negative_kid() -> None:
    first_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    rotated_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    first_jwk = rsa_public_jwk(first_key, kid="first-key")
    rotated_jwk = rsa_public_jwk(rotated_key, kid="rotated-key")
    clock = [0.0]
    requests: list[Request] = []

    def rotating_jwks(request: Request) -> Response:
        requests.append(request)
        keys = [first_jwk] if len(requests) < 3 else [first_jwk, rotated_jwk]
        return Response(200, json={"keys": keys})

    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(rotating_jwks),
        monotonic=lambda: clock[0],
    )
    await verifier.verify(issue_asymmetric_token(first_key, kid="first-key"))
    clock[0] = 31.0
    rotated_token = issue_asymmetric_token(rotated_key, kid="rotated-key")
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(rotated_token)
    clock[0] = 62.0
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(issue_asymmetric_token(rotated_key, kid="rotation-trigger"))

    result = await verifier.verify(rotated_token)

    assert result.token.subject == "opaque-subject-1"
    assert len(requests) == 3


async def test_negative_kid_cache_is_ttl_and_size_bounded(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clock = [0.0]
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_unknown_kid_cache_max_entries=1),
        jwks_transport=jwks_transport(jwk),
        monotonic=lambda: clock[0],
    )
    await verifier.verify(issue_asymmetric_token(private_key))
    for kid in ("unknown-a", "unknown-b"):
        with pytest.raises(AuthVerificationError):
            await verifier.verify(issue_asymmetric_token(private_key, kid=kid))
    assert tuple(verifier._negative_kids) == ("unknown-b",)

    clock[0] = 31.0
    verifier._prune_negative_kids(clock[0])
    assert not verifier._negative_kids


async def test_expired_jwks_cache_refreshes_during_longer_unknown_kid_cooldown(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clock = [0.0]
    requests: list[Request] = []

    def outage_after_prime(request: Request) -> Response:
        requests.append(request)
        if len(requests) == 1:
            return Response(200, json={"keys": [jwk]})
        return Response(503)

    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_jwks_cache_ttl_seconds=30,
            token_unknown_kid_cache_ttl_seconds=300,
        ),
        jwks_transport=MockTransport(outage_after_prime),
        monotonic=lambda: clock[0],
    )
    token = issue_asymmetric_token(private_key)
    await verifier.verify(token)
    clock[0] = 31.0

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(token)
    clock[0] = 32.0
    with pytest.raises(AuthVerificationUnavailableError, match="cooling down"):
        await verifier.verify(token)

    assert len(requests) == 2


async def test_refresh_failure_cooldown_preserves_valid_cached_key_hits(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clock = [0.0]
    requests: list[Request] = []

    def outage_after_prime(request: Request) -> Response:
        requests.append(request)
        if len(requests) == 1:
            return Response(200, json={"keys": [jwk]})
        return Response(503)

    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(outage_after_prime),
        monotonic=lambda: clock[0],
    )
    valid_token = issue_asymmetric_token(private_key)
    await verifier.verify(valid_token)
    clock[0] = 31.0
    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key, kid="unknown-during-outage"))

    clock[0] = 32.0
    assert (await verifier.verify(valid_token)).token.token_id == "token-id-1"
    with pytest.raises(AuthVerificationUnavailableError, match="cooling down"):
        await verifier.verify(issue_asymmetric_token(private_key, kid="another-unknown"))
    assert len(requests) == 2


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


def test_flow_verifier_rejects_ambiguous_clients_and_malformed_claim_collections() -> None:
    """Keep provider inputs bounded before token or network processing begins."""
    assert UUID(actor_id_from_flow_identity("https://issuer.example", "opaque-subject"))
    assert _normalize_audience(["workstream-api", "secondary-api"]) == (
        "workstream-api",
        "secondary-api",
    )
    assert _normalize_scopes(["workstream:human", "profile:read"]) == frozenset(
        {"workstream:human", "profile:read"}
    )
    with pytest.raises(AuthVerificationError, match="audience"):
        _normalize_audience(["audience"] * 17)
    with pytest.raises(AuthVerificationError, match="audience"):
        _normalize_audience("a" * 257)
    with pytest.raises(AuthVerificationError, match="scope"):
        _normalize_scopes(["embedded whitespace"])
    with pytest.raises(AuthVerificationError, match="scope"):
        _normalize_scopes([f"scope-{index}" for index in range(65)])

    settings = production_verifier_settings()
    transport = MockTransport(lambda _request: Response(500))
    with pytest.raises(ValueError, match="JWKS transport"):
        FlowAuthVerifier(
            settings,
            jwks_transport=transport,
            jwks_client_factory=AsyncClient,
        )
    with pytest.raises(ValueError, match="introspection transport"):
        FlowAuthVerifier(
            settings,
            introspection_transport=transport,
            introspection_client_factory=AsyncClient,
        )

    with pytest.raises(ValueError, match="modulus"):
        FlowAuthVerifier._validate_jwk_strength({}, algorithm="RS256")
    with pytest.raises(ValueError, match="curve"):
        FlowAuthVerifier._validate_jwk_strength({"crv": "P-384"}, algorithm="ES256")
    with pytest.raises(ValueError, match="curve"):
        FlowAuthVerifier._validate_jwk_strength({"crv": "X25519"}, algorithm="EdDSA")


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


async def test_service_and_agent_tokens_receive_no_legacy_authority(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk),
    )

    service = await verifier.verify(
        issue_asymmetric_token(
            private_key,
            subject_kind="service",
            scope="workstream:service",
        )
    )
    agent_token = issue_asymmetric_token(
        private_key,
        subject_kind="agent",
        scope="agent:identity",
    )
    agent = await verifier.verify(agent_token)
    space = await verifier.verify(
        issue_asymmetric_token(private_key, subject_kind="space", scope="space:identity")
    )

    assert service.legacy is None
    assert agent.legacy is None
    assert space.legacy is None
    with pytest.raises(HTTPException) as exc_info:
        await get_registered_actor(agent, None, None)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "unsupported_subject_kind"

    app = create_app(production_verifier_settings())
    app.state.auth_verifier = verifier

    async def no_database_session():
        yield None

    app.dependency_overrides[get_db_session] = no_database_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {agent_token}"},
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

    with pytest.raises(AuthVerificationError, match="service scope"):
        await verifier.verify(
            issue_asymmetric_token(
                private_key,
                subject_kind="service",
                scope="workstream:access",
            )
        )


async def test_jwks_unavailability_is_typed_and_redacted() -> None:
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(lambda request: Response(503, text="secret issuer body")),
    )
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    bearer = issue_asymmetric_token(private_key)

    with pytest.raises(AuthVerificationUnavailableError) as exc_info:
        await verifier.verify(bearer)

    assert bearer not in str(exc_info.value)
    assert "secret issuer body" not in str(exc_info.value)


@pytest.mark.parametrize(
    "jwks_payload",
    [
        {"keys": []},
        {"keys": [{"kid": "duplicate"}, {"kid": "duplicate"}]},
        {"keys": [{"kid": "wrong-use", "alg": "RS256", "kty": "RSA", "use": "enc"}]},
    ],
)
async def test_invalid_jwks_documents_fail_closed(jwks_payload: dict[str, Any]) -> None:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(lambda request: Response(200, json=jwks_payload)),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key))


async def test_weak_rsa_signing_key_is_rejected() -> None:
    weak_key = rsa.generate_private_key(public_exponent=65_537, key_size=1_024)
    weak_jwk = rsa_public_jwk(weak_key, kid="weak-key")
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(weak_jwk),
    )

    with pytest.warns(jwt.InsecureKeyLengthWarning):
        token = issue_asymmetric_token(weak_key, kid="weak-key")
    with pytest.raises(AuthVerificationUnavailableError, match="invalid"):
        await verifier.verify(token)


@pytest.mark.parametrize(
    "jwk_override",
    [
        {"kty": "EC"},
        {"alg": "RS512"},
        {"key_ops": ["sign"]},
        {"use": "enc"},
    ],
)
async def test_incompatible_jwk_metadata_is_rejected(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    jwk_override: dict[str, Any],
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport({**jwk, **jwk_override}),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key))


async def test_malformed_and_excessive_jwks_fail_closed(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    responses = [
        Response(200, content=b"not-json"),
        Response(200, json={"keys": [jwk, {**jwk, "kid": "second"}]}),
    ]
    for response, settings in (
        (responses[0], production_verifier_settings()),
        (responses[1], production_verifier_settings(token_jwks_max_keys=1)),
    ):
        verifier = FlowAuthVerifier(
            settings,
            jwks_transport=MockTransport(lambda request, response=response: response),
        )
        with pytest.raises(AuthVerificationUnavailableError):
            await verifier.verify(issue_asymmetric_token(private_key))


async def test_jwks_redirect_does_not_receive_or_forward_bearer(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, _ = rsa_signing_material
    requests: list[Request] = []

    def redirect(request: Request) -> Response:
        requests.append(request)
        return Response(302, headers={"location": "https://attacker.test/jwks"})

    bearer = issue_asymmetric_token(private_key)
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(redirect),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(bearer)

    assert len(requests) == 1
    assert requests[0].url.host == "issuer.example.test"
    assert requests[0].headers.get("authorization") is None
    assert requests[0].content == b""
    assert all(request.url.host != "attacker.test" for request in requests)


async def test_oversized_jwks_response_fails_before_json_buffering() -> None:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_jwks_max_response_bytes=1_024),
        jwks_transport=MockTransport(
            lambda request: Response(200, content=b"{" + b'"padding":"' + b"x" * 2_000 + b'"}')
        ),
    )

    with pytest.raises(AuthVerificationUnavailableError, match="exceeds"):
        await verifier.verify(issue_asymmetric_token(private_key))


async def test_required_introspection_is_separate_bound_and_no_redirect(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    jwks_requests: list[Request] = []
    introspection_requests: list[Request] = []

    def introspection_handler(request: Request) -> Response:
        introspection_requests.append(request)
        return Response(
            200,
            json={
                "active": True,
                "iss": "https://issuer.example.test",
                "sub": "opaque-subject-1",
                "aud": "workstream",
                "jti": "token-id-1",
            },
        )

    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
        ),
        jwks_transport=jwks_transport(jwk, jwks_requests),
        introspection_transport=MockTransport(introspection_handler),
    )
    bearer = issue_asymmetric_token(private_key)

    result = await verifier.verify(bearer)

    assert result.token.token_id == "token-id-1"
    assert len(jwks_requests) == 1
    assert jwks_requests[0].headers.get("authorization") is None
    assert bearer.encode() not in jwks_requests[0].content
    assert len(introspection_requests) == 1
    assert introspection_requests[0].method == "POST"
    assert introspection_requests[0].url.host == "introspection.example.test"
    assert introspection_requests[0].headers["authorization"].startswith("Basic ")
    assert bearer.encode() in introspection_requests[0].content

    redirect_requests: list[Request] = []

    def introspection_redirect(request: Request) -> Response:
        redirect_requests.append(request)
        return Response(302, headers={"location": "https://attacker.test/collect"})

    redirecting = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
        ),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(introspection_redirect),
    )
    with pytest.raises(AuthVerificationUnavailableError):
        await redirecting.verify(bearer)
    assert len(redirect_requests) == 1
    assert redirect_requests[0].url.host == "introspection.example.test"
    assert bearer.encode() in redirect_requests[0].content
    assert all(request.url.host != "attacker.test" for request in redirect_requests)


async def test_jwks_and_introspection_use_distinct_owned_client_factories(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clients: dict[str, list[AsyncClient]] = {"jwks": [], "introspection": []}

    def factory(name: str, transport: MockTransport):
        def build_client(**kwargs: Any) -> AsyncClient:
            client = AsyncClient(transport=transport, **kwargs)
            clients[name].append(client)
            return client

        return build_client

    introspection_transport = MockTransport(
        lambda request: Response(
            200,
            json={
                "active": True,
                "iss": "https://issuer.example.test",
                "sub": "opaque-subject-1",
                "aud": "workstream",
                "jti": "token-id-1",
            },
        )
    )
    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
        ),
        jwks_client_factory=factory("jwks", jwks_transport(jwk)),
        introspection_client_factory=factory("introspection", introspection_transport),
    )

    await verifier.verify(issue_asymmetric_token(private_key))

    assert len(clients["jwks"]) == 1
    assert len(clients["introspection"]) == 1
    assert clients["jwks"][0] is not clients["introspection"][0]
    assert clients["jwks"][0].is_closed
    assert clients["introspection"][0].is_closed


@pytest.mark.parametrize(
    "response_override",
    [
        {"active": False},
        {"iss": "https://other.example.test"},
        {"sub": "other-subject"},
        {"aud": "other-audience"},
        {"jti": "other-token-id"},
    ],
)
async def test_required_introspection_fails_closed_on_inactive_or_mismatch(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    response_override: dict[str, Any],
) -> None:
    private_key, jwk = rsa_signing_material
    response = {
        "active": True,
        "iss": "https://issuer.example.test",
        "sub": "opaque-subject-1",
        "aud": "workstream",
        "jti": "token-id-1",
    }
    response.update(response_override)
    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
        ),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(lambda request: Response(200, json=response)),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(issue_asymmetric_token(private_key))


@pytest.mark.parametrize("missing_field", ["iss", "sub", "aud", "jti"])
async def test_required_introspection_rejects_missing_identity_fields(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    missing_field: str,
) -> None:
    private_key, jwk = rsa_signing_material
    response = {
        "active": True,
        "iss": "https://issuer.example.test",
        "sub": "opaque-subject-1",
        "aud": "workstream",
        "jti": "token-id-1",
    }
    response.pop(missing_field)
    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
        ),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(lambda request: Response(200, json=response)),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(issue_asymmetric_token(private_key))


@pytest.mark.parametrize(
    "response",
    [
        Response(200, content=b"not-json-secret-response"),
        Response(200, content=b"x" * 300),
        Response(503, content=b"issuer-secret-response"),
    ],
)
async def test_introspection_response_failures_are_redacted(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    response: Response,
) -> None:
    private_key, jwk = rsa_signing_material
    bearer = issue_asymmetric_token(private_key)
    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
            token_introspection_max_response_bytes=256,
        ),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(lambda request: response),
    )

    with pytest.raises(AuthVerificationUnavailableError) as exc_info:
        await verifier.verify(bearer)

    error = exc_info.value
    assert error.__cause__ is None
    assert error.__context__ is None
    serialized_error = repr(vars(error)) + repr(error.args)
    for forbidden in (
        bearer,
        "client-secret",
        "not-json-secret-response",
        "issuer-secret-response",
    ):
        assert forbidden not in serialized_error


async def test_introspection_transport_error_drops_credential_bearing_exception(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    bearer = issue_asymmetric_token(private_key)

    def fail_with_request(request: Request) -> Response:
        raise httpx.ReadTimeout("transport-secret", request=request)

    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
        ),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(fail_with_request),
    )

    with pytest.raises(AuthVerificationUnavailableError) as exc_info:
        await verifier.verify(bearer)

    error = exc_info.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert bearer not in repr(vars(error))
    assert "client-secret" not in repr(vars(error))


async def test_introspection_total_timeout_fails_closed(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material

    async def slow_introspection(request: Request) -> Response:
        await asyncio.sleep(0.6)
        return Response(200, json={"active": True})

    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_introspection_mode="required",
            token_introspection_disabled_reason=None,
            token_introspection_url="https://introspection.example.test/oauth/introspect",
            token_introspection_client_id="workstream-client",
            token_introspection_client_secret="client-secret",
            token_introspection_total_timeout_seconds=0.5,
        ),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(slow_introspection),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key))


def test_legacy_compatibility_dependency_has_fixed_consumer_allowlist() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    sources = {
        path.relative_to(app_root).as_posix(): path.read_text() for path in app_root.rglob("*.py")
    }

    assert {path for path, source in sources.items() if "get_registered_actor" in source} == {
        "api/deps/auth.py",
        "api/routes/auth.py",
        "modules/checkers/router.py",
        "modules/projects/router.py",
        "modules/tasks/router.py",
    }
    assert {
        path for path, source in sources.items() if "get_auth_verification_result" in source
    } == {"api/deps/api_controls.py", "api/deps/auth.py", "api/deps/authorization.py"}
    assert {path for path, source in sources.items() if "AuthVerificationResult" in source} == {
        "adapters/auth/dev.py",
        "adapters/auth/flow.py",
        "api/deps/api_controls.py",
        "api/deps/auth.py",
        "api/deps/authorization.py",
        "api/deps/rate_controls.py",
        "core/auth.py",
        "interfaces/auth.py",
        "schemas/auth.py",
    }
    assert {
        path
        for path, source in sources.items()
        if "LegacyAuthorizationCompatibilityContext" in source
    } == {
        "adapters/auth/dev.py",
        "adapters/auth/flow.py",
        "schemas/auth.py",
    }
    assert {path for path, source in sources.items() if "result.legacy" in source} == {
        "api/deps/auth.py"
    }


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
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid bearer token"
    assert response.json()["error"]["code"] == "invalid_token"
    assert response.json()["error"]["retryable"] is False


async def test_invalid_production_verifier_configuration_is_service_unavailable() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer opaque-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Identity verification unavailable"
    assert response.json()["error"]["code"] == "identity_verification_unavailable"
    assert response.json()["error"]["retryable"] is True


async def test_valid_dev_token_resolves_actor_context(
    monkeypatch: pytest.MonkeyPatch,
    auth_database_env: str,
) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "local")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "local-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "flow-subject-1")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "flow-dev-issuer")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_EMAIL", "contributor@example.test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_DISPLAY_NAME", "Contributor One")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor,reviewer")
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
    assert body["email"] is None
    assert body["display_name"] is None
    assert body["roles"] == ["contributor", "reviewer"]
    assert body["auth_source"] == "dev_mock"
    assert body["is_dev_auth"] is True
    assert body["audit_context"]["actor_id"] == body["actor_id"]
    assert body["audit_context"]["external_subject"] == "flow-subject-1"
    assert body["audit_context"]["external_issuer"] == "flow-dev-issuer"
    assert body["audit_context"]["auth_source"] == "dev_mock"
    assert body["audit_context"]["is_dev_auth"] is True


async def test_signed_flow_token_authorizes_actor_self_read_and_update(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    app = create_app(settings)
    app.state.auth_verifier = verifier
    token = issue_asymmetric_token(
        private_key,
        claims={
            "sub": "signed-self-actor",
            "jti": "signed-self-token",
            "roles": ["admin", "project_manager", "reviewer"],
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        read = await client.get(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        updated = await client.patch(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"display_name": "Signed Contributor", "contact_email": "signed@example.test"},
        )

    assert read.status_code == 200, read.text
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "Signed Contributor"
    assert updated.json()["contact_email"] == "signed@example.test"
    assert updated.json()["admin_roles"] == []
    assert updated.json()["project_role_grants"] == []
    async with db_session.get_session_factory()() as session:
        events = (
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "authorization_decision")
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        ).all()
    assert [(event.action_id, event.permission_id, event.after_facts) for event in events] == [
        ("actor.profile.read_self", "actor.profile.read_self", {"allowed": True}),
        ("actor.profile.update_self", "actor.profile.update_self", {"allowed": True}),
    ]
    serialized = repr([event.event_payload for event in events])
    assert "signed@example.test" not in serialized
    assert token not in serialized


async def test_signed_tokens_bootstrap_and_admin_grant_lifecycle(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prove the supported bootstrap, grant, replay, scope, and revoke flow."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(
        settings,
        jwks_transport=jwks_transport(jwk),
    )
    admin_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth08-admin", "jti": "auth08-admin-token", "roles": ["viewer"]},
    )
    target_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth08-target", "jti": "auth08-target-token", "roles": ["admin"]},
    )
    audit_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth08-audit", "jti": "auth08-audit-token"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    target_headers = {"Authorization": f"Bearer {target_token}"}
    audit_headers = {"Authorization": f"Bearer {audit_token}"}
    original_commit = AsyncSession.commit
    fail_feature_commit = False
    fail_evidence_action: ActionId | None = None
    fail_target_lookup: str | None = None
    fail_touch = False
    original_add_authority_event = AuditService.add_authority_event
    original_profile_read = ActorService.read_admin_profile
    original_link_read = ActorService.read_admin_identity_link
    original_touch = ActorService.touch_after_authorization

    async def add_authority_event_with_failure(service, value):
        nonlocal fail_evidence_action
        if fail_evidence_action is not None and value.action_id is fail_evidence_action:
            fail_evidence_action = None
            raise SQLAlchemyError("forced authorization evidence failure")
        return await original_add_authority_event(service, value)

    async def profile_read_with_failure(service, actor_profile_id):
        nonlocal fail_target_lookup
        if fail_target_lookup == "profile":
            fail_target_lookup = None
            raise SQLAlchemyError("forced profile lookup failure")
        return await original_profile_read(service, actor_profile_id)

    async def link_read_with_failure(service, actor_profile_id):
        nonlocal fail_target_lookup
        if fail_target_lookup == "identity_link":
            fail_target_lookup = None
            raise SQLAlchemyError("forced identity-link lookup failure")
        return await original_link_read(service, actor_profile_id)

    async def touch_with_failure(service, resolved):
        nonlocal fail_touch
        if fail_touch:
            fail_touch = False
            raise SQLAlchemyError("forced caller timestamp touch failure")
        return await original_touch(service, resolved)

    async def commit_with_one_feature_failure(session: AsyncSession) -> None:
        nonlocal fail_feature_commit
        feature_rows = tuple(session.sync_session.new) + tuple(
            session.sync_session.identity_map.values()
        )
        if fail_feature_commit and any(
            isinstance(
                row,
                (ActorProfile, ActorIdentityLink, AdminRoleGrant, AuthorityIdempotencyRecord),
            )
            for row in feature_rows
        ):
            fail_feature_commit = False
            raise SQLAlchemyError("forced feature commit failure")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", commit_with_one_feature_failure)
    monkeypatch.setattr(AuditService, "add_authority_event", add_authority_event_with_failure)
    monkeypatch.setattr(ActorService, "read_admin_profile", profile_read_with_failure)
    monkeypatch.setattr(ActorService, "read_admin_identity_link", link_read_with_failure)
    monkeypatch.setattr(ActorService, "touch_after_authorization", touch_with_failure)

    async def actor_state(actor_id: UUID) -> tuple:
        async with db_session.get_session_factory()() as session:
            return tuple(
                (
                    await session.execute(
                        text(
                            "select p.display_name,p.last_seen_at,l.last_verified_at "
                            "from actor_profiles p join actor_identity_links l "
                            "on l.actor_profile_id=p.id where p.id=:actor"
                        ),
                        {"actor": str(actor_id)},
                    )
                ).one()
            )

    async def authority_counts() -> tuple[int, int, int]:
        async with db_session.get_session_factory()() as session:
            return (
                int(await session.scalar(select(func.count()).select_from(AdminRoleGrant)) or 0),
                int(
                    await session.scalar(
                        select(func.count()).select_from(AuthorityIdempotencyRecord)
                    )
                    or 0
                ),
                int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0),
            )

    def assert_retryable_service_unavailable(response: Response) -> None:
        assert response.status_code == 503
        error = response.json()["error"]
        assert set(error) == {"code", "message", "retryable", "correlation_id", "details"}
        assert error["code"] == "service_unavailable"
        assert error["message"] == "Service unavailable"
        assert error["retryable"] is True
        assert error["details"] == {}
        UUID(error["correlation_id"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        admin_profile = await client.get("/api/v1/actors/me", headers=admin_headers)
        target_profile = await client.get("/api/v1/actors/me", headers=target_headers)
        audit_profile = await client.get("/api/v1/actors/me", headers=audit_headers)
        assert admin_profile.status_code == target_profile.status_code == 200
        assert audit_profile.status_code == 200
        admin_id = UUID(admin_profile.json()["actor_profile_id"])
        target_id = UUID(target_profile.json()["actor_profile_id"])
        audit_id = UUID(audit_profile.json()["actor_profile_id"])

        token_role_denied = await client.get(
            "/api/v1/authorization/permissions",
            headers=admin_headers,
        )
        assert token_role_denied.status_code == 403
        assert token_role_denied.json()["error"]["code"] == "permission_not_granted"

        dry_run_code, dry_run = await run_admin_bootstrap(admin_id, execute=False)
        assert dry_run_code == 0
        assert dry_run == {
            "result_code": "eligible",
            "actor_profile_id": str(admin_id),
            "would_change": True,
        }

        exit_code, bootstrap = await run_admin_bootstrap(admin_id, execute=True)
        assert exit_code == 0
        assert bootstrap == {
            "result_code": "bootstrapped",
            "actor_profile_id": str(admin_id),
            "grant_id": bootstrap["grant_id"],
            "changed": True,
        }
        repeated_code, repeated = await run_admin_bootstrap(target_id, execute=True)
        assert repeated_code == 3
        assert repeated == {
            "result_code": "admin_role_grant_exists",
            "actor_profile_id": str(target_id),
            "grant_id": bootstrap["grant_id"],
            "changed": False,
        }
        concealed_targets = {
            "service": uuid4(),
            "suspended": uuid4(),
            "no_active_link": uuid4(),
        }
        private_provenance = {
            "created_by": f"auth09c-created-by-{uuid4()}",
            "linked_by": f"auth09c-linked-by-{uuid4()}",
            "lifecycle_by": f"auth09c-lifecycle-by-{uuid4()}",
        }
        project_one, project_two = uuid4(), uuid4()
        now = datetime.now(UTC)
        async with db_session.get_session_factory()() as session:
            target_row = await session.get(ActorProfile, str(target_id))
            assert target_row is not None
            target_row.contact_email = "auth09c-private-contact@example.test"
            session.add_all(
                [
                    Project(
                        id=str(project_one),
                        name="AUTH-08 scope one",
                        slug=f"auth08-scope-one-{project_one}",
                        status="draft",
                    ),
                    Project(
                        id=str(project_two),
                        name="AUTH-08 scope two",
                        slug=f"auth08-scope-two-{project_two}",
                        status="draft",
                    ),
                    ActorProfile(
                        id=str(concealed_targets["service"]),
                        actor_kind="service",
                        status="active",
                        provisioning_method="manual_service_provisioning",
                        service_identity="workstream.artifact.verifier",
                        created_by=private_provenance["created_by"],
                    ),
                    ActorProfile(
                        id=str(concealed_targets["suspended"]),
                        actor_kind="human",
                        status="suspended",
                        provisioning_method="automatic_first_access",
                        created_by=private_provenance["created_by"],
                        suspended_by=private_provenance["lifecycle_by"],
                        suspended_at=now,
                        suspension_reason="Concealment fixture",
                    ),
                    ActorProfile(
                        id=str(concealed_targets["no_active_link"]),
                        actor_kind="human",
                        status="active",
                        provisioning_method="automatic_first_access",
                        created_by=private_provenance["created_by"],
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ActorIdentityLink(
                        id=str(uuid4()),
                        actor_profile_id=str(concealed_targets["service"]),
                        issuer="https://identity.test",
                        subject="auth08-service-target",
                        subject_kind="service",
                        status="active",
                        linked_by=private_provenance["linked_by"],
                    ),
                    ActorIdentityLink(
                        id=str(uuid4()),
                        actor_profile_id=str(concealed_targets["suspended"]),
                        issuer="https://identity.test",
                        subject="auth08-suspended-target",
                        subject_kind="human",
                        status="active",
                        linked_by=private_provenance["linked_by"],
                        last_verified_at=now,
                    ),
                    ActorIdentityLink(
                        id=str(uuid4()),
                        actor_profile_id=str(concealed_targets["no_active_link"]),
                        issuer="https://identity.test",
                        subject="auth08-revoked-link-target",
                        subject_kind="human",
                        status="revoked",
                        linked_by=private_provenance["linked_by"],
                        last_verified_at=now,
                        revoked_by=private_provenance["lifecycle_by"],
                        revoked_at=now,
                        revoked_reason="Concealment fixture",
                    ),
                ]
            )
            await session.commit()

        profile_fields = {
            "actor_profile_id",
            "actor_kind",
            "status",
            "provisioning_method",
            "service_identity",
            "display_name",
            "created_at",
            "updated_at",
            "last_seen_at",
            "suspended_at",
            "reactivated_at",
            "deactivated_at",
        }
        link_fields = {
            "identity_link_id",
            "actor_profile_id",
            "subject_kind",
            "status",
            "linked_at",
            "last_verified_at",
            "revoked_at",
            "reactivated_at",
        }
        caplog.clear()
        caplog.set_level(logging.DEBUG, logger="app")
        before_admin_actor_read = await actor_state(admin_id)
        before_target_actor_read = await actor_state(target_id)
        target_admin_profile = await client.get(
            f"/api/v1/actors/{target_id}",
            headers=admin_headers,
        )
        target_admin_link = await client.get(
            f"/api/v1/actors/{target_id}/identity-links",
            headers=admin_headers,
        )
        service_admin_profile = await client.get(
            f"/api/v1/actors/{concealed_targets['service']}",
            headers=admin_headers,
        )
        service_admin_link = await client.get(
            f"/api/v1/actors/{concealed_targets['service']}/identity-links",
            headers=admin_headers,
        )
        suspended_admin_profile = await client.get(
            f"/api/v1/actors/{concealed_targets['suspended']}",
            headers=admin_headers,
        )
        revoked_admin_link = await client.get(
            f"/api/v1/actors/{concealed_targets['no_active_link']}/identity-links",
            headers=admin_headers,
        )
        assert [
            response.status_code
            for response in (
                target_admin_profile,
                target_admin_link,
                service_admin_profile,
                service_admin_link,
                suspended_admin_profile,
                revoked_admin_link,
            )
        ] == [200] * 6
        assert set(target_admin_profile.json()) == profile_fields
        assert set(target_admin_link.json()) == link_fields
        assert target_admin_profile.json()["actor_kind"] == "human"
        assert target_admin_profile.json()["service_identity"] is None
        assert service_admin_profile.json()["actor_kind"] == "service"
        assert service_admin_profile.json()["service_identity"] == (
            ServiceIdentity.ARTIFACT_VERIFIER.value
        )
        assert service_admin_profile.json()["last_seen_at"] is None
        assert service_admin_link.json()["last_verified_at"] is None
        assert suspended_admin_profile.json()["status"] == "suspended"
        assert revoked_admin_link.json()["status"] == "revoked"
        serialized_admin_reads = json.dumps(
            [
                target_admin_profile.json(),
                target_admin_link.json(),
                service_admin_profile.json(),
                service_admin_link.json(),
                suspended_admin_profile.json(),
                revoked_admin_link.json(),
            ],
            sort_keys=True,
        )
        for private_value in (
            "auth08-target",
            "auth08-service-target",
            "auth08-suspended-target",
            "auth08-revoked-link-target",
            "https://identity.test",
            "Concealment fixture",
            "auth09c-private-contact@example.test",
            admin_token,
            target_token,
            bootstrap["grant_id"],
            *private_provenance.values(),
        ):
            assert private_value not in serialized_admin_reads
            assert private_value not in caplog.text
        assert await actor_state(target_id) == before_target_actor_read
        after_admin_actor_read = await actor_state(admin_id)
        assert after_admin_actor_read[1] > before_admin_actor_read[1]
        assert after_admin_actor_read[2] > before_admin_actor_read[2]

        async with db_session.get_session_factory()() as session:
            target_allow_events = (
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                        AuditEvent.action_id.in_(
                            ("actor.profile.read", "actor.identity_link.read")
                        ),
                        AuditEvent.resource_id == str(target_id),
                    )
                )
            ).all()
        assert len(target_allow_events) == 2
        expected_evidence = {
            "actor.profile.read": ("actor.profile.read_any", target_admin_profile),
            "actor.identity_link.read": ("actor.identity_link.read", target_admin_link),
        }
        assert {event.action_id for event in target_allow_events} == set(expected_evidence)
        for event in target_allow_events:
            expected_permission, route_response = expected_evidence[event.action_id]
            assert event.permission_id == expected_permission
            assert event.actor_id == str(admin_id)
            assert event.target_actor_ref == str(target_id)
            assert event.target_ref_id == str(target_id)
            assert event.matched_grant_id == bootstrap["grant_id"]
            assert event.project_id is None
            assert event.after_facts == {"allowed": True}
            assert UUID(str(event.request_id)) == UUID(route_response.headers["x-request-id"])
            assert UUID(str(event.correlation_id)) == UUID(
                route_response.headers["x-correlation-id"]
            )

        async def actor_admin_state() -> tuple[datetime, datetime, datetime]:
            async with db_session.get_session_factory()() as session:
                return tuple(
                    (
                        await session.execute(
                            text(
                                "select p.updated_at,p.last_seen_at,l.last_verified_at "
                                "from actor_profiles p join actor_identity_links l "
                                "on l.actor_profile_id=p.id where p.id=:actor"
                            ),
                            {"actor": str(admin_id)},
                        )
                    ).one()
                )

        before_self_profile = await actor_admin_state()
        before_self_profile_counts = await authority_counts()
        self_profile = await client.get(
            f"/api/v1/actors/{admin_id}",
            headers=admin_headers,
        )
        assert self_profile.status_code == 200, self_profile.text
        after_self_profile = await actor_admin_state()
        assert after_self_profile[0] > before_self_profile[0]
        assert after_self_profile[1] > before_self_profile[1]
        assert after_self_profile[2] > before_self_profile[2]
        assert datetime.fromisoformat(self_profile.json()["updated_at"]) == after_self_profile[0]
        assert datetime.fromisoformat(self_profile.json()["last_seen_at"]) == after_self_profile[1]
        after_self_profile_counts = await authority_counts()
        assert after_self_profile_counts[:2] == before_self_profile_counts[:2]
        assert after_self_profile_counts[2] == before_self_profile_counts[2] + 1

        before_self_link = await actor_admin_state()
        before_self_link_counts = await authority_counts()
        self_link = await client.get(
            f"/api/v1/actors/{admin_id}/identity-links",
            headers=admin_headers,
        )
        assert self_link.status_code == 200, self_link.text
        after_self_link = await actor_admin_state()
        assert after_self_link[0] > before_self_link[0]
        assert after_self_link[1] > before_self_link[1]
        assert after_self_link[2] > before_self_link[2]
        assert datetime.fromisoformat(self_link.json()["last_verified_at"]) == after_self_link[2]
        after_self_link_counts = await authority_counts()
        assert after_self_link_counts[:2] == before_self_link_counts[:2]
        assert after_self_link_counts[2] == before_self_link_counts[2] + 1

        before_missing_reads = await actor_state(admin_id)
        before_missing_authority_counts = await authority_counts()
        absent_id = uuid4()
        missing_profile = await client.get(
            f"/api/v1/actors/{absent_id}",
            headers=admin_headers,
        )
        missing_link = await client.get(
            f"/api/v1/actors/{absent_id}/identity-links",
            headers=admin_headers,
        )
        assert missing_profile.status_code == missing_link.status_code == 404
        concealed_missing_bodies = []
        for response in (missing_profile, missing_link):
            body = response.json()
            UUID(body["error"].pop("correlation_id"))
            concealed_missing_bodies.append(body)
        assert concealed_missing_bodies[0] == concealed_missing_bodies[1]
        assert concealed_missing_bodies[0]["error"]["code"] == "actor_resource_not_found"
        assert await actor_state(admin_id) == before_missing_reads
        assert await authority_counts() == before_missing_authority_counts

        async def assert_failed_admin_read(path: str) -> None:
            before_failure_state = await actor_state(admin_id)
            before_failure_counts = await authority_counts()
            failed_response = await client.get(path, headers=admin_headers)
            assert_retryable_service_unavailable(failed_response)
            assert await actor_state(admin_id) == before_failure_state
            assert await authority_counts() == before_failure_counts

        profile_path = f"/api/v1/actors/{target_id}"
        link_path = f"/api/v1/actors/{target_id}/identity-links"
        for action_id, path in (
            (ActionId.ACTOR_PROFILE_READ, profile_path),
            (ActionId.ACTOR_IDENTITY_LINK_READ, link_path),
        ):
            fail_evidence_action = action_id
            await assert_failed_admin_read(path)

        for lookup_kind, path in (
            ("profile", profile_path),
            ("identity_link", link_path),
        ):
            fail_target_lookup = lookup_kind
            await assert_failed_admin_read(path)

        for path in (profile_path, link_path):
            fail_touch = True
            await assert_failed_admin_read(path)

        for path in (profile_path, link_path):
            fail_feature_commit = True
            await assert_failed_admin_read(path)

        before_read = await actor_state(admin_id)
        fail_feature_commit = True
        failed_read = await client.get(
            "/api/v1/authorization/permissions",
            headers=admin_headers,
        )
        assert_retryable_service_unavailable(failed_read)
        assert await actor_state(admin_id) == before_read

        permissions = await client.get(
            "/api/v1/authorization/permissions",
            headers=admin_headers,
        )
        definitions = await client.get(
            "/api/v1/authorization/admin-role-definitions",
            headers=admin_headers,
        )
        assert permissions.status_code == definitions.status_code == 200
        assert permissions.json()["total"] == 74
        assert len(permissions.json()["items"]) == 74
        assert definitions.json()["total"] == 5
        assert [item["role"] for item in definitions.json()["items"]] == [
            "access_administrator",
            "operator",
            "project_manager",
            "finance_authority",
            "audit_authority",
        ]
        after_read = await actor_state(admin_id)
        assert after_read[1] > before_read[1]
        assert after_read[2] > before_read[2]

        fail_feature_commit = True
        failed_patch = await client.patch(
            "/api/v1/actors/me",
            headers=admin_headers,
            json={"display_name": "AUTH-08 administrator"},
        )
        assert_retryable_service_unavailable(failed_patch)
        assert await actor_state(admin_id) == after_read
        successful_patch = await client.patch(
            "/api/v1/actors/me",
            headers=admin_headers,
            json={"display_name": "AUTH-08 administrator"},
        )
        assert successful_patch.status_code == 200
        after_patch = await actor_state(admin_id)
        assert after_patch[0] == "AUTH-08 administrator"
        assert after_patch[1] > after_read[1]
        assert after_patch[2] > after_read[2]

        self_grant = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(admin_id),
                "role": "operator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Must be rejected",
            },
        )
        invalid_role_scope = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(target_id),
                "role": "operator",
                "scope_type": "project",
                "scope_project_id": str(uuid4()),
                "reason": "Invalid role scope",
            },
        )
        oversized_reason = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(target_id),
                "role": "operator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "\u00e9" * 251,
            },
        )
        missing_target = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(uuid4()),
                "role": "operator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Absent target",
            },
        )
        assert self_grant.status_code == 403
        assert self_grant.json()["error"]["code"] == "self_grant_forbidden"
        assert invalid_role_scope.status_code == 422
        assert invalid_role_scope.json()["error"]["code"] == "invalid_role_scope"
        assert oversized_reason.status_code == 422
        assert oversized_reason.json()["error"]["code"] == "invalid_request"
        assert missing_target.status_code == 404
        assert missing_target.json()["error"]["code"] == "actor_not_found"
        concealed_responses = [missing_target]
        for target in concealed_targets.values():
            concealed_responses.append(
                await client.post(
                    "/api/v1/admin-role-grants",
                    headers={**admin_headers, "Idempotency-Key": str(uuid4())},
                    json={
                        "target_actor_profile_id": str(target),
                        "role": "operator",
                        "scope_type": "system",
                        "scope_project_id": None,
                        "reason": "Concealed ineligible target",
                    },
                )
            )
        assert [response.status_code for response in concealed_responses] == [404] * 4
        assert {
            (
                response.json()["detail"],
                response.json()["error"]["code"],
                response.json()["error"]["message"],
                response.json()["error"]["retryable"],
            )
            for response in concealed_responses
        } == {("Actor not found", "actor_not_found", "Actor not found", False)}
        async with db_session.get_session_factory()() as session:
            await session.execute(text("alter table actor_profiles disable trigger user"))
            await session.execute(
                text("alter table actor_identity_links disable trigger user")
            )
            await session.execute(
                text(
                    "update actor_profiles set status='active',suspended_by=null,"
                    "suspended_at=null,suspension_reason=null,reactivated_by=null,"
                    "reactivated_at=null,reactivation_reason=null where id=:actor"
                ),
                {"actor": str(concealed_targets["suspended"])},
            )
            await session.execute(
                text(
                    "update actor_identity_links set status='active',revoked_by=null,"
                    "revoked_at=null,revoked_reason=null,reactivated_by=null,"
                    "reactivated_at=null,reactivation_reason=null "
                    "where actor_profile_id=:actor"
                ),
                {"actor": str(concealed_targets["no_active_link"])},
            )
            await session.execute(text("alter table actor_identity_links enable trigger user"))
            await session.execute(text("alter table actor_profiles enable trigger user"))
            await session.commit()

        malformed_responses = [
            await client.get(
                "/api/v1/admin-role-grants",
                headers=admin_headers,
                params={"scope_type": "system", "status": "pending"},
            ),
            await client.get(
                "/api/v1/admin-role-grants",
                headers=admin_headers,
                params={"scope_type": "system", "limit": 0},
            ),
            await client.get(
                "/api/v1/admin-role-grants",
                headers=admin_headers,
                params={"scope_type": "system", "limit": 101},
            ),
            await client.get(
                "/api/v1/actors/not-a-uuid/admin-role-grants",
                headers=admin_headers,
                params={"scope_type": "system"},
            ),
            await client.post(
                "/api/v1/admin-role-grants",
                headers={**admin_headers, "Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": str(target_id),
                    "role": "administrator",
                    "scope_type": "system",
                    "scope_project_id": None,
                    "reason": "Unknown role",
                },
            ),
            await client.post(
                "/api/v1/admin-role-grants",
                headers={**admin_headers, "Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": str(target_id),
                    "role": "project_manager",
                    "scope_type": "organization",
                    "scope_project_id": None,
                    "reason": "Unknown scope",
                },
            ),
            await client.post(
                "/api/v1/admin-role-grants/not-a-uuid/revoke",
                headers={**admin_headers, "Idempotency-Key": str(uuid4())},
                json={"reason": "Malformed grant selector"},
            ),
        ]
        assert [response.status_code for response in malformed_responses] == [422] * 7
        assert {response.json()["error"]["code"] for response in malformed_responses} == {
            "invalid_request"
        }

        absent_project = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(target_id),
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": str(uuid4()),
                "reason": "Absent canonical project",
            },
        )
        assert absent_project.status_code == 404
        assert absent_project.json()["error"]["code"] == "resource_not_found"

        for actor_id, role in (
            (target_id, "project_manager"),
            (audit_id, "audit_authority"),
        ):
            response = await client.post(
                "/api/v1/admin-role-grants",
                headers={**admin_headers, "Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": str(actor_id),
                    "role": role,
                    "scope_type": "project",
                    "scope_project_id": str(project_one),
                    "reason": "Exact project authority proof",
                },
            )
            assert response.status_code == 201, response.text

        audit_visible = await client.get(
            "/api/v1/admin-role-grants",
            headers=audit_headers,
            params={"scope_type": "project", "scope_project_id": str(project_one)},
        )
        project_audit_actor_read = await client.get(
            f"/api/v1/actors/{target_id}",
            headers=audit_headers,
        )
        project_audit_link_read = await client.get(
            f"/api/v1/actors/{target_id}/identity-links",
            headers=audit_headers,
        )
        audit_wrong_scope = await client.get(
            "/api/v1/admin-role-grants",
            headers=audit_headers,
            params={"scope_type": "project", "scope_project_id": str(project_two)},
        )
        audit_mutation = await client.post(
            "/api/v1/admin-role-grants",
            headers={**audit_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(audit_id),
                "role": "operator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Audit authority is read-only",
            },
        )
        audit_history_visible = await client.get(
            f"/api/v1/actors/{target_id}/admin-role-grants",
            headers=audit_headers,
            params={"scope_type": "project", "scope_project_id": str(project_one)},
        )
        assert audit_visible.status_code == 200
        assert audit_visible.json()["total"] == 2
        assert {item["scope_project_id"] for item in audit_visible.json()["items"]} == {
            str(project_one)
        }
        assert audit_wrong_scope.status_code == audit_mutation.status_code == 403
        for project_audit_read in (project_audit_actor_read, project_audit_link_read):
            assert project_audit_read.status_code == 403
            assert project_audit_read.json()["error"]["code"] == "permission_not_granted"
        assert audit_wrong_scope.json()["error"]["code"] == "scope_not_authorized"
        assert audit_mutation.json()["error"]["code"] == "permission_not_granted"
        assert audit_history_visible.status_code == 200
        assert audit_history_visible.json()["total"] == 1
        assert audit_history_visible.json()["items"][0]["target_actor_profile_id"] == str(
            target_id
        )

        system_audit_grant = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(audit_id),
                "role": "audit_authority",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "System audit custody proof",
            },
        )
        assert system_audit_grant.status_code == 201, system_audit_grant.text
        system_audit_reads = [
            await client.get("/api/v1/authorization/permissions", headers=audit_headers),
            await client.get(
                "/api/v1/authorization/admin-role-definitions",
                headers=audit_headers,
            ),
            await client.get(
                "/api/v1/admin-role-grants",
                headers=audit_headers,
                params={"scope_type": "system", "status": "all"},
            ),
            await client.get(
                f"/api/v1/actors/{audit_id}/admin-role-grants",
                headers=audit_headers,
                params={"scope_type": "system", "status": "all"},
            ),
            await client.get(f"/api/v1/actors/{target_id}", headers=audit_headers),
            await client.get(
                f"/api/v1/actors/{target_id}/identity-links",
                headers=audit_headers,
            ),
        ]
        assert [response.status_code for response in system_audit_reads] == [200] * 6
        assert system_audit_reads[0].json()["total"] == 74
        assert system_audit_reads[1].json()["total"] == 5
        assert system_audit_reads[2].json()["total"] == 2
        assert system_audit_reads[3].json()["total"] == 1

        key = str(uuid4())
        issue_payload = {
            "target_actor_profile_id": str(target_id),
            "role": "operator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "On-call operations coverage",
        }
        before_failed_issue = await authority_counts()
        before_failed_issue_actor = await actor_state(admin_id)
        fail_feature_commit = True
        failed_issue = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": key},
            json=issue_payload,
        )
        assert_retryable_service_unavailable(failed_issue)
        assert await authority_counts() == before_failed_issue
        assert await actor_state(admin_id) == before_failed_issue_actor
        issued = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": key},
            json=issue_payload,
        )
        after_issue_actor = await actor_state(admin_id)
        assert after_issue_actor[1] > before_failed_issue_actor[1]
        assert after_issue_actor[2] > before_failed_issue_actor[2]
        replayed = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": key},
            json=issue_payload,
        )
        assert issued.status_code == 201, issued.text
        assert replayed.status_code == 201, replayed.text
        assert issued.json() == replayed.json()
        grant_id = issued.json()["resource_id"]

        mismatch = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": key},
            json=issue_payload | {"reason": "Different request"},
        )
        duplicate = await client.post(
            "/api/v1/admin-role-grants",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=issue_payload,
        )
        assert mismatch.status_code == 409, mismatch.text
        assert mismatch.json()["error"]["code"] == "idempotency_mismatch"
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "admin_role_grant_exists"

        listed = await client.get(
            "/api/v1/admin-role-grants",
            headers=admin_headers,
            params={"scope_type": "system", "status": "all"},
        )
        history = await client.get(
            f"/api/v1/actors/{target_id}/admin-role-grants",
            headers=admin_headers,
            params={"scope_type": "system", "status": "all"},
        )
        assert listed.status_code == history.status_code == 200
        assert listed.json()["total"] == 3
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["grant_reason"] == issue_payload["reason"]
        serialized = json.dumps(history.json(), sort_keys=True)
        assert "auth08-target" not in serialized
        assert target_token not in serialized

        invalid_scope = await client.get(
            "/api/v1/admin-role-grants",
            headers=admin_headers,
            params={"scope_type": "system", "scope_project_id": str(uuid4())},
        )
        invalid_cursor = await client.get(
            "/api/v1/admin-role-grants",
            headers=admin_headers,
            params={"scope_type": "system", "cursor": "not-a-cursor"},
        )
        first_page = await client.get(
            "/api/v1/admin-role-grants",
            headers=admin_headers,
            params={"scope_type": "system", "status": "all", "limit": 1},
        )
        malformed_valid_cursor = await client.get(
            "/api/v1/admin-role-grants",
            headers=admin_headers,
            params={
                "scope_type": "system",
                "cursor": first_page.json()["next_cursor"] + "$",
            },
        )
        assert invalid_scope.status_code == invalid_cursor.status_code == 400
        missing_project_scope = await client.get(
            "/api/v1/admin-role-grants",
            headers=admin_headers,
            params={"scope_type": "project"},
        )
        assert missing_project_scope.status_code == 400
        assert missing_project_scope.json()["error"]["code"] == "invalid_request"
        assert malformed_valid_cursor.status_code == 400
        assert invalid_scope.json()["error"]["code"] == "invalid_request"
        assert invalid_cursor.json()["error"]["code"] == "invalid_request"

        target_self = await client.get("/api/v1/actors/me", headers=target_headers)
        target_definitions = await client.get(
            "/api/v1/authorization/admin-role-definitions",
            headers=target_headers,
        )
        assert target_self.json()["admin_roles"] == ["operator", "project_manager"]
        assert target_definitions.status_code == 403
        assert target_definitions.json()["error"]["code"] == "permission_not_granted"

        revoke_key = str(uuid4())
        before_failed_revoke = await authority_counts()
        before_failed_revoke_actor = await actor_state(admin_id)
        fail_feature_commit = True
        failed_revoke = await client.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers={**admin_headers, "Idempotency-Key": revoke_key},
            json={"reason": "On-call rotation ended"},
        )
        assert_retryable_service_unavailable(failed_revoke)
        assert await authority_counts() == before_failed_revoke
        assert await actor_state(admin_id) == before_failed_revoke_actor
        revoked = await client.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers={**admin_headers, "Idempotency-Key": revoke_key},
            json={"reason": "On-call rotation ended"},
        )
        after_revoke_actor = await actor_state(admin_id)
        assert after_revoke_actor[1] > before_failed_revoke_actor[1]
        assert after_revoke_actor[2] > before_failed_revoke_actor[2]
        revoke_replay = await client.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers={**admin_headers, "Idempotency-Key": revoke_key},
            json={"reason": "On-call rotation ended"},
        )
        assert revoked.status_code == revoke_replay.status_code == 200
        assert revoked.json() == revoke_replay.json()
        assert revoked.json()["version"] == 2

        before_revoke_mismatch = await authority_counts()
        revoke_mismatch = await client.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers={**admin_headers, "Idempotency-Key": revoke_key},
            json={"reason": "Different revoke request"},
        )
        after_revoke_mismatch = await authority_counts()
        assert revoke_mismatch.status_code == 409
        assert revoke_mismatch.json()["error"]["code"] == "idempotency_mismatch"
        assert after_revoke_mismatch[:2] == before_revoke_mismatch[:2]
        assert after_revoke_mismatch[2] == before_revoke_mismatch[2] + 1

        revoked_new_key = await client.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Already revoked"},
        )
        absent_grant = await client.post(
            f"/api/v1/admin-role-grants/{uuid4()}/revoke",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Absent grant"},
        )
        self_revoke = await client.post(
            f"/api/v1/admin-role-grants/{bootstrap['grant_id']}/revoke",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Must be rejected"},
        )
        assert revoked_new_key.status_code == absent_grant.status_code == 404
        assert revoked_new_key.json()["error"]["code"] == "grant_not_found"
        concealed_grant_bodies = []
        for response in (revoked_new_key, absent_grant):
            body = response.json()
            UUID(body["error"].pop("correlation_id"))
            concealed_grant_bodies.append(body)
        assert concealed_grant_bodies[0] == concealed_grant_bodies[1]
        assert self_revoke.status_code == 403
        assert self_revoke.json()["error"]["code"] == "self_role_revoke_forbidden"

        target_after = await client.get("/api/v1/actors/me", headers=target_headers)
        assert target_after.json()["admin_roles"] == ["project_manager"]
    async with db_session.get_session_factory()() as session:
        lifecycle_counts = dict(
            (
                await session.execute(
                    select(AuditEvent.event_type, func.count())
                    .where(
                        AuditEvent.event_type.in_(
                            [
                                "InitialAccessAdministratorBootstrapped",
                                "AdminRoleGrantIssued",
                                "AdminRoleGrantRevoked",
                                "AuthorityInvalidationRequested",
                            ]
                        )
                    )
                    .group_by(AuditEvent.event_type)
                )
            ).all()
        )
    assert lifecycle_counts == {
        "InitialAccessAdministratorBootstrapped": 1,
        "AdminRoleGrantIssued": 4,
        "AdminRoleGrantRevoked": 1,
        "AuthorityInvalidationRequested": 5,
    }
    await db_session.dispose_engine()


def test_bootstrap_command_manifest_matches_the_active_catalogue() -> None:
    assert BOOTSTRAP_COMMAND_MANIFEST.action_id.value == "admin_role_grant.bootstrap"
    assert BOOTSTRAP_COMMAND_MANIFEST.permission_id.value == "admin_role.grant"
    assert BOOTSTRAP_COMMAND_MANIFEST.principal == "workstream:system:bootstrap"


def test_bootstrap_cli_preserves_committed_outcome_when_engine_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    actor_id, grant_id = uuid4(), uuid4()

    async def successful_run(_actor_profile_id: UUID, *, execute: bool):
        assert execute is True
        return 0, {
            "result_code": "bootstrapped",
            "actor_profile_id": str(actor_id),
            "grant_id": str(grant_id),
            "changed": True,
        }

    async def failed_cleanup() -> None:
        raise RuntimeError("forced cleanup failure")

    monkeypatch.setattr(bootstrap_command, "_run", successful_run)
    monkeypatch.setattr(bootstrap_command, "dispose_engine", failed_cleanup)

    assert bootstrap_command.main(["--actor-profile-id", str(actor_id), "--execute"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "result_code": "bootstrapped",
        "actor_profile_id": str(actor_id),
        "grant_id": str(grant_id),
        "changed": True,
    }


def test_bootstrap_cli_does_not_relabel_internal_type_error_as_invalid_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def broken_run(_actor_profile_id: UUID, *, execute: bool):
        assert execute is True
        raise TypeError("forced internal contract failure")

    async def clean_disposal() -> None:
        return None

    monkeypatch.setattr(bootstrap_command, "_run", broken_run)
    monkeypatch.setattr(bootstrap_command, "dispose_engine", clean_disposal)

    assert bootstrap_command.main(["--actor-profile-id", str(uuid4()), "--execute"]) == 1
    assert json.loads(capsys.readouterr().out) == {"result_code": "infrastructure_failure"}


@pytest.mark.parametrize(
    ("argv", "expected_code", "expected_result"),
    [
        ([], 2, "invalid_request"),
        (["--actor-profile-id", "not-a-uuid", "--execute"], 2, "invalid_request"),
        (
            ["--actor-profile-id", str(uuid4()), "--dry-run", "--execute"],
            2,
            "invalid_request",
        ),
    ],
)
def test_bootstrap_cli_rejects_arguments_without_echoing_them(
    argv: list[str],
    expected_code: int,
    expected_result: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def clean_disposal() -> None:
        return None

    monkeypatch.setattr(bootstrap_command, "dispose_engine", clean_disposal)
    assert bootstrap_command.main(argv) == expected_code
    assert json.loads(capsys.readouterr().out) == {"result_code": expected_result}


def test_bootstrap_cli_reports_interrupt_and_pre_outcome_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    actor_id = uuid4()
    calls = 0

    def interrupted_then_clean(coroutine):
        nonlocal calls
        calls += 1
        coroutine.close()
        if calls == 1:
            raise KeyboardInterrupt
        return None

    monkeypatch.setattr(bootstrap_command.asyncio, "run", interrupted_then_clean)
    assert bootstrap_command.main(["--actor-profile-id", str(actor_id), "--execute"]) == 1
    assert json.loads(capsys.readouterr().out) == {"result_code": "interrupted"}

    calls = 0

    def failed_before_and_during_cleanup(coroutine):
        nonlocal calls
        calls += 1
        coroutine.close()
        raise RuntimeError(f"failure-{calls}")

    monkeypatch.setattr(bootstrap_command.asyncio, "run", failed_before_and_during_cleanup)
    assert bootstrap_command.main(["--actor-profile-id", str(actor_id), "--execute"]) == 1
    assert json.loads(capsys.readouterr().out) == {"result_code": "infrastructure_failure"}


async def test_admin_bootstrap_replay_and_cross_revoke_are_concurrency_safe(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use independent request sessions and barriers to prove serialized authority."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    tokens = {
        name: issue_asymmetric_token(
            private_key,
            claims={"sub": f"auth08-race-{name}", "jti": f"auth08-race-{name}-token"},
        )
        for name in (
            "one",
            "two",
            "target",
            "duplicate",
            "pm-target-one",
            "pm-target-two",
        )
    }
    headers = {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        profiles = {
            name: UUID(
                (await client.get("/api/v1/actors/me", headers=actor_headers)).json()[
                    "actor_profile_id"
                ]
            )
            for name, actor_headers in headers.items()
        }

        original_lock_control = AdminAuthorizationRepository.lock_control
        bootstrap_ready = asyncio.Event()
        bootstrap_arrivals = 0

        async def barrier_lock_control(self):
            nonlocal bootstrap_arrivals
            bootstrap_arrivals += 1
            if bootstrap_arrivals == 2:
                bootstrap_ready.set()
            await bootstrap_ready.wait()
            return await original_lock_control(self)

        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            barrier_lock_control,
        )
        bootstrap_results = await asyncio.gather(
            run_admin_bootstrap(profiles["one"], execute=True),
            run_admin_bootstrap(profiles["two"], execute=True),
        )
        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            original_lock_control,
        )
        assert sorted(code for code, _ in bootstrap_results) == [0, 3]
        winner_index = next(
            index for index, (code, _result) in enumerate(bootstrap_results) if code == 0
        )
        winner_name = ("one", "two")[winner_index]
        other_name = ("two", "one")[winner_index]
        bootstrap_grant_id = bootstrap_results[winner_index][1]["grant_id"]

        async def read_winner_timestamps() -> tuple[datetime, datetime]:
            async with db_session.get_session_factory()() as session:
                return tuple(
                    (
                        await session.execute(
                            text(
                                "select p.last_seen_at,l.last_verified_at "
                                "from actor_profiles p join actor_identity_links l "
                                "on l.actor_profile_id=p.id where p.id=:actor"
                            ),
                            {"actor": str(profiles[winner_name])},
                        )
                    ).one()
                )

        timestamps_before = await read_winner_timestamps()
        original_touch_verified_actor = ActorRepository.touch_verified_actor
        original_commit = AsyncSession.commit
        older_touch_ready = asyncio.Event()
        newer_committed = asyncio.Event()
        newer_committed_timestamps: tuple[datetime, datetime] | None = None

        async def barrier_touch_verified_actor(self, profile, link):
            if asyncio.current_task().get_name() == "auth08-older-timestamp-read":
                older_touch_ready.set()
                await newer_committed.wait()
            return await original_touch_verified_actor(self, profile, link)

        async def ordered_commit(session: AsyncSession) -> None:
            nonlocal newer_committed_timestamps
            await original_commit(session)
            if asyncio.current_task().get_name() == "auth08-newer-timestamp-read":
                newer_committed_timestamps = await read_winner_timestamps()
                newer_committed.set()

        monkeypatch.setattr(
            ActorRepository,
            "touch_verified_actor",
            barrier_touch_verified_actor,
        )
        monkeypatch.setattr(AsyncSession, "commit", ordered_commit)
        older_read = asyncio.create_task(
            client.get(
                "/api/v1/authorization/permissions",
                headers=headers[winner_name],
            ),
            name="auth08-older-timestamp-read",
        )
        await older_touch_ready.wait()
        newer_read = asyncio.create_task(
            client.get(
                "/api/v1/authorization/permissions",
                headers=headers[winner_name],
            ),
            name="auth08-newer-timestamp-read",
        )
        try:
            crossed_reads = await asyncio.gather(older_read, newer_read)
        finally:
            monkeypatch.setattr(
                ActorRepository,
                "touch_verified_actor",
                original_touch_verified_actor,
            )
            monkeypatch.setattr(AsyncSession, "commit", original_commit)
        assert [response.status_code for response in crossed_reads] == [200, 200]
        assert newer_committed_timestamps is not None
        timestamps_after = await read_winner_timestamps()
        async with db_session.get_session_factory()() as session:
            crossed_allow_count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action_id == "authorization.permission_catalogue.read",
                    AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                )
            )
        assert timestamps_after[0] > timestamps_before[0]
        assert timestamps_after[1] > timestamps_before[1]
        assert timestamps_after[0] >= newer_committed_timestamps[0]
        assert timestamps_after[1] >= newer_committed_timestamps[1]
        assert crossed_allow_count == 2

        original_reserve = AuthorityIdempotencyRepository.reserve
        reserve_ready = asyncio.Event()
        reserve_arrivals = 0

        async def barrier_reserve(self, **kwargs):
            nonlocal reserve_arrivals
            reserve_arrivals += 1
            if reserve_arrivals == 2:
                reserve_ready.set()
            await reserve_ready.wait()
            return await original_reserve(self, **kwargs)

        monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", barrier_reserve)
        replay_key = str(uuid4())
        operator_payload = {
            "target_actor_profile_id": str(profiles["target"]),
            "role": "operator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "Concurrent replay proof",
        }
        replay_responses = await asyncio.gather(
            *(
                client.post(
                    "/api/v1/admin-role-grants",
                    headers={**headers[winner_name], "Idempotency-Key": replay_key},
                    json=operator_payload,
                )
                for _ in range(2)
            )
        )
        monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", original_reserve)
        assert [response.status_code for response in replay_responses] == [201, 201]
        assert replay_responses[0].json() == replay_responses[1].json()

        duplicate_ready = asyncio.Event()
        duplicate_arrivals = 0

        async def duplicate_barrier_lock_control(self):
            nonlocal duplicate_arrivals
            duplicate_arrivals += 1
            if duplicate_arrivals == 2:
                duplicate_ready.set()
            await duplicate_ready.wait()
            return await original_lock_control(self)

        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            duplicate_barrier_lock_control,
        )
        duplicate_payload = operator_payload | {
            "target_actor_profile_id": str(profiles["duplicate"]),
            "reason": "Different-key duplicate proof",
        }
        duplicate_responses = await asyncio.gather(
            *(
                client.post(
                    "/api/v1/admin-role-grants",
                    headers={**headers[winner_name], "Idempotency-Key": str(uuid4())},
                    json=duplicate_payload,
                )
                for _ in range(2)
            )
        )
        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            original_lock_control,
        )
        assert sorted(response.status_code for response in duplicate_responses) == [201, 409]
        assert (
            next(
                response for response in duplicate_responses if response.status_code == 409
            ).json()["error"]["code"]
            == "admin_role_grant_exists"
        )

        second_admin = await client.post(
            "/api/v1/admin-role-grants",
            headers={**headers[winner_name], "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(profiles[other_name]),
                "role": "access_administrator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Cross-revocation proof",
            },
        )
        assert second_admin.status_code == 201, second_admin.text
        second_admin_grant_id = second_admin.json()["resource_id"]

        revoke_ready = asyncio.Event()
        revoke_arrivals = 0

        async def revoke_barrier_lock_control(self):
            nonlocal revoke_arrivals
            revoke_arrivals += 1
            if revoke_arrivals == 2:
                revoke_ready.set()
            await revoke_ready.wait()
            return await original_lock_control(self)

        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            revoke_barrier_lock_control,
        )
        revoke_results = await asyncio.gather(
            client.post(
                f"/api/v1/admin-role-grants/{second_admin_grant_id}/revoke",
                headers={**headers[winner_name], "Idempotency-Key": str(uuid4())},
                json={"reason": "Concurrent cross-revoke"},
            ),
            client.post(
                f"/api/v1/admin-role-grants/{bootstrap_grant_id}/revoke",
                headers={**headers[other_name], "Idempotency-Key": str(uuid4())},
                json={"reason": "Concurrent cross-revoke"},
            ),
        )
        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            original_lock_control,
        )
        assert sorted(response.status_code for response in revoke_results) == [200, 403]
        assert (
            next(response for response in revoke_results if response.status_code == 403).json()[
                "error"
            ]["code"]
            == "permission_not_granted"
        )

        if revoke_results[0].status_code == 200:
            surviving_admin, issuance_actor = winner_name, other_name
        else:
            surviving_admin, issuance_actor = other_name, winner_name

        async def restore_issuance_actor() -> str:
            response = await client.post(
                "/api/v1/admin-role-grants",
                headers={
                    **headers[surviving_admin],
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "target_actor_profile_id": str(profiles[issuance_actor]),
                    "role": "access_administrator",
                    "scope_type": "system",
                    "scope_project_id": None,
                    "reason": "Ordered revoke-versus-issue proof",
                },
            )
            assert response.status_code == 201, response.text
            return response.json()["resource_id"]

        async def run_ordered_revoke_vs_issue(
            *,
            first: str,
            target_name: str,
            issuance_grant_id: str,
        ) -> tuple[Response, Response]:
            first_locked = asyncio.Event()

            async def ordered_lock_control(self):
                if asyncio.current_task().get_name() == first:
                    control = await original_lock_control(self)
                    first_locked.set()
                    return control
                await first_locked.wait()
                return await original_lock_control(self)

            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_control",
                ordered_lock_control,
            )
            issue_task = asyncio.create_task(
                client.post(
                    "/api/v1/admin-role-grants",
                    headers={
                        **headers[issuance_actor],
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "target_actor_profile_id": str(profiles[target_name]),
                        "role": "project_manager",
                        "scope_type": "system",
                        "scope_project_id": None,
                        "reason": "Concurrent Project Manager authorization proof",
                    },
                ),
                name="issue",
            )
            revoke_task = asyncio.create_task(
                client.post(
                    f"/api/v1/admin-role-grants/{issuance_grant_id}/revoke",
                    headers={
                        **headers[surviving_admin],
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={"reason": "Concurrent authority removal proof"},
                ),
                name="revoke",
            )
            issue_response, revoke_response = await asyncio.gather(
                issue_task,
                revoke_task,
            )
            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_control",
                original_lock_control,
            )
            return issue_response, revoke_response

        issuance_grant_id = await restore_issuance_actor()
        issue_first, revoke_second = await run_ordered_revoke_vs_issue(
            first="issue",
            target_name="pm-target-one",
            issuance_grant_id=issuance_grant_id,
        )
        assert issue_first.status_code == 201, issue_first.text
        assert revoke_second.status_code == 200, revoke_second.text
        issue_first_grant_id = issue_first.json()["resource_id"]
        revoke_second_grant_id = issuance_grant_id

        issuance_grant_id = await restore_issuance_actor()
        revoke_first_grant_id = issuance_grant_id
        issue_second, revoke_first = await run_ordered_revoke_vs_issue(
            first="revoke",
            target_name="pm-target-two",
            issuance_grant_id=issuance_grant_id,
        )
        assert revoke_first.status_code == 200, revoke_first.text
        assert issue_second.status_code == 403
        assert issue_second.json()["error"]["code"] == "permission_not_granted"

    async with db_session.get_session_factory()() as session:
        active_admins = await session.scalar(
            text(
                "select count(*) from admin_role_grants where "
                "role='access_administrator' and scope_type='system' and status='active'"
            )
        )
        event_counts = dict(
            (
                await session.execute(
                    select(AuditEvent.event_type, func.count())
                    .where(
                        AuditEvent.event_type.in_(
                            [
                                "InitialAccessAdministratorBootstrapped",
                                "AdminRoleGrantIssued",
                                "AdminRoleGrantRevoked",
                                "AdminRoleGrantIssueDenied",
                            ]
                        )
                    )
                    .group_by(AuditEvent.event_type)
                )
            ).all()
        )
        linked_pair_counts: dict[tuple[str, str], int] = {}
        for resource_id, event_type in (
            (issue_first_grant_id, "AdminRoleGrantIssued"),
            (revoke_second_grant_id, "AdminRoleGrantRevoked"),
            (revoke_first_grant_id, "AdminRoleGrantRevoked"),
        ):
            success_ids = (
                await session.scalars(
                    select(AuditEvent.id).where(
                        AuditEvent.entity_id == resource_id,
                        AuditEvent.event_type == event_type,
                    )
                )
            ).all()
            linked_count = 0
            for success_id in success_ids:
                linked_count += int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(AuditEvent.invalidation_cause_event_id == success_id)
                    )
                    or 0
                )
            linked_pair_counts[(resource_id, event_type)] = linked_count
            assert len(success_ids) == 1
        denied_second_issue = int(
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "SensitiveAuthorizationDenied",
                    AuditEvent.action_id == "admin_role_grant.issue",
                    AuditEvent.resource_id == str(profiles["pm-target-two"]),
                )
            )
            or 0
        )
        forbidden_second_issue_state = int(
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    (
                        (AuditEvent.event_type == "AdminRoleGrantIssued")
                        & (AuditEvent.target_actor_ref == str(profiles["pm-target-two"]))
                    )
                    | (
                        (AuditEvent.event_type == "AuthorityInvalidationRequested")
                        & (
                            AuditEvent.invalidation_target_ref
                            == str(profiles["pm-target-two"])
                        )
                    )
                )
            )
            or 0
        )
    assert active_admins == 1
    assert event_counts == {
        "InitialAccessAdministratorBootstrapped": 1,
        "AdminRoleGrantIssued": 6,
        "AdminRoleGrantRevoked": 3,
        "AdminRoleGrantIssueDenied": 2,
    }
    assert set(linked_pair_counts.values()) == {1}
    assert denied_second_issue == 1
    assert forbidden_second_issue_state == 0
    await db_session.dispose_engine()


async def test_actor_admin_reads_hold_caller_and_grant_locks_through_disclosure(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove lifecycle and grant changes serialize after both bounded reads."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    reader_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09c-profile-reader", "jti": "auth09c-profile-reader-token"},
    )
    link_reader_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09c-link-reader", "jti": "auth09c-link-reader-token"},
    )
    custodian_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09c-custodian", "jti": "auth09c-custodian-token"},
    )
    target_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09c-target", "jti": "auth09c-target-token"},
    )
    reader_headers = {"Authorization": f"Bearer {reader_token}"}
    link_reader_headers = {"Authorization": f"Bearer {link_reader_token}"}
    custodian_headers = {"Authorization": f"Bearer {custodian_token}"}
    pause_kind: str | None = None
    entered = asyncio.Event()
    release = asyncio.Event()
    transition_backend_pids: asyncio.Queue[int] = asyncio.Queue()
    captured_grant_transition_tasks: set[asyncio.Task] = set()
    original_profile_read = ActorService.read_admin_profile
    original_link_read = ActorService.read_admin_identity_link
    original_get_grant = AdminAuthorizationRepository.get_grant

    async def pause_profile_read(service: ActorService, actor_profile_id: UUID):
        if pause_kind == "profile":
            entered.set()
            await release.wait()
        return await original_profile_read(service, actor_profile_id)

    async def pause_link_read(service: ActorService, actor_profile_id: UUID):
        if pause_kind == "identity_link":
            entered.set()
            await release.wait()
        return await original_link_read(service, actor_profile_id)

    async def capture_grant_transition_backend(repository, *args, **kwargs):
        task = asyncio.current_task()
        if (
            task is not None
            and task.get_name() == "auth09c-grant-revocation-transition"
            and task not in captured_grant_transition_tasks
        ):
            captured_grant_transition_tasks.add(task)
            backend_pid = await repository._session.scalar(text("select pg_backend_pid()"))
            transition_backend_pids.put_nowait(int(backend_pid))
        return await original_get_grant(repository, *args, **kwargs)

    monkeypatch.setattr(ActorService, "read_admin_profile", pause_profile_read)
    monkeypatch.setattr(ActorService, "read_admin_identity_link", pause_link_read)
    monkeypatch.setattr(
        AdminAuthorizationRepository,
        "get_grant",
        capture_grant_transition_backend,
    )

    async def capture_transition_backend(session: AsyncSession) -> None:
        backend_pid = await session.scalar(text("select pg_backend_pid()"))
        transition_backend_pids.put_nowait(int(backend_pid))

    async def actor_timestamps(actor_id: UUID) -> tuple[datetime | None, datetime | None]:
        async with db_session.get_session_factory()() as session:
            return tuple(
                (
                    await session.execute(
                        text(
                            "select p.last_seen_at,l.last_verified_at from actor_profiles p "
                            "join actor_identity_links l on l.actor_profile_id=p.id "
                            "where p.id=:actor"
                        ),
                        {"actor": str(actor_id)},
                    )
                ).one()
            )

    async def set_profile_state(actor_id: UUID, custodian_id: UUID, state: str) -> None:
        async with db_session.get_session_factory()() as session:
            await capture_transition_backend(session)
            if state == "suspended":
                statement = (
                    "update actor_profiles set status='suspended',suspended_by=:by,"
                    "suspended_at=clock_timestamp(),suspension_reason='race proof' "
                    "where id=:actor"
                )
            else:
                statement = (
                    "update actor_profiles set status='deactivated',deactivated_by=:by,"
                    "deactivated_at=clock_timestamp(),deactivation_reason='race proof' "
                    "where id=:actor"
                )
            await session.execute(text(statement), {"actor": str(actor_id), "by": str(custodian_id)})
            await session.commit()

    async def reset_profile(actor_id: UUID) -> None:
        async with db_session.get_session_factory()() as session:
            await session.execute(text("alter table actor_profiles disable trigger user"))
            await session.execute(
                text(
                    "update actor_profiles set status='active',suspended_by=null,"
                    "suspended_at=null,suspension_reason=null,deactivated_by=null,"
                    "deactivated_at=null,deactivation_reason=null,reactivated_by=null,"
                    "reactivated_at=null,reactivation_reason=null where id=:actor"
                ),
                {"actor": str(actor_id)},
            )
            await session.execute(text("alter table actor_profiles enable trigger user"))
            await session.commit()

    async def revoke_link(actor_id: UUID, custodian_id: UUID) -> None:
        async with db_session.get_session_factory()() as session:
            await capture_transition_backend(session)
            await session.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by=:by,"
                    "revoked_at=clock_timestamp(),revoked_reason='race proof' "
                    "where actor_profile_id=:actor"
                ),
                {"actor": str(actor_id), "by": str(custodian_id)},
            )
            await session.commit()

    async def reset_link(actor_id: UUID) -> None:
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text("alter table actor_identity_links disable trigger user")
            )
            await session.execute(
                text(
                    "update actor_identity_links set status='active',revoked_by=null,"
                    "revoked_at=null,revoked_reason=null,reactivated_by=null,"
                    "reactivated_at=null,reactivation_reason=null "
                    "where actor_profile_id=:actor"
                ),
                {"actor": str(actor_id)},
            )
            await session.execute(
                text("alter table actor_identity_links enable trigger user")
            )
            await session.commit()

    async def wait_for_transition_lock(
        transition_task: asyncio.Task,
        transition_backend_pid: int,
    ) -> None:
        for _ in range(250):
            if transition_task.done():
                raise AssertionError("disabling transition bypassed the read lock")
            async with db_session.get_session_factory()() as session:
                waiting = await session.scalar(
                    text(
                        "select coalesce(cardinality(pg_blocking_pids(:pid)),0)>0"
                    ),
                    {"pid": transition_backend_pid},
                )
            if waiting:
                return
            await asyncio.sleep(0.02)
        raise AssertionError("disabling transition never reached a PostgreSQL lock wait")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        reader = await client.get("/api/v1/actors/me", headers=reader_headers)
        link_reader = await client.get("/api/v1/actors/me", headers=link_reader_headers)
        custodian = await client.get("/api/v1/actors/me", headers=custodian_headers)
        target = await client.get(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {target_token}"},
        )
        reader_id = UUID(reader.json()["actor_profile_id"])
        link_reader_id = UUID(link_reader.json()["actor_profile_id"])
        custodian_id = UUID(custodian.json()["actor_profile_id"])
        target_id = UUID(target.json()["actor_profile_id"])
        bootstrap_code, _bootstrap = await run_admin_bootstrap(custodian_id, execute=True)
        assert bootstrap_code == 0
        reader_grants: dict[UUID, str] = {}
        for current_reader_id in (reader_id, link_reader_id):
            reader_grant = await client.post(
                "/api/v1/admin-role-grants",
                headers={**custodian_headers, "Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": str(current_reader_id),
                    "role": "access_administrator",
                    "scope_type": "system",
                    "scope_project_id": None,
                    "reason": "AUTH-09C concurrency reader",
                },
            )
            assert reader_grant.status_code == 201, reader_grant.text
            reader_grants[current_reader_id] = reader_grant.json()["resource_id"]

        for current_kind, path_suffix, current_headers, current_reader_id in (
            ("profile", "", reader_headers, reader_id),
            ("identity_link", "/identity-links", link_reader_headers, link_reader_id),
        ):
            current_grant_id = reader_grants[current_reader_id]
            for transition in ("suspended", "link_revoked", "grant_revoked", "deactivated"):
                pause_kind = current_kind
                entered = asyncio.Event()
                release = asyncio.Event()
                read_task = asyncio.create_task(
                    client.get(
                        f"/api/v1/actors/{target_id}{path_suffix}",
                        headers=current_headers,
                    )
                )
                await asyncio.wait_for(entered.wait(), timeout=5)
                if transition in {"suspended", "deactivated"}:
                    transition_task = asyncio.create_task(
                        set_profile_state(current_reader_id, custodian_id, transition)
                    )
                elif transition == "link_revoked":
                    transition_task = asyncio.create_task(
                        revoke_link(current_reader_id, custodian_id)
                    )
                else:
                    transition_task = asyncio.create_task(
                        client.post(
                            f"/api/v1/admin-role-grants/{current_grant_id}/revoke",
                            headers={
                                **custodian_headers,
                                "Idempotency-Key": str(uuid4()),
                            },
                            json={"reason": "AUTH-09C matched grant race"},
                        ),
                        name="auth09c-grant-revocation-transition",
                    )
                transition_backend_pid = await asyncio.wait_for(
                    transition_backend_pids.get(),
                    timeout=5,
                )
                await wait_for_transition_lock(transition_task, transition_backend_pid)
                release.set()
                read_response = await read_task
                transition_result = await transition_task
                assert read_response.status_code == 200, read_response.text
                if transition == "grant_revoked":
                    assert transition_result.status_code == 200, transition_result.text
                disabled_timestamps = await actor_timestamps(current_reader_id)
                denied = await client.get(
                    f"/api/v1/actors/{target_id}{path_suffix}",
                    headers=current_headers,
                )
                assert denied.status_code == 403
                assert await actor_timestamps(current_reader_id) == disabled_timestamps

                if transition in {"suspended", "deactivated"}:
                    if transition == "suspended":
                        await reset_profile(current_reader_id)
                elif transition == "link_revoked":
                    await reset_link(current_reader_id)
                else:
                    replacement = await client.post(
                        "/api/v1/admin-role-grants",
                        headers={
                            **custodian_headers,
                            "Idempotency-Key": str(uuid4()),
                        },
                        json={
                            "target_actor_profile_id": str(current_reader_id),
                            "role": "access_administrator",
                            "scope_type": "system",
                            "scope_project_id": None,
                            "reason": "Restore AUTH-09C reader authority",
                        },
                    )
                    assert replacement.status_code == 201, replacement.text
                    current_grant_id = replacement.json()["resource_id"]
                pause_kind = None


async def test_controlled_service_actor_provisioning_is_atomic_private_and_concurrent(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prove fixed service binding, replay, conflicts, rollback, and pre-admission denial."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    app = create_app(settings)
    app.state.auth_verifier = verifier
    admin_token = issue_asymmetric_token(
        private_key,
        claims={
            "sub": "auth09b-admin",
            "email": "private-admin@example.test",
            "jti": "auth09b-admin-token",
        },
    )
    ordinary_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09b-ordinary", "jti": "auth09b-ordinary-token"},
    )
    service_subject = "Opaque-Service-Subject/Verifier:01"
    service_token = issue_asymmetric_token(
        private_key,
        subject_kind="service",
        scope="workstream:service",
        claims={"sub": service_subject, "jti": "auth09b-service-token"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    ordinary_headers = {"Authorization": f"Bearer {ordinary_token}"}
    service_headers = {"Authorization": f"Bearer {service_token}"}
    nonhuman_headers = {
        kind: {
            "Authorization": "Bearer "
            + issue_asymmetric_token(
                private_key,
                subject_kind=kind,
                scope=f"{kind}:identity",
                claims={"sub": f"auth09b-{kind}", "jti": f"auth09b-{kind}-token"},
            )
        }
        for kind in ("agent", "space")
    }

    async def actor_timestamps(actor_id: UUID) -> tuple[datetime | None, datetime | None]:
        async with db_session.get_session_factory()() as session:
            return tuple(
                (
                    await session.execute(
                        text(
                            "select p.last_seen_at,l.last_verified_at "
                            "from actor_profiles p join actor_identity_links l "
                            "on l.actor_profile_id=p.id where p.id=:actor"
                        ),
                        {"actor": str(actor_id)},
                    )
                ).one()
            )

    async def service_state(identity: ServiceIdentity) -> tuple | None:
        async with db_session.get_session_factory()() as session:
            return (
                await session.execute(
                    text(
                        "select p.id,p.actor_kind,p.status,p.provisioning_method,p.created_by,"
                        "p.last_seen_at,l.issuer,l.subject,l.subject_kind,l.status,l.linked_by,"
                        "l.last_verified_at from actor_profiles p join actor_identity_links l "
                        "on l.actor_profile_id=p.id where p.service_identity=:identity"
                    ),
                    {"identity": identity.value},
                )
            ).one_or_none()

    async def authority_counts() -> tuple[int, int, int, int]:
        async with db_session.get_session_factory()() as session:
            return (
                int(await session.scalar(select(func.count()).select_from(ActorProfile)) or 0),
                int(await session.scalar(select(func.count()).select_from(ActorIdentityLink)) or 0),
                int(
                    await session.scalar(
                        select(func.count()).select_from(AuthorityIdempotencyRecord)
                    )
                    or 0
                ),
                int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0),
            )

    async def run_reservation_race(
        calls: tuple[tuple[dict[str, Any], str], tuple[dict[str, Any], str]],
    ) -> tuple[Response, Response]:
        original_reserve = AuthorityIdempotencyRepository.reserve
        ready = asyncio.Event()
        arrivals = 0

        async def barrier_reserve(self, **kwargs):
            nonlocal arrivals
            arrivals += 1
            if arrivals == 2:
                ready.set()
            await ready.wait()
            return await original_reserve(self, **kwargs)

        monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", barrier_reserve)
        try:
            first, second = calls
            return tuple(
                await asyncio.wait_for(
                    asyncio.gather(
                        client.post(
                            "/api/v1/service-actors",
                            headers={**admin_headers, "Idempotency-Key": first[1]},
                            json=first[0],
                        ),
                        client.post(
                            "/api/v1/service-actors",
                            headers={**admin_headers, "Idempotency-Key": second[1]},
                            json=second[0],
                        ),
                    ),
                    timeout=60,
                )
            )
        finally:
            monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", original_reserve)

    observed_response_bodies: list[str] = []

    async def capture_response(response: Response) -> None:
        await response.aread()
        observed_response_bodies.append(response.text)

    caplog.set_level(logging.DEBUG, logger="app")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        event_hooks={"response": [capture_response]},
    ) as client:
        admin_profile = await client.get("/api/v1/actors/me", headers=admin_headers)
        ordinary_profile = await client.get("/api/v1/actors/me", headers=ordinary_headers)
        assert admin_profile.status_code == ordinary_profile.status_code == 200
        admin_id = UUID(admin_profile.json()["actor_profile_id"])
        assert (await run_admin_bootstrap(admin_id, execute=True))[0] == 0
        caller_before = await actor_timestamps(admin_id)

        reason = "Bind the verifier service to its exact issuer subject"
        payload = {
            "service_identity": ServiceIdentity.ARTIFACT_VERIFIER.value,
            "subject": service_subject,
            "reason": reason,
        }
        key = str(uuid4())
        created = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": key},
            json=payload,
        )
        assert created.status_code == 201, created.text
        created_body = created.json()
        assert set(created_body) == {
            "actor_profile_id",
            "service_identity",
            "actor_status",
            "identity_link_status",
            "provisioning_method",
            "created_at",
            "linked_at",
        }
        assert created_body["service_identity"] == ServiceIdentity.ARTIFACT_VERIFIER.value
        assert created_body["actor_status"] == created_body["identity_link_status"] == "active"
        assert created_body["provisioning_method"] == "manual_service_provisioning"
        assert service_subject not in created.text
        assert reason not in created.text
        assert settings.token_issuer not in created.text

        state = await service_state(ServiceIdentity.ARTIFACT_VERIFIER)
        assert state is not None
        assert state[0] == created_body["actor_profile_id"]
        assert state[1:5] == (
            "service",
            "active",
            "manual_service_provisioning",
            str(admin_id),
        )
        assert state[5] is None
        assert state[6:11] == (
            settings.token_issuer,
            service_subject,
            "service",
            "active",
            str(admin_id),
        )
        assert state[11] is None
        caller_after_create = await actor_timestamps(admin_id)
        assert caller_after_create[0] > caller_before[0]
        assert caller_after_create[1] > caller_before[1]

        replayed = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": key},
            json=payload,
        )
        assert replayed.status_code == 201
        assert replayed.json() == created_body
        assert await service_state(ServiceIdentity.ARTIFACT_VERIFIER) == state
        caller_after_replay = await actor_timestamps(admin_id)
        assert caller_after_replay[0] > caller_after_create[0]
        assert caller_after_replay[1] > caller_after_create[1]

        original_replay_response = ServiceActorProvisioningService.replay_response

        async def unavailable_replay(self, **kwargs):
            raise ServiceActorProvisioningUnavailable("forced unavailable replay")

        monkeypatch.setattr(
            ServiceActorProvisioningService,
            "replay_response",
            unavailable_replay,
        )
        unavailable_replay_result = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": key},
            json=payload,
        )
        monkeypatch.setattr(
            ServiceActorProvisioningService,
            "replay_response",
            original_replay_response,
        )
        assert unavailable_replay_result.status_code == 503
        assert unavailable_replay_result.json()["error"]["code"] == "service_unavailable"
        assert await actor_timestamps(admin_id) == caller_after_replay
        assert await service_state(ServiceIdentity.ARTIFACT_VERIFIER) == state

        mismatched = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": key},
            json=payload | {"reason": "A different bounded reason"},
        )
        assert mismatched.status_code == 409
        assert mismatched.json()["error"]["code"] == "idempotency_mismatch"
        assert await actor_timestamps(admin_id) == caller_after_replay
        assert await service_state(ServiceIdentity.ARTIFACT_VERIFIER) == state

        fixed_identity_conflict = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=payload | {"subject": "another-subject"},
        )
        assert fixed_identity_conflict.status_code == 409
        assert (
            fixed_identity_conflict.json()["error"]["code"]
            == "service_identity_already_provisioned"
        )
        subject_conflict = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=payload
            | {"service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value},
        )
        assert subject_conflict.status_code == 409
        assert subject_conflict.json()["error"]["code"] == "identity_subject_already_linked"
        assert await service_state(ServiceIdentity.ARTIFACT_PUT_RESOLVER) is None

        denied = await client.post(
            "/api/v1/service-actors",
            headers={**ordinary_headers, "Idempotency-Key": str(uuid4())},
            json=payload | {"service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "permission_not_granted"
        for kind, headers in nonhuman_headers.items():
            unsupported = await client.post(
                "/api/v1/service-actors",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json=payload
                | {"service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value},
            )
            assert unsupported.status_code == 403
            assert unsupported.json()["error"]["code"] == "unsupported_subject_kind", kind

        rejected_subject = "private-" + "x" * 220
        rejected_reason = "private-" + "y" * 520
        invalid = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=payload | {"subject": rejected_subject, "reason": rejected_reason},
        )
        assert invalid.status_code == 422
        assert rejected_subject not in invalid.text
        assert rejected_reason not in invalid.text
        whitespace_subject = " private-service-subject "
        whitespace = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=payload
            | {
                "service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
                "subject": whitespace_subject,
            },
        )
        assert whitespace.status_code == 422
        assert whitespace_subject not in whitespace.text
        invalid_identity = "private-unknown-service-identity"
        unknown = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=payload | {"service_identity": invalid_identity},
        )
        assert unknown.status_code == 422
        assert invalid_identity not in unknown.text
        invalid_key = "private-invalid-idempotency-key"
        invalid_header = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": invalid_key},
            json=payload,
        )
        assert invalid_header.status_code == 422
        assert invalid_key not in invalid_header.text
        assert service_subject not in invalid_header.text
        assert reason not in invalid_header.text

        for path in ("/api/v1/actors/me", "/api/v1/auth/me"):
            service_denial = await client.get(path, headers=service_headers)
            assert service_denial.status_code == 403
            assert service_denial.json()["error"]["code"] == "service_actor_not_provisioned"
        assert await service_state(ServiceIdentity.ARTIFACT_VERIFIER) == state

        race_key = str(uuid4())
        scheduler_payload = payload | {
            "service_identity": ServiceIdentity.ARTIFACT_SCHEDULER.value,
            "subject": "auth09b-scheduler",
        }
        same_replays = await run_reservation_race(
            ((scheduler_payload, race_key), (scheduler_payload, race_key))
        )
        assert [response.status_code for response in same_replays] == [201, 201]
        assert same_replays[0].json() == same_replays[1].json()

        drift_key = str(uuid4())
        materializer_payload = payload | {
            "service_identity": ServiceIdentity.ARTIFACT_MATERIALIZER.value,
            "subject": "auth09b-materializer-a",
        }
        drift_race = await run_reservation_race(
            (
                (materializer_payload, drift_key),
                (materializer_payload | {"subject": "auth09b-materializer-b"}, drift_key),
            )
        )
        assert sorted(response.status_code for response in drift_race) == [201, 409]
        assert (
            next(response for response in drift_race if response.status_code == 409).json()[
                "error"
            ]["code"]
            == "idempotency_mismatch"
        )

        output_payload = payload | {
            "service_identity": ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
            "subject": "auth09b-output-a",
        }
        fixed_race = await run_reservation_race(
            (
                (output_payload, str(uuid4())),
                (output_payload | {"subject": "auth09b-output-b"}, str(uuid4())),
            )
        )
        assert sorted(response.status_code for response in fixed_race) == [201, 409]
        assert (
            next(response for response in fixed_race if response.status_code == 409).json()[
                "error"
            ]["code"]
            == "service_identity_already_provisioned"
        )

        shared_subject = "auth09b-shared-external-identity"
        external_race = await run_reservation_race(
            (
                (
                    payload
                    | {
                        "service_identity": ServiceIdentity.ARTIFACT_BINDING.value,
                        "subject": shared_subject,
                    },
                    str(uuid4()),
                ),
                (
                    payload
                    | {
                        "service_identity": ServiceIdentity.ARTIFACT_GUIDE_READER.value,
                        "subject": shared_subject,
                    },
                    str(uuid4()),
                ),
            )
        )
        assert sorted(response.status_code for response in external_race) == [201, 409]
        assert (
            next(response for response in external_race if response.status_code == 409).json()[
                "error"
            ]["code"]
            == "identity_subject_already_linked"
        )

        failure_identity = (
            ServiceIdentity.ARTIFACT_BINDING
            if await service_state(ServiceIdentity.ARTIFACT_BINDING) is None
            else ServiceIdentity.ARTIFACT_GUIDE_READER
        )
        failure_payload = payload | {
            "service_identity": failure_identity.value,
            "subject": "auth09b-evidence-retry",
        }
        failure_key = str(uuid4())
        before_failure = await authority_counts()
        original_add_authority_event = AuditService.add_authority_event

        async def fail_success_evidence(self, event):
            if event.event_type is AuthorityEventType.SERVICE_ACTOR_PROVISIONED:
                raise SQLAlchemyError("forced service evidence failure")
            return await original_add_authority_event(self, event)

        monkeypatch.setattr(AuditService, "add_authority_event", fail_success_evidence)
        failed = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": failure_key},
            json=failure_payload,
        )
        monkeypatch.setattr(AuditService, "add_authority_event", original_add_authority_event)
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "service_unavailable"
        assert failed.json()["error"]["retryable"] is True
        assert await authority_counts() == before_failure
        assert await service_state(failure_identity) is None

        retried = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": failure_key},
            json=failure_payload,
        )
        assert retried.status_code == 201, retried.text

        commit_payload = payload | {
            "service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
            "subject": "auth09b-commit-retry",
        }
        commit_key = str(uuid4())
        before_commit_failure = await authority_counts()
        original_commit = AsyncSession.commit
        fail_next_commit = True

        async def fail_service_commit(session: AsyncSession) -> None:
            nonlocal fail_next_commit
            if fail_next_commit:
                fail_next_commit = False
                raise SQLAlchemyError("forced service commit failure")
            await original_commit(session)

        monkeypatch.setattr(AsyncSession, "commit", fail_service_commit)
        commit_failed = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": commit_key},
            json=commit_payload,
        )
        monkeypatch.setattr(AsyncSession, "commit", original_commit)
        assert commit_failed.status_code == 503
        assert commit_failed.json()["error"]["code"] == "service_unavailable"
        assert await authority_counts() == before_commit_failure
        assert await service_state(ServiceIdentity.ARTIFACT_PUT_RESOLVER) is None
        commit_retried = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": commit_key},
            json=commit_payload,
        )
        assert commit_retried.status_code == 201, commit_retried.text

        class CanonicalIssuerUnavailable:
            async def verify(self, token: str):
                return await verifier.verify(token)

            def canonical_issuer(self) -> str:
                raise AuthVerificationUnavailableError("issuer unavailable")

        app.state.auth_verifier = CanonicalIssuerUnavailable()
        unavailable = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=payload,
        )
        app.state.auth_verifier = verifier
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "identity_verification_unavailable"

    sensitive_values = {
        admin_token,
        ordinary_token,
        service_token,
        *(
            headers["Authorization"].removeprefix("Bearer ")
            for headers in nonhuman_headers.values()
        ),
        settings.token_issuer,
        "private-admin@example.test",
        "auth09b-admin",
        "auth09b-admin-token",
        "auth09b-ordinary",
        "auth09b-ordinary-token",
        service_subject,
        "auth09b-service-token",
        *(f"auth09b-{kind}" for kind in nonhuman_headers),
        *(f"auth09b-{kind}-token" for kind in nonhuman_headers),
        reason,
        "A different bounded reason",
        "another-subject",
        rejected_subject,
        rejected_reason,
        invalid_identity,
        invalid_key,
        scheduler_payload["subject"],
        materializer_payload["subject"],
        "auth09b-materializer-b",
        output_payload["subject"],
        "auth09b-output-b",
        shared_subject,
        failure_payload["subject"],
        commit_payload["subject"],
    }
    assert all(value not in body for value in sensitive_values for body in observed_response_bodies)
    assert all(value not in caplog.text for value in sensitive_values)

    async with db_session.get_session_factory()() as session:
        service_profiles = (
            await session.scalars(select(ActorProfile).where(ActorProfile.actor_kind == "service"))
        ).all()
        pending = int(
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        )
        service_events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type == AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value
                )
            )
        ).all()
        audit_rows = (
            await session.scalars(text("select row_to_json(audit_events)::text from audit_events"))
        ).all()
        conflict_denials = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type
                    == AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED.value,
                    AuditEvent.denial_code == "identity_link_conflict",
                )
            )
        ).all()
        service_grants = int(
            await session.scalar(
                select(func.count())
                .select_from(AdminRoleGrant)
                .where(
                    AdminRoleGrant.target_actor_profile_id.in_(
                        [profile.id for profile in service_profiles]
                    )
                )
            )
            or 0
        )
    assert service_profiles
    assert all(profile.last_seen_at is None for profile in service_profiles)
    assert pending == 0
    assert service_grants == 0
    assert service_events
    assert all(event.action_id is None for event in service_events)
    assert all(event.permission_id == "actor.service.provision" for event in service_events)
    serialized_audit = "\n".join(audit_rows)
    assert all(value not in serialized_audit for value in sensitive_values)
    assert conflict_denials
    assert all(event.action_id == "actor.service.provision" for event in conflict_denials)
    await db_session.dispose_engine()


async def test_service_actor_provisioning_failure_and_authority_races_are_atomic(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bound evidence failures and crossed authority changes without partial state."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    app = create_app(settings)
    app.state.auth_verifier = verifier
    first_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09b-race-admin-one", "jti": "auth09b-race-admin-one-token"},
    )
    second_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "auth09b-race-admin-two", "jti": "auth09b-race-admin-two-token"},
    )
    first_headers = {"Authorization": f"Bearer {first_token}"}
    second_headers = {"Authorization": f"Bearer {second_token}"}

    async def snapshot(actor_id: UUID) -> tuple[int, int, int, int, datetime, datetime]:
        async with db_session.get_session_factory()() as session:
            timestamps = (
                await session.execute(
                    text(
                        "select p.last_seen_at,l.last_verified_at "
                        "from actor_profiles p join actor_identity_links l "
                        "on l.actor_profile_id=p.id where p.id=:actor"
                    ),
                    {"actor": str(actor_id)},
                )
            ).one()
            return (
                int(await session.scalar(select(func.count()).select_from(ActorProfile)) or 0),
                int(await session.scalar(select(func.count()).select_from(ActorIdentityLink)) or 0),
                int(
                    await session.scalar(
                        select(func.count()).select_from(AuthorityIdempotencyRecord)
                    )
                    or 0
                ),
                int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0),
                timestamps[0],
                timestamps[1],
            )

    async def binding_count(identity: ServiceIdentity, subject: str) -> tuple[int, int]:
        async with db_session.get_session_factory()() as session:
            profiles = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ActorProfile)
                    .where(ActorProfile.service_identity == identity.value)
                )
                or 0
            )
            links = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ActorIdentityLink)
                    .where(
                        ActorIdentityLink.issuer == settings.token_issuer,
                        ActorIdentityLink.subject == subject,
                    )
                )
                or 0
            )
            return profiles, links

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first_profile = await client.get("/api/v1/actors/me", headers=first_headers)
        second_profile = await client.get("/api/v1/actors/me", headers=second_headers)
        assert first_profile.status_code == second_profile.status_code == 200
        first_id = UUID(first_profile.json()["actor_profile_id"])
        second_id = UUID(second_profile.json()["actor_profile_id"])
        assert (await run_admin_bootstrap(first_id, execute=True))[0] == 0
        second_grant = await client.post(
            "/api/v1/admin-role-grants",
            headers={**first_headers, "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(second_id),
                "role": "access_administrator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Independent authority for crossed mutation proof",
            },
        )
        assert second_grant.status_code == 201, second_grant.text

        failure_cases = (
            (
                ServiceIdentity.ARTIFACT_VERIFIER,
                "auth09b-decision-evidence-failure",
                AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
                False,
            ),
            (
                ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                "auth09b-invalidation-evidence-failure",
                AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
                False,
            ),
            (
                ServiceIdentity.ARTIFACT_BINDING,
                "auth09b-idempotency-completion-failure",
                None,
                True,
            ),
        )
        original_add_authority_event = AuditService.add_authority_event
        original_complete = AuthorityIdempotencyRepository.complete
        for identity, subject, failed_event, fail_completion in failure_cases:
            key = str(uuid4())
            payload = {
                "service_identity": identity.value,
                "subject": subject,
                "reason": "Prove exact failure rollback and retry",
            }
            before = await snapshot(first_id)

            async def fail_selected_evidence(self, event, *, selected=failed_event):
                if selected is not None and event.event_type is selected:
                    raise SQLAlchemyError("forced bounded authority evidence failure")
                return await original_add_authority_event(self, event)

            async def fail_idempotency_completion(self, claim, response):
                raise SQLAlchemyError("forced idempotency completion failure")

            if fail_completion:
                monkeypatch.setattr(
                    AuthorityIdempotencyRepository,
                    "complete",
                    fail_idempotency_completion,
                )
            else:
                monkeypatch.setattr(AuditService, "add_authority_event", fail_selected_evidence)
            try:
                failed = await client.post(
                    "/api/v1/service-actors",
                    headers={**first_headers, "Idempotency-Key": key},
                    json=payload,
                )
            finally:
                monkeypatch.setattr(
                    AuditService,
                    "add_authority_event",
                    original_add_authority_event,
                )
                monkeypatch.setattr(
                    AuthorityIdempotencyRepository,
                    "complete",
                    original_complete,
                )
            assert failed.status_code == 503, failed.text
            failure_error = failed.json()["error"]
            assert failure_error["code"] == "service_unavailable"
            assert failure_error["message"] == "Service unavailable"
            assert failure_error["retryable"] is True
            assert UUID(failure_error["correlation_id"])
            assert failure_error["details"] == {}
            assert await snapshot(first_id) == before
            assert await binding_count(identity, subject) == (0, 0)

            retried = await client.post(
                "/api/v1/service-actors",
                headers={**first_headers, "Idempotency-Key": key},
                json=payload,
            )
            assert retried.status_code == 201, retried.text
            assert await binding_count(identity, subject) == (1, 1)

        same_pair_identity = ServiceIdentity.ARTIFACT_SCHEDULER
        same_pair_subject = "auth09b-same-pair-distinct-keys"
        same_pair_payload = {
            "service_identity": same_pair_identity.value,
            "subject": same_pair_subject,
            "reason": "Serialize one exact binding across distinct request keys",
        }
        same_pair_keys = (str(uuid4()), str(uuid4()))
        original_reserve = AuthorityIdempotencyRepository.reserve
        reservation_ready = asyncio.Event()
        reservation_arrivals = 0

        async def barrier_reserve(self, **kwargs):
            nonlocal reservation_arrivals
            reservation_arrivals += 1
            if reservation_arrivals == 2:
                reservation_ready.set()
            await reservation_ready.wait()
            return await original_reserve(self, **kwargs)

        monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", barrier_reserve)
        try:
            same_pair_responses = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        client.post(
                            "/api/v1/service-actors",
                            headers={**first_headers, "Idempotency-Key": key},
                            json=same_pair_payload,
                        )
                        for key in same_pair_keys
                    )
                ),
                timeout=60,
            )
        finally:
            monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", original_reserve)
        assert sorted(response.status_code for response in same_pair_responses) == [201, 409]
        losing_response = next(
            response for response in same_pair_responses if response.status_code == 409
        )
        assert losing_response.json()["error"]["code"] == "service_identity_already_provisioned"
        winner = next(response for response in same_pair_responses if response.status_code == 201)
        winner_actor_id = winner.json()["actor_profile_id"]
        assert await binding_count(same_pair_identity, same_pair_subject) == (1, 1)
        async with db_session.get_session_factory()() as session:
            pair_records = (
                await session.scalars(
                    select(AuthorityIdempotencyRecord).where(
                        AuthorityIdempotencyRecord.idempotency_key.in_(same_pair_keys)
                    )
                )
            ).all()
            pair_events = (
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.resource_id == winner_actor_id,
                        AuditEvent.event_type.in_(
                            [
                                AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value,
                                AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
                            ]
                        ),
                    )
                )
            ).all()
        assert len(pair_records) == 1
        assert pair_records[0].status == "committed"
        assert [event.event_type for event in pair_events].count(
            AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value
        ) == 1
        assert [event.event_type for event in pair_events].count(
            AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value
        ) == 1

        async with db_session.get_session_factory()() as session:
            first_grant_id = await session.scalar(
                select(AdminRoleGrant.id).where(
                    AdminRoleGrant.target_actor_profile_id == str(first_id),
                    AdminRoleGrant.role == "access_administrator",
                    AdminRoleGrant.status == "active",
                )
            )
        assert first_grant_id is not None
        crossed_identity = ServiceIdentity.ARTIFACT_MATERIALIZER
        crossed_subject = "auth09b-crossed-revocation"
        crossed_key = str(uuid4())
        crossed_payload = {
            "service_identity": crossed_identity.value,
            "subject": crossed_subject,
            "reason": "Cross provisioning with matched grant revocation",
        }
        original_lock_control = AdminAuthorizationRepository.lock_control
        control_ready = asyncio.Event()
        control_arrivals = 0

        async def barrier_lock_control(self):
            nonlocal control_arrivals
            control_arrivals += 1
            if control_arrivals == 2:
                control_ready.set()
            await control_ready.wait()
            return await original_lock_control(self)

        monkeypatch.setattr(AdminAuthorizationRepository, "lock_control", barrier_lock_control)
        try:
            crossed_provision, crossed_revoke = await asyncio.wait_for(
                asyncio.gather(
                    client.post(
                        "/api/v1/service-actors",
                        headers={**first_headers, "Idempotency-Key": crossed_key},
                        json=crossed_payload,
                    ),
                    client.post(
                        f"/api/v1/admin-role-grants/{first_grant_id}/revoke",
                        headers={**second_headers, "Idempotency-Key": str(uuid4())},
                        json={"reason": "Revoke while service provisioning is queued"},
                    ),
                ),
                timeout=60,
            )
        finally:
            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_control",
                original_lock_control,
            )
        assert crossed_revoke.status_code == 200, crossed_revoke.text
        assert crossed_provision.status_code in {201, 403}, crossed_provision.text
        if crossed_provision.status_code == 403:
            assert crossed_provision.json()["error"]["code"] == "permission_not_granted"
        expected_binding = (1, 1) if crossed_provision.status_code == 201 else (0, 0)
        assert await binding_count(crossed_identity, crossed_subject) == expected_binding
        crossed_actor_id = (
            crossed_provision.json()["actor_profile_id"]
            if crossed_provision.status_code == 201
            else None
        )

        denied_after_revoke = await client.post(
            "/api/v1/service-actors",
            headers={**first_headers, "Idempotency-Key": crossed_key},
            json=crossed_payload,
        )
        assert denied_after_revoke.status_code == 403
        assert denied_after_revoke.json()["error"]["code"] == "permission_not_granted"
        crossed_denial_request_ids = [denied_after_revoke.headers["x-request-id"]]
        if crossed_provision.status_code == 403:
            crossed_denial_request_ids.append(crossed_provision.headers["x-request-id"])

    async with db_session.get_session_factory()() as session:
        first_grant = await session.get(AdminRoleGrant, first_grant_id)
        pending = int(
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        )
        crossed_records = (
            await session.scalars(
                select(AuthorityIdempotencyRecord).where(
                    AuthorityIdempotencyRecord.idempotency_key == crossed_key
                )
            )
        ).all()
        crossed_events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action_id == ActionId.ACTOR_SERVICE_PROVISION.value,
                    AuditEvent.actor_id == str(first_id),
                    AuditEvent.request_id.in_(crossed_denial_request_ids),
                )
            )
        ).all()
        revoked_events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_id == str(first_grant_id),
                    AuditEvent.event_type == AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED.value,
                )
            )
        ).all()
        assert len(revoked_events) == 1
        revoke_invalidations = int(
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type
                    == AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
                    AuditEvent.invalidation_cause_event_id == revoked_events[0].id,
                )
            )
            or 0
        )
        crossed_success_evidence = []
        if crossed_actor_id is not None:
            crossed_success_evidence = (
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.resource_id == crossed_actor_id,
                        AuditEvent.event_type.in_(
                            [
                                AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value,
                                AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
                            ]
                        ),
                    )
                )
            ).all()
    assert first_grant is not None and first_grant.status == "revoked"
    assert pending == 0
    expected_success = crossed_provision.status_code == 201
    assert len(crossed_records) == int(expected_success)
    if crossed_records:
        assert crossed_records[0].status == "committed"
    expected_denials = 1 if expected_success else 2
    assert len(crossed_events) == expected_denials
    assert all(
        event.event_type == AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED.value
        and event.denial_code == "permission_not_granted"
        for event in crossed_events
    )
    assert revoke_invalidations == 1
    assert len(crossed_success_evidence) == 2 * int(expected_success)
    if crossed_success_evidence:
        assert {event.event_type for event in crossed_success_evidence} == {
            AuthorityEventType.SERVICE_ACTOR_PROVISIONED.value,
            AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED.value,
        }
    await db_session.dispose_engine()


async def test_auth_me_maps_actor_registry_failure_to_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    auth_database_env: str,
) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "local")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "local-token")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "registry-failure-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "flow-dev-issuer")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor")
    get_settings.cache_clear()

    async def fail_resolve_actor(self, token, *, request_id, correlation_id):
        raise SQLAlchemyError("registry unavailable")

    monkeypatch.setattr(ActorService, "resolve_verified_actor", fail_resolve_actor)
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer local-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Actor registry unavailable"
    assert response.json()["error"]["code"] == "service_unavailable"
    assert response.json()["error"]["message"] == "Service unavailable"
    assert response.json()["error"]["retryable"] is True


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

    first_verifier = DevelopmentAuthVerifier(first)
    second_verifier = DevelopmentAuthVerifier(second)
    first_result = await first_verifier.verify(first.dev_auth_token)
    second_result = await second_verifier.verify(second.dev_auth_token)
    first_actor = first_result.legacy_actor()
    second_actor = second_result.legacy_actor()

    assert first_verifier.canonical_issuer() == first_result.token.issuer == "same-issuer"
    assert second_verifier.canonical_issuer() == second_result.token.issuer == "same-issuer"
    assert first_actor.actor_id == second_actor.actor_id
    assert first_actor.email is None
    assert second_actor.email is None


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


@pytest.mark.parametrize(
    ("field_name", "error_message"),
    [
        ("dev_auth_subject", "WORKSTREAM_DEV_AUTH_SUBJECT must be set"),
        ("dev_auth_issuer", "WORKSTREAM_DEV_AUTH_ISSUER must be set"),
    ],
)
def test_dev_auth_rejects_whitespace_only_identity_anchors(
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
    values[field_name] = " \t "

    with pytest.raises(RuntimeError, match=error_message):
        DevelopmentAuthVerifier(Settings(**values))


@pytest.mark.parametrize("field_name", ["dev_auth_subject", "dev_auth_issuer"])
def test_dev_auth_rejects_surrounding_identity_anchor_whitespace(field_name: str) -> None:
    values = {
        "environment": "local",
        "auth_provider": "dev",
        "dev_auth_token": "local-token",
        "dev_auth_subject": "subject",
        "dev_auth_issuer": "issuer",
    }
    values[field_name] = f" {values[field_name]} "

    with pytest.raises(RuntimeError, match=f"WORKSTREAM_{field_name.upper()}"):
        DevelopmentAuthVerifier(Settings(**values))


def test_dev_auth_rejects_issuer_above_persisted_utf8_bound() -> None:
    with pytest.raises(RuntimeError, match="WORKSTREAM_DEV_AUTH_ISSUER"):
        DevelopmentAuthVerifier(
            Settings(
                environment="local",
                auth_provider="dev",
                dev_auth_token="local-token",
                dev_auth_subject="subject",
                dev_auth_issuer="é" * 101,
            )
        )
    with pytest.raises(RuntimeError, match="WORKSTREAM_FLOW_AUTH_ISSUER"):
        FlowAuthVerifier(
            Settings(
                environment="test",
                auth_provider="flow",
                flow_auth_issuer="é" * 101,
                flow_auth_audience="workstream",
                flow_auth_local_hmac_secret="local-secret",
            )
        )
    with pytest.raises(RuntimeError, match="WORKSTREAM_TOKEN_ISSUER"):
        FlowAuthVerifier(
            production_verifier_settings(
                token_issuer="https://issuer.example.test/" + "é" * 100,
            )
        )


async def test_flow_auth_verifier_boundary_rejects_unconfigured_verification() -> None:
    with pytest.raises(RuntimeError, match="WORKSTREAM_TOKEN_ISSUER"):
        FlowAuthVerifier(Settings(auth_provider="flow"))


async def test_flow_role_normalization_ignores_non_string_values() -> None:
    assert normalize_legacy_roles(
        [
            "contributor",
            {"api_key": "must-not-persist"},
            42,
            " reviewer ",
            "",
        ]
    ) == ("contributor", "reviewer")


async def test_dev_role_normalization_uses_bounded_compatibility_contract() -> None:
    long_role = "x" * 129
    roles = ",".join([*(f"role-{index}" for index in range(35)), long_role])
    result = await DevelopmentAuthVerifier(
        Settings(
            environment="local",
            auth_provider="dev",
            dev_auth_token="local-token",
            dev_auth_subject="subject",
            dev_auth_issuer="issuer",
            dev_auth_roles=roles,
        )
    ).verify("local-token")

    assert result.legacy is not None
    assert result.legacy.roles == tuple(f"role-{index}" for index in range(32))


async def test_permission_policy_allows_required_role() -> None:
    actor = (
        await DevelopmentAuthVerifier(
            Settings(
                environment="local",
                auth_provider="dev",
                dev_auth_token="local-token",
                dev_auth_subject="subject",
                dev_auth_issuer="issuer",
                dev_auth_roles="contributor,reviewer",
            )
        ).verify("local-token")
    ).legacy_actor()

    require_any_role(actor, {"reviewer"})


async def test_permission_policy_rejects_missing_role() -> None:
    actor = (
        await DevelopmentAuthVerifier(
            Settings(
                environment="local",
                auth_provider="dev",
                dev_auth_token="local-token",
                dev_auth_subject="subject",
                dev_auth_issuer="issuer",
                dev_auth_roles="contributor",
            )
        ).verify("local-token")
    ).legacy_actor()

    with pytest.raises(PermissionDenied, match="actor lacks required role"):
        require_any_role(actor, {"finance"})


async def test_actor_profile_lifecycle_real_postgres_matrix(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove profile state, replay, reusable conflicts, concealment, and privacy."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    tokens = {
        name: issue_asymmetric_token(
            private_key,
            claims={
                "sub": f"auth09d-a-{name}",
                "jti": f"auth09d-a-{name}-token",
                "email": f"private-{name}@example.test",
            },
        )
        for name in ("admin", "target", "ordinary", "replay_target", "failure_target")
    }
    headers = {
        name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()
    }

    async def profile_state(actor_id: UUID) -> tuple:
        async with db_session.get_session_factory()() as session:
            return tuple(
                (
                    await session.execute(
                        text(
                            "select p.status,p.suspended_by,p.suspended_at,p.suspension_reason,"
                            "p.reactivated_by,p.reactivated_at,p.reactivation_reason,"
                            "p.deactivated_by,p.deactivated_at,p.deactivation_reason,"
                            "p.last_seen_at,l.last_verified_at from actor_profiles p "
                            "join actor_identity_links l on l.actor_profile_id=p.id "
                            "where p.id=:actor"
                        ),
                        {"actor": str(actor_id)},
                    )
                ).one()
            )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        profiles = {
            name: UUID(
                (await client.get("/api/v1/actors/me", headers=actor_headers)).json()[
                    "actor_profile_id"
                ]
            )
            for name, actor_headers in headers.items()
        }
        assert (await run_admin_bootstrap(profiles["admin"], execute=True))[0] == 0

        provisioned_service = await client.post(
            "/api/v1/service-actors",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={
                "service_identity": ServiceIdentity.ARTIFACT_VERIFIER.value,
                "subject": "auth09d-a-service-target",
                "reason": "Provision exact lifecycle service target",
            },
        )
        assert provisioned_service.status_code == 201, provisioned_service.text
        service_target_id = UUID(provisioned_service.json()["actor_profile_id"])
        service_before = await profile_state(service_target_id)
        service_suspend = await client.post(
            f"/api/v1/actors/{service_target_id}/suspend",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Suspend fixed service target"},
        )
        assert service_suspend.status_code == 200, service_suspend.text
        service_suspended = await profile_state(service_target_id)
        assert service_suspended[0] == "suspended"
        assert service_suspended[1] == str(profiles["admin"])
        assert service_suspended[10:] == service_before[10:]
        service_reactivate = await client.post(
            f"/api/v1/actors/{service_target_id}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Reactivate fixed service target"},
        )
        assert service_reactivate.status_code == 200, service_reactivate.text
        service_active = await profile_state(service_target_id)
        assert service_active[0] == "active"
        assert service_active[1:4] == (None, None, None)
        assert service_active[4] == str(profiles["admin"])
        assert service_active[10:] == service_before[10:]
        service_deactivate = await client.post(
            f"/api/v1/actors/{service_target_id}/deactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Terminally deactivate fixed service target"},
        )
        assert service_deactivate.status_code == 200, service_deactivate.text
        service_terminal = await profile_state(service_target_id)
        assert service_terminal[0] == "deactivated"
        assert service_terminal[7] == str(profiles["admin"])
        assert service_terminal[10:] == service_before[10:]

        async def lifecycle_atomic_state(actor_id: UUID) -> tuple:
            async with db_session.get_session_factory()() as session:
                return (
                    await profile_state(actor_id),
                    await profile_state(profiles["admin"]),
                    int(await session.scalar(text("select count(*) from audit_events")) or 0),
                    int(
                        await session.scalar(
                            text("select count(*) from authority_idempotency_records")
                        )
                        or 0
                    ),
                    int(
                        await session.scalar(
                            text(
                                "select count(*) from authority_idempotency_records "
                                "where status='pending'"
                            )
                        )
                        or 0
                    ),
                )

        failure_target = profiles["failure_target"]
        failure_path = f"/api/v1/actors/{failure_target}/suspend"
        original_reserve = AuthorityIdempotencyRepository.reserve
        original_add_event = AuditService.add_authority_event
        original_target_lookup = AdminAuthorizationRepository.lock_actor_lifecycle_target
        original_flush = AsyncSession.flush
        original_touch = ActorService.touch_after_authorization
        original_complete = AuthorityIdempotencyRepository.complete
        original_commit = AsyncSession.commit

        async def fail_reservation(*_args, **_kwargs):
            raise SQLAlchemyError("forced lifecycle reservation failure")

        async def fail_authorization_evidence(service, event):
            if event.event_type is AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED:
                raise SQLAlchemyError("forced lifecycle authorization evidence failure")
            return await original_add_event(service, event)

        async def fail_target_lookup(*_args, **_kwargs):
            raise SQLAlchemyError("forced lifecycle target lookup failure")

        async def fail_state_flush(session, *args, **kwargs):
            if any(
                isinstance(value, ActorProfile)
                and value.id == str(failure_target)
                and value.status == "suspended"
                for value in session.dirty
            ):
                raise SQLAlchemyError("forced lifecycle state flush failure")
            return await original_flush(session, *args, **kwargs)

        async def fail_caller_touch(*_args, **_kwargs):
            raise SQLAlchemyError("forced lifecycle caller touch failure")

        async def fail_success_evidence(service, event):
            if event.event_type is AuthorityEventType.ACTOR_PROFILE_SUSPENDED:
                raise SQLAlchemyError("forced lifecycle success evidence failure")
            return await original_add_event(service, event)

        async def fail_invalidation_evidence(service, event):
            if event.event_type is AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED:
                raise SQLAlchemyError("forced lifecycle invalidation evidence failure")
            return await original_add_event(service, event)

        async def fail_completion(*_args, **_kwargs):
            raise SQLAlchemyError("forced lifecycle idempotency completion failure")

        async def fail_commit(*_args, **_kwargs):
            raise SQLAlchemyError("forced lifecycle commit failure")

        failure_stages = (
            (AuthorityIdempotencyRepository, "reserve", original_reserve, fail_reservation),
            (AuditService, "add_authority_event", original_add_event, fail_authorization_evidence),
            (
                AdminAuthorizationRepository,
                "lock_actor_lifecycle_target",
                original_target_lookup,
                fail_target_lookup,
            ),
            (AsyncSession, "flush", original_flush, fail_state_flush),
            (ActorService, "touch_after_authorization", original_touch, fail_caller_touch),
            (AuditService, "add_authority_event", original_add_event, fail_success_evidence),
            (AuditService, "add_authority_event", original_add_event, fail_invalidation_evidence),
            (AuthorityIdempotencyRepository, "complete", original_complete, fail_completion),
            (AsyncSession, "commit", original_commit, fail_commit),
        )
        failed_keys: list[str] = []
        for owner, attribute, original, failure in failure_stages:
            before_failure = await lifecycle_atomic_state(failure_target)
            failure_key = str(uuid4())
            failed_keys.append(failure_key)
            monkeypatch.setattr(owner, attribute, failure)
            try:
                failed_response = await client.post(
                    failure_path,
                    headers={**headers["admin"], "Idempotency-Key": failure_key},
                    json={"reason": f"Atomic lifecycle failure at {attribute}"},
                )
            finally:
                monkeypatch.setattr(owner, attribute, original)
            assert failed_response.status_code == 503, failed_response.text
            failure_error = failed_response.json()["error"]
            assert failure_error["code"] == "service_unavailable"
            assert failure_error["message"] == "Service unavailable"
            assert failure_error["retryable"] is True
            assert failure_error["details"] == {}
            UUID(failure_error["correlation_id"])
            assert await lifecycle_atomic_state(failure_target) == before_failure
            async with db_session.get_session_factory()() as session:
                assert (
                    await session.scalar(
                        text(
                            "select count(*) from authority_idempotency_records "
                            "where idempotency_key=:key"
                        ),
                        {"key": failure_key},
                    )
                    or 0
                ) == 0

        reused_failed_key = await client.post(
            failure_path,
            headers={**headers["admin"], "Idempotency-Key": failed_keys[-1]},
            json={"reason": "Atomic lifecycle failure at commit"},
        )
        assert reused_failed_key.status_code == 200, reused_failed_key.text
        restored_failure_target = await client.post(
            f"/api/v1/actors/{failure_target}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Restore failure matrix target"},
        )
        assert restored_failure_target.status_code == 200, restored_failure_target.text

        missing = await client.post(
            f"/api/v1/actors/{uuid4()}/suspend",
            headers={**headers["ordinary"], "Idempotency-Key": str(uuid4())},
            json={"reason": "must not disclose the target"},
        )
        assert missing.status_code == 403
        assert missing.json()["error"]["code"] == "permission_not_granted"
        authorized_missing = await client.post(
            f"/api/v1/actors/{uuid4()}/suspend",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "authorized target lookup"},
        )
        assert authorized_missing.status_code == 404
        assert authorized_missing.json()["error"]["code"] == "actor_not_found"
        self_denial = await client.post(
            f"/api/v1/actors/{profiles['admin']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "self suspension must fail"},
        )
        assert self_denial.status_code == 403
        assert self_denial.json()["error"]["code"] == "resource_guard_denied"
        self_deactivate = await client.post(
            f"/api/v1/actors/{profiles['admin']}/deactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "self deactivation must fail"},
        )
        assert self_deactivate.status_code == 403
        assert self_deactivate.json()["error"]["code"] == "resource_guard_denied"

        delegated = await client.post(
            "/api/v1/admin-role-grants",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(profiles["ordinary"]),
                "role": "access_administrator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Replay authority-loss proof",
            },
        )
        assert delegated.status_code == 201, delegated.text
        authority_replay_key = str(uuid4())
        delegated_mutation = await client.post(
            f"/api/v1/actors/{profiles['replay_target']}/suspend",
            headers={**headers["ordinary"], "Idempotency-Key": authority_replay_key},
            json={"reason": "Delegated lifecycle proof"},
        )
        assert delegated_mutation.status_code == 200, delegated_mutation.text
        disable_delegate = await client.post(
            f"/api/v1/actors/{profiles['ordinary']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Temporarily remove caller authority"},
        )
        assert disable_delegate.status_code == 200, disable_delegate.text
        delegate_disabled_state = await profile_state(profiles["ordinary"])
        denied_replay = await client.post(
            f"/api/v1/actors/{profiles['replay_target']}/suspend",
            headers={**headers["ordinary"], "Idempotency-Key": authority_replay_key},
            json={"reason": "Delegated lifecycle proof"},
        )
        assert denied_replay.status_code == 403
        assert denied_replay.json()["error"]["code"] == "actor_suspended"
        assert await profile_state(profiles["ordinary"]) == delegate_disabled_state
        restore_delegate = await client.post(
            f"/api/v1/actors/{profiles['ordinary']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Restore delegated administrator"},
        )
        assert restore_delegate.status_code == 200, restore_delegate.text

        target_before = await profile_state(profiles["target"])
        reason = "  Investigate bounded lifecycle access  "
        suspend_key = str(uuid4())
        original_add_event = AuditService.add_authority_event

        async def fail_lifecycle_success(service, event):
            if event.event_type is AuthorityEventType.ACTOR_PROFILE_SUSPENDED:
                raise SQLAlchemyError("forced lifecycle evidence failure")
            return await original_add_event(service, event)

        monkeypatch.setattr(AuditService, "add_authority_event", fail_lifecycle_success)
        failed = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": suspend_key},
            json={"reason": reason},
        )
        monkeypatch.setattr(AuditService, "add_authority_event", original_add_event)
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "service_unavailable"
        assert await profile_state(profiles["target"]) == target_before

        suspended = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": suspend_key},
            json={"reason": reason},
        )
        assert suspended.status_code == 200, suspended.text
        assert suspended.json() == {
            "resource_type": "actor_profile",
            "resource_id": str(profiles["target"]),
            "version": None,
            "http_status": 200,
        }
        assert reason.strip() not in suspended.text
        assert "private-target@example.test" not in suspended.text
        after_suspend = await profile_state(profiles["target"])
        assert after_suspend[0] == "suspended"
        assert after_suspend[1] == str(profiles["admin"])
        assert after_suspend[2] is not None
        assert after_suspend[3] == reason.strip()
        assert after_suspend[10:] == target_before[10:]

        mismatch = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": suspend_key},
            json={"reason": "changed reason under one operation"},
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "idempotency_mismatch"

        conflict_key = str(uuid4())
        conflict = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": conflict_key},
            json={"reason": "second transition"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "actor_already_suspended"

        reactivated = await client.post(
            f"/api/v1/actors/{profiles['target']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": suspend_key},
            json={"reason": "Correction complete"},
        )
        assert reactivated.status_code == 200, reactivated.text
        after_reactivate = await profile_state(profiles["target"])
        assert after_reactivate[0] == "active"
        assert after_reactivate[1:4] == (None, None, None)
        assert after_reactivate[4] == str(profiles["admin"])
        assert after_reactivate[5] is not None
        assert after_reactivate[6] == "Correction complete"
        assert after_reactivate[10:] == target_before[10:]
        visible_reactivation = await client.get(
            f"/api/v1/actors/{profiles['target']}",
            headers=headers["admin"],
        )
        assert visible_reactivation.status_code == 200
        assert visible_reactivation.json()["reactivated_at"] is not None

        retry_conflict_key = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": conflict_key},
            json={"reason": "second transition"},
        )
        assert retry_conflict_key.status_code == 200, retry_conflict_key.text

        replay = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": suspend_key},
            json={"reason": reason},
        )
        assert replay.status_code == 200
        assert replay.json() == suspended.json()

        deactivated = await client.post(
            f"/api/v1/actors/{profiles['target']}/deactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Terminal security response"},
        )
        assert deactivated.status_code == 200, deactivated.text
        terminal = await client.post(
            f"/api/v1/actors/{profiles['target']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "must remain terminal"},
        )
        assert terminal.status_code == 409
        assert terminal.json()["error"]["code"] == "actor_deactivated_terminal"
        after_deactivate = await profile_state(profiles["target"])
        assert after_deactivate[0] == "deactivated"
        assert after_deactivate[7] == str(profiles["admin"])
        assert after_deactivate[8] is not None
        assert after_deactivate[9] == "Terminal security response"
        assert after_deactivate[10:] == target_before[10:]

    async with db_session.get_session_factory()() as session:
        lifecycle_records = (
            await session.execute(
                    text(
                        "select operation,status,count(*) from authority_idempotency_records "
                        "where response_resource_id=:target "
                        "group by operation,status order by operation,status"
                ),
                {"target": str(profiles["target"])},
            )
        ).all()
        assert lifecycle_records == [
            ("actor_profile.deactivate", "committed", 1),
            ("actor_profile.reactivate", "committed", 1),
            ("actor_profile.suspend", "committed", 2),
        ]
        event_counts = dict(
            (
                await session.execute(
                    text(
                        "select event_type,count(*) from audit_events "
                        "where resource_type='actor_profile' and resource_id=:target "
                        "and (event_type like 'ActorProfile%' "
                        "or event_type='SensitiveAuthorizationDenied') "
                        "group by event_type"
                    ),
                    {"target": str(profiles["target"])},
                )
            ).all()
        )
        assert event_counts["ActorProfileSuspended"] == 2
        assert event_counts["ActorProfileReactivated"] == 1
        assert event_counts["ActorProfileDeactivated"] == 1
        assert event_counts["SensitiveAuthorizationDenied"] == 3
        denial_rows = (
            await session.execute(
                text(
                    "select matched_grant_id,reason,denial_code,before_facts,after_facts "
                    "from audit_events where event_type='SensitiveAuthorizationDenied' "
                    "and action_id in ('actor.profile.suspend','actor.profile.reactivate',"
                    "'actor.profile.deactivate')"
                )
            )
        ).all()
        assert denial_rows
        assert all(row.matched_grant_id is None for row in denial_rows)
        denial_evidence = json.dumps([tuple(row) for row in denial_rows], default=str)
        for private_value in (
            settings.token_issuer,
            *tokens.values(),
            *(f"private-{name}@example.test" for name in headers),
            reason.strip(),
            derive_reason_digest(reason.strip()),
        ):
            assert private_value not in denial_evidence
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        ) == 0


async def _wait_for_named_database_lock(database_url: str, application_name: str) -> None:
    """Observe the ordered lifecycle request waiting on a PostgreSQL lock."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            for _ in range(5000):
                waiting = await connection.scalar(
                    text(
                        "select exists(select 1 from pg_stat_activity where "
                        "application_name=:name and wait_event_type='Lock')"
                    ),
                    {"name": application_name},
                )
                if waiting:
                    return
                await asyncio.sleep(0)
    finally:
        await engine.dispose()
    raise AssertionError("ordered lifecycle request never reached the database lock")


async def test_actor_profile_lifecycle_real_postgres_concurrency(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serialize exact replay and competing transitions without timing sleeps."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    admin_headers = {
        "Authorization": "Bearer "
        + issue_asymmetric_token(
            private_key,
            claims={"sub": "auth09d-a-race-admin", "jti": "auth09d-a-race-admin-token"},
        )
    }
    target_headers = {
        "Authorization": "Bearer "
        + issue_asymmetric_token(
            private_key,
            claims={"sub": "auth09d-a-race-target", "jti": "auth09d-a-race-target-token"},
        )
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        admin_id = UUID(
            (await client.get("/api/v1/actors/me", headers=admin_headers)).json()[
                "actor_profile_id"
            ]
        )
        target_id = UUID(
            (await client.get("/api/v1/actors/me", headers=target_headers)).json()[
                "actor_profile_id"
            ]
        )
        bootstrap_code, bootstrap = await run_admin_bootstrap(admin_id, execute=True)
        assert bootstrap_code == 0
        path = f"/api/v1/actors/{target_id}/suspend"
        payload = {"reason": "Concurrent exact profile suspension"}

        async def concurrent_posts(keys: tuple[str, str]) -> tuple[Response, Response]:
            original_reserve = AuthorityIdempotencyRepository.reserve
            ready = asyncio.Event()
            arrivals = 0

            async def barrier_reserve(self, **kwargs):
                nonlocal arrivals
                arrivals += 1
                if arrivals == 2:
                    ready.set()
                await ready.wait()
                return await original_reserve(self, **kwargs)

            monkeypatch.setattr(AuthorityIdempotencyRepository, "reserve", barrier_reserve)
            try:
                responses = await asyncio.wait_for(
                    asyncio.gather(
                        client.post(
                            path,
                            headers={**admin_headers, "Idempotency-Key": keys[0]},
                            json=payload,
                        ),
                        client.post(
                            path,
                            headers={**admin_headers, "Idempotency-Key": keys[1]},
                            json=payload,
                        ),
                    ),
                    timeout=60,
                )
                return responses[0], responses[1]
            finally:
                monkeypatch.setattr(
                    AuthorityIdempotencyRepository,
                    "reserve",
                    original_reserve,
                )

        shared_key = str(uuid4())
        same_key = await concurrent_posts((shared_key, shared_key))
        assert [response.status_code for response in same_key] == [200, 200]
        assert same_key[0].json() == same_key[1].json()

        reactivated = await client.post(
            f"/api/v1/actors/{target_id}/reactivate",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Prepare distinct-key race"},
        )
        assert reactivated.status_code == 200, reactivated.text

        competing_keys = (str(uuid4()), str(uuid4()))
        different_keys = await concurrent_posts(competing_keys)
        assert sorted(response.status_code for response in different_keys) == [200, 409]
        loser = next(
            (key, response)
            for key, response in zip(competing_keys, different_keys, strict=True)
            if response.status_code == 409
        )
        assert loser[1].json()["error"]["code"] == "actor_already_suspended"

        reactivated_again = await client.post(
            f"/api/v1/actors/{target_id}/reactivate",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Prove losing key remains reusable"},
        )
        assert reactivated_again.status_code == 200, reactivated_again.text
        reused_loser = await client.post(
            path,
            headers={**admin_headers, "Idempotency-Key": loser[0]},
            json=payload,
        )
        assert reused_loser.status_code == 200, reused_loser.text

        async def create_race_actor(name: str) -> tuple[UUID, dict[str, str]]:
            token = issue_asymmetric_token(
                private_key,
                claims={"sub": f"auth09d-a-race-{name}", "jti": f"auth09d-a-race-{name}-token"},
            )
            actor_headers = {"Authorization": f"Bearer {token}"}
            response = await client.get("/api/v1/actors/me", headers=actor_headers)
            assert response.status_code == 200, response.text
            return UUID(response.json()["actor_profile_id"]), actor_headers

        async def grant_access_administrator(target: UUID, reason: str) -> str:
            response = await client.post(
                "/api/v1/admin-role-grants",
                headers={**admin_headers, "Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": str(target),
                    "role": "access_administrator",
                    "scope_type": "system",
                    "scope_project_id": None,
                    "reason": reason,
                },
            )
            assert response.status_code == 201, response.text
            return response.json()["resource_id"]

        async def ordered_requests(
            first_name: str,
            requests: tuple[
                tuple[str, str, dict[str, str], dict[str, str], str],
                tuple[str, str, dict[str, str], dict[str, str], str],
            ],
        ) -> tuple[tuple[str, Response], tuple[str, Response]]:
            original_lock_control = AdminAuthorizationRepository.lock_control
            first_locked = asyncio.Event()
            waiter_name = f"auth09d-{uuid4().hex}"

            async def ordered_lock_control(self):
                if asyncio.current_task().get_name() == first_name:
                    control = await original_lock_control(self)
                    first_locked.set()
                    await asyncio.wait_for(
                        _wait_for_named_database_lock(auth_database_env, waiter_name),
                        timeout=5,
                    )
                    return control
                await first_locked.wait()
                await self._session.execute(
                    text("select set_config('application_name', :name, true)"),
                    {"name": waiter_name},
                )
                return await original_lock_control(self)

            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_control",
                ordered_lock_control,
            )
            try:
                tasks = [
                    asyncio.create_task(
                        client.post(
                            request_path,
                            headers={**request_headers, "Idempotency-Key": key},
                            json=body,
                        ),
                        name=name,
                    )
                    for name, request_path, request_headers, body, key in requests
                ]
                responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
                return (
                    (requests[0][4], responses[0]),
                    (requests[1][4], responses[1]),
                )
            finally:
                monkeypatch.setattr(
                    AdminAuthorizationRepository,
                    "lock_control",
                    original_lock_control,
                )

        def lifecycle_request(
            *,
            name: str,
            target: UUID,
            transition: str,
            request_headers: dict[str, str] = admin_headers,
        ) -> tuple[str, str, dict[str, str], dict[str, str], str]:
            return (
                name,
                f"/api/v1/actors/{target}/{transition}",
                request_headers,
                {"reason": f"Ordered {transition} proof for {name}"},
                str(uuid4()),
            )

        reusable_keys: list[str] = []

        suspend_first_id, _ = await create_race_actor("suspend-first")
        suspend_first = await ordered_requests(
            "suspend-first",
            (
                lifecycle_request(
                    name="suspend-first",
                    target=suspend_first_id,
                    transition="suspend",
                ),
                lifecycle_request(
                    name="deactivate-second",
                    target=suspend_first_id,
                    transition="deactivate",
                ),
            ),
        )
        assert [result.status_code for _, result in suspend_first] == [200, 200]

        deactivate_first_id, _ = await create_race_actor("deactivate-first")
        deactivate_first = await ordered_requests(
            "deactivate-first",
            (
                lifecycle_request(
                    name="deactivate-first",
                    target=deactivate_first_id,
                    transition="deactivate",
                ),
                lifecycle_request(
                    name="suspend-second",
                    target=deactivate_first_id,
                    transition="suspend",
                ),
            ),
        )
        assert [result.status_code for _, result in deactivate_first] == [200, 409]
        assert deactivate_first[1][1].json()["error"]["code"] == "actor_deactivated_terminal"
        reusable_keys.append(deactivate_first[1][0])

        reactivate_first_id, _ = await create_race_actor("reactivate-first")
        prepared_reactivate_first = await client.post(
            f"/api/v1/actors/{reactivate_first_id}/suspend",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Prepare reactivation-first race"},
        )
        assert prepared_reactivate_first.status_code == 200, prepared_reactivate_first.text
        reactivate_first = await ordered_requests(
            "reactivate-first",
            (
                lifecycle_request(
                    name="reactivate-first",
                    target=reactivate_first_id,
                    transition="reactivate",
                ),
                lifecycle_request(
                    name="deactivate-after-reactivation",
                    target=reactivate_first_id,
                    transition="deactivate",
                ),
            ),
        )
        assert [result.status_code for _, result in reactivate_first] == [200, 200]

        suspended_deactivate_first_id, _ = await create_race_actor(
            "suspended-deactivate-first"
        )
        prepared_deactivate_first = await client.post(
            f"/api/v1/actors/{suspended_deactivate_first_id}/suspend",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Prepare deactivation-first suspended race"},
        )
        assert prepared_deactivate_first.status_code == 200, prepared_deactivate_first.text
        suspended_deactivate_first = await ordered_requests(
            "deactivate-suspended-first",
            (
                lifecycle_request(
                    name="deactivate-suspended-first",
                    target=suspended_deactivate_first_id,
                    transition="deactivate",
                ),
                lifecycle_request(
                    name="reactivate-after-deactivation",
                    target=suspended_deactivate_first_id,
                    transition="reactivate",
                ),
            ),
        )
        assert [result.status_code for _, result in suspended_deactivate_first] == [200, 409]
        assert (
            suspended_deactivate_first[1][1].json()["error"]["code"]
            == "actor_deactivated_terminal"
        )
        reusable_keys.append(suspended_deactivate_first[1][0])

        admin_two_id, _ = await create_race_actor("three-admin-two")
        admin_three_id, _ = await create_race_actor("three-admin-three")
        await grant_access_administrator(admin_two_id, "Three-admin race participant two")
        await grant_access_administrator(admin_three_id, "Three-admin race participant three")
        three_admin = await ordered_requests(
            "three-admin-first-loss",
            (
                lifecycle_request(
                    name="three-admin-first-loss",
                    target=admin_two_id,
                    transition="suspend",
                ),
                lifecycle_request(
                    name="three-admin-second-loss",
                    target=admin_three_id,
                    transition="suspend",
                ),
            ),
        )
        assert [result.status_code for _, result in three_admin] == [200, 200]

        grant_race_id, grant_race_headers = await create_race_actor("grant-race")
        await grant_access_administrator(grant_race_id, "Profile and grant race participant")
        grant_race_key = str(uuid4())
        profile_grant_race = await ordered_requests(
            "profile-loss-first",
            (
                lifecycle_request(
                    name="profile-loss-first",
                    target=grant_race_id,
                    transition="suspend",
                ),
                (
                    "grant-revoke-second",
                    f"/api/v1/admin-role-grants/{bootstrap['grant_id']}/revoke",
                    grant_race_headers,
                    {"reason": "Reciprocal profile and grant loss"},
                    grant_race_key,
                ),
            ),
        )
        assert [result.status_code for _, result in profile_grant_race] == [200, 403]
        assert profile_grant_race[1][1].json()["error"]["code"] == "actor_suspended"
        reusable_keys.append(grant_race_key)

        reciprocal_one_id, reciprocal_one_headers = await create_race_actor(
            "reciprocal-one"
        )
        reciprocal_two_id, reciprocal_two_headers = await create_race_actor(
            "reciprocal-two"
        )
        await grant_access_administrator(reciprocal_one_id, "Reciprocal administrator one")
        await grant_access_administrator(reciprocal_two_id, "Reciprocal administrator two")
        disable_bootstrap = await client.post(
            f"/api/v1/actors/{admin_id}/suspend",
            headers={**reciprocal_one_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Leave exactly two effective administrators"},
        )
        assert disable_bootstrap.status_code == 200, disable_bootstrap.text
        reciprocal_second_key = str(uuid4())
        reciprocal = await ordered_requests(
            "reciprocal-one-first",
            (
                lifecycle_request(
                    name="reciprocal-one-first",
                    target=reciprocal_two_id,
                    transition="suspend",
                    request_headers=reciprocal_one_headers,
                ),
                (
                    "reciprocal-two-second",
                    f"/api/v1/actors/{reciprocal_one_id}/suspend",
                    reciprocal_two_headers,
                    {"reason": "Reciprocal final-authority loss"},
                    reciprocal_second_key,
                ),
            ),
        )
        assert [result.status_code for _, result in reciprocal] == [200, 403]
        assert reciprocal[1][1].json()["error"]["code"] == "actor_suspended"
        reusable_keys.append(reciprocal_second_key)

    async with db_session.get_session_factory()() as session:
        state = (
            await session.execute(
                text(
                    "select p.status,count(r.id) filter (where r.status='committed') "
                    "from actor_profiles p left join authority_idempotency_records r "
                    "on r.response_resource_id=p.id::uuid where p.id=:target "
                    "group by p.status"
                ),
                {"target": str(target_id)},
            )
        ).one()
        assert tuple(state) == ("suspended", 5)
        counts = dict(
            (
                await session.execute(
                    text(
                        "select event_type,count(*) from audit_events "
                        "where target_actor_ref=:target and event_type in "
                        "('ActorProfileSuspended','ActorProfileReactivated',"
                        "'SensitiveAuthorizationDenied') group by event_type"
                    ),
                    {"target": str(target_id)},
                )
            ).all()
        )
        assert counts == {
            "ActorProfileSuspended": 3,
            "ActorProfileReactivated": 2,
            "SensitiveAuthorizationDenied": 1,
        }
        ordered_states = dict(
            (
                await session.execute(
                    select(ActorProfile.id, ActorProfile.status).where(
                        ActorProfile.id.in_(
                            [
                                str(suspend_first_id),
                                str(deactivate_first_id),
                                str(reactivate_first_id),
                                str(suspended_deactivate_first_id),
                                str(admin_two_id),
                                str(admin_three_id),
                                str(grant_race_id),
                                str(admin_id),
                                str(reciprocal_one_id),
                                str(reciprocal_two_id),
                            ]
                        )
                    )
                )
            ).all()
        )
        assert ordered_states == {
            str(suspend_first_id): "deactivated",
            str(deactivate_first_id): "deactivated",
            str(reactivate_first_id): "deactivated",
            str(suspended_deactivate_first_id): "deactivated",
            str(admin_two_id): "suspended",
            str(admin_three_id): "suspended",
            str(grant_race_id): "suspended",
            str(admin_id): "suspended",
            str(reciprocal_one_id): "active",
            str(reciprocal_two_id): "suspended",
        }
        assert await AdminAuthorizationRepository(
            session
        ).count_effective_access_administrators() == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        ) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.idempotency_key.in_(reusable_keys))
            )
            or 0
        ) == 0
        lifecycle_event_counts = dict(
            (
                await session.execute(
                    select(AuditEvent.event_type, func.count())
                    .where(
                        AuditEvent.event_type.in_(
                            [
                                "ActorProfileSuspended",
                                "ActorProfileReactivated",
                                "ActorProfileDeactivated",
                                "SensitiveAuthorizationDenied",
                            ]
                        )
                    )
                    .group_by(AuditEvent.event_type)
                )
            ).all()
        )
        assert lifecycle_event_counts == {
            "ActorProfileSuspended": 11,
            "ActorProfileReactivated": 3,
            "ActorProfileDeactivated": 4,
            "SensitiveAuthorizationDenied": 5,
        }


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
    assert "/api/v1/demo/worker-profile" not in paths
    assert not any(
        segment in forbidden_segments for path in paths for segment in path.strip("/").split("/")
    )
