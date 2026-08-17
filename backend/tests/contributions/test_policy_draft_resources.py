"""Resource isolation during complete draft replacement."""

from types import SimpleNamespace

import pytest

from app.modules.compensation.api import PolicyAdapterBindingUnavailable
from app.modules.contributions.api import ContributionPolicyConflict
from tests.contributions.policy_test_support import service_fixture
from tests.contributions.test_policy_draft_update import install_draft, update_request


async def _assert_foreign_policy_denied() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    assert fixture.authorization.prepared == []


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
async def test_update_conceals_cross_project_policy_before_authorization() -> None:
    await _assert_foreign_policy_denied()


@pytest.mark.asyncio
async def test_update_conceals_cross_project_version_before_authorization() -> None:
    await _assert_foreign_policy_denied()


@pytest.mark.asyncio
async def test_update_conceals_cross_project_request_before_authorization() -> None:
    await _assert_foreign_policy_denied()
