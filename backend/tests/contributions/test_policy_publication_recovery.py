"""Immutable duplicate recovery for policy publication and retirement."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyPublishRequest,
    ContributionPolicyRetireRequest,
)
from app.modules.contributions.models import ContributionPolicyLifecycleEvent
from app.modules.contributions.policy_validation import policy_request_digest
from tests.contributions.policy_test_support import service_fixture


def _event(request, action: str, event_type: str) -> ContributionPolicyLifecycleEvent:
    return ContributionPolicyLifecycleEvent(
        id=uuid4(),
        operation_id=request.operation_id,
        publication_custody_operation_id=request.operation_id,
        request_digest=policy_request_digest(action, request),
        event_type=event_type,
        actor_profile_id=str(request.actor_profile_id),
        project_id=str(request.project_id),
        contribution_policy_id=request.contribution_policy_id,
        contribution_policy_version_id=request.contribution_policy_version_id,
        version_number=1,
        prior_current_version_id=None,
        prior_current_version_number=None,
        from_policy_status="draft",
        to_policy_status="active",
        from_version_status="draft",
        to_version_status="published",
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_duplicate_publish_returns_original_event_after_authorized_read() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    event = _event(request, "contribution.policy.publish", "published")
    fixture.repository.get_event_by_operation.return_value = event
    result = await fixture.service.publish(request)
    assert result.event_id == event.id


@pytest.mark.asyncio
async def test_duplicate_retire_returns_original_event_after_authorized_read() -> None:
    fixture = service_fixture()
    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    event = _event(request, "contribution.policy.retire", "retired")
    event.from_policy_status = "active"
    event.to_policy_status = "retired"
    event.from_version_status = "published"
    event.to_version_status = "retired"
    fixture.repository.get_event_by_operation.return_value = event
    result = await fixture.service.retire(request)
    assert result.event_id == event.id


@pytest.mark.asyncio
async def test_duplicate_digest_mismatch_is_concealed() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    event = _event(request, "contribution.policy.publish", "published")
    event.request_digest = "sha256:" + "0" * 64
    fixture.repository.get_event_by_operation.return_value = event
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.publish(request)


@pytest.mark.asyncio
async def test_duplicate_recovery_skips_mutation_authorization() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    fixture.repository.get_event_by_operation.return_value = _event(
        request, "contribution.policy.publish", "published"
    )
    await fixture.service.publish(request)
    assert fixture.authorization.prepared == []
    fixture.repository.create_transition_custody.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_recovery_read_denial_is_concealed() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    fixture.repository.get_event_by_operation.return_value = _event(
        request, "contribution.policy.publish", "published"
    )

    async def deny(request):
        del request
        raise ContributionPolicyConflict("contribution_policy_not_found")

    fixture.authorization.authorize_contribution_policy_read = deny
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.publish(request)


@pytest.mark.asyncio
async def test_duplicate_recovery_creates_no_second_product_effect() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    fixture.repository.get_event_by_operation.return_value = _event(
        request, "contribution.policy.publish", "published"
    )
    await fixture.service.publish(request)
    fixture.repository.create_transition_custody.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_recovery_creates_no_second_authorization_evidence() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    fixture.repository.get_event_by_operation.return_value = _event(
        request, "contribution.policy.publish", "published"
    )
    await fixture.service.publish(request)
    assert fixture.authorization.consumed == []


@pytest.mark.asyncio
async def test_duplicate_recovery_creates_no_second_lifecycle_event() -> None:
    fixture = service_fixture()
    request = ContributionPolicyPublishRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    fixture.repository.get_event_by_operation.return_value = _event(
        request, "contribution.policy.publish", "published"
    )
    await fixture.service.publish(request)
    fixture.repository.flush_transition_event.assert_not_awaited()
