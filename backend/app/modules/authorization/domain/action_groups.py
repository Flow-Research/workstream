"""Exact shared kernel action classifications; these sets grant no authority."""
from app.modules.authorization.catalogue import GUIDE_PROPOSAL_ACTION_IDS, POST_POLICY_HUMAN_ACTION_IDS, POST_POLICY_MUTATION_ACTION_IDS

from app.modules.authorization.domain.task_authority import TASK_IMPORT_BATCH_ACTIONS, TaskImportBatchResourceContext
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain import (
    adapter_bindings,
    model_usage as checker_models,
    checker_outputs,
    checker_registry,
    checker_retry,
    post_submit_deliveries,
    artifact_operator,
    contribution_policies,
)
from app.modules.authorization.domain.artifact_operator import ARTIFACT_OPERATOR_ACTIONS
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
SYSTEM_OPERATOR_MODEL_MUTATIONS = checker_models.MODEL_ADMIN_ACTIONS
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
        ActionId.CONTRIBUTION_READ_SELF, ActionId.CONTRIBUTION_READ_PROJECT,
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        *TASK_IMPORT_BATCH_ACTIONS,
        ActionId.ARTIFACT_TASK_IMPORT_SOURCE_DECLARE,
        ActionId.ARTIFACT_TASK_IMPORT_SOURCE_UPLOAD,
        ActionId.ARTIFACT_TASK_IMPORT_SOURCE_READ,
        ActionId.CHECKER_PRE_SUBMIT_EXECUTE,
        ActionId.CHECKER_PRE_SUBMIT_FINALIZE,
        ActionId.TASK_QUEUE_READ, ActionId.PROJECT_TASK_QUEUE_READ, ActionId.OPERATIONS_TASK_QUEUE_READ,
        ActionId.PROJECT_CREATE,
        ActionId.OPERATIONS_POST_SUBMIT_DELIVERY_RECONCILE,
        ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
        *GUIDE_BOUND_PROJECT_MANAGER_ACTIONS,
        *SUBMISSION_POLICY_MUTATIONS,
        *POST_POLICY_MUTATION_ACTION_IDS,
        *adapter_bindings.ADAPTER_BINDING_ACTIONS,
        *contribution_policies.CONTRIBUTION_POLICY_ACTIONS,
        *checker_models.CHECKER_MODEL_ACTIONS,
        *checker_outputs.CHECKER_OUTPUT_ACTIONS,
        *ARTIFACT_OPERATOR_ACTIONS,
    }
)


ADMIN_ACTIONS = (
    frozenset(
        {
            ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE,
            ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
            ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
            ActionId.ADMIN_ROLE_GRANT_LIST,
            ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
            ActionId.ADMIN_ROLE_GRANT_ISSUE,
            ActionId.ADMIN_ROLE_GRANT_REVOKE,
            ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
            ActionId.ACTOR_SERVICE_PROVISION,
            ActionId.ACTOR_PROFILE_READ,
            ActionId.ACTOR_IDENTITY_LINK_READ,
            ActionId.ACTOR_PROFILE_SUSPEND,
            ActionId.ACTOR_PROFILE_REACTIVATE,
            ActionId.ACTOR_PROFILE_DEACTIVATE,
            ActionId.ACTOR_IDENTITY_LINK_REVOKE,
            ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
            ActionId.PROJECT_ROLE_GRANT_ISSUE,
            ActionId.PROJECT_ROLE_GRANT_REVOKE,
            ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
            ActionId.PROJECT_ROLE_GRANT_LIST,
            ActionId.PROJECT_ROLE_GRANT_READ,
            ActionId.PROJECT_SETUP_RUN_READ,
            ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
            ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
            ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
            ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
            ActionId.PROJECT_ACTIVE_GUIDE_READ,
        }
    )
    | adapter_bindings.ADAPTER_BINDING_READ_ACTIONS
    | contribution_policies.CONTRIBUTION_POLICY_READ_ACTIONS
    | checker_registry.CHECKER_REGISTRY_ACTIONS
    | checker_models.MODEL_ADMIN_ACTIONS
    | {ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR}
    | checker_retry.CHECKER_RETRY_ACTIONS
    | post_submit_deliveries.POST_SUBMIT_DELIVERY_MUTATION_ACTIONS
    | artifact_operator.ARTIFACT_OPERATOR_ACTIONS
)
SERIALIZED_ADMIN_READS = (
    frozenset(
        {
            ActionId.ACTOR_PROFILE_READ,
            ActionId.ACTOR_IDENTITY_LINK_READ,
            ActionId.PROJECT_SETUP_RUN_READ,
            ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
            ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
            ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
            ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
            ActionId.PROJECT_ACTIVE_GUIDE_READ,
        }
    )
    | adapter_bindings.ADAPTER_BINDING_READ_ACTIONS
    | contribution_policies.CONTRIBUTION_POLICY_READ_ACTIONS
    | checker_registry.CHECKER_REGISTRY_READ_ACTIONS
    | artifact_operator.ARTIFACT_OPERATOR_READ_ACTIONS
)
ADMIN_MUTATIONS = (
    frozenset(
        {
            ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE,
            ActionId.ADMIN_ROLE_GRANT_REVOKE,
            ActionId.ACTOR_SERVICE_PROVISION,
            ActionId.ACTOR_PROFILE_SUSPEND,
            ActionId.ACTOR_PROFILE_REACTIVATE,
            ActionId.ACTOR_PROFILE_DEACTIVATE,
            ActionId.ACTOR_IDENTITY_LINK_REVOKE,
            ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
        }
    )
    | PROJECT_SCOPED_ADMIN_MUTATIONS
    | checker_registry.CHECKER_REGISTRY_MUTATION_ACTIONS
    | checker_models.MODEL_ADMIN_ACTIONS
    | {ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR}
    | checker_retry.CHECKER_RETRY_ACTIONS
    | post_submit_deliveries.POST_SUBMIT_DELIVERY_MUTATION_ACTIONS
    | {ActionId.ARTIFACT_VERIFICATION_JOB_RETRY}
)

