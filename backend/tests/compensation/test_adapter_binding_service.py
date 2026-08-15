"""Focused PostgreSQL proof for the hidden adapter-binding service."""

import asyncio

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.compensation.api import (
    AdapterBindingCreateRequest,
    AdapterBindingConflict,
    AdapterBindingReadRequest,
    AdapterBindingResumeRequest,
    AdapterBindingSuspendRequest,
    AdapterBindingUnavailable,
)
from app.modules.compensation.models import (
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)
from app.modules.compensation.service import AdapterBindingService
from adapter_binding_test_support import (
    Authorization as _Authorization,
    BlockingAuthorization as _BlockingAuthorization,
    CloseFailureAuthorization as _CloseFailureAuthorization,
    Eligibility as _Eligibility,
    Prepared as _Prepared,
    service as _service,
)
BindingSeed = Callable[[], Awaitable[tuple[UUID, UUID, UUID]]]
pytest_plugins = ("adapter_binding_fixtures",)


@pytest.mark.asyncio
async def test_create_suspend_resume_persists_contiguous_immutable_history(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _Authorization()
    async with db_session.get_session_factory()() as session:
        service = _service(session, authorization)
        async with session.begin():
            created = await service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
                    instrument_type="money", adapter_actor_id=adapter_id,
                    route_key="adapter.primary",
                )
            )
        async with session.begin():
            suspended = await service.suspend(
                AdapterBindingSuspendRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
                    adapter_binding_id=created.adapter_binding_id,
                    expected_lifecycle_version=1,
                )
            )
        async with session.begin():
            resumed = await service.resume(
                AdapterBindingResumeRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
                    adapter_binding_id=created.adapter_binding_id,
                    expected_lifecycle_version=2,
                )
            )
        view = await service.read(
            AdapterBindingReadRequest(
                actor_profile_id=actor_id,
                project_id=project_id,
                adapter_binding_id=created.adapter_binding_id,
            )
        )
    assert resumed.prior_suspension_event_id == suspended.event_id
    assert (authorization.prepared, authorization.consumed, authorization.closed) == (3, 3, 3)
    async with db_session.get_session_factory()() as session:
        events = (
            await session.scalars(
                select(CompensationAdapterBindingLifecycleEvent).order_by(
                    CompensationAdapterBindingLifecycleEvent.to_lifecycle_version
                )
            )
        ).all()
        binding = await session.get(
            ProjectCompensationAdapterBinding, created.adapter_binding_id
        )
    assert [event.event_type for event in events] == ["created", "suspended", "resumed"]
    assert binding is not None and (binding.status, binding.binding_lifecycle_version) == (
        "active", 3
    )
    assert binding.resumed_by == str(actor_id)
    assert binding.resumed_at is not None
    assert view.resumed_by == actor_id
    assert view.resumed_at == binding.resumed_at


@pytest.mark.asyncio
async def test_exact_duplicate_recovers_without_second_mutation_authorization(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _Authorization()
    request = AdapterBindingCreateRequest(
        operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
        instrument_type="money", adapter_actor_id=adapter_id, route_key="adapter.primary",
    )
    async with db_session.get_session_factory()() as session:
        service = _service(session, authorization)
        async with session.begin():
            original = await service.create(request)
        async with session.begin():
            recovered = await service.create(request)
    assert recovered == original
    assert (authorization.prepared, authorization.consumed, authorization.closed) == (1, 1, 1)


@pytest.mark.asyncio
async def test_close_failure_prevents_product_state_and_event(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _CloseFailureAuthorization()
    async with db_session.get_session_factory()() as session:
        service = _service(session, authorization)
        with pytest.raises(AdapterBindingUnavailable, match="close_failed"):
            async with session.begin():
                await service.create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=adapter_id, route_key="adapter.primary",
                    )
                )
    assert (authorization.prepared, authorization.consumed, authorization.closed) == (1, 1, 1)
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(ProjectCompensationAdapterBinding.id)) is None
        assert await session.scalar(select(CompensationAdapterBindingLifecycleEvent.id)) is None


