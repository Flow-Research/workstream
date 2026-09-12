"""Exact activated action, fixed-service matrix and human/direct-kernel denials."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability,
    ActionId,
    ActionOwner,
    PermissionId,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    AuthorizationDenied,
    HumanAuthorizationContext,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from .support import Case
from .test_prepared import legacy_resource


@pytest.mark.parametrize("identity", list(ServiceIdentity))
async def test_finalization_action_service_matrix(monkeypatch, identity):
    case = Case(monkeypatch, identity=identity)
    action = ActionId.PROJECT_SETUP_RUN_UPDATE
    definition = ACTION_BY_ID[action]
    assert definition.availability is ActionAvailability.ACTIVE
    assert definition.owner is ActionOwner.AUTH_12B2
    assert definition.permission_id is PermissionId.PROJECT_GUIDE_MANAGE
    assert (action in SERVICE_ACTIONS_BY_IDENTITY.get(identity, ())) == (
        identity is ServiceIdentity.PROJECT_SETUP
    )
    # Reach the real kernel's sealed preparation matrix independently of the
    # adapter's fixed-identity binding guard.
    service = case.first.service
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.PROJECT, project_id=case.facts.project_id
    )
    if identity is ServiceIdentity.PROJECT_SETUP:
        authority = await service._authorization._prepare_prelocked(
            service._consumer_token, action, scope
        )
        service._authorization._discard_prelocked(authority)
        async with case.prepare() as prepared:
            await prepared.consume_new(case.facts)
    else:
        with pytest.raises(PreparedAuthorizationUnsupported) as caught:
            await service._authorization._prepare_prelocked(service._consumer_token, action, scope)
        assert caught.value.denial_code.value == "permission_not_granted"
    service.close()


@pytest.mark.parametrize("principal", ["service", "project_manager", "administrator"])
@pytest.mark.parametrize("kind", ["exact", "legacy"])
async def test_human_and_direct_kernel_finalization_denied(monkeypatch, principal, kind):
    case = Case(monkeypatch)
    service = case.first.service
    kernel = service._authorization
    resource = case.resource() if kind == "exact" else legacy_resource(case.facts.project_id)
    if principal != "service":
        context = HumanAuthorizationContext(
            **{
                **service._context.model_dump(exclude={"service_identity"}),
                "actor_kind": ActorKind.HUMAN,
            }
        )

        # Even an available broad grant cannot give humans this fixed-service action.
        async def grant(*args, **kwargs):
            return SimpleNamespace(id=str(uuid4()), status="active", role=principal)

        monkeypatch.setattr(service._repository, "find_effective_grant", grant, raising=False)
        kernel = AuthorizationService(case.session, context, admin_repository=service._repository)
        kernel._audit = case.evidence
        human = PreparedAuthorizationService(case.session, context, kernel, service._repository)
        with pytest.raises(PreparedAuthorizationUnsupported):
            await kernel._prepare_prelocked(
                human._consumer_token,
                ActionId.PROJECT_SETUP_RUN_UPDATE,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT, project_id=case.facts.project_id
                ),
            )
        human.close()
    with pytest.raises(AuthorizationDenied) as caught:
        await kernel.require(ActionId.PROJECT_SETUP_RUN_UPDATE, resource)
    assert not caught.value.decision.allowed
    assert len(case.evidence.events) == 1
    assert case.evidence.events[0].after_facts["allowed"] is False
    service.close()


def test_setup_existing_active_pairs_and_downstream_plans_are_preserved():
    expected = {
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC: PermissionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE: PermissionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN: PermissionId.PROJECT_GUIDE_MANAGE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE: PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionId.PROJECT_SETUP_RUN_UPDATE: PermissionId.PROJECT_GUIDE_MANAGE,
    }
    assert {
        action: ACTION_BY_ID[action].permission_id
        for action in SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.PROJECT_SETUP]
        if ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
    } == expected
    assert (
        ACTION_BY_ID[ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE].availability
        is ActionAvailability.PLANNED
    )
    assert ACTION_BY_ID[ActionId.PROJECT_GUIDE_ACTIVATE].availability is ActionAvailability.PLANNED


def test_exact_active_action_inventory():
    """Preserve finalization and the complete catalogue after proposal activation."""
    from app.modules.authorization.catalogue import ACTION_DEFINITIONS

    assert {
        definition.action_id
        for definition in ACTION_DEFINITIONS
        if definition.availability is ActionAvailability.ACTIVE
    } == {
        ActionId.ACTOR_PROFILE_READ_SELF,
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
        ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
        ActionId.ADMIN_ROLE_GRANT_LIST,
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
        ActionId.ACTOR_PROFILE_READ,
        ActionId.ACTOR_IDENTITY_LINK_READ,
        ActionId.ACTOR_SERVICE_PROVISION,
        ActionId.ACTOR_PROFILE_SUSPEND,
        ActionId.ACTOR_PROFILE_REACTIVATE,
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
        ActionId.PROJECT_CREATE,
        ActionId.PROJECT_GUIDE_CREATE,
        ActionId.PROJECT_GUIDE_UPDATE,
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC,
        ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        ActionId.PROJECT_SETUP_RUN_UPDATE,
        ActionId.PROJECT_REVIEW_POLICY_UPDATE,
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE,
        ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ,
        ActionId.PROJECT_GUIDE_COMPILATION_CORRECTION_REQUEST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE,
        ActionId.PROJECT_READ,
        ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        ActionId.ARTIFACT_GUIDE_SOURCE_READ,
        ActionId.ARTIFACT_VERIFICATION_EXECUTE,
        ActionId.ARTIFACT_PENDING_WORK_SCAN,
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
        ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE,
        ActionId.SUBMISSION_CREATE,
        ActionId.TASK_CLAIM,
        ActionId.TASK_START,
        ActionId.TASK_WORK_CONTEXT_READ,
        ActionId.PROJECT_TASK_WORK_CONTEXT_READ,
        ActionId.OPERATIONS_TASK_START_OVERRIDE,
        ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
        ActionId.COMPENSATION_ADAPTER_BINDING_READ,
        ActionId.COMPENSATION_ADAPTER_BINDING_CREATE,
        ActionId.COMPENSATION_ADAPTER_BINDING_SUSPEND,
        ActionId.COMPENSATION_ADAPTER_BINDING_RESUME,
        ActionId.CONTRIBUTION_POLICY_READ,
        ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT,
        ActionId.CONTRIBUTION_POLICY_UPDATE_DRAFT,
        ActionId.CONTRIBUTION_POLICY_PUBLISH,
        ActionId.CONTRIBUTION_POLICY_RETIRE,
    }
