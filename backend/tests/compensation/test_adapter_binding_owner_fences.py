"""PostgreSQL proof for CP03A real owner fences and retained CP02 guards."""

import asyncio

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.actors.api import (
    CompensationAdapterActorEligibilityFacts,
    CompensationAdapterActorUnavailable,
)
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.compensation.api import (
    AdapterBindingCreateRequest,
    AdapterBindingConflict,
    AdapterBindingMutationAuthorizationFacts,
    AdapterBindingResumeRequest,
    AdapterBindingSuspendRequest,
)
from app.modules.compensation.service import AdapterBindingService
from app.modules.compensation.models import (
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)
from app.modules.projects.api import (
    ProjectCompensationBindingEligibilityFacts,
    ProjectCompensationBindingUnavailable,
)
from app.modules.projects.models import Project
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility

BindingSeed = Callable[[], Awaitable[tuple[UUID, UUID, UUID]]]
pytest_plugins = ("adapter_binding_fixtures",)


@dataclass(frozen=True, slots=True)
class _CompensationAdapterEligibilityMarker:
    actor_id: UUID


class _OwnerFences:
    def __init__(self, session, marker: _CompensationAdapterEligibilityMarker) -> None:
        self.session = session
        self.marker = marker

    async def lock_compensation_binding_project(
        self, project_id: UUID
    ) -> ProjectCompensationBindingEligibilityFacts:
        row = await self.session.scalar(
            select(Project).where(Project.id == str(project_id)).with_for_update()
        )
        if row is None or row.status not in {"draft", "active"}:
            raise ProjectCompensationBindingUnavailable("project_unavailable")
        return ProjectCompensationBindingEligibilityFacts(project_id=project_id)

    async def lock_compensation_adapter_actor(
        self, adapter_actor_id: UUID
    ) -> CompensationAdapterActorEligibilityFacts:
        row = await self.session.scalar(
            select(ActorProfile)
            .where(ActorProfile.id == str(adapter_actor_id))
            .with_for_update()
        )
        if (
            row is None
            or row.status != "active"
            or row.service_identity is not None
            or adapter_actor_id != self.marker.actor_id
        ):
            raise CompensationAdapterActorUnavailable("actor_unavailable")
        return CompensationAdapterActorEligibilityFacts(adapter_actor_id=adapter_actor_id)


class _BlockingAuthorization:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.prepared = 0

    async def authorize_adapter_binding_read(self, request) -> None:
        del request

    async def prepare_adapter_binding_mutation(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> object:
        self.prepared += 1
        return facts

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        assert prepared is facts
        self.entered.set()
        await self.release.wait()
        return facts.actor_profile_id

    def close_adapter_binding_mutation(self, prepared: object) -> None:
        del prepared


async def _prepare_suspended(
    project_id: UUID, adapter_id: UUID, actor_id: UUID, *, real_owners: bool = False
) -> UUID:
    authorization = _BlockingAuthorization()
    authorization.release.set()
    async with db_session.get_session_factory()() as session:
        owners = _OwnerFences(session, _CompensationAdapterEligibilityMarker(adapter_id))
        service = AdapterBindingService(
            session, read_authorization=authorization,
            mutation_authorization=authorization,
            projects=ProjectCompensationBindingEligibility(session) if real_owners else owners,
            actors=CompensationAdapterActorEligibility(session) if real_owners else owners,
        )
        async with session.begin():
            created = await service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.primary",
                )
            )
        async with session.begin():
            await service.suspend(
                AdapterBindingSuspendRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, adapter_binding_id=created.adapter_binding_id,
                    expected_lifecycle_version=1,
                )
            )
    return created.adapter_binding_id


async def _make_adapter_target(adapter_id: UUID) -> None:
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            profile = await session.get(ActorProfile, str(adapter_id))
            assert profile is not None
            profile.actor_kind = "service"
            profile.provisioning_method = "manual_service_provisioning"
            profile.service_identity = ServiceIdentity.COMPENSATION_ADAPTER.value
            link = await session.scalar(
                select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == str(adapter_id)
                )
            )
            assert link is not None
            link.subject_kind = "service"


