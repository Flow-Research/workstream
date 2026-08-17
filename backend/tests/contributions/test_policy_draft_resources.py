"""Resource isolation during complete draft replacement."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.compensation.api import (
    CompensationInstrumentType,
    LockedPolicyAdapterBindingFacts,
    PolicyAdapterBindingUnavailable,
)
from app.modules.contributions.api import ContributionPolicyConflict
from tests.contributions.policy_test_support import service_fixture
from tests.contributions.test_policy_draft_update import install_draft, update_request


@pytest.mark.asyncio
async def test_update_rejects_retired_unit_without_effect() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    fixture.repository.lock_unit.return_value = SimpleNamespace(status="retired")

    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)

    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_update_conceals_cross_project_unit_without_effect() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    fixture.repository.lock_unit.return_value = None

    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)


@pytest.mark.asyncio
async def test_update_rejects_inactive_adapter_binding_without_effect() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)

    async def deny(**facts: object) -> object:
        del facts
        raise PolicyAdapterBindingUnavailable("inactive")

    fixture.service._bindings.lock_policy_adapter_binding = deny  # noqa: SLF001
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)

    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_conceals_cross_project_adapter_binding_without_effect() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)

    async def conceal(**facts: object) -> object:
        del facts
        raise PolicyAdapterBindingUnavailable("cross_project")

    fixture.service._bindings.lock_policy_adapter_binding = conceal  # noqa: SLF001
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ("project_id", "binding_id", "instrument_type"))
async def test_update_rejects_mismatched_adapter_binding_owner_facts(
    mismatch: str,
) -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    definition = request.rules[0].definitions[0]

    async def mismatched(**facts: object) -> LockedPolicyAdapterBindingFacts:
        del facts
        return LockedPolicyAdapterBindingFacts(
            project_id=uuid4() if mismatch == "project_id" else request.project_id,
            adapter_binding_id=(
                uuid4() if mismatch == "binding_id" else definition.adapter_binding_id
            ),
            instrument_type=(
                CompensationInstrumentType.PROJECT_POINTS
                if mismatch == "instrument_type"
                else definition.instrument_type
            ),
            binding_lifecycle_version=1,
        )

    fixture.service._bindings.lock_policy_adapter_binding = mismatched  # noqa: SLF001
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.update_draft(request)
    assert fixture.authorization.prepared == []
    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_conceals_cross_project_policy_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    fixture.repository.get_policy.assert_awaited_once_with(
        request.project_id, request.contribution_policy_id, for_update=True
    )
    fixture.repository.get_version.assert_awaited_once()
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_update_conceals_cross_project_version_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    fixture.repository.get_version.return_value = None
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    fixture.repository.get_policy.assert_awaited_once()
    fixture.repository.get_version.assert_awaited_once()
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_update_conceals_cross_project_request_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)

    async def wrong_project(project_id: object) -> object:
        del project_id
        return SimpleNamespace(project_id=uuid4())

    fixture.service._projects.lock_contribution_policy_project = wrong_project  # noqa: SLF001
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    fixture.repository.get_policy.assert_not_awaited()
    assert fixture.authorization.prepared == []