@pytest.mark.asyncio
async def test_owner_denial_precedes_actor_lookup_and_authorization(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _Authorization()
    eligibility = _Eligibility(project_available=False)
    async with db_session.get_session_factory()() as session:
        service = _service(session, authorization, eligibility)
        with pytest.raises(AdapterBindingConflict, match="compensation_adapter_binding_not_found"):
            async with session.begin():
                await service.create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=adapter_id, route_key="adapter.primary",
                    )
                )
    assert eligibility.calls == ["project"]
    assert (authorization.prepared, authorization.consumed, authorization.closed) == (0, 0, 0)


@pytest.mark.asyncio
async def test_defensively_rejects_tampered_request_before_authorization(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    request = AdapterBindingCreateRequest(
        operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
        instrument_type="money", adapter_actor_id=adapter_id, route_key="adapter.primary",
    )
    object.__setattr__(request, "instrument_type", "credits")
    authorization = _Authorization()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(ValueError, match="instrument_type"):
            async with session.begin():
                await _service(session, authorization).create(request)
    assert authorization.prepared == 0


@pytest.mark.asyncio
async def test_prepared_fake_rejects_copy_replay_and_transaction_replacement(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _Authorization()
    async with db_session.get_session_factory()() as session:
        service = _service(session, authorization)
        async with session.begin():
            await service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.primary",
                )
            )
        prepared = next(iter(authorization._prepared.values()))
        copied = _Prepared(prepared.facts, prepared.transaction_id)
        async with session.begin():
            with pytest.raises(AssertionError):
                await authorization.consume_adapter_binding_mutation(copied, prepared.facts)
            with pytest.raises(AssertionError):
                await authorization.consume_adapter_binding_mutation(prepared, prepared.facts)
        async with session.begin():
            replaced_transaction = await authorization.prepare_adapter_binding_mutation(
                prepared.facts
            )
        async with session.begin():
            with pytest.raises(AssertionError):
                await authorization.consume_adapter_binding_mutation(
                    replaced_transaction, prepared.facts
                )


@pytest.mark.asyncio
async def test_production_default_denies_before_product_state(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    async with db_session.get_session_factory()() as session:
        service = AdapterBindingService(
            session, projects=_Eligibility(), actors=_Eligibility()
        )
        with pytest.raises(AdapterBindingUnavailable):
            async with session.begin():
                await service.create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=adapter_id, route_key="adapter.primary",
                    )
                )
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(ProjectCompensationAdapterBinding.id)) is None
        assert await session.scalar(select(CompensationAdapterBindingLifecycleEvent.id)) is None


@pytest.mark.asyncio
async def test_concurrent_duplicate_waits_then_recovers_one_effect(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    request = AdapterBindingCreateRequest(
        operation_id=uuid4(), actor_profile_id=actor_id, project_id=project_id,
        instrument_type="money", adapter_actor_id=adapter_id, route_key="adapter.primary",
    )
    winner_auth = _BlockingAuthorization()
    loser_auth = _Authorization()

    async def run(authorization: _Authorization):
        async with db_session.get_session_factory()() as session:
            async with session.begin():
                return await _service(session, authorization).create(request)

    winner = asyncio.create_task(run(winner_auth))
    await winner_auth.entered.wait()
    loser = asyncio.create_task(run(loser_auth))
    await asyncio.sleep(0.05)
    assert not loser.done()
    winner_auth.release.set()
    first, second = await asyncio.gather(winner, loser)
    assert first == second
    assert winner_auth.prepared + loser_auth.prepared == 1
    async with db_session.get_session_factory()() as session:
        assert len((await session.scalars(select(ProjectCompensationAdapterBinding))).all()) == 1
        assert len(
            (await session.scalars(select(CompensationAdapterBindingLifecycleEvent))).all()
        ) == 1


@pytest.mark.asyncio
async def test_database_rejects_missing_event_and_mismatched_attribution(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    binding_id = uuid4()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                session.add(
                    ProjectCompensationAdapterBinding(
                        id=binding_id, project_id=str(project_id), instrument_type="money",
                        adapter_actor_id=str(adapter_id), route_key="adapter.primary",
                        status="active", binding_lifecycle_version=1,
                        created_by=str(actor_id),
                    )
                )

    binding_id = uuid4()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="attribution mismatch"):
            async with session.begin():
                session.add(
                    ProjectCompensationAdapterBinding(
                        id=binding_id, project_id=str(project_id),
                        instrument_type="money", adapter_actor_id=str(adapter_id),
                        route_key="adapter.primary", status="active",
                        binding_lifecycle_version=1, created_by=str(actor_id),
                    )
                )
                await session.flush()
                session.add(
                    CompensationAdapterBindingLifecycleEvent(
                        id=uuid4(), operation_id=uuid4(),
                        request_digest="sha256:" + "0" * 64,
                        project_id=str(project_id), adapter_binding_id=binding_id,
                        event_type="created", actor_profile_id=str(adapter_id),
                        from_status=None, to_status="active",
                        from_lifecycle_version=0, to_lifecycle_version=1,
                    )
                )
                await session.flush()


@pytest.mark.asyncio
async def test_absent_and_unauthorized_reads_are_equally_concealed(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _Authorization()
    async with db_session.get_session_factory()() as session:
        service = _service(session, authorization)
        async with session.begin():
            created = await service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.primary",
                )
            )
        absent_request = AdapterBindingReadRequest(
            actor_profile_id=actor_id, project_id=project_id,
            adapter_binding_id=uuid4(),
        )
        with pytest.raises(AdapterBindingConflict) as absent:
            await service.read(absent_request)
        authorization.read_available = False
        with pytest.raises(AdapterBindingConflict) as unauthorized:
            await service.read(
                AdapterBindingReadRequest(
                    actor_profile_id=actor_id, project_id=project_id,
                    adapter_binding_id=created.adapter_binding_id,
                )
            )
    assert str(absent.value) == str(unauthorized.value) == "compensation_adapter_binding_not_found"


