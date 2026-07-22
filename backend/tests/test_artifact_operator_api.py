"""HTTP contract proofs for the hidden Operator artifact router."""

from __future__ import annotations

from uuid import uuid4

from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_db_session
from app.main import create_app
from app.modules.artifacts.operator import artifact_provider_readiness
from app.modules.artifacts.models import ArtifactBinding, ArtifactPutAttempt, ArtifactReplica
from app.modules.artifacts.router import (
    _concealed,
    get_artifact_authorization_context,
    get_artifact_operator_authority,
    get_artifact_recovery_authority,
    router,
)
from app.modules.artifacts.schemas import (
    ArtifactOperatorAuthorizationEvidence,
    DenyArtifactOperatorAuthority,
    DenyArtifactRecoveryAuthority,
)
from app.modules.authorization.catalogue import ACTION_BY_ID
from app.core.config import Settings
from tests.test_artifact_recovery import (
    _AllowRecoveryAuthority,
    _context,
    _exhausted_job,
    _settings,
    recovery_database_env,  # noqa: F401 - imported pytest fixture
)


EXPECTED = {
    ("GET", "/api/v1/operator/artifacts/bindings"),
    ("GET", "/api/v1/operator/artifacts/contents/{content_id}/replicas"),
    ("GET", "/api/v1/operator/artifacts/replicas/{replica_id}/receipts"),
    ("GET", "/api/v1/operator/artifacts/verification-jobs/{verification_job_id}"),
    ("POST", "/api/v1/operator/artifacts/verification-jobs/{verification_job_id}/retry"),
    ("GET", "/api/v1/operator/artifacts/recovery-attempts/{recovery_attempt_id}"),
    ("GET", "/api/v1/operator/artifacts/audit-events"),
    ("GET", "/api/v1/operator/artifacts/admission-usage"),
    ("GET", "/api/v1/operator/artifacts/readiness"),
}


def test_operator_router_exposes_exact_hidden_surface() -> None:
    actual = {
        (method, f"/api/v1{route.path}")
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if route.path.startswith("/operator/artifacts")
    }
    assert actual == EXPECTED


def test_concealed_errors_do_not_expose_authority_or_existence() -> None:
    error = _concealed(RuntimeError("provider_object_ref=s3://secret"))
    assert error.status_code == 404
    assert error.detail == "Artifact resource not found"


def test_readiness_contract_contains_no_provider_internals() -> None:
    payload = artifact_provider_readiness(Settings())
    assert set(payload) == {
        "backend",
        "provider_profile",
        "configured",
        "active",
        "status",
        "prerequisites",
    }
    assert "endpoint" not in str(payload).lower()
    assert "credential" not in str(payload).lower()


