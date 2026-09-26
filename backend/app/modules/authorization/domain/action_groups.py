"""Exact shared kernel action classifications; these sets grant no authority."""
from app.modules.authorization.catalogue import GUIDE_PROPOSAL_ACTION_IDS, POST_POLICY_HUMAN_ACTION_IDS, POST_POLICY_MUTATION_ACTION_IDS

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain import adapter_bindings, contribution_policies
from app.modules.authorization.runtime import PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION

GUIDE_BOUND_PROJECT_MANAGER_ACTIONS = frozenset(
    {
        ActionId.PROJECT_GUIDE_ACTIVATE,
        ActionId.PROJECT_GUIDE_CREATE,
        ActionId.PROJECT_GUIDE_UPDATE,
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        ActionId.PROJECT_REVIEW_POLICY_UPDATE,
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE,
    }
)
GUIDE_BOUND_PROJECT_MANAGER_ACTIONS |= GUIDE_PROPOSAL_ACTION_IDS | POST_POLICY_HUMAN_ACTION_IDS
EXACT_PROJECT_MANAGER_SCOPE_ACTIONS = frozenset({
    ActionId.PROJECT_GUIDE_COMPILATION_REQUEST, ActionId.PROJECT_GUIDE_ACTIVATE,
}) | GUIDE_PROPOSAL_ACTION_IDS | POST_POLICY_HUMAN_ACTION_IDS
SUBMISSION_POLICY_MUTATIONS = frozenset(PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION)

PROJECT_SCOPED_ADMIN_MUTATIONS = frozenset(
    {
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
        *adapter_bindings.ADAPTER_BINDING_MUTATION_ACTIONS,
        *contribution_policies.CONTRIBUTION_POLICY_MUTATION_ACTIONS,
    }
)
CONTEXT_DIGEST_ACTIONS = frozenset(
    {
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        ActionId.TASK_QUEUE_READ, ActionId.PROJECT_TASK_QUEUE_READ, ActionId.OPERATIONS_TASK_QUEUE_READ,
        ActionId.PROJECT_CREATE,
        *GUIDE_BOUND_PROJECT_MANAGER_ACTIONS,
        *SUBMISSION_POLICY_MUTATIONS,
        *POST_POLICY_MUTATION_ACTION_IDS,
        *adapter_bindings.ADAPTER_BINDING_ACTIONS,
        *contribution_policies.CONTRIBUTION_POLICY_ACTIONS,
    }
)


def supports_prepared_denial(action_id: ActionId, resource_context: object) -> bool:
    """Admit only the existing action/context pairs for prepare-time denial evidence."""
    from app.modules.authorization.domain.task_authority import TASK_ACTIONS, TaskAuthorityResourceContext
    from app.modules.authorization.domain.project_create import ProjectCreateResourceContext
    from app.modules.authorization.runtime import (
        ProjectGuideMutationPrepareDenialResourceContext, ProjectGuideSufficiencyMutationResourceContext,
        ProjectPolicyMutationPrepareDenialResourceContext, ProjectSubmissionArtifactPolicyMutationResourceContext,
    )
    return (
        (
            action_id in contribution_policies.CONTRIBUTION_POLICY_MUTATION_ACTIONS
            and type(resource_context) is contribution_policies.ContributionPolicyMutationScopeDenialResourceContext
            and resource_context.requested_action == action_id
        )
        or
        (action_id in TASK_ACTIONS and isinstance(resource_context, TaskAuthorityResourceContext))
        or
        (
            action_id is ActionId.PROJECT_CREATE
            and isinstance(resource_context, ProjectCreateResourceContext)
        )
        or (
            action_id in GUIDE_BOUND_PROJECT_MANAGER_ACTIONS
            and isinstance(
                resource_context,
                (
                    ProjectGuideMutationPrepareDenialResourceContext,
                    ProjectGuideSufficiencyMutationResourceContext,
                ),
            )
        )
        or (
            action_id
            in {
                ActionId.PROJECT_REVIEW_POLICY_UPDATE,
                ActionId.PROJECT_REVISION_POLICY_UPDATE,
            }
            and isinstance(resource_context, ProjectPolicyMutationPrepareDenialResourceContext)
        )
        or (
            action_id in SUBMISSION_POLICY_MUTATIONS
            and isinstance(
                resource_context,
                ProjectSubmissionArtifactPolicyMutationResourceContext,
            )
        )
    )
