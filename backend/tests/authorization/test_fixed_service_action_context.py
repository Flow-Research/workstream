"""Focused fixed-service action preflight behavior."""

from uuid import uuid4

import pytest

from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
from app.modules.artifacts.authorization import PreparedSubmissionBindingAuthorization
from app.modules.artifacts.submission_bindings import SubmissionBindingAuthorityFacts
from app.modules.authorization import prepared
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDenialCode,
    IdentityLinkStatus,
    PreparedAuthorizationUnsupported,
    ServiceAuthorizationContext,
)


@pytest.mark.parametrize(
    ("actor_status", "link_status", "action_id", "expected_denial"),
    [
        (
            ActorStatus.ACTIVE,
            IdentityLinkStatus.ACTIVE,
            ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
            None,
        ),
        (
            ActorStatus.SUSPENDED,
            IdentityLinkStatus.ACTIVE,
            ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        ),
        (
            ActorStatus.ACTIVE,
            IdentityLinkStatus.REVOKED,
            ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        ),
        (
            ActorStatus.ACTIVE,
            IdentityLinkStatus.ACTIVE,
            ActionId.PROJECT_READ,
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_fixed_service_action_context_enforces_lifecycle_and_matrix(
    actor_status: ActorStatus,
    link_status: IdentityLinkStatus,
    action_id: ActionId,
    expected_denial: AuthorizationDenialCode | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow only an active principal with an active matrix action."""
    context = ServiceAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.SERVICE,
        actor_status=actor_status,
        identity_link_id=uuid4(),
        identity_link_status=link_status,
        service_identity=ServiceIdentity.ARTIFACT_BINDING,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )

    async def fixed_context(*_args):
        return context

    monkeypatch.setattr(prepared, "fixed_service_authorization_context", fixed_context)
    operation = prepared.fixed_service_action_context(
        object(),
        service_identity=ServiceIdentity.ARTIFACT_BINDING,
        action_id=action_id,
        request_id=context.request_id,
        correlation_id=context.correlation_id,
    )
    if expected_denial is None:
        assert await operation is context
    else:
        with pytest.raises(PreparedAuthorizationUnsupported) as exc_info:
            await operation
        assert exc_info.value.denial_code is expected_denial


@pytest.mark.asyncio
async def test_submission_binding_validation_is_concealed() -> None:
    """Malformed exact binding facts never expose Pydantic validation details."""
    ids = [uuid4() for _ in range(12)]
    facts = SubmissionBindingAuthorityFacts(
        admission_id=ids[0], evidence_set_id=ids[1], actor_profile_id=ids[2],
        identity_link_id=ids[3], project_id=ids[4], task_id=ids[5],
        assignment_id=ids[6], predecessor_submission_id=None,
        predecessor_submission_version=None, submission_id=ids[7],
        submission_version=1, guide_id=ids[8], guide_version="1",
        source_snapshot_id=ids[9], source_snapshot_sha256="invalid",
        effective_policy_id=ids[10], effective_policy_sha256="sha256:" + "1" * 64,
        pre_submit_policy_id=ids[11], pre_submit_policy_sha256="sha256:" + "2" * 64,
        locked_policy_context_hash="sha256:" + "3" * 64,
        semantic_manifest_id=uuid4(), semantic_manifest_sha256="sha256:" + "4" * 64,
        content_id=uuid4(), sha256="sha256:" + "5" * 64, byte_count=1,
        logical_role="submission_bundle_original",
    )
    authority = PreparedSubmissionBindingAuthorization(
        object(), request_id=uuid4(), correlation_id=uuid4()
    )
    with pytest.raises(SubmissionAdmissionConsumptionError) as exc_info:
        await authority.consume(facts)
    assert exc_info.value.code == "submission_bundle_admission_unavailable"