@pytest.mark.parametrize("operation", ("create", "resume"))
@pytest.mark.parametrize("locked_owner", ("project", "actor", "identity_link"))
@pytest.mark.asyncio
async def test_owner_rows_remain_locked_through_protected_mutation(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    operation: str,
    locked_owner: str,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    await _make_adapter_target(adapter_id)
    binding_id = (
        await _prepare_suspended(project_id, adapter_id, actor_id, real_owners=True)
        if operation == "resume"
        else None
    )
    authorization = _BlockingAuthorization()

    async def mutate() -> None:
        async with db_session.get_session_factory()() as session:
            service = AdapterBindingService(
                session, read_authorization=authorization,
                mutation_authorization=authorization,
                projects=ProjectCompensationBindingEligibility(session),
                actors=CompensationAdapterActorEligibility(session),
            )
            async with session.begin():
                if operation == "create":
                    await service.create(
                        AdapterBindingCreateRequest(
                            operation_id=uuid4(), actor_profile_id=actor_id,
                            project_id=project_id, instrument_type="money",
                            adapter_actor_id=adapter_id, route_key="adapter.primary",
                        )
                    )
                else:
                    assert binding_id is not None
                    await service.resume(
                        AdapterBindingResumeRequest(
                            operation_id=uuid4(), actor_profile_id=actor_id,
                            project_id=project_id, adapter_binding_id=binding_id,
                            expected_lifecycle_version=2,
                        )
                    )

    async def eligibility_change() -> None:
        async with db_session.get_session_factory()() as session:
            with pytest.raises(DBAPIError):
                async with session.begin():
                    await session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    if locked_owner == "project":
                        statement = select(Project).where(Project.id == str(project_id))
                    elif locked_owner == "actor":
                        statement = select(ActorProfile).where(ActorProfile.id == str(adapter_id))
                    else:
                        statement = select(ActorIdentityLink).where(
                            ActorIdentityLink.actor_profile_id == str(adapter_id)
                        )
                    await session.scalar(statement.with_for_update())

    mutation = asyncio.create_task(mutate())
    entered = asyncio.create_task(authorization.entered.wait())
    try:
        done, _ = await asyncio.wait(
            {entered, mutation}, timeout=30, return_when=asyncio.FIRST_COMPLETED
        )
        if mutation in done:
            await mutation
            raise AssertionError("mutation completed before authorization")
        assert entered in done, "mutation did not reach authorization"
        await eligibility_change()
        authorization.release.set()
        await mutation
    finally:
        authorization.release.set()
        entered.cancel()
        mutation.cancel()
        with suppress(asyncio.CancelledError):
            await entered
        with suppress(asyncio.CancelledError):
            await mutation


@pytest.mark.parametrize("operation", ("create", "resume"))
@pytest.mark.parametrize("ineligible_owner", ("project", "actor", "identity_link"))
@pytest.mark.asyncio
async def test_committed_owner_ineligibility_denies_before_authorization(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    operation: str,
    ineligible_owner: str,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    await _make_adapter_target(adapter_id)
    binding_id = (
        await _prepare_suspended(project_id, adapter_id, actor_id, real_owners=True)
        if operation == "resume"
        else None
    )
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            if ineligible_owner == "project":
                project = await session.get(Project, str(project_id))
                assert project is not None
                project.status = "closed"
            elif ineligible_owner == "actor":
                actor = await session.get(ActorProfile, str(adapter_id))
                assert actor is not None
                actor.status = "deactivated"
                actor.deactivated_by = str(actor_id)
                actor.deactivated_at = datetime.now(UTC)
                actor.deactivation_reason = "compensation adapter disabled"
            else:
                link = await session.scalar(
                    select(ActorIdentityLink).where(
                        ActorIdentityLink.actor_profile_id == str(adapter_id)
                    )
                )
                assert link is not None
                link.status = "revoked"
                link.revoked_by = str(actor_id)
                link.revoked_at = datetime.now(UTC)
                link.revoked_reason = "compensation adapter credential revoked"

    authorization = _BlockingAuthorization()
    authorization.release.set()
    async with db_session.get_session_factory()() as session:
        service = AdapterBindingService(
            session, read_authorization=authorization,
            mutation_authorization=authorization,
            projects=ProjectCompensationBindingEligibility(session),
            actors=CompensationAdapterActorEligibility(session),
        )
        with pytest.raises(AdapterBindingConflict):
            async with session.begin():
                if operation == "create":
                    await service.create(
                        AdapterBindingCreateRequest(
                            operation_id=uuid4(), actor_profile_id=actor_id,
                            project_id=project_id, instrument_type="money",
                            adapter_actor_id=adapter_id, route_key="adapter.primary",
                        )
                    )
                else:
                    assert binding_id is not None
                    await service.resume(
                        AdapterBindingResumeRequest(
                            operation_id=uuid4(), actor_profile_id=actor_id,
                            project_id=project_id, adapter_binding_id=binding_id,
                            expected_lifecycle_version=2,
                        )
                    )
    assert authorization.prepared == 0
    async with db_session.get_session_factory()() as session:
        binding_count = await session.scalar(
            select(func.count()).select_from(ProjectCompensationAdapterBinding)
        )
        event_count = await session.scalar(
            select(func.count()).select_from(CompensationAdapterBindingLifecycleEvent)
        )
        binding = (
            await session.get(ProjectCompensationAdapterBinding, binding_id)
            if binding_id is not None
            else None
        )
    expected_count = 0 if operation == "create" else 1
    assert binding_count == expected_count and event_count == expected_count * 2
    if binding is not None:
        assert (binding.status, binding.binding_lifecycle_version) == ("suspended", 2)


@pytest.mark.asyncio
async def test_database_rejects_event_changes_and_binding_identity_mutation(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    binding_id = await _prepare_suspended(project_id, adapter_id, actor_id)
    async with db_session.get_session_factory()() as session:
        for statement in (
            update(CompensationAdapterBindingLifecycleEvent).values(request_digest="sha256:" + "1" * 64),
            delete(CompensationAdapterBindingLifecycleEvent),
            update(ProjectCompensationAdapterBinding)
            .where(ProjectCompensationAdapterBinding.id == binding_id)
            .values(route_key="adapter.changed"),
        ):
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    await session.execute(statement)


@pytest.mark.asyncio
async def test_active_replacement_blocks_resume_of_suspended_binding(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    suspended_id = await _prepare_suspended(project_id, adapter_id, actor_id)
    authorization = _BlockingAuthorization()
    authorization.release.set()
    async with db_session.get_session_factory()() as session:
        owners = _OwnerFences(session, _CompensationAdapterEligibilityMarker(adapter_id))
        service = AdapterBindingService(
            session, read_authorization=authorization,
            mutation_authorization=authorization, projects=owners, actors=owners,
        )
        async with session.begin():
            await service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.replacement",
                )
            )
        with pytest.raises(AdapterBindingConflict):
            async with session.begin():
                await service.resume(
                    AdapterBindingResumeRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, adapter_binding_id=suspended_id,
                        expected_lifecycle_version=2,
                    )
                )
    assert authorization.prepared == 1


@pytest.mark.asyncio
async def test_existing_art_service_identity_cannot_substitute_for_cp03_registration(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, _, actor_id = await binding_seed()
    art_actor_id = uuid4()
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            session.add(
                ActorProfile(
                    id=str(art_actor_id), actor_kind="service", status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
                    created_by=str(actor_id),
                )
            )
            await session.flush()
            session.add(
                ActorIdentityLink(
                    id=str(uuid4()), actor_profile_id=str(art_actor_id),
                    issuer="https://compensation.test", subject=f"art-{art_actor_id}",
                    subject_kind="service", status="active", linked_by=str(actor_id),
                )
            )
    authorization = _BlockingAuthorization()
    authorization.release.set()
    async with db_session.get_session_factory()() as session:
        owners = _OwnerFences(
            session, _CompensationAdapterEligibilityMarker(art_actor_id)
        )
        with pytest.raises(AdapterBindingConflict):
            async with session.begin():
                await AdapterBindingService(
                    session, read_authorization=authorization,
                    mutation_authorization=authorization, projects=owners, actors=owners,
                ).create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=art_actor_id, route_key="adapter.primary",
                    )
                )
    assert authorization.prepared == 0


@pytest.mark.asyncio
async def test_unmarked_human_actor_cannot_substitute_for_owner_eligibility(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, _, actor_id = await binding_seed()
    authorization = _BlockingAuthorization()
    authorization.release.set()
    async with db_session.get_session_factory()() as session:
        owners = _OwnerFences(session, _CompensationAdapterEligibilityMarker(uuid4()))
        with pytest.raises(AdapterBindingConflict):
            async with session.begin():
                await AdapterBindingService(
                    session, read_authorization=authorization,
                    mutation_authorization=authorization, projects=owners, actors=owners,
                ).create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=actor_id, route_key="adapter.primary",
                    )
                )
    assert authorization.prepared == 0