@pytest.mark.asyncio
async def test_tampered_read_selector_denies_before_read_authorization(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, _, actor_id = await binding_seed()
    request = AdapterBindingReadRequest(
        actor_profile_id=actor_id, project_id=project_id, adapter_binding_id=uuid4()
    )
    object.__setattr__(request, "adapter_binding_id", "bad")
    authorization = _Authorization()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(ValueError, match="adapter_binding_id must be a UUID"):
            await _service(session, authorization).read(request)
    assert authorization.read_authorized == 0


@pytest.mark.parametrize("transition", ("suspend", "resume"))
@pytest.mark.asyncio
async def test_concurrent_transition_allows_one_version_advance(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    transition: str,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    setup_auth = _Authorization()
    async with db_session.get_session_factory()() as session:
        service = _service(session, setup_auth)
        async with session.begin():
            created = await service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.primary",
                )
            )
        if transition == "resume":
            async with session.begin():
                await service.suspend(
                    AdapterBindingSuspendRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, adapter_binding_id=created.adapter_binding_id,
                        expected_lifecycle_version=1,
                    )
                )

    async def attempt(operation_id: UUID) -> str:
        authorization = _Authorization()
        async with db_session.get_session_factory()() as session:
            service = _service(session, authorization)
            try:
                async with session.begin():
                    request_type = (
                        AdapterBindingSuspendRequest
                        if transition == "suspend"
                        else AdapterBindingResumeRequest
                    )
                    request = request_type(
                        operation_id=operation_id, actor_profile_id=actor_id,
                        project_id=project_id, adapter_binding_id=created.adapter_binding_id,
                        expected_lifecycle_version=1 if transition == "suspend" else 2,
                    )
                    await getattr(service, transition)(request)
                return "advanced"
            except AdapterBindingConflict:
                return "conflict"

    assert sorted(await asyncio.gather(attempt(uuid4()), attempt(uuid4()))) == [
        "advanced", "conflict"
    ]
    async with db_session.get_session_factory()() as session:
        binding = await session.get(
            ProjectCompensationAdapterBinding, created.adapter_binding_id
        )
        events = (
            await session.scalars(
                select(CompensationAdapterBindingLifecycleEvent).where(
                    CompensationAdapterBindingLifecycleEvent.adapter_binding_id
                    == created.adapter_binding_id
                )
            )
        ).all()
    expected_version = 2 if transition == "suspend" else 3
    assert binding is not None and binding.binding_lifecycle_version == expected_version
    assert len(events) == expected_version
