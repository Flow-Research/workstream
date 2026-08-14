"""Shared isolated PostgreSQL fixtures for compensation adapter-binding tests."""

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.core.config import get_settings
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from project_create_fixtures import insert_historical_project

BindingSeed = Callable[[], Awaitable[tuple[UUID, UUID, UUID]]]


async def seed_nonempty_0003_adapter_binding(database_url: str) -> None:
    """Seed one FK-valid legacy binding without disabling system triggers."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,created_by) values "
            "('00000000-0000-0000-0000-000000000003','service','active',"
            "'manual_service_provisioning','00000000-0000-0000-0000-000000000003'); "
            "insert into actor_identity_links "
            "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) values "
            "('00000000-0000-0000-0000-000000000004',"
            "'00000000-0000-0000-0000-000000000003','https://migration.test',"
            "'adapter-preflight','service','active',"
            "'00000000-0000-0000-0000-000000000003'); "
            "alter table projects disable trigger project_creation_custody; "
            "insert into projects (id,name,slug,status) values "
            "('00000000-0000-0000-0000-000000000002','Migration preflight',"
            "'migration-preflight','draft'); "
            "alter table projects enable trigger project_creation_custody; "
            "alter table project_compensation_adapter_bindings disable trigger "
            "project_compensation_binding_update_guard; "
            "insert into project_compensation_adapter_bindings "
            "(id,project_id,instrument_type,adapter_actor_id,route_key,created_by) values "
            "('00000000-0000-0000-0000-000000000001',"
            "'00000000-0000-0000-0000-000000000002','money',"
            "'00000000-0000-0000-0000-000000000003','adapter.primary',"
            "'00000000-0000-0000-0000-000000000003'); "
            "alter table project_compensation_adapter_bindings enable trigger "
            "project_compensation_binding_update_guard"
        )
    finally:
        await connection.close()


@pytest.fixture
def compensation_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    yield clean_postgres_database
    get_settings.cache_clear()


@pytest.fixture
def binding_seed() -> BindingSeed:
    async def seed() -> tuple[UUID, UUID, UUID]:
        project_id, adapter_id, actor_id = uuid4(), uuid4(), uuid4()
        async with db_session.get_session_factory()() as session:
            session.add_all(
                (
                    ActorProfile(
                        id=str(actor_id), actor_kind="human", status="active",
                        provisioning_method="automatic_first_access", created_by=str(actor_id),
                    ),
                    ActorProfile(
                        id=str(adapter_id), actor_kind="human", status="active",
                        provisioning_method="automatic_first_access",
                        # Neutral FK row only. The separate CP02 marker simulates
                        # the future ACTORS-owned positive eligibility decision.
                        created_by=str(actor_id),
                    ),
                )
            )
            await session.flush()
            session.add_all(
                (
                    ActorIdentityLink(
                        id=str(uuid4()), actor_profile_id=str(actor_id),
                        issuer="https://compensation.test", subject=f"creator-{actor_id}",
                        subject_kind="human", status="active", linked_by=str(actor_id),
                        last_verified_at=datetime.now(UTC),
                    ),
                    ActorIdentityLink(
                        id=str(uuid4()), actor_profile_id=str(adapter_id),
                        issuer="https://compensation.test", subject=f"adapter-{adapter_id}",
                        subject_kind="human", status="active", linked_by=str(actor_id),
                    ),
                )
            )
            await insert_historical_project(
                session, project_id=str(project_id), name="Compensation project",
                slug=f"compensation-{str(project_id)[:8]}",
            )
            await session.commit()
        return project_id, adapter_id, actor_id

    return seed
