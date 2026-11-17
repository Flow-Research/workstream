"""Reuse the established Finance/PREP fixture with exact policy facts."""

from uuid import uuid4

from app.modules.authorization.api import (
    ContributionPolicyCreateDraftFacts,
    ContributionPolicyUpdateDraftFacts,
    ContributionPolicyPublishFacts,
    ContributionPolicyRetireFacts,
    ContributionPolicyMutationAuthorityFacts,
    action_id,
)
from app.modules.authorization.contribution_policy_authorization import (
    ContributionPolicyAuthorizationAdapter,
)
from tests.authorization.test_adapter_binding_authorization import _adapter

ACTIONS = ("create_draft", "update_draft", "publish", "retire")
DIGEST = "sha256:" + "a" * 64


def adapter(project_id, **kwargs):
    """Use real AUTH/PREP with the existing bounded Finance repository."""
    original, context, session, evidence = _adapter(project_id, **kwargs)
    original._authorization._admin.expected_roles = frozenset({"finance_authority", "project_manager"})
    return (
        ContributionPolicyAuthorizationAdapter(original._authorization, original._prepared),
        context,
        session,
        evidence,
    )


def mutation(actor, project, operation="create_draft"):
    """Build independently scoped and complete action-specific public facts."""
    policy, version = uuid4(), uuid4()
    identity = dict(
        project_id=project, contribution_policy_id=policy, contribution_policy_version_id=version
    )
    if operation == "create_draft":
        resource = ContributionPolicyCreateDraftFacts(project_id=project)
    elif operation == "update_draft":
        resource = ContributionPolicyUpdateDraftFacts(**identity)
    elif operation == "publish":
        resource = ContributionPolicyPublishFacts(
            **identity, rules_and_definitions_digest=DIGEST, adapter_binding_ids=(uuid4(),)
        )
    else:
        resource = ContributionPolicyRetireFacts(**identity)
    return ContributionPolicyMutationAuthorityFacts(
        action_id=action_id("contribution.policy." + operation),
        actor_profile_id=actor,
        operation_id=uuid4(),
        request_digest=DIGEST,
        contribution_policy_id=policy,
        contribution_policy_version_id=version,
        expected_policy_status=None if operation == "create_draft" else "active",
        expected_version_status=None
        if operation == "create_draft"
        else ("published" if operation == "retire" else "draft"),
        resource_facts=resource,
    )
