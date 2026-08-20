"""Hidden terminal ContributionPolicy retirement behavior."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyRetireRequest,
)
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion
from tests.contributions.policy_test_support import service_fixture


@pytest.mark.asyncio
async def test_retire_is_terminal_and_attributable() -> None:
    fixture = service_fixture()
    policy_id, version_id = uuid4(), uuid4()
    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=policy_id,
        contribution_policy_version_id=version_id,
    )
    policy = ContributionPolicy(
        id=policy_id,
        project_id=str(fixture.project_id),
        name="Policy",
        status="active",
        current_published_version_id=version_id,
        created_by=str(fixture.actor_id),
    )
    version = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=str(fixture.project_id),
        version_number=1,
        status="published",
        created_by=str(fixture.actor_id),
        published_by=str(fixture.actor_id),
        published_at=datetime.now(UTC),
    )
    fixture.repository.get_policy.return_value = policy
    fixture.repository.get_version.return_value = version

    async def stamp(custody) -> None:
        custody.occurred_at = datetime.now(UTC)

    fixture.repository.create_transition_custody.side_effect = stamp
    result = await fixture.service.retire(request)

    assert result.event_type == "retired"
    assert policy.status == version.status == "retired"
    assert policy.last_transition_operation_id == request.operation_id


def test_retire_blocks_future_selection_without_rewriting_history() -> None:
    request_fields = ContributionPolicyRetireRequest.__dataclass_fields__
    assert "project_guide_id" not in request_fields
    assert "task_id" not in request_fields
    assert "submission_id" not in request_fields


@pytest.mark.asyncio
async def test_retired_aggregate_cannot_be_resurrected() -> None:
    fixture = service_fixture()
    policy_id, version_id = uuid4(), uuid4()
    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=policy_id,
        contribution_policy_version_id=version_id,
    )
    policy = ContributionPolicy(
        id=policy_id,
        project_id=str(fixture.project_id),
        name="Policy",
        status="retired",
        current_published_version_id=version_id,
        created_by=str(fixture.actor_id),
        retired_by=str(fixture.actor_id),
        retired_at=datetime.now(UTC),
    )
    version = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=str(fixture.project_id),
        version_number=1,
        status="retired",
        created_by=str(fixture.actor_id),
        published_by=str(fixture.actor_id),
        published_at=datetime.now(UTC),
        retired_by=str(fixture.actor_id),
        retired_at=datetime.now(UTC),
    )
    fixture.repository.get_policy.return_value = policy
    fixture.repository.get_version.return_value = version
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.retire(request)
    assert fixture.authorization.prepared == []