def supports_prepared_denial(action_id: ActionId, resource_context: object) -> bool:
    """Admit only the existing action/context pairs for prepare-time denial evidence."""
    from app.modules.authorization.domain.submission_finalization import SubmissionFinalizationResourceContext
    from app.modules.authorization.domain.submission_cleanup import SubmissionSourceCleanupResourceContext
    from app.modules.authorization.domain.submission_intake import IntakeReservationResourceContext, IntakeReservationPreflightResourceContext, IntakeAcceptanceResourceContext
    from app.modules.authorization.domain.task_authority import TASK_ACTIONS, TaskAuthorityResourceContext
    from app.modules.authorization.domain.project_create import ProjectCreateResourceContext
    from app.modules.authorization.domain.checker_retry import (
        CheckerRetryPrepareDenialResourceContext,
    )
    from app.modules.authorization.runtime import (
        TaskImportSourceResourceContext,
        ProjectGuideMutationPrepareDenialResourceContext, ProjectGuideSufficiencyMutationResourceContext,
        ProjectPolicyMutationPrepareDenialResourceContext, ProjectSubmissionArtifactPolicyMutationResourceContext,
    )
    return (
        (action_id is ActionId.ARTIFACT_SOURCE_CLEANUP and type(resource_context) is SubmissionSourceCleanupResourceContext)
        or (action_id is ActionId.ARTIFACT_SUBMISSION_FINALIZE and type(resource_context) is SubmissionFinalizationResourceContext)
        or (action_id is ActionId.SUBMISSION_CREATE and type(resource_context) is IntakeAcceptanceResourceContext)
        or (action_id is ActionId.SUBMISSION_INTAKE_RESERVE and type(resource_context) in {IntakeReservationResourceContext, IntakeReservationPreflightResourceContext})
        or (
            action_id in checker_outputs.CHECKER_OUTPUT_ACTIONS
            and type(resource_context) is checker_outputs.CheckerOutputResourceContext
        )
        or
        (
            action_id in checker_models.CHECKER_MODEL_ACTIONS
            and type(resource_context)
            is checker_models.CHECKER_MODEL_RESOURCE_BY_ACTION[action_id]
        )
        or
        (
            action_id in checker_registry.CHECKER_REGISTRY_MUTATION_ACTIONS
            and type(resource_context)
            is checker_registry.ExternalCheckerRegistryResourceContext
        )
        or (
            action_id is ActionId.OPERATIONS_CHECKER_RETRY
            and type(resource_context) is CheckerRetryPrepareDenialResourceContext
        )
        or
        (
            action_id in contribution_policies.CONTRIBUTION_POLICY_MUTATION_ACTIONS
            and type(resource_context) is contribution_policies.ContributionPolicyMutationScopeDenialResourceContext
            and resource_context.requested_action == action_id
        )
        or
        (action_id in TASK_ACTIONS and isinstance(resource_context, TaskAuthorityResourceContext))
        or (action_id in TASK_IMPORT_BATCH_ACTIONS and type(resource_context) is TaskImportBatchResourceContext)
        or (
            action_id in {ActionId.ARTIFACT_TASK_IMPORT_SOURCE_DECLARE, ActionId.ARTIFACT_TASK_IMPORT_SOURCE_UPLOAD,
                          ActionId.ARTIFACT_TASK_IMPORT_SOURCE_READ}
            and type(resource_context) is TaskImportSourceResourceContext
        )
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
