from __future__ import annotations

from tests.authentication.support import (
    production_verifier_settings,
    issue_asymmetric_token,
    jwks_transport,
)
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)


import ast
import asyncio
import json
import logging
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import (  # type: ignore[import-not-found]
    ASGITransport,
    AsyncClient,
    Response,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (  # type: ignore[import-not-found]
    AsyncSession,
)

from app.adapters.auth.dev import DevelopmentAuthVerifier
from app.adapters.auth.flow import (
    FlowAuthVerifier,
)
from app.core.config import Settings, get_settings
from app.core.permissions import PermissionDenied, require_any_role
from app.db import session as db_session
from app.interfaces.auth import AuthVerificationUnavailableError
from app.main import create_app
from app.modules.audit.schemas import AuthorityEventType
from app.modules.audit.service import AuditService
from app.modules.actors.service import ActorService
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.models import (
    AdminRoleGrant,
    AuthorityIdempotencyRecord,
    ProjectRoleGrant,
)
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
from auth_concurrency_support import ordered_control_requests, wait_for_named_database_lock
from app.modules.tasks.models import AuditEvent
from scripts.bootstrap_access_administrator import (
    _run as run_admin_bootstrap,
)


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


def test_retired_submitter_eligibility_bridge_has_no_runtime_consumers() -> None:
    """Do not reintroduce the removed self-activation authority path."""
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

    assert consumers == set()
    assert compatibility_calls == []


def current_task_name() -> str:
    """Return the current asyncio task name with an explicit test invariant."""
    task = asyncio.current_task()
    if task is None:
        raise AssertionError("an asyncio task is required")
    return task.get_name()




def test_legacy_compatibility_dependency_has_fixed_consumer_allowlist() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    sources = {
        path.relative_to(app_root).as_posix(): path.read_text() for path in app_root.rglob("*.py")
    }

    assert {path for path, source in sources.items() if "get_registered_actor" in source} == {
        "api/deps/auth.py",
        "modules/checkers/router.py",
        "modules/tasks/router.py",
    }
    assert {
        path for path, source in sources.items() if "get_auth_verification_result" in source
    } == {
        "api/deps/api_controls.py",
        "api/deps/auth.py",
        "api/deps/authorization.py",
        "modules/projects/guide_mutation_router.py",
        "modules/projects/policy_mutation_router.py",
    }
    assert {path for path, source in sources.items() if "AuthVerificationResult" in source} == {
        "adapters/auth/dev.py",
        "adapters/auth/flow.py",
        "api/deps/api_controls.py",
        "api/deps/auth.py",
        "api/deps/authorization.py",
        "api/deps/rate_controls.py",
        "core/auth.py",
        "interfaces/auth.py",
        "modules/projects/guide_mutation_router.py",
        "modules/projects/policy_mutation_router.py",
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


async def test_valid_dev_token_resolves_canonical_profile(
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
            "/api/v1/actors/me",
            headers={"Authorization": "Bearer local-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["actor_profile_id"]
    assert body["actor_kind"] == "human"
    assert body["status"] == "active"
    assert body["domains"] == ["contributor"]
    assert body["admin_roles"] == []
    assert body["contact_email"] is None
    assert body["display_name"] is None
    assert not {"roles", "external_subject", "external_issuer", "audit_context"} & body.keys()


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


async def test_controlled_endpoint_provisions_review_and_adapter_target_identities(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env)
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    admin_token = issue_asymmetric_token(
        private_key,
        claims={"sub": "xint003-02c-admin", "jti": "xint003-02c-admin-token"},
    )
    headers = {"Authorization": f"Bearer {admin_token}"}
    identities = (
        ServiceIdentity.REVIEW_PREFERENCE_EXPIRY,
        ServiceIdentity.REVIEW_LEASE_EXPIRY,
        ServiceIdentity.REVIEW_AUTHORITY_INVALIDATION_RECONCILIATION,
        ServiceIdentity.REVIEW_RECONCILIATION,
        ServiceIdentity.REVIEW_ARTIFACT_REFERENCE_RECONCILIATION,
        ServiceIdentity.REVIEW_PROJECTION,
        ServiceIdentity.COMPENSATION_ADAPTER,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        profile = await client.get("/api/v1/actors/me", headers=headers)
        assert profile.status_code == 200
        assert (await run_admin_bootstrap(UUID(profile.json()["actor_profile_id"]), execute=True))[
            0
        ] == 0
        for identity in identities:
            response = await client.post(
                "/api/v1/service-actors",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={
                    "service_identity": identity.value,
                    "subject": f"xint003-02c:{identity.value}",
                    "reason": "Provision the exact fixed REV service principal",
                },
            )
            assert response.status_code == 201, response.text
            assert response.json()["service_identity"] == identity.value

    async with db_session.get_session_factory()() as session:
        rows = tuple(
            (
                await session.execute(
                    select(ActorProfile.id, ActorProfile.service_identity).where(
                        ActorProfile.service_identity.in_(
                            tuple(identity.value for identity in identities)
                        )
                    )
                )
            ).all()
        )
        actor_ids = tuple(row.id for row in rows)
        admin_grants = int(
            await session.scalar(
                select(func.count())
                .select_from(AdminRoleGrant)
                .where(AdminRoleGrant.target_actor_profile_id.in_(actor_ids))
            )
            or 0
        )
        project_grants = int(
            await session.scalar(
                select(func.count())
                .select_from(ProjectRoleGrant)
                .where(ProjectRoleGrant.actor_profile_id.in_(actor_ids))
            )
            or 0
        )
    assert {row.service_identity for row in rows} == {identity.value for identity in identities}
    assert admin_grants == project_grants == 0


async def test_controlled_service_actor_provisioning_includes_project_setup_and_is_atomic(
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
        unprovisioned_service = await client.post(
            "/api/v1/service-actors",
            headers={**service_headers, "Idempotency-Key": str(uuid4())},
            json=payload,
        )
        assert unprovisioned_service.status_code == 403
        assert unprovisioned_service.json()["error"]["code"] == "service_actor_not_provisioned"
        assert await service_state(ServiceIdentity.ARTIFACT_VERIFIER) is None
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
        service_human_path_denial = await client.post(
            "/api/v1/service-actors",
            headers={**service_headers, "Idempotency-Key": str(uuid4())},
            json=payload,
        )
        assert service_human_path_denial.status_code == 403
        assert service_human_path_denial.json()["error"]["code"] == "permission_not_granted"
        assert await service_state(ServiceIdentity.ARTIFACT_VERIFIER) == state
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
            json=payload | {"service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value},
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
                json=payload | {"service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value},
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

        for path, expected_code in (
            ("/api/v1/actors/me", "permission_not_granted"),
        ):
            service_denial = await client.get(path, headers=service_headers)
            assert service_denial.status_code == 403
            assert service_denial.json()["error"]["code"] == expected_code
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

        setup_subject = "Opaque-Service-Subject/ProjectSetup:01"
        setup_payload = payload | {
            "service_identity": ServiceIdentity.PROJECT_SETUP.value,
            "subject": setup_subject,
        }
        setup_created = await client.post(
            "/api/v1/service-actors",
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
            json=setup_payload,
        )
        assert setup_created.status_code == 201, setup_created.text
        assert setup_created.json()["service_identity"] == ServiceIdentity.PROJECT_SETUP.value
        setup_state = await service_state(ServiceIdentity.PROJECT_SETUP)
        assert setup_state is not None
        assert setup_state[1:4] == ("service", "active", "manual_service_provisioning")
        assert setup_state[5] is None
        assert setup_state[6:11] == (
            settings.token_issuer,
            setup_subject,
            "service",
            "active",
            str(admin_id),
        )
        assert setup_state[11] is None

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
        str(value)
        for value in {
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
            setup_subject,
        }
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
        service_project_grants = int(
            await session.scalar(
                select(func.count())
                .select_from(ProjectRoleGrant)
                .where(
                    ProjectRoleGrant.actor_profile_id.in_(
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
    assert service_project_grants == 0
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


async def test_actor_self_maps_actor_registry_failure_to_service_unavailable(
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
            "/api/v1/actors/me",
            headers={"Authorization": "Bearer local-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Actor registry unavailable"
    assert response.json()["error"]["code"] == "service_unavailable"
    assert response.json()["error"]["message"] == "Service unavailable"
    assert response.json()["error"]["retryable"] is True


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
    headers = {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}

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


async def test_actor_identity_link_lifecycle_real_postgres_matrix(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove link state, atomic failure, replay, owner, grant, and privacy behavior."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env).model_copy(
        update={"api_admin_mutation_rate_limit": 1_000}
    )
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))
    names = ("admin", "target", "ordinary", "failure")
    tokens = {
        name: issue_asymmetric_token(
            private_key,
            claims={
                "sub": f"auth09d-b-{name}",
                "jti": f"auth09d-b-{name}-token",
                "email": f"private-auth09d-b-{name}@example.test",
            },
        )
        for name in names
    }
    headers = {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}

    async def actor_link_state(actor_id: UUID) -> tuple:
        async with db_session.get_session_factory()() as session:
            return tuple(
                (
                    await session.execute(
                        text(
                            "select p.status,p.last_seen_at,l.id,l.status,l.revoked_by,"
                            "l.revoked_at,l.revoked_reason,l.reactivated_by,l.reactivated_at,"
                            "l.reactivation_reason,l.last_verified_at from actor_profiles p "
                            "join actor_identity_links l on l.actor_profile_id=p.id "
                            "where p.id=:actor"
                        ),
                        {"actor": str(actor_id)},
                    )
                ).one()
            )

    async def idempotency_count(key: str) -> int:
        async with db_session.get_session_factory()() as session:
            return int(
                await session.scalar(
                    text(
                        "select count(*) from authority_idempotency_records "
                        "where idempotency_key=:key"
                    ),
                    {"key": key},
                )
                or 0
            )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        profiles = {
            name: UUID(
                (await client.get("/api/v1/actors/me", headers=headers[name])).json()[
                    "actor_profile_id"
                ]
            )
            for name in names
        }
        assert (await run_admin_bootstrap(profiles["admin"], execute=True))[0] == 0
        states = {name: await actor_link_state(actor_id) for name, actor_id in profiles.items()}
        links = {name: UUID(state[2]) for name, state in states.items()}

        async def atomic_state(target: UUID) -> tuple:
            async with db_session.get_session_factory()() as session:
                return (
                    await actor_link_state(target),
                    await actor_link_state(profiles["admin"]),
                    tuple(
                        await session.scalars(
                            text("select to_jsonb(g)::text from admin_role_grants g order by g.id")
                        )
                    ),
                    tuple(
                        await session.scalars(
                            text("select to_jsonb(e)::text from audit_events e order by e.id")
                        )
                    ),
                    tuple(
                        await session.scalars(
                            text(
                                "select to_jsonb(i)::text from "
                                "authority_idempotency_records i order by i.id"
                            )
                        )
                    ),
                )

        async def link_authorization_events(resource_id: UUID) -> tuple[tuple, ...]:
            async with db_session.get_session_factory()() as session:
                return tuple(
                    (
                        await session.execute(
                            select(
                                AuditEvent.event_type,
                                AuditEvent.action_id,
                                AuditEvent.permission_id,
                                AuditEvent.resource_type,
                                AuditEvent.resource_id,
                                AuditEvent.denial_code,
                                AuditEvent.matched_grant_id,
                            )
                            .where(AuditEvent.resource_id == str(resource_id))
                            .order_by(AuditEvent.created_at, AuditEvent.id)
                        )
                    ).all()
                )

        failure_target = profiles["failure"]
        failure_link = links["failure"]
        original_reserve = AuthorityIdempotencyRepository.reserve
        original_add_event = AuditService.add_authority_event
        original_target_lookup = AdminAuthorizationRepository.lock_identity_link_lifecycle_target
        original_flush = AsyncSession.flush
        original_touch = ActorService.touch_after_authorization
        original_complete = AuthorityIdempotencyRepository.complete
        original_commit = AsyncSession.commit

        async def run_failure_matrix(operation: str) -> str:
            target_status = "revoked" if operation == "revoke" else "active"
            event_type = (
                AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED
                if operation == "revoke"
                else AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED
            )

            async def fail_reservation(*_args, **_kwargs):
                raise SQLAlchemyError("forced link lifecycle reservation failure")

            async def fail_authorization_evidence(service, event):
                if event.event_type is AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED:
                    raise SQLAlchemyError("forced link lifecycle authorization evidence failure")
                return await original_add_event(service, event)

            async def fail_target_lookup(*_args, **_kwargs):
                raise SQLAlchemyError("forced link lifecycle target lookup failure")

            async def fail_state_flush(session, *args, **kwargs):
                if any(
                    isinstance(value, ActorIdentityLink)
                    and value.id == str(failure_link)
                    and value.status == target_status
                    for value in session.dirty
                ):
                    raise SQLAlchemyError("forced link lifecycle state flush failure")
                return await original_flush(session, *args, **kwargs)

            async def fail_caller_touch(*_args, **_kwargs):
                raise SQLAlchemyError("forced link lifecycle caller touch failure")

            async def fail_success_evidence(service, event):
                if event.event_type is event_type:
                    raise SQLAlchemyError("forced link lifecycle success evidence failure")
                return await original_add_event(service, event)

            async def fail_invalidation_evidence(service, event):
                if event.event_type is AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED:
                    raise SQLAlchemyError("forced link lifecycle invalidation failure")
                return await original_add_event(service, event)

            async def fail_completion(*_args, **_kwargs):
                raise SQLAlchemyError("forced link lifecycle completion failure")

            async def fail_commit(*_args, **_kwargs):
                raise SQLAlchemyError("forced link lifecycle commit failure")

            stages = (
                (AuthorityIdempotencyRepository, "reserve", original_reserve, fail_reservation),
                (
                    AuditService,
                    "add_authority_event",
                    original_add_event,
                    fail_authorization_evidence,
                ),
                (
                    AdminAuthorizationRepository,
                    "lock_identity_link_lifecycle_target",
                    original_target_lookup,
                    fail_target_lookup,
                ),
                (AsyncSession, "flush", original_flush, fail_state_flush),
                (ActorService, "touch_after_authorization", original_touch, fail_caller_touch),
                (AuditService, "add_authority_event", original_add_event, fail_success_evidence),
                (
                    AuditService,
                    "add_authority_event",
                    original_add_event,
                    fail_invalidation_evidence,
                ),
                (AuthorityIdempotencyRepository, "complete", original_complete, fail_completion),
                (AsyncSession, "commit", original_commit, fail_commit),
            )
            final_key = ""
            for owner, attribute, original, failure in stages:
                before = await atomic_state(failure_target)
                final_key = str(uuid4())
                monkeypatch.setattr(owner, attribute, failure)
                try:
                    response = await client.post(
                        f"/api/v1/actor-identity-links/{failure_link}/{operation}",
                        headers={**headers["admin"], "Idempotency-Key": final_key},
                        json={"reason": f"Atomic {operation} failure at {attribute}"},
                    )
                finally:
                    monkeypatch.setattr(owner, attribute, original)
                assert response.status_code == 503, response.text
                assert response.json()["error"] | {"correlation_id": None} == {
                    "code": "service_unavailable",
                    "message": "Service unavailable",
                    "details": {},
                    "correlation_id": None,
                    "retryable": True,
                }
                UUID(response.json()["error"]["correlation_id"])
                assert await atomic_state(failure_target) == before
                assert await idempotency_count(final_key) == 0
            return final_key

        revoke_retry_key = await run_failure_matrix("revoke")
        revoke_after_failures = await client.post(
            f"/api/v1/actor-identity-links/{failure_link}/revoke",
            headers={**headers["admin"], "Idempotency-Key": revoke_retry_key},
            json={"reason": "Atomic revoke failure at commit"},
        )
        assert revoke_after_failures.status_code == 200, revoke_after_failures.text
        reactivate_retry_key = await run_failure_matrix("reactivate")
        reactivate_after_failures = await client.post(
            f"/api/v1/actor-identity-links/{failure_link}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": reactivate_retry_key},
            json={"reason": "Atomic reactivate failure at commit"},
        )
        assert reactivate_after_failures.status_code == 200, reactivate_after_failures.text

        missing_link = uuid4()
        private_missing_key = str(uuid4())
        private_missing = await client.post(
            f"/api/v1/actor-identity-links/{missing_link}/revoke",
            headers={**headers["ordinary"], "Idempotency-Key": private_missing_key},
            json={"reason": "must not disclose missing link"},
        )
        assert private_missing.status_code == 403
        assert private_missing.json()["error"]["code"] == "permission_not_granted"
        assert await idempotency_count(private_missing_key) == 0
        authorized_missing_key = str(uuid4())
        missing_caller_before = await actor_link_state(profiles["admin"])
        missing_events_before = await link_authorization_events(missing_link)
        authorized_missing = await client.post(
            f"/api/v1/actor-identity-links/{missing_link}/revoke",
            headers={**headers["admin"], "Idempotency-Key": authorized_missing_key},
            json={"reason": "authorized missing link"},
        )
        assert authorized_missing.status_code == 404
        assert authorized_missing.json()["error"]["code"] == "resource_not_found"
        assert await idempotency_count(authorized_missing_key) == 0
        assert await actor_link_state(profiles["admin"]) == missing_caller_before
        missing_events_after = await link_authorization_events(missing_link)
        assert missing_events_after[: len(missing_events_before)] == missing_events_before
        assert missing_events_after[len(missing_events_before) :] == (
            (
                "SensitiveAuthorizationDenied",
                "actor.identity_link.revoke",
                "actor.identity_link.revoke",
                "actor_identity_link",
                str(missing_link),
                "resource_not_found",
                None,
            ),
        )
        self_key = str(uuid4())
        self_revoke = await client.post(
            f"/api/v1/actor-identity-links/{links['admin']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": self_key},
            json={"reason": "self link revocation must fail"},
        )
        assert self_revoke.status_code == 403
        assert self_revoke.json()["error"]["code"] == "resource_guard_denied"
        assert await idempotency_count(self_key) == 0

        target_before = await actor_link_state(profiles["target"])
        normalized_reason = "  Investigate exact identity link  "
        revoke_key = str(uuid4())
        revoked = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": revoke_key},
            json={"reason": normalized_reason},
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json() == {
            "resource_type": "actor_identity_link",
            "resource_id": str(links["target"]),
            "version": None,
            "http_status": 200,
        }
        assert normalized_reason.strip() not in revoked.text
        target_revoked = await actor_link_state(profiles["target"])
        assert target_revoked[0] == "active"
        assert target_revoked[3] == "revoked"
        assert target_revoked[4] == str(profiles["admin"])
        assert target_revoked[6] == normalized_reason.strip()
        assert target_revoked[1] == target_before[1]
        assert target_revoked[10] == target_before[10]

        caller_before_mismatch = await actor_link_state(profiles["admin"])
        mismatch = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": revoke_key},
            json={"reason": "changed link lifecycle reason"},
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "idempotency_mismatch"
        assert await actor_link_state(profiles["admin"]) == caller_before_mismatch
        assert await actor_link_state(profiles["target"]) == target_revoked
        conflict_key = str(uuid4())
        caller_before_conflict = await actor_link_state(profiles["admin"])
        conflict = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": conflict_key},
            json={"reason": "second link revocation"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "identity_link_already_revoked"
        assert await idempotency_count(conflict_key) == 0
        assert await actor_link_state(profiles["admin"]) == caller_before_conflict
        assert await actor_link_state(profiles["target"]) == target_revoked

        reactivated = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": revoke_key},
            json={"reason": "Repair exact identity link"},
        )
        assert reactivated.status_code == 200, reactivated.text
        target_reactivated = await actor_link_state(profiles["target"])
        assert target_reactivated[3] == "active"
        assert target_reactivated[4:7] == (None, None, None)
        assert target_reactivated[7] == str(profiles["admin"])
        assert target_reactivated[9] == "Repair exact identity link"
        assert target_reactivated[1] == target_before[1]
        assert target_reactivated[10] == target_before[10]

        caller_before_replay = await actor_link_state(profiles["admin"])
        replay = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": revoke_key},
            json={"reason": normalized_reason},
        )
        assert replay.status_code == 200
        assert replay.json() == revoked.json()
        assert await actor_link_state(profiles["target"]) == target_reactivated
        caller_after_replay = await actor_link_state(profiles["admin"])
        assert caller_after_replay[1] > caller_before_replay[1]
        assert caller_after_replay[10] > caller_before_replay[10]

        reused_conflict = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": conflict_key},
            json={"reason": "second link revocation"},
        )
        assert reused_conflict.status_code == 200, reused_conflict.text

        repair_for_suspension = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Prepare suspended owner proof"},
        )
        assert repair_for_suspension.status_code == 200, repair_for_suspension.text
        suspend_owner = await client.post(
            f"/api/v1/actors/{profiles['target']}/suspend",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Suspend owner while repairing link"},
        )
        assert suspend_owner.status_code == 200, suspend_owner.text
        suspended_revoke = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Revoke suspended owner link"},
        )
        assert suspended_revoke.status_code == 200, suspended_revoke.text
        suspended_reactivate = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Repair suspended owner link"},
        )
        assert suspended_reactivate.status_code == 200, suspended_reactivate.text
        owner_still_blocked = await client.patch(
            "/api/v1/actors/me",
            headers=headers["target"],
            json={"display_name": "Suspended owner cannot mutate"},
        )
        assert owner_still_blocked.status_code == 403
        assert owner_still_blocked.json()["error"]["code"] == "actor_suspended"
        restore_owner = await client.post(
            f"/api/v1/actors/{profiles['target']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Restore suspended owner"},
        )
        assert restore_owner.status_code == 200, restore_owner.text

        delegated = await client.post(
            "/api/v1/admin-role-grants",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(profiles["ordinary"]),
                "role": "access_administrator",
                "scope_type": "system",
                "scope_project_id": None,
                "reason": "Link reactivation grant non-restoration proof",
            },
        )
        assert delegated.status_code == 201, delegated.text
        ordinary_revoke = await client.post(
            f"/api/v1/actor-identity-links/{links['ordinary']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Revoke delegated actor link"},
        )
        assert ordinary_revoke.status_code == 200, ordinary_revoke.text
        revoke_grant = await client.post(
            f"/api/v1/admin-role-grants/{delegated.json()['resource_id']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Revoke grant independently"},
        )
        assert revoke_grant.status_code == 200, revoke_grant.text
        ordinary_reactivate = await client.post(
            f"/api/v1/actor-identity-links/{links['ordinary']}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Reactivate without restoring grant"},
        )
        assert ordinary_reactivate.status_code == 200, ordinary_reactivate.text
        async with db_session.get_session_factory()() as session:
            assert (
                await session.scalar(
                    select(AdminRoleGrant.status).where(
                        AdminRoleGrant.id == UUID(delegated.json()["resource_id"])
                    )
                )
                == "revoked"
            )

        provisioned_service = await client.post(
            "/api/v1/service-actors",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={
                "service_identity": ServiceIdentity.ARTIFACT_SCHEDULER.value,
                "subject": "auth09d-b-service-link-target",
                "reason": "Provision service link lifecycle target",
            },
        )
        assert provisioned_service.status_code == 201, provisioned_service.text
        service_id = UUID(provisioned_service.json()["actor_profile_id"])
        service_state = await actor_link_state(service_id)
        service_link = UUID(service_state[2])
        service_revoke = await client.post(
            f"/api/v1/actor-identity-links/{service_link}/revoke",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Revoke fixed service link"},
        )
        assert service_revoke.status_code == 200, service_revoke.text
        service_reactivate = await client.post(
            f"/api/v1/actor-identity-links/{service_link}/reactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Reactivate fixed service link without admission"},
        )
        assert service_reactivate.status_code == 200, service_reactivate.text
        assert (await actor_link_state(service_id))[10] is None

        deactivate_target = await client.post(
            f"/api/v1/actors/{profiles['target']}/deactivate",
            headers={**headers["admin"], "Idempotency-Key": str(uuid4())},
            json={"reason": "Terminal owner proof"},
        )
        assert deactivate_target.status_code == 200, deactivate_target.text
        terminal_key = str(uuid4())
        terminal_link = await client.post(
            f"/api/v1/actor-identity-links/{links['target']}/revoke",
            headers={**headers["admin"], "Idempotency-Key": terminal_key},
            json={"reason": "Terminal owner link must not change"},
        )
        assert terminal_link.status_code == 409
        assert terminal_link.json()["error"]["code"] == "actor_deactivated_terminal"
        assert await idempotency_count(terminal_key) == 0

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        ) == 0
        link_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.event_type.in_(
                            ["ActorIdentityLinkRevoked", "ActorIdentityLinkReactivated"]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        assert link_events
        assert all(event.target_actor_ref for event in link_events)
        evidence = json.dumps(
            [
                (
                    event.event_type,
                    event.resource_type,
                    event.resource_id,
                    event.target_actor_ref,
                    event.before_facts,
                    event.after_facts,
                )
                for event in link_events
            ],
            default=str,
        )
        for private in (
            settings.token_issuer,
            *tokens.values(),
            *(f"private-auth09d-b-{name}@example.test" for name in names),
            normalized_reason.strip(),
            derive_reason_digest(normalized_reason.strip()),
        ):
            assert private not in evidence


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

        ordered_requests = partial(
            ordered_control_requests,
            client=client, monkeypatch=monkeypatch, database_url=auth_database_env,
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

        suspended_deactivate_first_id, _ = await create_race_actor("suspended-deactivate-first")
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
            suspended_deactivate_first[1][1].json()["error"]["code"] == "actor_deactivated_terminal"
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

        reciprocal_one_id, reciprocal_one_headers = await create_race_actor("reciprocal-one")
        reciprocal_two_id, reciprocal_two_headers = await create_race_actor("reciprocal-two")
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
        assert (
            await AdminAuthorizationRepository(session).count_effective_access_administrators() == 1
        )
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


async def test_actor_identity_link_lifecycle_real_postgres_concurrency(
    auth_database_env: str,
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove link and mixed-authority races with observed PostgreSQL blockers."""
    private_key, jwk = rsa_signing_material
    settings = production_verifier_settings(database_url=auth_database_env).model_copy(
        update={"api_admin_mutation_rate_limit": 1_000}
    )
    app = create_app(settings)
    app.state.auth_verifier = FlowAuthVerifier(settings, jwks_transport=jwks_transport(jwk))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        actors: dict[str, tuple[UUID, UUID, dict[str, str]]] = {}

        async def create_actor(name: str) -> tuple[UUID, UUID, dict[str, str]]:
            token = issue_asymmetric_token(
                private_key,
                claims={
                    "sub": f"auth09d-b-race-{name}",
                    "jti": f"auth09d-b-race-{name}-token",
                },
            )
            actor_headers = {"Authorization": f"Bearer {token}"}
            response = await client.get("/api/v1/actors/me", headers=actor_headers)
            assert response.status_code == 200, response.text
            actor_id = UUID(response.json()["actor_profile_id"])
            async with db_session.get_session_factory()() as session:
                link_id = UUID(
                    await session.scalar(
                        select(ActorIdentityLink.id).where(
                            ActorIdentityLink.actor_profile_id == str(actor_id)
                        )
                    )
                )
            actors[name] = (actor_id, link_id, actor_headers)
            return actors[name]

        bootstrap_id, _, bootstrap_headers = await create_actor("bootstrap")
        bootstrap_code, bootstrap = await run_admin_bootstrap(bootstrap_id, execute=True)
        assert bootstrap_code == 0

        async def grant_admin(
            target_id: UUID,
            caller_headers: dict[str, str],
            reason: str,
        ) -> UUID:
            response = await client.post(
                "/api/v1/admin-role-grants",
                headers={**caller_headers, "Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": str(target_id),
                    "role": "access_administrator",
                    "scope_type": "system",
                    "scope_project_id": None,
                    "reason": reason,
                },
            )
            assert response.status_code == 201, response.text
            return UUID(response.json()["resource_id"])

        async def link_post(
            link_id: UUID,
            operation: str,
            caller_headers: dict[str, str],
            key: str,
            reason: str,
        ) -> Response:
            return await client.post(
                f"/api/v1/actor-identity-links/{link_id}/{operation}",
                headers={**caller_headers, "Idempotency-Key": key},
                json={"reason": reason},
            )

        tracked_events = (
            "ActorIdentityLinkRevoked",
            "ActorIdentityLinkReactivated",
            "ActorProfileSuspended",
            "AdminRoleGrantRevoked",
            "AuthorityInvalidationRequested",
            "SensitiveAuthorizationDenied",
        )

        async def audit_counts() -> dict[str, int]:
            async with db_session.get_session_factory()() as session:
                return {
                    event_type: count
                    for event_type, count in (
                        await session.execute(
                            select(AuditEvent.event_type, func.count())
                            .where(AuditEvent.event_type.in_(tracked_events))
                            .group_by(AuditEvent.event_type)
                        )
                    ).all()
                }

        async def assert_audit_delta(
            before: dict[str, int],
            expected: dict[str, int],
        ) -> None:
            after = await audit_counts()
            assert {
                event_type: after.get(event_type, 0) - before.get(event_type, 0)
                for event_type in tracked_events
            } == {event_type: expected.get(event_type, 0) for event_type in tracked_events}

        async def idempotency_status(key: str) -> str | None:
            async with db_session.get_session_factory()() as session:
                return await session.scalar(
                    select(AuthorityIdempotencyRecord.status).where(
                        AuthorityIdempotencyRecord.idempotency_key == key
                    )
                )

        async def actor_state(actor_id: UUID) -> tuple[str, datetime, datetime, str]:
            async with db_session.get_session_factory()() as session:
                row = (
                    await session.execute(
                        select(
                            ActorProfile.status,
                            ActorProfile.last_seen_at,
                            ActorIdentityLink.last_verified_at,
                            ActorIdentityLink.status,
                        )
                        .join(
                            ActorIdentityLink,
                            ActorIdentityLink.actor_profile_id == ActorProfile.id,
                        )
                        .where(ActorProfile.id == str(actor_id))
                    )
                ).one()
                assert row[1] is not None and row[2] is not None
                return row[0], row[1], row[2], row[3]

        async def grant_state(grant_id: UUID) -> tuple[str, str]:
            async with db_session.get_session_factory()() as session:
                row = (
                    await session.execute(
                        select(
                            AdminRoleGrant.status,
                            AdminRoleGrant.target_actor_profile_id,
                        ).where(AdminRoleGrant.id == grant_id)
                    )
                ).one()
                return row[0], row[1]

        async def effective_access_administrators() -> set[str]:
            async with db_session.get_session_factory()() as session:
                return set(
                    await session.scalars(
                        select(AdminRoleGrant.target_actor_profile_id)
                        .join(
                            ActorProfile,
                            ActorProfile.id == AdminRoleGrant.target_actor_profile_id,
                        )
                        .join(
                            ActorIdentityLink,
                            ActorIdentityLink.actor_profile_id == ActorProfile.id,
                        )
                        .where(
                            AdminRoleGrant.role == "access_administrator",
                            AdminRoleGrant.scope_type == "system",
                            AdminRoleGrant.status == "active",
                            ActorProfile.actor_kind == "human",
                            ActorProfile.status == "active",
                            ActorIdentityLink.status == "active",
                        )
                        .distinct()
                    )
                )

        async def concurrent_link_posts(
            link_id: UUID,
            operation: str,
            keys: tuple[str, str],
        ) -> tuple[Response, Response]:
            original_reserve = AuthorityIdempotencyRepository.reserve
            original_lock_control = AdminAuthorizationRepository.lock_control
            first_blocker_acquired = asyncio.Event()
            release_first = asyncio.Event()
            second_entered = asyncio.Event()
            waiter_name = f"auth09db-link-{uuid4().hex}"
            same_key = keys[0] == keys[1]

            async def observed_reserve(self, **kwargs):
                task_name = current_task_name()
                if not same_key:
                    return await original_reserve(self, **kwargs)
                if task_name == "concurrent-link-first":
                    result = await original_reserve(self, **kwargs)
                    first_blocker_acquired.set()
                    await release_first.wait()
                    return result
                await first_blocker_acquired.wait()
                await self._session.execute(
                    text("select set_config('application_name', :name, true)"),
                    {"name": waiter_name},
                )
                second_entered.set()
                return await original_reserve(self, **kwargs)

            async def observed_lock_control(self):
                task_name = current_task_name()
                if same_key:
                    return await original_lock_control(self)
                if task_name == "concurrent-link-first":
                    control = await original_lock_control(self)
                    first_blocker_acquired.set()
                    await release_first.wait()
                    return control
                await first_blocker_acquired.wait()
                await self._session.execute(
                    text("select set_config('application_name', :name, true)"),
                    {"name": waiter_name},
                )
                second_entered.set()
                return await original_lock_control(self)

            monkeypatch.setattr(
                AuthorityIdempotencyRepository,
                "reserve",
                observed_reserve,
            )
            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_control",
                observed_lock_control,
            )
            try:
                first_task = asyncio.create_task(
                    link_post(
                        link_id,
                        operation,
                        bootstrap_headers,
                        keys[0],
                        f"Concurrent {operation} exact link",
                    ),
                    name="concurrent-link-first",
                )
                await asyncio.wait_for(first_blocker_acquired.wait(), timeout=20)
                second_task = asyncio.create_task(
                    link_post(
                        link_id,
                        operation,
                        bootstrap_headers,
                        keys[1],
                        f"Concurrent {operation} exact link",
                    ),
                    name="concurrent-link-second",
                )
                await asyncio.wait_for(second_entered.wait(), timeout=20)
                await asyncio.wait_for(
                    wait_for_named_database_lock(auth_database_env, waiter_name),
                    timeout=20,
                )
                release_first.set()
                first, second = await asyncio.wait_for(
                    asyncio.gather(first_task, second_task),
                    timeout=60,
                )
                return first, second
            finally:
                release_first.set()
                monkeypatch.setattr(
                    AuthorityIdempotencyRepository,
                    "reserve",
                    original_reserve,
                )
                monkeypatch.setattr(
                    AdminAuthorizationRepository,
                    "lock_control",
                    original_lock_control,
                )

        expected_one_link_success = {
            "AuthorityInvalidationRequested": 1,
            "SensitiveAuthorizationDenied": 0,
        }
        for operation, initial_revoke, final_status, conflict_code, success_event in (
            (
                "revoke",
                False,
                "revoked",
                "identity_link_already_revoked",
                "ActorIdentityLinkRevoked",
            ),
            (
                "reactivate",
                True,
                "active",
                "identity_link_not_revoked",
                "ActorIdentityLinkReactivated",
            ),
        ):
            for key_kind in ("same", "different"):
                actor_id, link_id, _ = await create_actor(f"{operation}-{key_kind}")
                if initial_revoke:
                    prepared = await link_post(
                        link_id,
                        "revoke",
                        bootstrap_headers,
                        str(uuid4()),
                        "Prepare revoked-link concurrency row",
                    )
                    assert prepared.status_code == 200, prepared.text
                before = await audit_counts()
                keys = (
                    (shared := str(uuid4()), shared)
                    if key_kind == "same"
                    else (str(uuid4()), str(uuid4()))
                )
                responses = await concurrent_link_posts(link_id, operation, keys)
                statuses = sorted(response.status_code for response in responses)
                if key_kind == "same":
                    assert statuses == [200, 200]
                    assert responses[0].json() == responses[1].json()
                    assert await idempotency_status(keys[0]) == "committed"
                    denial_count = 0
                else:
                    assert statuses == [200, 409]
                    loser_index = next(
                        index
                        for index, response in enumerate(responses)
                        if response.status_code == 409
                    )
                    assert responses[loser_index].json()["error"]["code"] == conflict_code
                    assert await idempotency_status(keys[1 - loser_index]) == "committed"
                    assert await idempotency_status(keys[loser_index]) is None
                    denial_count = 1
                assert (await actor_state(actor_id))[3] == final_status
                await assert_audit_delta(
                    before,
                    {
                        **expected_one_link_success,
                        success_event: 1,
                        "SensitiveAuthorizationDenied": denial_count,
                    },
                )

        ordered_requests = partial(
            ordered_control_requests,
            client=client, monkeypatch=monkeypatch, database_url=auth_database_env,
        )

        def link_request(
            name: str,
            link_id: UUID,
            operation: str,
            caller_headers: dict[str, str] = bootstrap_headers,
        ) -> tuple[str, str, dict[str, str], dict[str, str], str]:
            return (
                name,
                f"/api/v1/actor-identity-links/{link_id}/{operation}",
                caller_headers,
                {"reason": f"Ordered {operation} for {name}"},
                str(uuid4()),
            )

        ordered_rows = (
            (False, "revoke", "reactivate", [200, 200], None, "active"),
            (False, "reactivate", "revoke", [409, 200], "identity_link_not_revoked", "revoked"),
            (True, "reactivate", "revoke", [200, 200], None, "revoked"),
            (True, "revoke", "reactivate", [409, 200], "identity_link_already_revoked", "active"),
        )
        for index, (initial_revoke, first, second, statuses, error, final_status) in enumerate(
            ordered_rows
        ):
            actor_id, link_id, _ = await create_actor(f"ordered-{index}")
            if initial_revoke:
                prepared = await link_post(
                    link_id,
                    "revoke",
                    bootstrap_headers,
                    str(uuid4()),
                    "Prepare ordered revoked-link row",
                )
                assert prepared.status_code == 200, prepared.text
            before = await audit_counts()
            results = await ordered_requests(
                f"ordered-{index}-first",
                (
                    link_request(f"ordered-{index}-first", link_id, first),
                    link_request(f"ordered-{index}-second", link_id, second),
                ),
            )
            assert [response.status_code for _, response in results] == statuses
            if error is not None:
                assert results[0][1].json()["error"]["code"] == error
                assert await idempotency_status(results[0][0]) is None
                expected_denials = 1
                expected_invalidation = 1
            else:
                assert [await idempotency_status(key) for key, _ in results] == [
                    "committed",
                    "committed",
                ]
                expected_denials = 0
                expected_invalidation = 2
            assert await idempotency_status(results[1][0]) == "committed"
            assert (await actor_state(actor_id))[3] == final_status
            await assert_audit_delta(
                before,
                {
                    "ActorIdentityLinkRevoked": int(error is None or second == "revoke"),
                    "ActorIdentityLinkReactivated": int(error is None or second == "reactivate"),
                    "AuthorityInvalidationRequested": expected_invalidation,
                    "SensitiveAuthorizationDenied": expected_denials,
                },
            )

        custodian = (bootstrap_id, bootstrap_headers)

        async def two_admins(
            name: str,
        ) -> tuple[
            tuple[UUID, UUID, dict[str, str], UUID],
            tuple[UUID, UUID, dict[str, str], UUID],
        ]:
            nonlocal custodian
            a_id, a_link, a_headers = await create_actor(f"{name}-a")
            b_id, b_link, b_headers = await create_actor(f"{name}-b")
            a_grant = await grant_admin(a_id, custodian[1], f"Grant {name} administrator A")
            b_grant = await grant_admin(b_id, custodian[1], f"Grant {name} administrator B")
            disabled = await client.post(
                f"/api/v1/actors/{custodian[0]}/suspend",
                headers={**a_headers, "Idempotency-Key": str(uuid4())},
                json={"reason": f"Leave exactly two administrators for {name}"},
            )
            assert disabled.status_code == 200, disabled.text
            return (a_id, a_link, a_headers, a_grant), (
                b_id,
                b_link,
                b_headers,
                b_grant,
            )

        async def assert_mixed_row(
            first_request: tuple[str, str, dict[str, str], dict[str, str], str],
            second_request: tuple[str, str, dict[str, str], dict[str, str], str],
            denial_code: str,
            success_event: str,
        ) -> tuple[str, str]:
            before = await audit_counts()
            results = await ordered_requests(first_request[0], (first_request, second_request))
            assert [response.status_code for _, response in results] == [200, 403]
            assert results[1][1].json()["error"]["code"] == denial_code
            assert await idempotency_status(results[0][0]) == "committed"
            assert await idempotency_status(results[1][0]) is None
            await assert_audit_delta(
                before,
                {
                    success_event: 1,
                    "AuthorityInvalidationRequested": 1,
                    "SensitiveAuthorizationDenied": 1,
                },
            )
            return results[0][0], results[1][0]

        a, b = await two_admins("profile-first")
        await assert_mixed_row(
            (
                "profile-first-a",
                f"/api/v1/actors/{b[0]}/suspend",
                a[2],
                {"reason": "Profile loss before link loss"},
                str(uuid4()),
            ),
            link_request("profile-first-b", a[1], "revoke", b[2]),
            "actor_suspended",
            "ActorProfileSuspended",
        )
        assert (await actor_state(a[0]))[0::3] == ("active", "active")
        assert (await actor_state(b[0]))[0::3] == ("suspended", "active")
        assert await grant_state(a[3]) == ("active", str(a[0]))
        assert await grant_state(b[3]) == ("active", str(b[0]))
        assert await effective_access_administrators() == {str(a[0])}
        custodian = (a[0], a[2])

        a, b = await two_admins("link-first")
        await assert_mixed_row(
            link_request("link-first-b", a[1], "revoke", b[2]),
            (
                "link-first-a",
                f"/api/v1/actors/{b[0]}/suspend",
                a[2],
                {"reason": "Profile loss after link loss"},
                str(uuid4()),
            ),
            "identity_link_revoked",
            "ActorIdentityLinkRevoked",
        )
        assert (await actor_state(a[0]))[0::3] == ("active", "revoked")
        assert (await actor_state(b[0]))[0::3] == ("active", "active")
        assert await grant_state(a[3]) == ("active", str(a[0]))
        assert await grant_state(b[3]) == ("active", str(b[0]))
        assert await effective_access_administrators() == {str(b[0])}
        custodian = (b[0], b[2])

        a, b = await two_admins("link-grant")
        await assert_mixed_row(
            link_request("link-grant-a", b[1], "revoke", a[2]),
            (
                "link-grant-b",
                f"/api/v1/admin-role-grants/{a[3]}/revoke",
                b[2],
                {"reason": "Grant loss after link loss"},
                str(uuid4()),
            ),
            "identity_link_revoked",
            "ActorIdentityLinkRevoked",
        )
        assert (await actor_state(a[0]))[0::3] == ("active", "active")
        assert (await actor_state(b[0]))[0::3] == ("active", "revoked")
        assert await grant_state(a[3]) == ("active", str(a[0]))
        assert await grant_state(b[3]) == ("active", str(b[0]))
        assert await effective_access_administrators() == {str(a[0])}
        custodian = (a[0], a[2])

        a, b = await two_admins("grant-link")
        await assert_mixed_row(
            (
                "grant-link-b",
                f"/api/v1/admin-role-grants/{a[3]}/revoke",
                b[2],
                {"reason": "Grant loss before link loss"},
                str(uuid4()),
            ),
            link_request("grant-link-a", b[1], "revoke", a[2]),
            "permission_not_granted",
            "AdminRoleGrantRevoked",
        )
        assert (await actor_state(a[0]))[0::3] == ("active", "active")
        assert (await actor_state(b[0]))[0::3] == ("active", "active")
        assert await grant_state(a[3]) == ("revoked", str(a[0]))
        assert await grant_state(b[3]) == ("active", str(b[0]))
        assert await effective_access_administrators() == {str(b[0])}
        custodian = (b[0], b[2])

        a_id, _, a_headers = await create_actor("three-a")
        b_id, _, b_headers = await create_actor("three-b")
        c_id, c_link, c_headers = await create_actor("three-c")
        a_grant = await grant_admin(a_id, custodian[1], "Grant three-way administrator A")
        b_grant = await grant_admin(b_id, custodian[1], "Grant three-way administrator B")
        c_grant = await grant_admin(c_id, custodian[1], "Grant three-way administrator C")
        remove_custodian = await client.post(
            f"/api/v1/actors/{custodian[0]}/suspend",
            headers={**a_headers, "Idempotency-Key": str(uuid4())},
            json={"reason": "Leave exactly three administrators"},
        )
        assert remove_custodian.status_code == 200, remove_custodian.text
        original_lock_control = AdminAuthorizationRepository.lock_control
        first_locked = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()
        third_entered = asyncio.Event()
        second_name = f"auth09db-three-second-{uuid4().hex}"
        third_name = f"auth09db-three-third-{uuid4().hex}"

        async def three_way_lock_control(self):
            task_name = current_task_name()
            if task_name == "three-profile-first":
                control = await original_lock_control(self)
                first_locked.set()
                await release_first.wait()
                return control
            await first_locked.wait()
            application_name = second_name if task_name == "three-grant-second" else third_name
            await self._session.execute(
                text("select set_config('application_name', :name, true)"),
                {"name": application_name},
            )
            (second_entered if task_name == "three-grant-second" else third_entered).set()
            return await original_lock_control(self)

        monkeypatch.setattr(
            AdminAuthorizationRepository,
            "lock_control",
            three_way_lock_control,
        )
        three_before = await audit_counts()
        three_keys = (str(uuid4()), str(uuid4()), str(uuid4()))
        try:
            first_task = asyncio.create_task(
                client.post(
                    f"/api/v1/actors/{b_id}/suspend",
                    headers={**a_headers, "Idempotency-Key": three_keys[0]},
                    json={"reason": "Three-way profile loss first"},
                ),
                name="three-profile-first",
            )
            await first_locked.wait()
            second_task = asyncio.create_task(
                client.post(
                    f"/api/v1/admin-role-grants/{a_grant}/revoke",
                    headers={**c_headers, "Idempotency-Key": three_keys[1]},
                    json={"reason": "Three-way grant loss second"},
                ),
                name="three-grant-second",
            )
            await asyncio.wait_for(second_entered.wait(), timeout=20)
            await asyncio.wait_for(
                wait_for_named_database_lock(auth_database_env, second_name),
                timeout=20,
            )
            third_task = asyncio.create_task(
                link_post(
                    c_link,
                    "revoke",
                    b_headers,
                    three_keys[2],
                    "Three-way link loss denied third",
                ),
                name="three-link-third",
            )
            await asyncio.wait_for(third_entered.wait(), timeout=20)
            await asyncio.wait_for(
                wait_for_named_database_lock(auth_database_env, third_name),
                timeout=20,
            )
            release_first.set()
            three_responses = await asyncio.wait_for(
                asyncio.gather(first_task, second_task, third_task),
                timeout=60,
            )
        finally:
            release_first.set()
            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_control",
                original_lock_control,
            )
        assert [response.status_code for response in three_responses] == [200, 200, 403]
        assert three_responses[2].json()["error"]["code"] == "actor_suspended"
        assert [await idempotency_status(key) for key in three_keys] == [
            "committed",
            "committed",
            None,
        ]
        await assert_audit_delta(
            three_before,
            {
                "ActorProfileSuspended": 1,
                "AdminRoleGrantRevoked": 1,
                "AuthorityInvalidationRequested": 2,
                "SensitiveAuthorizationDenied": 1,
            },
        )
        assert (await actor_state(a_id))[0::3] == ("active", "active")
        assert (await actor_state(b_id))[0::3] == ("suspended", "active")
        assert (await actor_state(c_id))[0::3] == ("active", "active")
        assert await grant_state(a_grant) == ("revoked", str(a_id))
        assert await grant_state(b_grant) == ("active", str(b_id))
        assert await grant_state(c_grant) == ("active", str(c_id))
        assert await effective_access_administrators() == {str(c_id)}
        custodian = (c_id, c_headers)

        async def actor_self_race(method: str, lifecycle_first: bool, index: int) -> None:
            target_id, target_link, target_headers = await create_actor(
                f"self-{method.lower()}-{lifecycle_first}-{index}"
            )
            before_target = await actor_state(target_id)
            before_admin = await actor_state(custodian[0])
            before_events = await audit_counts()
            lifecycle_key = str(uuid4())
            self_name = f"self-{index}"
            lifecycle_name = f"lifecycle-{index}"
            waiter_name = f"auth09db-self-{uuid4().hex}"
            self_lock_owner = ActorService
            self_lock_attribute = "lock_actor_self_for_authorization"
            original_self_lock = getattr(self_lock_owner, self_lock_attribute)
            original_link_lock = AdminAuthorizationRepository.lock_identity_link_lifecycle_target
            first_locked = asyncio.Event()
            release_first = asyncio.Event()
            waiter_entered = asyncio.Event()
            captured_after_self: list[tuple[datetime, datetime]] = []

            if lifecycle_first:

                async def ordered_link_lock(self, identity_link_id):
                    locked = await original_link_lock(self, identity_link_id)
                    first_locked.set()
                    await release_first.wait()
                    return locked

                async def ordered_self_lock(service, *args):
                    await first_locked.wait()
                    await service._session.execute(
                        text("select set_config('application_name', :name, true)"),
                        {"name": waiter_name},
                    )
                    waiter_entered.set()
                    return await original_self_lock(service, *args)

            else:

                async def ordered_self_lock(service, *args):
                    locked = await original_self_lock(service, *args)
                    first_locked.set()
                    await release_first.wait()
                    return locked

                async def ordered_link_lock(self, identity_link_id):
                    await first_locked.wait()
                    await self._session.execute(
                        text("select set_config('application_name', :name, true)"),
                        {"name": waiter_name},
                    )
                    waiter_entered.set()
                    locked = await original_link_lock(self, identity_link_id)
                    if locked is not None:
                        captured_after_self.append(
                            (locked[1].last_seen_at, locked[0].last_verified_at)
                        )
                    return locked

            monkeypatch.setattr(
                self_lock_owner,
                self_lock_attribute,
                ordered_self_lock,
            )
            monkeypatch.setattr(
                AdminAuthorizationRepository,
                "lock_identity_link_lifecycle_target",
                ordered_link_lock,
            )
            self_task: asyncio.Task[Response] | None = None
            lifecycle_task: asyncio.Task[Response] | None = None
            try:

                async def self_request() -> Response:
                    return await client.request(
                        method,
                        "/api/v1/actors/me",
                        headers=target_headers,
                        json=(
                            {"display_name": f"Ordered self patch {index}"}
                            if method == "PATCH"
                            else None
                        ),
                    )

                async def lifecycle_request() -> Response:
                    return await link_post(
                        target_link,
                        "revoke",
                        custodian[1],
                        lifecycle_key,
                        f"Ordered self lifecycle {index}",
                    )

                async def require_first_lock(task: asyncio.Task[Response]) -> None:
                    lock_task = asyncio.create_task(first_locked.wait())
                    done, _ = await asyncio.wait(
                        {task, lock_task},
                        timeout=20,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if lock_task in done:
                        return
                    lock_task.cancel()
                    if task in done:
                        early = task.result()
                        raise AssertionError(
                            f"blocker returned before target lock: {early.status_code} {early.text}"
                        )
                    raise AssertionError("blocker did not reach the target lock")

                async def require_waiter(task: asyncio.Task[Response]) -> None:
                    waiter_task = asyncio.create_task(waiter_entered.wait())
                    done, _ = await asyncio.wait(
                        {task, waiter_task},
                        timeout=20,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if waiter_task in done:
                        return
                    waiter_task.cancel()
                    if task in done:
                        early = task.result()
                        raise AssertionError(
                            f"{method} lifecycle_first={lifecycle_first} waiter returned "
                            f"before target lock: {early.status_code} {early.text}"
                        )
                    raise AssertionError(
                        f"{method} lifecycle_first={lifecycle_first} waiter did not "
                        "reach the target lock"
                    )

                if lifecycle_first:
                    lifecycle_task = asyncio.create_task(lifecycle_request(), name=lifecycle_name)
                    await require_first_lock(lifecycle_task)
                    self_task = asyncio.create_task(self_request(), name=self_name)
                else:
                    self_task = asyncio.create_task(self_request(), name=self_name)
                    await require_first_lock(self_task)
                    lifecycle_task = asyncio.create_task(lifecycle_request(), name=lifecycle_name)
                waiter = self_task if lifecycle_first else lifecycle_task
                assert waiter is not None
                await require_waiter(waiter)
                await asyncio.wait_for(
                    wait_for_named_database_lock(auth_database_env, waiter_name),
                    timeout=20,
                )
                release_first.set()
                self_response, lifecycle_response = await asyncio.wait_for(
                    asyncio.gather(self_task, lifecycle_task),
                    timeout=60,
                )
            finally:
                release_first.set()
                tasks = [
                    task
                    for task in (self_task, lifecycle_task)
                    if task is not None and not task.done()
                ]
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                monkeypatch.setattr(
                    self_lock_owner,
                    self_lock_attribute,
                    original_self_lock,
                )
                monkeypatch.setattr(
                    AdminAuthorizationRepository,
                    "lock_identity_link_lifecycle_target",
                    original_link_lock,
                )
            assert lifecycle_response.status_code == 200, lifecycle_response.text
            assert await idempotency_status(lifecycle_key) == "committed"
            final_target = await actor_state(target_id)
            final_admin = await actor_state(custodian[0])
            assert final_target[3] == "revoked"
            assert final_admin[1] > before_admin[1]
            assert final_admin[2] > before_admin[2]
            if lifecycle_first:
                assert self_response.status_code == 403, self_response.text
                assert self_response.json()["error"]["code"] == "identity_link_revoked"
                assert final_target[1:3] == before_target[1:3]
                denial_count = 1
            else:
                assert self_response.status_code == 200, self_response.text
                assert captured_after_self
                assert final_target[1:3] == captured_after_self[0]
                assert final_target[1] > before_target[1]
                assert final_target[2] > before_target[2]
                denial_count = 0
            await assert_audit_delta(
                before_events,
                {
                    "ActorIdentityLinkRevoked": 1,
                    "AuthorityInvalidationRequested": 1,
                    "SensitiveAuthorizationDenied": denial_count,
                },
            )

        index = 0
        for method in ("GET", "PATCH"):
            for lifecycle_first in (False, True):
                index += 1
                await actor_self_race(method, lifecycle_first, index)

    async with db_session.get_session_factory()() as session:
        assert (
            await AdminAuthorizationRepository(session).count_effective_access_administrators() == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthorityIdempotencyRecord)
                .where(AuthorityIdempotencyRecord.status == "pending")
            )
            or 0
        ) == 0


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

    assert "/api/v1/actors/me" in paths
    assert "/api/v1/auth/me" not in paths
    assert "/api/v1/demo/worker-profile" not in paths
    assert not any(
        segment in forbidden_segments for path in paths for segment in path.strip("/").split("/")
    )
