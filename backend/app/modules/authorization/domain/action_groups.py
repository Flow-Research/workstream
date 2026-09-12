"""Exact shared kernel action classifications; these sets grant no authority."""
from app.modules.authorization.catalogue import GUIDE_PROPOSAL_ACTION_IDS

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain import adapter_bindings, contribution_policies
from app.modules.authorization.runtime import PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION

GUIDE_BOUND_PROJECT_MANAGER_ACTIONS = frozenset(
    {
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
GUIDE_BOUND_PROJECT_MANAGER_ACTIONS |= GUIDE_PROPOSAL_ACTION_IDS
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
        ActionId.PROJECT_CREATE,
        *GUIDE_BOUND_PROJECT_MANAGER_ACTIONS,
        *SUBMISSION_POLICY_MUTATIONS,
        *adapter_bindings.ADAPTER_BINDING_ACTIONS,
        *contribution_policies.CONTRIBUTION_POLICY_ACTIONS,
    }
)
