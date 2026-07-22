"""Closed authority and redaction proofs for Operator artifact operations."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.artifacts.operator import (
    ArtifactOperatorEvidenceError,
    ArtifactOperatorService,
    InProcessArtifactAdmissionMetrics,
    artifact_provider_readiness,
)
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
    for band in ("normal", "warning", "critical", "exhausted"):
        metrics.pressure("project", band)
    assert sum(metrics.snapshot().values()) == 4
    assert ArtifactOperatorService._pressure(74, 100) == "normal"
    assert ArtifactOperatorService._pressure(75, 100) == "warning"
    assert ArtifactOperatorService._pressure(90, 100) == "critical"
    assert ArtifactOperatorService._pressure(100, 100) == "exhausted"
    with pytest.raises(ValueError):
        metrics.pressure("credential", "normal")


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