class _AllowOperatorAuthority:
    async def authorize(self, *, facts, **_values: object) -> ArtifactOperatorAuthorizationEvidence:
        return ArtifactOperatorAuthorizationEvidence(
            action_id=facts.action_id,
            permission_id=ACTION_BY_ID[facts.action_id].permission_id.value,
            decision_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_real_http_operator_path_returns_redacted_lineage_and_recovery(
    recovery_database_env: str,  # noqa: F811
    tmp_path,
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap = None
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source_job, _orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            attempt = await session.scalar(select(ArtifactPutAttempt))
            assert attempt is not None and attempt.replica_id is not None
            replica = await session.get(ArtifactReplica, attempt.replica_id)
            assert replica is not None
            replica_id = replica.id
            source_job_id = source_job.id
            source_job_cas_version = source_job.cas_version
            binding_id = "00000000-0000-0000-0000-000000000101"
            second_binding_id = "00000000-0000-0000-0000-000000000102"
            session.add_all(
                [
                    ArtifactBinding(
                        id=binding_id,
                        content_id=replica.content_id,
                        project_id=project_id,
                        resource_type="task",
                        resource_id=task_id,
                        logical_role="submission",
                        scope_version=1,
                        actor_id=str(context.actor_profile_id),
                        attribution_type="human",
                    ),
                    ArtifactBinding(
                        id=second_binding_id,
                        content_id=replica.content_id,
                        project_id=project_id,
                        resource_type="task",
                        resource_id=task_id,
                        logical_role="diagnostic",
                        scope_version=1,
                        actor_id=str(context.actor_profile_id),
                        attribution_type="human",
                    ),
                ]
            )
            await session.commit()

            app = create_app(settings)

            async def session_override():
                try:
                    yield session
                finally:
                    if session.in_transaction():
                        await session.rollback()

            async def context_override():
                return context

            app.dependency_overrides[get_db_session] = session_override
            app.dependency_overrides[get_artifact_authorization_context] = context_override
            app.dependency_overrides[get_artifact_operator_authority] = _AllowOperatorAuthority
            app.dependency_overrides[get_artifact_recovery_authority] = _AllowRecoveryAuthority

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                binding = await client.get(
                    "/api/v1/operator/artifacts/bindings",
                    params={"resource_type": "task", "resource_id": task_id, "limit": 1},
                )
                assert binding.status_code == 200
                assert binding.json()["items"][0]["id"] == binding_id
                assert binding.json()["next_cursor"] == binding_id
                content_id = binding.json()["items"][0]["content_id"]
                next_binding = await client.get(
                    "/api/v1/operator/artifacts/bindings",
                    params={
                        "resource_type": "task",
                        "resource_id": task_id,
                        "cursor": binding_id,
                        "limit": 1,
                    },
                )
                assert next_binding.json()["items"][0]["id"] == second_binding_id

                replicas = await client.get(
                    f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
                )
                assert replicas.status_code == 200
                replica_payload = replicas.json()["items"][0]
                assert replica_payload["id"] == replica_id
                assert "provider_object_ref" not in replica_payload
                assert "provider_profile" not in replica_payload

                receipts = await client.get(
                    f"/api/v1/operator/artifacts/replicas/{replica_id}/receipts"
                )
                assert receipts.status_code == 200
                assert "request_digest" not in receipts.text
                assert "idempotency_key" not in receipts.text

                job = await client.get(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}"
                )
                assert job.status_code == 200
                assert job.json()["status"] == "provider_unavailable"

                retry = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "reason": "provider remained unavailable",
                        "client_idempotency_key": "operator-http-retry",
                        "expected_source_job_cas_version": source_job_cas_version,
                    },
                )
                assert retry.status_code == 202
                recovery_id = retry.json()["recovery_attempt_id"]

                recovery = await client.get(
                    f"/api/v1/operator/artifacts/recovery-attempts/{recovery_id}"
                )
                assert recovery.status_code == 200
                assert recovery.json()["source_verification_job_id"] == source_job_id

                audit = await client.get(
                    "/api/v1/operator/artifacts/audit-events",
                    params={
                        "resource_type": "artifact_recovery_attempt",
                        "resource_id": recovery_id,
                    },
                )
                assert audit.status_code == 200
                assert audit.json()["items"][0]["event_type"] == "ArtifactRecoveryInitiated"

                usage = await client.get(
                    "/api/v1/operator/artifacts/admission-usage",
                    params={"project_id": project_id, "task_id": task_id},
                )
                assert usage.status_code == 200
                assert usage.json()["items"]
                assert "producer_ref" not in usage.text
                invalid_cursor = await client.get(
                    "/api/v1/operator/artifacts/admission-usage",
                    params={"project_id": project_id, "cursor": "invalid"},
                )
                assert invalid_cursor.status_code == 422

                readiness = await client.get("/api/v1/operator/artifacts/readiness")
                assert readiness.status_code == 200
                assert readiness.json()["active"] is False

                app.dependency_overrides[get_artifact_operator_authority] = (
                    DenyArtifactOperatorAuthority
                )
                concealed = await client.get(
                    f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
                )
                assert concealed.status_code == 404
                assert content_id not in concealed.text

                app.dependency_overrides[get_artifact_recovery_authority] = (
                    DenyArtifactRecoveryAuthority
                )
                denied_retry = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{uuid4()}/retry",
                    json={
                        "project_id": project_id,
                        "reason": "probe",
                        "client_idempotency_key": "denied-probe",
                        "expected_source_job_cas_version": 0,
                    },
                )
                assert denied_retry.status_code == 404
    finally:
        if bootstrap is not None:
            bootstrap.close()
        await engine.dispose()
