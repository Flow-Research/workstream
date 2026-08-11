"""Pure resource guards for fixed-service prepared authorization."""

from __future__ import annotations

from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation import (
    ProjectGuideCompilationExecuteResourceContext,
)
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
    if action_id is ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN:
        return (
            isinstance(resource, ProjectGuideSufficiencyMutationResourceContext)
            and resource.execution_kind == "setup_service"
            and resource.scope_project_id == project_id
        )
    if action_id is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE:
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
    return None
