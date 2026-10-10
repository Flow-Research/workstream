"""Current PostgreSQL proof for the closed service-identity vocabulary."""

import asyncio
import re

import asyncpg
import pytest

from app.core.identifiers import new_record_id
from app.modules.actors.api import SERVICE_IDENTITY_VALUES
from app.modules.actors.models import ActorProfile


pytestmark = pytest.mark.postgres_schema_contract
FIXED_IDENTITIES = (
    "workstream.task.post_submit_router",
    "workstream.compensation.adapter",
    "workstream.outbox.dispatcher",
    "workstream.task.assignment_reconciler",
)
IDENTITY_PATTERN = r"workstream\.[a-z_]+\.[a-z_]+"


async def _constraint_definition(database_url: str) -> str:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return await connection.fetchval(
            "select pg_get_constraintdef(c.oid) from pg_constraint c "
            "where c.conrelid='actor_profiles'::regclass "
            "and c.conname='ck_actor_profiles_kind_service_identity'"
        )
    finally:
        await connection.close()


async def _insert_service(database_url: str, identity: str) -> str:
    actor_id = str(new_record_id())
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            await connection.execute(
                "insert into actor_profiles "
                "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                "values($1,'service','active','manual_service_provisioning',$2,$3)",
                actor_id,
                identity,
                actor_id,
            )
            await connection.execute(
                "insert into actor_identity_links "
                "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                "values($1,$2,'workstream.internal',$3,'service','active',"
                "'workstream:system:bootstrap')",
                str(new_record_id()),
                actor_id,
                identity,
            )
        return actor_id
    finally:
        await connection.close()


def test_database_and_model_expose_the_exact_service_identity_vocabulary(
    isolated_database_env: str,
) -> None:
    database_definition = asyncio.run(_constraint_definition(isolated_database_env))
    model_constraint = next(
        constraint
        for constraint in ActorProfile.__table__.constraints
        if constraint.name == "ck_actor_profiles_kind_service_identity"
    )
    expected = set(SERVICE_IDENTITY_VALUES)
    assert set(re.findall(IDENTITY_PATTERN, database_definition)) == expected
    assert set(re.findall(IDENTITY_PATTERN, str(model_constraint.sqltext))) == expected


def test_fixed_service_identities_accept_once_and_reject_unknown_or_duplicate(
    isolated_database_env: str,
) -> None:
    for identity in FIXED_IDENTITIES:
        asyncio.run(_insert_service(isolated_database_env, identity))

    with pytest.raises(asyncpg.CheckViolationError) as unknown:
        asyncio.run(_insert_service(isolated_database_env, "workstream.outbox.unknown"))
    assert unknown.value.constraint_name == "ck_actor_profiles_kind_service_identity"

    with pytest.raises(asyncpg.UniqueViolationError) as duplicate:
        asyncio.run(_insert_service(isolated_database_env, FIXED_IDENTITIES[1]))
    assert duplicate.value.constraint_name == "service_identity"


def test_router_vocabulary_upgrade_preserves_rows_without_provisioning(
    isolated_database_env, migration_lock,
):
    from alembic import command
    from app.db import session as db_session
    from tests.migration_fixtures import _config

    async def reset():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()

    async def snapshot():
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            rows = []
            for table in ("actor_profiles", "actor_identity_links", "audit_events"):
                rows.append(tuple(await connection.fetch(
                    f"select to_jsonb(t)::text from public.{table} t order by id"
                )))
            return tuple(rows)
        finally:
            await connection.close()

    with migration_lock():
        asyncio.run(reset())
        command.upgrade(_config(), "0016_review_lifecycle_fence")
        asyncio.run(_insert_service(isolated_database_env, "workstream.outbox.dispatcher"))
        before = asyncio.run(snapshot())
        assert before[0] and before[1]
        command.upgrade(_config(), "0017_acceptance_source_contracts")
        assert asyncio.run(snapshot()) == before
        assert "workstream.task.post_submit_router" in asyncio.run(_constraint_definition(isolated_database_env))
        asyncio.run(_insert_service(isolated_database_env, "workstream.task.post_submit_router"))
