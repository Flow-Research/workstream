"""Public AUTH fact parity for hidden ContributionPolicy publication."""

from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    ActionId,
    ContributionPolicyPublishFacts,
    ContributionPolicyRetireFacts,
    contribution_policy_resource_digest,
)
from app.modules.contributions.api import (
    ContributionPolicyPublishAuthorizationFacts,
    ContributionPolicyRetireAuthorizationFacts,
)
from tests.contributions.policy_test_support import service_fixture
from tests.contributions.test_policy_publish import _install_complete_draft, _request


@pytest.mark.asyncio
async def test_publish_facts_match_public_auth_digest() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _install_complete_draft(fixture, request)
    await fixture.service.publish(request)
    facts = fixture.authorization.prepared[0]
    assert isinstance(facts, ContributionPolicyPublishAuthorizationFacts)
    auth_facts = ContributionPolicyPublishFacts(
        project_id=facts.project_id,
        contribution_policy_id=facts.contribution_policy_id,
        contribution_policy_version_id=facts.contribution_policy_version_id,
        rules_and_definitions_digest=facts.rules_and_definitions_digest,
        adapter_binding_ids=facts.adapter_binding_ids,
    )
    digest = contribution_policy_resource_digest(
        ActionId("contribution.policy.publish"), auth_facts
    )
    assert digest == contribution_policy_resource_digest(ActionId(facts.action), auth_facts)


def test_retire_facts_match_public_auth_digest() -> None:
    actor, operation, project, policy, version = (uuid4() for _ in range(5))
    facts = ContributionPolicyRetireAuthorizationFacts(
        action="contribution.policy.retire",
        actor_profile_id=actor,
        operation_id=operation,
        request_digest="sha256:" + "a" * 64,
        project_id=project,
        contribution_policy_id=policy,
        contribution_policy_version_id=version,
    )
    auth_facts = ContributionPolicyRetireFacts(
        project_id=facts.project_id,
        contribution_policy_id=facts.contribution_policy_id,
        contribution_policy_version_id=facts.contribution_policy_version_id,
    )
    digest = contribution_policy_resource_digest(ActionId("contribution.policy.retire"), auth_facts)
    assert digest.startswith("sha256:") and len(digest) == 71
