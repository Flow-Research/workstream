"""Create-draft behavior for hidden ContributionPolicy service."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.contributions.api import ContributionPolicyConflict
from app.modules.contributions.models import ContributionPolicy
from tests.contributions.policy_test_support import create_request, service_fixture


@pytest.mark.asyncio
async def test_create_draft_creates_version_one_for_new_policy() -> None:
    fixture = service_fixture()

    result = await fixture.service.create_draft(create_request(fixture))

    assert result.event_type == "draft_created"
    assert result.version_number == 1
    assert len(fixture.authorization.consumed) == 1
    assert len(fixture.authorization.closed) == 1
    fixture.repository.add_policy_version_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_draft_rejects_second_open_draft_for_project_without_effect() -> None:
    fixture = service_fixture()
    fixture.repository.get_open_draft.return_value = SimpleNamespace(id=uuid4())

    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.create_draft(create_request(fixture))

    assert fixture.authorization.prepared == []
    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_draft_conceals_project_owner_mismatch() -> None:
    fixture = service_fixture()

    async def wrong_project(project_id: object) -> object:
        del project_id
        return SimpleNamespace(project_id=uuid4())

    fixture.service._projects.lock_contribution_policy_project = wrong_project  # noqa: SLF001

    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.create_draft(create_request(fixture))

    assert fixture.authorization.prepared == []
    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_draft_creates_next_version_on_current_non_retired_policy() -> None:
    fixture = service_fixture()
    policy = ContributionPolicy(
        id=uuid4(),
        project_id=str(fixture.project_id),
        name="Existing",
        status="active",
        current_published_version_id=None,
        created_by=str(fixture.actor_id),
    )
    fixture.repository.get_reusable_policy.return_value = policy
    fixture.repository.next_version_number.return_value = 3

    result = await fixture.service.create_draft(create_request(fixture))

    assert result.contribution_policy_id == policy.id
    assert result.version_number == 3


@pytest.mark.asyncio
async def test_create_draft_denies_without_composed_authority() -> None:
    fixture = service_fixture()
    fixture.service._mutation_authorization = (  # noqa: SLF001
        fixture.service.__class__(fixture.service._session)._mutation_authorization  # noqa: SLF001
    )

    with pytest.raises(RuntimeError, match="contribution_policy_unavailable"):
        await fixture.service.create_draft(create_request(fixture))

    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_draft_retains_project_policy_fence_through_mutation() -> None:
    fixture = service_fixture()
    await fixture.service.create_draft(create_request(fixture))
    fixture.repository.lock_project_scope.assert_awaited_once_with(fixture.project_id)


@pytest.mark.asyncio
async def test_create_draft_does_not_reuse_retired_policy() -> None:
    fixture = service_fixture()
    retired_policy = ContributionPolicy(
        id=uuid4(),
        project_id=str(fixture.project_id),
        name="Retired",
        status="retired",
        current_published_version_id=uuid4(),
        created_by=str(fixture.actor_id),
    )
    fixture.repository.get_reusable_policy.return_value = retired_policy

    result = await fixture.service.create_draft(create_request(fixture))

    assert result.contribution_policy_id != retired_policy.id
    assert result.version_number == 1
    created_version = fixture.repository.add_policy_version_event.await_args.args[1]
    assert created_version.contribution_policy_id == result.contribution_policy_id
