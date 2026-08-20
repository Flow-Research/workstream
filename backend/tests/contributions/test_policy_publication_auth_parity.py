"""Public AUTH fact parity for hidden ContributionPolicy publication."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.authorization.api import (
    ActionId,
    ContributionPolicyPublishFacts,
    ContributionPolicyRetireFacts,
    contribution_policy_resource_digest,
)
from app.modules.contributions.api import (
    ContributionPolicyPublishAuthorizationFacts,
    ContributionPolicyRetireRequest,
    ContributionPolicyRetireAuthorizationFacts,
)
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion
from app.modules.contributions.policy_graph import publication_graph_facts
from tests.contributions.policy_test_support import service_fixture
from tests.contributions.test_policy_publish import _install_complete_draft, _request


@pytest.mark.asyncio
async def test_publish_facts_match_public_auth_digest() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _, version = _install_complete_draft(fixture, request)
    rules, _ = fixture.repository.lock_publication_graph.return_value
    set_committed_value(version, "rules", rules)
    graph_digest, binding_ids = publication_graph_facts(version)
    expected_facts = ContributionPolicyPublishFacts(
        project_id=request.project_id,
        contribution_policy_id=request.contribution_policy_id,
        contribution_policy_version_id=request.contribution_policy_version_id,
        rules_and_definitions_digest=graph_digest,
        adapter_binding_ids=binding_ids,
    )
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
    expected = contribution_policy_resource_digest(
        ActionId("contribution.policy.publish"), expected_facts
    )
    actual = contribution_policy_resource_digest(ActionId(facts.action), auth_facts)
    assert actual == expected


@pytest.mark.asyncio
async def test_retire_facts_match_public_auth_digest() -> None:
    fixture = service_fixture()
    policy_id, version_id = uuid4(), uuid4()
    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=policy_id,
        contribution_policy_version_id=version_id,
    )
    fixture.repository.get_policy.return_value = ContributionPolicy(
        id=policy_id,
        project_id=str(fixture.project_id),
        name="Policy",
        status="active",
        current_published_version_id=version_id,
        created_by=str(fixture.actor_id),
    )
    fixture.repository.get_version.return_value = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=str(fixture.project_id),
        version_number=1,
        status="published",
        created_by=str(fixture.actor_id),
        published_by=str(fixture.actor_id),
        published_at=datetime.now(UTC),
    )

    async def stamp(custody) -> None:
        custody.occurred_at = datetime.now(UTC)

    fixture.repository.create_transition_custody.side_effect = stamp
    await fixture.service.retire(request)
    facts = fixture.authorization.prepared[0]
    assert isinstance(facts, ContributionPolicyRetireAuthorizationFacts)
    auth_facts = ContributionPolicyRetireFacts(
        project_id=facts.project_id,
        contribution_policy_id=facts.contribution_policy_id,
        contribution_policy_version_id=facts.contribution_policy_version_id,
    )
    expected_facts = ContributionPolicyRetireFacts(
        project_id=request.project_id,
        contribution_policy_id=request.contribution_policy_id,
        contribution_policy_version_id=request.contribution_policy_version_id,
    )
    expected = contribution_policy_resource_digest(
        ActionId("contribution.policy.retire"), expected_facts
    )
    actual = contribution_policy_resource_digest(ActionId(facts.action), auth_facts)
    assert actual == expected
