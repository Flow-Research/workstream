"""Focused PostgreSQL proof for compensation adapter-binding persistence."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.compensation.repository import (
    CompensationAdapterActorInvalid,
    CompensationBindingRepository,
)
from app.modules.compensation.schemas import (
    CompensationInstrumentType,
    ProjectCompensationAdapterBindingInput,
)
from project_create_fixtures import insert_historical_project


@pytest.fixture
def compensation_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    """Bind compensation tests to a runner-owned isolated PostgreSQL database."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


async def _seed_binding_facts(
    *,
    profile_status: str = "active",
    link_status: str = "active",
    actor_kind: str = "service",
    service_identity: str | None = ServiceIdentity.ARTIFACT_VERIFIER.value,
) -> tuple[str, str, str]:
    project_id = str(uuid4())
    adapter_actor_id = str(uuid4())
    creator_id = str(uuid4())
    now = datetime.now(UTC)
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=creator_id,
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=creator_id,
                ),
                ActorProfile(
                    id=adapter_actor_id,
                    actor_kind=actor_kind,
                    status=profile_status,
                    provisioning_method=(
                        "manual_service_provisioning"
                        if actor_kind == "service"
                        else "automatic_first_access"
                    ),
                    service_identity=service_identity if actor_kind == "service" else None,
                    created_by=creator_id,
                    suspended_by=creator_id if profile_status == "suspended" else None,
                    suspended_at=now if profile_status == "suspended" else None,
                    suspension_reason="test suspension" if profile_status == "suspended" else None,
                    deactivated_by=creator_id if profile_status == "deactivated" else None,
                    deactivated_at=now if profile_status == "deactivated" else None,
                    deactivation_reason=(
                        "test deactivation" if profile_status == "deactivated" else None
                    ),
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=creator_id,
                    issuer="https://compensation.test",
                    subject=f"creator-{creator_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=creator_id,
                    last_verified_at=now,
                ),
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=adapter_actor_id,
                    issuer="https://compensation.test",
                    subject=f"adapter-{adapter_actor_id}",
                    subject_kind=actor_kind,
                    status=link_status,
                    linked_by=creator_id,
                    last_verified_at=now if actor_kind == "human" else None,
                    revoked_by=creator_id if link_status == "revoked" else None,
                    revoked_at=now if link_status == "revoked" else None,
                    revoked_reason="test revocation" if link_status == "revoked" else None,
                ),
            ]
        )
        await insert_historical_project(
            session,
            project_id=project_id,
            name="Compensation project",
            slug=f"compensation-{project_id[:8]}",
        )
        await session.commit()
    return project_id, adapter_actor_id, creator_id


def _binding_input(
    project_id: str,
    adapter_actor_id: str,
    creator_id: str,
    *,
    route_key: str = "adapter.primary",
) -> ProjectCompensationAdapterBindingInput:
    return ProjectCompensationAdapterBindingInput(
        id=uuid4(),
        project_id=project_id,
        instrument_type=CompensationInstrumentType.MONEY,
        adapter_actor_id=adapter_actor_id,
        route_key=route_key,
        created_by=creator_id,
    )


def test_binding_model_is_registered_without_secret_or_provider_columns() -> None:
    """Metadata exposes only canonical non-secret binding facts."""
    table = Base.metadata.tables["project_compensation_adapter_bindings"]
    assert set(table.columns.keys()) == {
        "id",
        "project_id",
        "instrument_type",
        "adapter_actor_id",
        "route_key",
        "status",
        "binding_lifecycle_version",
        "created_by",
        "created_at",
        "suspended_by",
        "suspended_at",
        "retired_by",
        "retired_at",
    }
    assert {"credential", "token", "endpoint", "provider_reference"}.isdisjoint(table.columns)
    assert "ck_project_compensation_adapter_bindings_route_key_no_traversal" in {
        constraint.name for constraint in table.constraints
    }


@pytest.mark.parametrize(
    "route_key",
    (
        "",
        "1adapter",
        "adapter/path",
        "https://provider",
        "adapter key",
        "adapter@key",
        "adapter?key",
        "adapter..secret",
        "adapter\nkey",
        "ü",
        "a" * 121,
    ),
)
def test_binding_input_rejects_noncanonical_route_keys(route_key: str) -> None:
    with pytest.raises(ValidationError):
        _binding_input(str(uuid4()), str(uuid4()), str(uuid4()), route_key=route_key)


def test_binding_input_rejects_secret_or_provider_fields() -> None:
    values = _binding_input(str(uuid4()), str(uuid4()), str(uuid4())).model_dump()
    for field in ("credential", "token", "endpoint", "provider_reference"):
        with pytest.raises(ValidationError):
            ProjectCompensationAdapterBindingInput.model_validate(values | {field: "secret"})


@pytest.mark.asyncio
async def test_repository_creates_only_active_exact_service_binding(
    compensation_database_env: str,
) -> None:
    project_id, actor_id, creator_id = await _seed_binding_facts()
    value = _binding_input(project_id, actor_id, creator_id)
    async with db_session.get_session_factory()() as session:
        binding = await CompensationBindingRepository(session).add_binding(
            value,
            expected_service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
        )
        assert binding.status == "active"
        assert binding.binding_lifecycle_version == 1
        assert binding.suspended_at is binding.retired_at is None
        await session.commit()

    async with db_session.get_session_factory()() as session:
        stored = await session.get(ProjectCompensationAdapterBinding, value.id)
        assert stored is not None
        assert stored.route_key == "adapter.primary"


