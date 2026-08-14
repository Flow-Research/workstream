"""Idempotent recovery proof for adapter-binding lifecycle mutations."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from adapter_binding_test_support import Authorization, BlockingAuthorization, service
from app.db import session as db_session
from app.modules.compensation.api import (
    AdapterBindingConflict,
    AdapterBindingCreateRequest,
    AdapterBindingResumeRequest,
    AdapterBindingSuspendRequest,
)
from app.modules.compensation.models import CompensationAdapterBindingLifecycleEvent

BindingSeed = Callable[[], Awaitable[tuple[UUID, UUID, UUID]]]
pytest_plugins = ("adapter_binding_fixtures",)


async def _create(project_id: UUID, adapter_id: UUID, actor_id: UUID):
    authorization = Authorization()
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            result = await service(session, authorization).create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.primary",
                )
            )
    return result


async def _request_for_transition(
    transition: str, project_id: UUID, adapter_id: UUID, actor_id: UUID
):
    created = await _create(project_id, adapter_id, actor_id)
    if transition == "suspend":
        return AdapterBindingSuspendRequest(
            operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
            adapter_binding_id=created.adapter_binding_id, expected_lifecycle_version=1,
        )
    authorization = Authorization()
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            await service(session, authorization).suspend(
                AdapterBindingSuspendRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, adapter_binding_id=created.adapter_binding_id,
                    expected_lifecycle_version=1,
                )
            )
    return AdapterBindingResumeRequest(
        operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
        adapter_binding_id=created.adapter_binding_id, expected_lifecycle_version=2,
    )


@pytest.mark.parametrize("transition", ("suspend", "resume"))
@pytest.mark.asyncio
async def test_concurrent_duplicate_transition_recovers_one_effect(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    transition: str,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    request = await _request_for_transition(transition, project_id, adapter_id, actor_id)
    winner_auth, loser_auth = BlockingAuthorization(), Authorization()

    async def run(authorization: Authorization):
        async with db_session.get_session_factory()() as session:
            async with session.begin():
                return await getattr(service(session, authorization), transition)(request)

    winner = asyncio.create_task(run(winner_auth))
    await winner_auth.entered.wait()
    loser = asyncio.create_task(run(loser_auth))
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(loser), timeout=0.1)
    winner_auth.release.set()
    first, second = await asyncio.gather(winner, loser)
    assert first == second
    assert winner_auth.prepared + loser_auth.prepared == 1
    async with db_session.get_session_factory()() as session:
        count = await session.scalar(
            select(func.count()).select_from(CompensationAdapterBindingLifecycleEvent).where(
                CompensationAdapterBindingLifecycleEvent.operation_id == request.operation_id
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_duplicate_mismatch_and_read_denial_are_concealed_without_mutation_prep(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    request = await _request_for_transition("suspend", project_id, adapter_id, actor_id)
    authorization = Authorization()
    async with db_session.get_session_factory()() as session:
        binding_service = service(session, authorization)
        async with session.begin():
            await binding_service.suspend(request)
        prepared = authorization.prepared
        mismatch = AdapterBindingSuspendRequest(
            operation_id=request.operation_id, actor_profile_id=actor_id,
            project_id=project_id, adapter_binding_id=request.adapter_binding_id,
            expected_lifecycle_version=2,
        )
        with pytest.raises(AdapterBindingConflict):
            async with session.begin():
                await binding_service.suspend(mismatch)
        authorization.read_available = False
        with pytest.raises(AdapterBindingConflict):
            async with session.begin():
                await binding_service.suspend(request)
    assert authorization.prepared == prepared
