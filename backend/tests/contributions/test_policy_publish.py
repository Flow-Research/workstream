"""Hidden ContributionPolicy publication behavior."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.contributions.api import ContributionPolicyPublishRequest
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyVersion,
    ContributionRule,
)
from tests.contributions.policy_test_support import service_fixture


def _request(fixture) -> ContributionPolicyPublishRequest:
    return ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )


def _install_complete_draft(fixture, request) -> tuple[ContributionPolicy, ContributionPolicyVersion]:
    policy = ContributionPolicy(
        id=request.contribution_policy_id,
        project_id=str(request.project_id),
        name="Policy",
        status="draft",
        created_by=str(request.actor_profile_id),
    )
    version = ContributionPolicyVersion(
        id=request.contribution_policy_version_id,
        contribution_policy_id=policy.id,
        project_id=str(request.project_id),
        version_number=1,
        status="draft",
        created_by=str(request.actor_profile_id),
    )
    accepted = ContributionRule(
        id=uuid4(), contribution_policy_version_id=version.id,
        project_id=policy.project_id, contribution_type="accepted_submission",
        compensation_mode="compensated",
    )
    reviewed = ContributionRule(
        id=uuid4(), contribution_policy_version_id=version.id,
        project_id=policy.project_id, contribution_type="completed_review",
        compensation_mode="unpaid",
    )
    definition = ContributionAwardDefinition(
        id=uuid4(), contribution_rule_id=accepted.id,
        contribution_policy_version_id=version.id, project_id=policy.project_id,
        contribution_type="accepted_submission", instrument_type="money",
        unit_code="USD", quantity=Decimal("10"), adapter_binding_id=uuid4(),
    )
    accepted.award_definitions = [definition]
    reviewed.award_definitions = []
    fixture.repository.get_policy.return_value = policy
    fixture.repository.get_version.return_value = version
    fixture.repository.lock_publication_graph.return_value = (
        [accepted, reviewed], [definition]
    )

    async def stamp(custody) -> None:
        custody.occurred_at = datetime.now(UTC)

    fixture.repository.create_transition_custody.side_effect = stamp
    return policy, version


@pytest.mark.asyncio
async def test_publish_uses_locked_server_owned_graph() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    policy, version = _install_complete_draft(fixture, request)

    result = await fixture.service.publish(request)

    assert result.event_type == "published"
    assert policy.current_published_version_id == version.id
    assert fixture.authorization.prepared[0].adapter_binding_ids


@pytest.mark.asyncio
async def test_publish_closes_authority_before_product_transition() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    policy, _ = _install_complete_draft(fixture, request)

    async def observe(custody) -> None:
        assert len(fixture.authorization.closed) == 1
        assert policy.status == "draft"
        custody.occurred_at = datetime.now(UTC)

    fixture.repository.create_transition_custody.side_effect = observe
    await fixture.service.publish(request)


@pytest.mark.asyncio
async def test_publish_is_hidden_deny_default() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _install_complete_draft(fixture, request)
    fixture.service._publication._mutation_authorization = fixture.service.__class__(  # noqa: SLF001
        fixture.service._session  # noqa: SLF001
    )._mutation_authorization  # noqa: SLF001

    with pytest.raises(RuntimeError, match="contribution_policy_unavailable"):
        await fixture.service.publish(request)

    fixture.repository.create_transition_custody.assert_not_awaited()
