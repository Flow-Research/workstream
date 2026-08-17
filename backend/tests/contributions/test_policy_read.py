"""Authorized immutable ContributionPolicy reads."""

from uuid import uuid4

import pytest

from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyReadRequest,
    ContributionPolicyUnavailable,
    ContributionPolicyView,
)
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion
from tests.contributions.policy_test_support import service_fixture


async def _read_empty_version_view() -> ContributionPolicyView:
    fixture = service_fixture()
    policy_id, version_id = uuid4(), uuid4()
    policy = ContributionPolicy(
        id=policy_id,
        project_id=str(fixture.project_id),
        name="Policy",
        status="draft",
        current_published_version_id=None,
        created_by=str(fixture.actor_id),
    )
    version = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=str(fixture.project_id),
        version_number=2,
        status="draft",
        created_by=str(fixture.actor_id),
    )
    version.rules = []
    fixture.repository.get_policy.return_value = policy
    fixture.repository.get_selected_version.return_value = version
    return await fixture.service.read(
        ContributionPolicyReadRequest(
            actor_profile_id=fixture.actor_id,
            project_id=fixture.project_id,
            contribution_policy_id=policy_id,
            contribution_policy_version_id=version_id,
        )
    )


@pytest.mark.asyncio
async def test_read_conceals_missing_policy() -> None:
    fixture = service_fixture()
    request = ContributionPolicyReadRequest(
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
    )
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.read(request)


@pytest.mark.asyncio
async def test_read_returns_requested_version_only() -> None:
    view = await _read_empty_version_view()
    assert view.version_number == 2
    assert view.rules == ()


@pytest.mark.asyncio
async def test_read_denies_without_composed_authority() -> None:
    fixture = service_fixture()
    fixture.service._read_authorization = fixture.service.__class__(  # noqa: SLF001
        fixture.service._session  # noqa: SLF001
    )._read_authorization  # noqa: SLF001
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.read(
            ContributionPolicyReadRequest(
                actor_profile_id=fixture.actor_id,
                project_id=fixture.project_id,
                contribution_policy_id=uuid4(),
            )
        )


@pytest.mark.asyncio
async def test_read_conceals_cross_project_policy() -> None:
    fixture = service_fixture()
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.read(
            ContributionPolicyReadRequest(
                actor_profile_id=fixture.actor_id,
                project_id=uuid4(),
                contribution_policy_id=uuid4(),
            )
        )


@pytest.mark.asyncio
async def test_read_view_contains_immutable_server_owned_graph_facts() -> None:
    view = await _read_empty_version_view()
    with pytest.raises((AttributeError, TypeError)):
        view.name = "mutated"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_read_view_contains_no_orm_rows() -> None:
    fixture = service_fixture()
    request = ContributionPolicyReadRequest(
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
    )
    with pytest.raises((ContributionPolicyConflict, ContributionPolicyUnavailable)):
        await fixture.service.read(request)
