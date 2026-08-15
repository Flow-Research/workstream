"""Direct PostgreSQL negative matrix for adapter-binding lifecycle custody."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.compensation.api import (
    AdapterBindingCreateRequest,
    AdapterBindingSuspendRequest,
)
from app.modules.compensation.models import (
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)
from adapter_binding_fixtures import BindingSeed
from adapter_binding_test_support import Authorization, service

pytest_plugins = ("adapter_binding_fixtures",)


async def _create_and_suspend(
    project_id: UUID, adapter_id: UUID, actor_id: UUID, route_key: str
) -> tuple[UUID, UUID]:
    authorization = Authorization()
    async with db_session.get_session_factory()() as session:
        binding_service = service(session, authorization)
        async with session.begin():
            created = await binding_service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key=route_key,
                )
            )
        async with session.begin():
            suspended = await binding_service.suspend(
                AdapterBindingSuspendRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, adapter_binding_id=created.adapter_binding_id,
                    expected_lifecycle_version=1,
                )
            )
    return created.adapter_binding_id, suspended.event_id


@pytest.mark.parametrize(
    "changes",
    (
        {"status": "active", "binding_lifecycle_version": 2},
        {
            "status": "suspended", "binding_lifecycle_version": 3,
            "suspended_by": "actor", "suspended_at": datetime.now(UTC),
        },
        {"status": "retired", "binding_lifecycle_version": 2},
        {"project_id": "replacement"},
        {"instrument_type": "project_points"},
        {"adapter_actor_id": "actor"},
        {"created_by": "adapter"},
        {"route_key": "adapter.changed"},
        {"id": "replacement"},
        {"created_at": datetime.now(UTC)},
        {"retired_by": "actor"},
        {"retired_at": datetime.now(UTC)},
    ),
)
@pytest.mark.asyncio
async def test_database_rejects_active_same_state_skip_retired_and_identity_changes(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    changes: dict[str, object],
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = Authorization()
    async with db_session.get_session_factory()() as session:
        binding_service = service(session, authorization)
        async with session.begin():
            created = await binding_service.create(
                AdapterBindingCreateRequest(
                    operation_id=uuid4(), actor_profile_id=actor_id,
                    project_id=project_id, instrument_type="money",
                    adapter_actor_id=adapter_id, route_key="adapter.primary",
                )
            )
        resolved = {
            key: (
                str(actor_id) if value == "actor"
                else str(adapter_id) if value == "adapter"
                else str(uuid4()) if value == "replacement"
                else value
            )
            for key, value in changes.items()
        }
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    update(ProjectCompensationAdapterBinding)
                    .where(ProjectCompensationAdapterBinding.id == created.adapter_binding_id)
                    .values(**resolved)
                )


@pytest.mark.asyncio
async def test_database_rejects_suspended_to_suspended_transition(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    binding_id, _ = await _create_and_suspend(
        project_id, adapter_id, actor_id, "adapter.primary"
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    update(ProjectCompensationAdapterBinding)
                    .where(ProjectCompensationAdapterBinding.id == binding_id)
                    .values(binding_lifecycle_version=3)
                )


@pytest.mark.parametrize("prior_case", ("missing", "cross_binding", "forged_actor"))
@pytest.mark.asyncio
async def test_database_rejects_invalid_resume_lineage_or_attribution(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    prior_case: str,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    first_id, first_suspension_id = await _create_and_suspend(
        project_id, adapter_id, actor_id, "adapter.first"
    )
    binding_id, suspension_id = first_id, first_suspension_id
    if prior_case == "cross_binding":
        binding_id, _ = await _create_and_suspend(
            project_id, adapter_id, actor_id, "adapter.second"
        )
        assert binding_id != first_id
        suspension_id = first_suspension_id
    elif prior_case == "missing":
        suspension_id = uuid4()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    update(ProjectCompensationAdapterBinding)
                    .where(ProjectCompensationAdapterBinding.id == binding_id)
                    .values(
                        status="active", binding_lifecycle_version=3,
                        suspended_by=None, suspended_at=None,
                        resumed_by=str(actor_id),
                    )
                )
                session.add(
                    CompensationAdapterBindingLifecycleEvent(
                        id=uuid4(), operation_id=uuid4(),
                        request_digest="sha256:" + "0" * 64,
                        project_id=str(project_id), adapter_binding_id=binding_id,
                        event_type="resumed",
                        actor_profile_id=str(
                            adapter_id if prior_case == "forged_actor" else actor_id
                        ),
                        from_status="suspended", to_status="active",
                        from_lifecycle_version=2, to_lifecycle_version=3,
                        prior_suspension_event_id=suspension_id,
                    )
                )
                await session.flush()
        binding = await session.scalar(
            select(ProjectCompensationAdapterBinding).where(
                ProjectCompensationAdapterBinding.id == binding_id
            )
        )
        assert binding is not None
        assert (
            binding.status, binding.binding_lifecycle_version,
            binding.resumed_by, binding.resumed_at,
        ) == ("suspended", 2, None, None)


@pytest.mark.parametrize("mutation", ("update", "delete", "truncate"))
@pytest.mark.asyncio
async def test_database_rejects_every_lifecycle_event_mutation(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    mutation: str,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    await _create_and_suspend(project_id, adapter_id, actor_id, "adapter.primary")
    statement = {
        "update": update(CompensationAdapterBindingLifecycleEvent).values(
            request_digest="sha256:" + "1" * 64
        ),
        "delete": delete(CompensationAdapterBindingLifecycleEvent),
        "truncate": text("truncate compensation_adapter_binding_lifecycle_events"),
    }[mutation]
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(statement)
