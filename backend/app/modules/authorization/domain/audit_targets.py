"""Exact project resource audit selectors, without raw product facts."""

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_proposals import GuideProposalResourceContext
from app.modules.authorization.domain.action_groups import (
    GUIDE_BOUND_PROJECT_MANAGER_ACTIONS, SUBMISSION_POLICY_MUTATIONS,
)
from app.modules.authorization.domain.project_create import ProjectCreateResourceContext
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext


def project_authority_audit_target(
    resource: object, action_id: ActionId,
) -> tuple[str | None, str, str, str, str] | None:
    """Project-scoped exact contexts share bounded audit selectors, never raw facts."""
    from app.modules.authorization.domain.contribution_policies import (
        ContributionPolicyReadResourceContext, ContributionPolicyMutationResourceContext,
    )
    from app.modules.authorization.domain.adapter_bindings import (
        AdapterBindingReadResourceContext,
        AdapterBindingMutationResourceContext,
    )
    from app.modules.authorization.domain.guide_compilation import (
        ProjectGuideCompilationRequestResourceContext,
        ProjectGuideCompilationExecuteResourceContext,
    )
    from app.modules.authorization.domain.guide_compilation_projections import (
        ProjectGuideProjectionResourceContext,
    )
    from app.modules.authorization.domain.project_setup_finalization import (
        ProjectSetupFinalizationResourceContext,
    )
    from app.modules.authorization.runtime import (
        PreSubmitCheckerInputResourceContext, ProjectSubmissionArtifactPolicyMutationResourceContext,
    )

    if isinstance(resource, TaskAuthorityResourceContext):
        project_id = str(resource.scope_project_id)
        return project_id, "project", project_id, "project", project_id
    if isinstance(resource, ProjectCreateResourceContext):
        return (
            None, "project_create_operation", str(resource.resource_id),
            "project", str(resource.requested_project_id),
        )
    if action_id in SUBMISSION_POLICY_MUTATIONS and isinstance(
        resource, ProjectSubmissionArtifactPolicyMutationResourceContext,
    ):
        project_id = str(resource.scope_project_id)
        return project_id, resource.resource_type, str(resource.resource_id), "project", project_id
    if isinstance(
        resource,
        (
            PreSubmitCheckerInputResourceContext,
            ProjectGuideCompilationRequestResourceContext,
            ProjectGuideCompilationExecuteResourceContext,
            ContributionPolicyReadResourceContext, ContributionPolicyMutationResourceContext,
            AdapterBindingReadResourceContext,
            AdapterBindingMutationResourceContext,
            ProjectGuideProjectionResourceContext,
            ProjectSetupFinalizationResourceContext,
            GuideProposalResourceContext,
        ),
    ):
        project_id = str(getattr(resource, "project_id", None) or resource.scope_project_id)
        return project_id, resource.resource_type, str(resource.resource_id), "project", project_id
    if action_id in GUIDE_BOUND_PROJECT_MANAGER_ACTIONS:
        scope_project_id = getattr(resource, "scope_project_id", None)
        if scope_project_id is not None:
            project_id = str(scope_project_id)
            return project_id, "project", project_id, "project", project_id
    return None
