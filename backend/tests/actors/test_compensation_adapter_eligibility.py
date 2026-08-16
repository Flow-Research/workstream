"""Focused ACTORS owner-eligibility behavior for compensation adapters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.actors.api import (
    SERVICE_IDENTITIES,
    CompensationAdapterActorUnavailable,
    ServiceIdentity,
)
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.authorization.catalogue import SERVICE_ACTIONS_BY_IDENTITY
from app.modules.authorization.service_actor_schemas import ServiceActorProvisionBody


def _profile(actor_id, **overrides):
    values = {
        "id": str(actor_id),
        "actor_kind": "service",
        "status": "active",
        "service_identity": ServiceIdentity.COMPENSATION_ADAPTER.value,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _link(actor_id, **overrides):
    values = {
        "actor_profile_id": str(actor_id),
        "subject_kind": "service",
        "status": "active",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_target_identity_is_provisionable_but_has_no_service_actions() -> None:
    body = ServiceActorProvisionBody.model_validate(
        {
            "service_identity": ServiceIdentity.COMPENSATION_ADAPTER.value,
            "subject": "compensation-adapter-target",
            "reason": "Register the exact compensation adapter target",
        }
    )

    assert body.service_identity is ServiceIdentity.COMPENSATION_ADAPTER
    assert body.service_identity not in SERVICE_ACTIONS_BY_IDENTITY


@pytest.mark.asyncio
async def test_exact_active_adapter_profile_and_link_are_eligible() -> None:
    actor_id = uuid4()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[_profile(actor_id), _link(actor_id)]))

    facts = await CompensationAdapterActorEligibility(session).lock_compensation_adapter_actor(
        actor_id
    )

    assert facts.adapter_actor_id == actor_id
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile",
    [
        None,
        _profile(uuid4(), actor_kind="human"),
        _profile(uuid4(), status="suspended"),
    ],
)
async def test_ineligible_profiles_are_concealed(profile) -> None:
    session = SimpleNamespace(scalar=AsyncMock(return_value=profile))

    with pytest.raises(CompensationAdapterActorUnavailable):
        await CompensationAdapterActorEligibility(session).lock_compensation_adapter_actor(uuid4())

    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", SERVICE_IDENTITIES - {ServiceIdentity.COMPENSATION_ADAPTER})
async def test_every_action_bearing_service_identity_is_ineligible(identity) -> None:
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=_profile(uuid4(), service_identity=identity.value))
    )

    with pytest.raises(CompensationAdapterActorUnavailable):
        await CompensationAdapterActorEligibility(session).lock_compensation_adapter_actor(uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "link",
    [
        None,
        _link(uuid4(), subject_kind="human"),
        _link(uuid4(), status="revoked"),
    ],
)
async def test_ineligible_identity_links_are_concealed(link) -> None:
    actor_id = uuid4()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[_profile(actor_id), link]))

    with pytest.raises(CompensationAdapterActorUnavailable):
        await CompensationAdapterActorEligibility(session).lock_compensation_adapter_actor(actor_id)

    assert session.scalar.await_count == 2
