"""Focused PostgreSQL proof for compensation adapter-binding persistence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
import pytest
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.compensation.models import ProjectCompensationAdapterBinding
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


async def _seed_binding_facts() -> tuple[str, str, str]:
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
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    # Neutral FK fixture only; CP03 owns the exact service identity.
                    created_by=creator_id,
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
                    subject_kind="human",
                    status="active",
                    linked_by=creator_id,
                    last_verified_at=now,
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


@pytest.mark.parametrize("status", ("suspended", "retired"))
@pytest.mark.asyncio
async def test_database_rejects_invalid_lifecycle_shape(
    compensation_database_env: str,
    status: str,
) -> None:
    project_id, actor_id, creator_id = await _seed_binding_facts()
    async with db_session.get_session_factory()() as session:
        values = _binding_input(project_id, actor_id, creator_id).model_dump()
        values["instrument_type"] = "money"
        now = datetime.now(UTC)
        session.add(
            ProjectCompensationAdapterBinding(
                **values,
                status=status,
                binding_lifecycle_version=1 if status == "suspended" else 2,
                suspended_by=creator_id if status == "suspended" else None,
                suspended_at=now if status == "suspended" else None,
                retired_by=creator_id if status == "retired" else None,
                retired_at=now if status == "retired" else None,
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_database_rejects_noncanonical_route_keys(
    compensation_database_env: str,
) -> None:
    project_id, actor_id, creator_id = await _seed_binding_facts()
    invalid_values = (
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
    )
    async with db_session.get_session_factory()() as session:
        for route_key in invalid_values:
            facts = _binding_input(project_id, actor_id, creator_id).model_dump()
            facts["instrument_type"] = "money"
            facts["route_key"] = route_key
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    session.add(
                        ProjectCompensationAdapterBinding(
                            **facts,
                            status="active",
                            binding_lifecycle_version=1,
                        )
                    )
                    await session.flush()
