"""Pure resource guards for fixed-service prepared authorization."""

from __future__ import annotations

from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.post_submit_routing import ROUTE, PostSubmitRoutingResourceContext, parse_post_submit_routing_prepare
from app.modules.authorization.domain.post_submit import (
    POST_SUBMIT_ACTIONS, PostSubmitResourceContext, parse_post_submit_prepare,
)
from app.modules.authorization.domain.assignment_invalidation import AssignmentInvalidationResourceContext, parse_assignment_invalidation_binding
from app.modules.authorization.domain.outbox_dispatch import OutboxDispatchResourceContext, prepared_outbox_digest
from app.modules.authorization.domain.post_policy import PostPolicyResourceContext, DERIVE
from app.modules.authorization.domain.guide_compilation import (
    ProjectGuideCompilationExecuteResourceContext,
    ProjectGuideCompilationRequestResourceContext,
)
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
)
from app.modules.authorization.domain.project_setup_finalization import ProjectSetupFinalizationResourceContext
from app.modules.authorization.runtime import (
    AuthorizationResourceContext,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectGuideSufficiencyMutationResourceContext,
    ProjectSubmissionArtifactPolicyMutationResourceContext,
)

_PROJECT_SETUP_ACTIONS = frozenset(
    {
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE,
        ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC,
        ActionId.PROJECT_SETUP_RUN_UPDATE,
        DERIVE,
    }
)


def is_project_setup_scope(action_id: ActionId, scope: PreparedAuthorityScope) -> bool:
    """Return whether a fixed setup action has one exact project scope."""
    return (
        action_id in _PROJECT_SETUP_ACTIONS
        and scope.kind is PreparedAuthorityScopeKind.PROJECT
        and scope.project_id is not None
    )


def project_setup_resource_matches(
    action_id: ActionId,
    resource: AuthorizationResourceContext,
    project_id: UUID | None,
) -> bool | None:
    """Validate setup-service facts, or return None for non-setup actions."""
    if action_id == DERIVE:
        return (type(resource) is PostPolicyResourceContext
                and resource.facts.locator.action_id == DERIVE
                and resource.scope_project_id == project_id)
    if action_id is ActionId.PROJECT_SETUP_RUN_UPDATE:
        return (
            isinstance(resource, ProjectSetupFinalizationResourceContext)
            and resource.scope_project_id == project_id
        )
    if action_id is ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN:
        if isinstance(resource, ProjectGuideProjectionResourceContext):
            return (
                resource.component == "guide_sufficiency"
                and resource.scope_project_id == project_id
            )
        return (
            isinstance(resource, ProjectGuideSufficiencyMutationResourceContext)
            and resource.execution_kind == "setup_service"
            and resource.scope_project_id == project_id
        )
    if action_id is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE:
        if isinstance(resource, ProjectGuideProjectionResourceContext):
            return (
                resource.component == "submission_artifact_policy"
                and resource.scope_project_id == project_id
            )
        return (
            isinstance(resource, ProjectSubmissionArtifactPolicyMutationResourceContext)
            and resource.execution_kind == "setup_service"
            and resource.target_kind == "derive"
            and resource.scope_project_id == project_id
        )
    if action_id is ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE:
        return (
            isinstance(resource, ProjectGuideCompilationExecuteResourceContext)
            and resource.scope_project_id == project_id
        )
    if action_id is ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC:
        return (
            isinstance(resource, ProjectGuideCompilationRequestResourceContext)
            and resource.trigger == "automatic_source_ready"
            and resource.scope_project_id == project_id
        )
    return None


def fixed_service_scope_project(action_id, scope, artifact_resource):
    """Admit exact setup, dispatcher or artifact scopes without conflating owners."""
    outbox = (action_id in {ActionId.OUTBOX_DISPATCH, ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE}
              and scope.kind is PreparedAuthorityScopeKind.PROJECT and scope.project_id is not None)
    if is_project_setup_scope(action_id, scope) or outbox or (
        action_id in POST_SUBMIT_ACTIONS | {ROUTE} and scope.kind is PreparedAuthorityScopeKind.PROJECT
        and scope.project_id is not None
    ):
        return scope.project_id
    if (artifact_resource is None or scope.kind is not PreparedAuthorityScopeKind.ARTIFACT_INTERNAL
            or scope.artifact_resource_type != artifact_resource[0]):
        from app.modules.authorization.runtime import PreparedAuthorizationUnsupported, AuthorizationDenialCode
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED)
    return None


def fixed_service_resource_matches(action_id, resource, project_id, artifact_type, artifact_id, expected):
    """Check the final resource against the exact prepared service scope."""
    if action_id is ROUTE:
        return type(resource) is PostSubmitRoutingResourceContext and resource.scope_project_id == project_id
    if action_id in POST_SUBMIT_ACTIONS:
        return (type(resource) is PostSubmitResourceContext and resource.action_id is action_id
                and resource.scope_project_id == project_id)
    if action_id is ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE:
        return type(resource) is AssignmentInvalidationResourceContext and resource.scope_project_id == project_id
    if action_id is ActionId.OUTBOX_DISPATCH:
        return type(resource) is OutboxDispatchResourceContext and resource.scope_project_id == project_id
    setup = project_setup_resource_matches(action_id, resource, project_id)
    if setup is not None:
        return setup
    return (expected is not None and isinstance(resource, expected[1])
            and resource.resource_type == artifact_type and resource.resource_id == artifact_id)


def prepared_request_digest(value):
    """One canonical request commitment shared by PREP issuance and consumption."""
    return canonical_json_hash({"domain": "workstream.prepared_authorization.request.v1", "request": value})


def prepared_fixed_service_bindings(action, request, invalid_error):
    """Keep exact dispatcher and assignment effect commitments with service guards."""
    if action is ROUTE:
        return {"routing_request": parse_post_submit_routing_prepare(action, request, invalid_error)}
    return {
        "post_submit_prepare_context": parse_post_submit_prepare(action, request, invalid_error),
        "assignment_invalidation_context": parse_assignment_invalidation_binding(action, request, invalid_error),
        "outbox_dispatch_digest": prepared_outbox_digest(action, request, invalid_error),
    }
