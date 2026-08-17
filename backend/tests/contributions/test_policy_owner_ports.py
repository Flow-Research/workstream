"""Public-owner port isolation for ContributionPolicy behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.contributions import contribution_policy_service
from app.adapters.projects import (
    project_contribution_policy_eligibility_port,
    project_locked_policy_context_port,
)
from app.modules.compensation.api import CompensationInstrumentType
from app.modules.compensation.api import PolicyAdapterBindingUnavailable
from app.modules.compensation.policy_binding_service import PolicyAdapterBindingLookup
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility


class _Session:
    def __init__(self, value: object) -> None:
        self.scalar = AsyncMock(return_value=value)


def test_compensation_policy_binding_lookup_is_compensation_owned() -> None:
    assert PolicyAdapterBindingLookup.__module__ == (
        "app.modules.compensation.policy_binding_service"
    )


def test_projects_policy_eligibility_is_projects_owned() -> None:
    assert ProjectContributionPolicyEligibility.__module__ == (
        "app.modules.projects.contribution_policy"
    )


def test_canonical_instrument_enum_is_public_and_closed() -> None:
    assert {item.value for item in CompensationInstrumentType} == {
        "money",
        "project_points",
    }
    with pytest.raises(ValueError):
        CompensationInstrumentType(str(uuid4()))


@pytest.mark.asyncio
async def test_compensation_policy_binding_lookup_retains_transaction_fence() -> None:
    project_id, binding_id = uuid4(), uuid4()
    session = _Session(
        SimpleNamespace(
            id=binding_id,
            status="active",
            binding_lifecycle_version=3,
        )
    )
    facts = await PolicyAdapterBindingLookup(session).lock_policy_adapter_binding(  # type: ignore[arg-type]
        project_id=project_id,
        adapter_binding_id=binding_id,
        instrument_type=CompensationInstrumentType.MONEY,
    )
    statement = session.scalar.await_args.args[0]
    assert facts.project_id == project_id
    assert facts.adapter_binding_id == binding_id
    assert facts.instrument_type is CompensationInstrumentType.MONEY
    assert facts.binding_lifecycle_version == 3
    assert statement._for_update_arg is not None  # noqa: SLF001


@pytest.mark.asyncio
async def test_compensation_policy_binding_lookup_rejects_inactive_binding() -> None:
    session = _Session(SimpleNamespace(id=uuid4(), status="suspended"))
    with pytest.raises(PolicyAdapterBindingUnavailable):
        await PolicyAdapterBindingLookup(session).lock_policy_adapter_binding(  # type: ignore[arg-type]
            project_id=uuid4(),
            adapter_binding_id=uuid4(),
            instrument_type=CompensationInstrumentType.MONEY,
        )


@pytest.mark.asyncio
async def test_compensation_policy_binding_lookup_conceals_cross_project_binding() -> None:
    session = _Session(None)
    with pytest.raises(PolicyAdapterBindingUnavailable):
        await PolicyAdapterBindingLookup(session).lock_policy_adapter_binding(  # type: ignore[arg-type]
            project_id=uuid4(),
            adapter_binding_id=uuid4(),
            instrument_type=CompensationInstrumentType.PROJECT_POINTS,
        )


@pytest.mark.asyncio
async def test_projects_policy_eligibility_port_retains_transaction_fence() -> None:
    project_id = uuid4()
    session = _Session(SimpleNamespace(status="active"))
    facts = await ProjectContributionPolicyEligibility(  # type: ignore[arg-type]
        session
    ).lock_contribution_policy_project(project_id)
    statement = session.scalar.await_args.args[0]
    assert facts.project_id == project_id
    assert statement._for_update_arg is not None  # noqa: SLF001


def test_contributions_composition_uses_public_owner_ports() -> None:
    session = _Session(None)
    service = contribution_policy_service(session)  # type: ignore[arg-type]
    assert service._projects.__class__.__module__.startswith(  # noqa: SLF001
        "app.modules.projects"
    )
    assert service._bindings.__class__.__module__.startswith(  # noqa: SLF001
        "app.modules.compensation"
    )


def test_projects_adapter_root_constructs_both_public_ports() -> None:
    session = _Session(None)
    assert project_contribution_policy_eligibility_port(  # type: ignore[arg-type]
        session
    ).__class__.__module__.startswith("app.modules.projects")
    assert project_locked_policy_context_port(  # type: ignore[arg-type]
        session
    ).__class__.__module__.startswith("app.modules.projects")
