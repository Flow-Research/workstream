"""Immutable operation recovery for ContributionPolicy mutations."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.contributions.api import ContributionPolicyConflict
from app.modules.contributions.policy_validation import policy_request_digest
from tests.contributions.policy_test_support import create_request, service_fixture


def recovered_event(fixture: SimpleNamespace, request: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        operation_id=request.operation_id,
        request_digest=policy_request_digest("contribution.policy.create_draft", request),
        event_type="draft_created",
        actor_profile_id=str(fixture.actor_id),
        project_id=str(fixture.project_id),
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
        version_number=1,
        prior_current_version_id=None,
        prior_current_version_number=None,
        from_policy_status=None,
        to_policy_status="draft",
        from_version_status=None,
        to_version_status="draft",
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_exact_duplicate_returns_immutable_original_result() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    event = recovered_event(fixture, request)
    fixture.repository.get_event_by_operation.return_value = event

    result = await fixture.service.create_draft(request)

    assert result.event_id == event.id
    assert result.operation_id == event.operation_id
    assert result.request_digest == event.request_digest
    assert result.event_type == event.event_type
    assert str(result.actor_profile_id) == event.actor_profile_id
    assert str(result.project_id) == event.project_id
    assert result.contribution_policy_id == event.contribution_policy_id
    assert result.contribution_policy_version_id == event.contribution_policy_version_id
    assert result.version_number == event.version_number
    assert result.prior_current_version_id == event.prior_current_version_id
    assert result.prior_current_version_number == event.prior_current_version_number
    assert result.from_policy_status == event.from_policy_status
    assert result.to_policy_status == event.to_policy_status
    assert result.from_version_status == event.from_version_status
    assert result.to_version_status == event.to_version_status
    assert result.occurred_at == event.occurred_at
    assert fixture.authorization.reads
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_digest_mismatch_is_concealed() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    event = recovered_event(fixture, request)
    event.request_digest = "sha256:" + "0" * 64
    fixture.repository.get_event_by_operation.return_value = event

    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.create_draft(request)


@pytest.mark.asyncio
async def test_recovery_creates_no_second_event() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    fixture.repository.get_event_by_operation.return_value = recovered_event(fixture, request)

    await fixture.service.create_draft(request)

    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_duplicate_requires_current_read_authorization() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    fixture.repository.get_event_by_operation.return_value = recovered_event(fixture, request)

    async def deny_read(request: object) -> None:
        del request
        raise ContributionPolicyConflict("denied")

    fixture.authorization.authorize_contribution_policy_read = deny_read
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.create_draft(request)


@pytest.mark.asyncio
async def test_revoked_read_cannot_recover() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    fixture.repository.get_event_by_operation.return_value = recovered_event(fixture, request)

    async def revoked(request: object) -> None:
        del request
        raise ContributionPolicyConflict("revoked")

    fixture.authorization.authorize_contribution_policy_read = revoked
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.create_draft(request)


@pytest.mark.asyncio
async def test_recovery_creates_no_second_mutation_authorization() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    fixture.repository.get_event_by_operation.return_value = recovered_event(fixture, request)
    await fixture.service.create_draft(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_recovery_creates_no_second_authorization_evidence() -> None:
    fixture = service_fixture()
    request = create_request(fixture)
    fixture.repository.get_event_by_operation.return_value = recovered_event(fixture, request)
    await fixture.service.create_draft(request)
    assert fixture.authorization.consumed == []
