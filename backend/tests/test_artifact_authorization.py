"""Closed authority and redaction proofs for Operator artifact operations."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.artifacts.operator import (
    ArtifactOperatorEvidenceError,
    ArtifactOperatorService,
    artifact_provider_readiness,
)
from app.modules.artifacts.models import ArtifactAdmissionScope
from app.modules.artifacts.metrics import InProcessArtifactAdmissionMetrics, pressure_band
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactOperatorAuthorityFacts,
    ArtifactOperatorAuthorizationEvidence,
    ArtifactOperatorResourceType,
    DenyArtifactOperatorAuthority,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDenied,
    AuthorizationDenialCode,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    SystemResourceContext,
)
from app.core.config import Settings
from app.modules.artifacts.service import (
    ArtifactAdmissionConfigurationError,
    ArtifactAdmissionService,
    _AdmissionFacts,
    _AdmissionScopeSpec,
)
from app.modules.artifacts.router import ArtifactReplicaResponse
from tests.test_authorization import _runtime_context, _runtime_service


OPERATOR_ACTIONS = (
    ActionId.ARTIFACT_BINDING_READ,
    ActionId.ARTIFACT_REPLICA_READ,
    ActionId.ARTIFACT_RECEIPT_READ,
    ActionId.ARTIFACT_VERIFICATION_JOB_READ,
    ActionId.ARTIFACT_VERIFICATION_JOB_RETRY,
    ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
    ActionId.ARTIFACT_AUDIT_READ,
    ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ,
)
INTERNAL_ACTIONS = (
    ActionId.ARTIFACT_VERIFICATION_EXECUTE,
    ActionId.ARTIFACT_PENDING_WORK_SCAN,
    ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
)


def _context() -> HumanAuthorizationContext:
    return HumanAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


@pytest.mark.parametrize("action", OPERATOR_ACTIONS + INTERNAL_ACTIONS)
async def test_real_kernel_keeps_artifact_actions_unavailable(action: ActionId) -> None:
    service, _evidence = _runtime_service(_runtime_context())
    with pytest.raises(AuthorizationDenied) as caught:
        await service.require(
            action,
            SystemResourceContext(resource_type="system", resource_id="workstream:system"),
        )
    assert caught.value.decision.denial_code is AuthorizationDenialCode.ACTION_UNAVAILABLE


async def test_production_operator_authority_denies() -> None:
    with pytest.raises(ArtifactAuthorityDeniedError):
        await DenyArtifactOperatorAuthority().authorize(
            authorization_context=_context(),
            facts=ArtifactOperatorAuthorityFacts(
                resource_type=ArtifactOperatorResourceType.CONTENT,
                resource_id=str(uuid4()),
                project_ids=(),
                action_id=ActionId.ARTIFACT_REPLICA_READ,
            ),
        )


class _WrongEvidenceAuthority:
    async def authorize(self, **_values: object) -> ArtifactOperatorAuthorizationEvidence:
        return ArtifactOperatorAuthorizationEvidence(
            action_id=ActionId.ARTIFACT_BINDING_READ,
            permission_id=PermissionId.ARTIFACT_BINDING_READ.value,
            decision_id=uuid4(),
        )


async def test_operator_service_rejects_mismatched_authority_evidence() -> None:
    service = ArtifactOperatorService(
        object(), _WrongEvidenceAuthority(), Settings(), InProcessArtifactAdmissionMetrics()
    )
    with pytest.raises(ArtifactOperatorEvidenceError):
        await service._authorize(
            _context(),
            ActionId.ARTIFACT_REPLICA_READ,
            ArtifactOperatorResourceType.CONTENT,
            str(uuid4()),
            (),
        )


def test_admission_metrics_are_bounded_and_classified() -> None:
    metrics = InProcessArtifactAdmissionMetrics()
    for counted in (0, 75, 90, 100):
        metrics.pressure("project", counted, 100)
    assert sum(metrics.snapshot().values()) == 4
    assert pressure_band(74, 100) == "normal"
    assert pressure_band(75, 100) == "warning"
    assert pressure_band(90, 100) == "critical"
    assert pressure_band(100, 100) == "exhausted"
    with pytest.raises(ValueError):
        metrics.pressure("credential", 1, 2)


def test_readiness_is_static_and_aws_never_active() -> None:
    disabled = artifact_provider_readiness(Settings())
    assert disabled["status"] == "inactive_disabled"
    assert disabled["active"] is False

    aws = Settings.model_construct(
        artifact_store_backend="s3_compatible",
        artifact_s3_provider_profile="aws_s3",
        artifact_admission_task_maximum_bytes=1,
        artifact_admission_producer_maximum_bytes=1,
        artifact_admission_project_maximum_bytes=1,
        artifact_admission_deployment_maximum_bytes=1,
        artifact_scratch_root=None,
    )
    readiness = artifact_provider_readiness(aws)
    assert readiness["status"] == "inactive_live_proof_required"
    assert readiness["active"] is False
    assert readiness["prerequisites"]["aws_live_proof_present"] is False


async def test_quota_reconciliation_is_configuration_driven_and_rollback_safe() -> None:
    service = ArtifactAdmissionService(object(), Settings(), object())
    existing_charge = SimpleNamespace(state="completed")
    service._repo = SimpleNamespace(
        database_now=AsyncMock(return_value=datetime.now(UTC)),
        get_admission_charge=AsyncMock(return_value=existing_charge),
    )
    counter = ArtifactAdmissionScope(
        scope_type="project",
        scope_id=str(uuid4()),
        limit_bytes=100,
        counted_bytes=80,
        cas_version=3,
    )
    facts = _AdmissionFacts(
        request_type="guide",
        producer_type="actor_profile",
        producer_ref=str(uuid4()),
        project_id=counter.scope_id,
        task_id=None,
        guide_source_item_id=str(uuid4()),
        upload_item_id=None,
        checker_run_id=None,
        logical_role=None,
        operation_identity="sha256:" + "a" * 64,
    )
    result = await service._reserve_charges(
        scopes=(_AdmissionScopeSpec("project", counter.scope_id, 200),),
        counters=(counter,),
        facts=facts,
        sha256="sha256:" + "b" * 64,
        byte_count=10,
    )
    assert result == (existing_charge,)
    assert counter.limit_bytes == 200
    assert counter.cas_version == 4

    with pytest.raises(ArtifactAdmissionConfigurationError):
        await service._reserve_charges(
            scopes=(_AdmissionScopeSpec("project", counter.scope_id, 79),),
            counters=(counter,),
            facts=facts,
            sha256="sha256:" + "c" * 64,
            byte_count=1,
        )
    assert counter.limit_bytes == 200


def test_operator_response_schema_rejects_provider_fields() -> None:
    with pytest.raises(ValidationError):
        ArtifactReplicaResponse(
            id=uuid4(),
            content_id=uuid4(),
            verification_state="pending",
            availability_state="unknown",
            integrity_state="unknown",
            last_reconciled_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            provider_object_ref="secret/key",
        )


@pytest.mark.parametrize(
    "resource_type",
    (
        "project",
        "project_guide",
        "guide_source_snapshot",
        "guide_source_snapshot_item",
        "task",
        "submission",
        "checker_run",
    ),
)
async def test_binding_resource_resolver_uses_canonical_product_lineage(
    resource_type: str,
) -> None:
    project_id = str(uuid4())
    session = SimpleNamespace(scalar=AsyncMock(return_value=project_id))
    service = ArtifactOperatorService(
        session, _WrongEvidenceAuthority(), Settings(), InProcessArtifactAdmissionMetrics()
    )

    assert await service._binding_resource_project(resource_type, str(uuid4())) == project_id
    session.scalar.assert_awaited_once()


async def test_binding_resource_resolver_fails_closed_for_unknown_type() -> None:
    session = SimpleNamespace(scalar=AsyncMock())
    service = ArtifactOperatorService(
        session, _WrongEvidenceAuthority(), Settings(), InProcessArtifactAdmissionMetrics()
    )

    assert await service._binding_resource_project("review", str(uuid4())) is None
    session.scalar.assert_not_awaited()


def test_operator_page_helpers_are_bounded_and_deduplicate_projects() -> None:
    first, second, third = (SimpleNamespace(id=str(uuid4())) for _ in range(3))
    page = ArtifactOperatorService._result(
        [first, second, third], 2, lambda row: {"id": row.id}
    )
    assert page.items == ({"id": first.id}, {"id": second.id})
    assert page.next_cursor == second.id
    assert ArtifactOperatorService._result([], 2, lambda row: row).next_cursor is None

    project_ids = ArtifactOperatorService._project_ids((second.id, first.id, second.id))
    assert project_ids == tuple(sorted({UUID(first.id), UUID(second.id)}, key=str))


async def test_audit_resource_resolver_composes_exact_artifact_lineage() -> None:
    project_id = str(uuid4())
    replica_id = str(uuid4())
    session = SimpleNamespace(scalar=AsyncMock(side_effect=(project_id, replica_id)))
    service = ArtifactOperatorService(
        session, _WrongEvidenceAuthority(), Settings(), InProcessArtifactAdmissionMetrics()
    )
    content_projects = (uuid4(),)
    replica_projects = (uuid4(),)
    service._content_projects = AsyncMock(return_value=content_projects)
    service._replica_projects = AsyncMock(return_value=replica_projects)

    binding_projects = await service._audit_projects("artifact_binding", str(uuid4()))
    assert binding_projects == (UUID(project_id),)
    assert await service._audit_projects("artifact_content", str(uuid4())) == content_projects
    assert await service._audit_projects("artifact_replica", replica_id) == replica_projects
    assert (
        await service._audit_projects("artifact_verification_job", str(uuid4()))
        == replica_projects
    )
    assert await service._audit_projects("unknown", str(uuid4())) == ()
    service._content_projects.assert_awaited_once()
    assert service._replica_projects.await_count == 2


async def test_audit_resource_resolver_conceals_missing_lineage() -> None:
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    service = ArtifactOperatorService(
        session, _WrongEvidenceAuthority(), Settings(), InProcessArtifactAdmissionMetrics()
    )
    service._replica_projects = AsyncMock()

    assert await service._audit_projects("artifact_binding", str(uuid4())) == ()
    assert await service._audit_projects("artifact_verification_job", str(uuid4())) == ()
    service._replica_projects.assert_not_awaited()


async def test_binding_discovery_projects_canonical_authorized_page() -> None:
    project_id = uuid4()
    resource_id = uuid4()
    first_id, second_id = str(uuid4()), str(uuid4())
    row = SimpleNamespace(
        id=first_id,
        content_id=str(uuid4()),
        project_id=str(project_id),
        resource_type="task",
        resource_id=str(resource_id),
        logical_role="submission",
        scope_version=1,
        supersedes_binding_id=None,
        created_at=datetime.now(UTC),
    )
    service = ArtifactOperatorService(
        object(), _WrongEvidenceAuthority(), Settings(), InProcessArtifactAdmissionMetrics()
    )
    service._binding_resource_project = AsyncMock(return_value=str(project_id))
    service._authorize = AsyncMock()
    service._page = AsyncMock(
        return_value=(row, SimpleNamespace(**{**vars(row), "id": second_id}))
    )

    result = await service.list_bindings(
        authorization_context=_context(),
        resource_type="task",
        resource_id=resource_id,
        cursor=None,
        limit=1,
    )

    assert result.next_cursor == first_id
    assert result.items == (
        {
            "id": first_id,
            "content_id": row.content_id,
            "project_id": str(project_id),
            "resource_type": "task",
            "resource_id": str(resource_id),
            "logical_role": "submission",
            "scope_version": 1,
            "supersedes_binding_id": None,
            "created_at": row.created_at,
        },
    )
    service._authorize.assert_awaited_once()
    authority_args = service._authorize.await_args.args
    assert authority_args[1:] == (
        ActionId.ARTIFACT_BINDING_READ,
        ArtifactOperatorResourceType.BINDING_SCOPE,
        f"task:{resource_id}",
        (project_id,),
    )