@pytest.mark.parametrize(
    ("profile_status", "link_status", "actor_kind", "expected_identity"),
    (
        ("suspended", "active", "service", ServiceIdentity.ARTIFACT_VERIFIER),
        ("deactivated", "active", "service", ServiceIdentity.ARTIFACT_VERIFIER),
        ("active", "revoked", "service", ServiceIdentity.ARTIFACT_VERIFIER),
        ("active", "active", "human", ServiceIdentity.ARTIFACT_VERIFIER),
        ("active", "active", "service", ServiceIdentity.ARTIFACT_SCHEDULER),
    ),
)
@pytest.mark.asyncio
async def test_repository_rejects_invalid_or_mismatched_adapter_actor(
    compensation_database_env: str,
    profile_status: str,
    link_status: str,
    actor_kind: str,
    expected_identity: ServiceIdentity,
) -> None:
    identity = ServiceIdentity.ARTIFACT_VERIFIER.value if actor_kind == "service" else None
    project_id, actor_id, creator_id = await _seed_binding_facts(
        profile_status=profile_status,
        link_status=link_status,
        actor_kind=actor_kind,
        service_identity=identity,
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            CompensationAdapterActorInvalid,
            match="compensation_adapter_actor_invalid",
        ):
            await CompensationBindingRepository(session).add_binding(
                _binding_input(project_id, actor_id, creator_id),
                expected_service_identity=expected_identity,
            )


@pytest.mark.asyncio
async def test_repository_rejects_missing_adapter_identity(
    compensation_database_env: str,
) -> None:
    project_id, _, creator_id = await _seed_binding_facts()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            CompensationAdapterActorInvalid,
            match="compensation_adapter_actor_invalid",
        ):
            await CompensationBindingRepository(session).add_binding(
                _binding_input(project_id, str(uuid4()), creator_id),
                expected_service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            )


@pytest.mark.asyncio
async def test_database_rejects_invalid_lifecycle_shape(
    compensation_database_env: str,
) -> None:
    project_id, actor_id, creator_id = await _seed_binding_facts()
    async with db_session.get_session_factory()() as session:
        values = _binding_input(project_id, actor_id, creator_id).model_dump()
        values["instrument_type"] = "money"
        session.add(
            ProjectCompensationAdapterBinding(
                **values,
                status="retired",
                binding_lifecycle_version=1,
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_database_enforces_lifecycle_transition_version_and_immutable_identity(
    compensation_database_env: str,
) -> None:
    project_id, actor_id, creator_id = await _seed_binding_facts()
    value = _binding_input(project_id, actor_id, creator_id)
    async with db_session.get_session_factory()() as session:
        await CompensationBindingRepository(session).add_binding(
            value,
            expected_service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
        )
        await session.commit()

    now = datetime.now(UTC)
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(ProjectCompensationAdapterBinding)
            .where(ProjectCompensationAdapterBinding.id == value.id)
            .values(
                status="suspended",
                binding_lifecycle_version=2,
                suspended_by=creator_id,
                suspended_at=now,
            )
        )
        await session.commit()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ProjectCompensationAdapterBinding)
                .where(ProjectCompensationAdapterBinding.id == value.id)
                .values(route_key="adapter.changed")
            )

    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ProjectCompensationAdapterBinding)
                .where(ProjectCompensationAdapterBinding.id == value.id)
                .values(suspended_at=now + timedelta(seconds=1))
            )


@pytest.mark.asyncio
async def test_active_binding_duplicate_race_has_one_winner(
    compensation_database_env: str,
) -> None:
    project_id, actor_id, creator_id = await _seed_binding_facts()

    async def create(route_key: str) -> str:
        async with db_session.get_session_factory()() as session:
            try:
                await CompensationBindingRepository(session).add_binding(
                    _binding_input(project_id, actor_id, creator_id, route_key=route_key),
                    expected_service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                )
                await session.commit()
                return "created"
            except IntegrityError:
                await session.rollback()
                return "conflict"

    assert sorted(await asyncio.gather(create("adapter.one"), create("adapter.two"))) == [
        "conflict",
        "created",
    ]
    async with db_session.get_session_factory()() as session:
        rows = (await session.scalars(select(ProjectCompensationAdapterBinding))).all()
        assert len(rows) == 1


@pytest.mark.postgres_schema_contract
def test_0052_binding_migration_round_trip(
    compensation_database_env: str,
) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "alembic"),
    )
    command.downgrade(config, "0051_review_queue_foundation")

    async def table_names() -> set[str]:
        engine = create_async_engine(compensation_database_env)
        try:
            async with engine.connect() as connection:
                return set(
                    await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                )
        finally:
            await engine.dispose()

    assert "project_compensation_adapter_bindings" not in asyncio.run(table_names())
    command.upgrade(config, "0052_compensation_bindings")
    assert "project_compensation_adapter_bindings" in asyncio.run(table_names())
