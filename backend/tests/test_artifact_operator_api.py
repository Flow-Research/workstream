"""HTTP contract proofs for the hidden Operator artifact router."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_db_session
from app.main import create_app
from app.modules.artifacts.operator import artifact_provider_readiness
from app.modules.artifacts.metrics import artifact_admission_metrics
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactPutAttempt,
    ArtifactPutObservationReceipt,
    ArtifactReplica,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.router import (
    _concealed,
    get_artifact_authorization_context,
    get_artifact_operator_authority,
    get_artifact_recovery_authority,
    router,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactOperatorAuthorizationEvidence,
    DenyArtifactOperatorAuthority,
    DenyArtifactRecoveryAuthority,
)
from app.modules.authorization.catalogue import ACTION_BY_ID
from app.modules.authorization.runtime import ActorStatus, IdentityLinkStatus
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


class _ProjectOperatorAuthority(_AllowOperatorAuthority):
    def __init__(self, project_id: str) -> None:
        self._project_id = UUID(project_id)

    async def authorize(self, *, facts, **values: object) -> ArtifactOperatorAuthorizationEvidence:
        if facts.project_ids != (self._project_id,):
            raise ArtifactAuthorityDeniedError("project scope is not authorized")
        return await super().authorize(facts=facts, **values)


class _ProjectRecoveryAuthority(_AllowRecoveryAuthority):
    def __init__(self, project_id: str) -> None:
        self._project_id = UUID(project_id)

    async def authorize(self, *, facts, **values: object):
        if facts.project_id != self._project_id:
            raise ArtifactAuthorityDeniedError("project scope is not authorized")
        return await super().authorize(facts=facts, **values)


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
            (
                project_id,
                task_id,
                submission_id,
                source_job,
                _orchestrator,
                bootstrap,
            ) = await _exhausted_job(session, settings, tmp_path, context)
            assert {scope_type for scope_type, _band in artifact_admission_metrics.snapshot()} == {
                "deployment",
                "project",
                "producer",
                "task",
            }
            attempt = await session.scalar(select(ArtifactPutAttempt))
            assert attempt is not None and attempt.replica_id is not None
            attempt_id = attempt.id
            attempt_sha256 = attempt.sha256
            attempt_byte_count = attempt.byte_count
            replica = await session.get(ArtifactReplica, attempt.replica_id)
            assert replica is not None
            replica_id = replica.id
            content_id = replica.content_id
            source_job_id = source_job.id
            source_job_cas_version = source_job.cas_version
            binding_id = "00000000-0000-0000-0000-000000000101"
            second_binding_id = "00000000-0000-0000-0000-000000000102"
            observation_receipt_id = "00000000-0000-0000-0000-000000000201"
            verification_receipt_id = "00000000-0000-0000-0000-000000000202"
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
                unbound_replicas = await client.get(
                    f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
                )
                unbound_job = await client.get(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}"
                )
                assert unbound_replicas.status_code == unbound_job.status_code == 200
                session.add_all(
                    [
                        ArtifactBinding(
                            id=binding_id,
                            content_id=content_id,
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
                            content_id=content_id,
                            project_id=project_id,
                            resource_type="task",
                            resource_id=task_id,
                            logical_role="diagnostic",
                            scope_version=1,
                            actor_id=str(context.actor_profile_id),
                            attribution_type="human",
                        ),
                        ArtifactPutObservationReceipt(
                            id=observation_receipt_id,
                            put_attempt_id=attempt_id,
                            execution_generation=99,
                            outcome="conflict",
                            expected_sha256=attempt_sha256,
                            expected_byte_count=attempt_byte_count,
                        ),
                        ArtifactVerificationReceipt(
                            id=verification_receipt_id,
                            verification_job_id=source_job_id,
                            execution_generation=99,
                            outcome="conflict",
                        ),
                    ]
                )
                await session.commit()
                binding = await client.get(
                    "/api/v1/operator/artifacts/bindings",
                    params={"resource_type": "task", "resource_id": task_id, "limit": 1},
                )
                assert binding.status_code == 200
                assert binding.json()["items"][0]["id"] == binding_id
                assert binding.json()["next_cursor"] == binding_id
                assert binding.json()["items"][0]["content_id"] == content_id
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
                final_binding_page = await client.get(
                    "/api/v1/operator/artifacts/bindings",
                    params={
                        "resource_type": "task",
                        "resource_id": task_id,
                        "cursor": second_binding_id,
                        "limit": 1,
                    },
                )
                assert final_binding_page.status_code == 200
                assert final_binding_page.json() == {"items": [], "next_cursor": None}

                replicas = await client.get(
                    f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
                )
                assert replicas.status_code == 200
                replica_payload = replicas.json()["items"][0]
                assert replica_payload["id"] == replica_id
                assert "provider_object_ref" not in replica_payload
                assert "provider_profile" not in replica_payload

                receipts = await client.get(
                    f"/api/v1/operator/artifacts/replicas/{replica_id}/receipts",
                    params={"limit": 1},
                )
                assert receipts.status_code == 200
                assert "request_digest" not in receipts.text
                assert "idempotency_key" not in receipts.text
                receipt_types = [receipts.json()["items"][0]["receipt_type"]]
                receipt_cursor = receipts.json()["next_cursor"]
                while receipt_cursor is not None:
                    receipt_page = await client.get(
                        f"/api/v1/operator/artifacts/replicas/{replica_id}/receipts",
                        params={"limit": 1, "cursor": receipt_cursor},
                    )
                    assert receipt_page.status_code == 200, receipt_page.text
                    receipt_types.extend(
                        item["receipt_type"] for item in receipt_page.json()["items"]
                    )
                    receipt_cursor = receipt_page.json().get("next_cursor")
                assert receipt_types == ["put", "put_observation", "verification"]
                malformed_receipt_cursor = await client.get(
                    f"/api/v1/operator/artifacts/replicas/{replica_id}/receipts",
                    params={"cursor": "invalid"},
                )
                assert malformed_receipt_cursor.status_code == 422
                for receipt_id in (observation_receipt_id, verification_receipt_id):
                    receipt_audit = await client.get(
                        "/api/v1/operator/artifacts/audit-events",
                        params={
                            "resource_type": "artifact_receipt",
                            "resource_id": receipt_id,
                        },
                    )
                    assert receipt_audit.status_code == 200
                    assert receipt_audit.json()["items"] == []

                job = await client.get(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}"
                )
                assert job.status_code == 200
                assert job.json()["status"] == "provider_unavailable"

                app.dependency_overrides[get_artifact_recovery_authority] = (
                    DenyArtifactRecoveryAuthority
                )
                denied_before_create = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "authority race",
                        "client_idempotency_key": "authority-race",
                        "expected_source_job_cas_version": source_job_cas_version,
                    },
                )
                assert denied_before_create.status_code == 404
                app.dependency_overrides[get_artifact_recovery_authority] = _AllowRecoveryAuthority
                for unavailable_context in (
                    context.model_copy(update={"actor_status": ActorStatus.SUSPENDED}),
                    context.model_copy(update={"identity_link_status": IdentityLinkStatus.REVOKED}),
                ):
                    app.dependency_overrides[get_artifact_authorization_context] = (
                        lambda unavailable_context=unavailable_context: unavailable_context
                    )
                    unavailable = await client.post(
                        f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                        json={
                            "project_id": project_id,
                            "task_id": task_id,
                            "submission_id": submission_id,
                            "reason": "identity race",
                            "client_idempotency_key": str(unavailable_context.actor_status),
                            "expected_source_job_cas_version": source_job_cas_version,
                        },
                    )
                    assert unavailable.status_code == 404
                app.dependency_overrides[get_artifact_authorization_context] = context_override
                stale_source = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "stale source fence",
                        "client_idempotency_key": "stale-source",
                        "expected_source_job_cas_version": source_job_cas_version + 1,
                    },
                )
                assert stale_source.status_code == 409

                retry = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "provider remained unavailable",
                        "client_idempotency_key": "operator-http-retry",
                        "expected_source_job_cas_version": source_job_cas_version,
                    },
                )
                assert retry.status_code == 202, retry.text
                recovery_id = retry.json()["recovery_attempt_id"]
                retry_job_id = retry.json()["retry_verification_job_id"]
                replay = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "provider remained unavailable",
                        "client_idempotency_key": "operator-http-retry",
                        "expected_source_job_cas_version": source_job_cas_version,
                    },
                )
                assert replay.status_code == 202
                assert replay.json()["replayed"] is True
                assert replay.json()["recovery_attempt_id"] == recovery_id
                altered = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "altered replay",
                        "client_idempotency_key": "operator-http-retry",
                        "expected_source_job_cas_version": source_job_cas_version,
                    },
                )
                assert altered.status_code == 409
                ineligible = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{retry_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "pending retry is ineligible",
                        "client_idempotency_key": "ineligible-retry",
                        "expected_source_job_cas_version": 0,
                    },
                )
                assert ineligible.status_code == 422

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
                    params={"project_id": project_id, "task_id": task_id, "limit": 1},
                )
                assert usage.status_code == 200
                assert usage.json()["items"]
                for item in usage.json()["items"]:
                    assert {
                        "unbound_ready_count": item["unbound_ready_count"],
                        "unbound_ready_bytes": item["unbound_ready_bytes"],
                        "stale_count": item["stale_count"],
                        "stale_bytes": item["stale_bytes"],
                    } == {
                        "unbound_ready_count": 0,
                        "unbound_ready_bytes": 0,
                        "stale_count": 0,
                        "stale_bytes": 0,
                    }
                assert "producer_ref" not in usage.text
                usage_types = [usage.json()["items"][0]["scope_type"]]
                usage_cursor = usage.json()["next_cursor"]
                while usage_cursor is not None:
                    usage_page = await client.get(
                        "/api/v1/operator/artifacts/admission-usage",
                        params={
                            "project_id": project_id,
                            "task_id": task_id,
                            "limit": 1,
                            "cursor": usage_cursor,
                        },
                    )
                    usage_types.extend(item["scope_type"] for item in usage_page.json()["items"])
                    usage_cursor = usage_page.json()["next_cursor"]
                assert usage_types == ["deployment", "project", "task"]
                invalid_cursor = await client.get(
                    "/api/v1/operator/artifacts/admission-usage",
                    params={"project_id": project_id, "cursor": "invalid"},
                )
                assert invalid_cursor.status_code == 422
                missing_project_usage = await client.get(
                    "/api/v1/operator/artifacts/admission-usage",
                    params={"project_id": str(uuid4())},
                )
                wrong_project_usage = await client.get(
                    "/api/v1/operator/artifacts/admission-usage",
                    params={"project_id": str(uuid4()), "task_id": task_id},
                )
                assert missing_project_usage.status_code == wrong_project_usage.status_code == 404
                assert (
                    missing_project_usage.json()["detail"] == wrong_project_usage.json()["detail"]
                )

                deferred_review_lookup = await client.get(
                    "/api/v1/operator/artifacts/bindings",
                    params={"resource_type": "review", "resource_id": str(uuid4())},
                )
                assert deferred_review_lookup.status_code == 422

                readiness = await client.get("/api/v1/operator/artifacts/readiness")
                assert readiness.status_code == 200
                assert readiness.json()["active"] is False

                app.dependency_overrides[get_artifact_operator_authority] = lambda: (
                    _ProjectOperatorAuthority(str(uuid4()))
                )
                cross_project = await client.get(
                    f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
                )
                missing = await client.get(
                    f"/api/v1/operator/artifacts/contents/{uuid4()}/replicas"
                )
                assert cross_project.status_code == missing.status_code == 404
                assert cross_project.json()["detail"] == missing.json()["detail"]
                assert cross_project.json()["error"]["code"] == missing.json()["error"]["code"]

                app.dependency_overrides[get_artifact_operator_authority] = (
                    DenyArtifactOperatorAuthority
                )
                concealed = await client.get(
                    f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
                )
                assert concealed.status_code == 404
                assert content_id not in concealed.text

                app.dependency_overrides[get_artifact_recovery_authority] = lambda: (
                    _ProjectRecoveryAuthority(str(uuid4()))
                )
                cross_project_retry = await client.post(
                    f"/api/v1/operator/artifacts/verification-jobs/{source_job_id}/retry",
                    json={
                        "project_id": project_id,
                        "task_id": task_id,
                        "submission_id": submission_id,
                        "reason": "cross-project probe",
                        "client_idempotency_key": "cross-project-probe",
                        "expected_source_job_cas_version": source_job_cas_version,
                    },
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
                assert cross_project_retry.status_code == denied_retry.status_code == 404
                assert cross_project_retry.json()["detail"] == denied_retry.json()["detail"]
    finally:
        if bootstrap is not None:
            bootstrap.close()
        await engine.dispose()
