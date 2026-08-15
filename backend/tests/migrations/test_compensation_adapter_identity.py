"""Focused PostgreSQL contract for migration 0005 adapter identity."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
import asyncpg
import pytest


def _config() -> Config:
    return Config(Path(__file__).resolve().parents[2] / "alembic.ini")


async def _execute(database_url: str, statement: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


async def _snapshot(database_url: str) -> tuple[str, str, str]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        definition = await connection.fetchval(
            "select pg_get_constraintdef(c.oid) from pg_constraint c "
            "join pg_class t on t.oid=c.conrelid where t.relname='actor_profiles' "
            "and c.conname='ck_actor_profiles_kind_service_identity'"
        )
        actor = await connection.fetchval(
            "select row_to_json(p)::text from actor_profiles p "
            "where id='00000000-0000-0000-0000-000000000005'"
        )
        revision = await connection.fetchval("select version_num from alembic_version")
        return definition, actor, revision
    finally:
        await connection.close()


async def _insert_adapter_actor(database_url: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            await connection.execute(
                "insert into actor_profiles "
                "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                "values ('00000000-0000-0000-0000-000000000005','service','active',"
                "'manual_service_provisioning','workstream.compensation.adapter',"
                "'00000000-0000-0000-0000-000000000005')"
            )
            await connection.execute(
                "insert into actor_identity_links "
                "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                "values ('00000000-0000-0000-0000-000000000015',"
                "'00000000-0000-0000-0000-000000000005','workstream.internal',"
                "'workstream.compensation.adapter','service','active',"
                "'workstream:system:bootstrap')"
            )
    finally:
        await connection.close()


def test_0005_accepts_only_the_closed_adapter_identity(
    isolated_database_env: str, migration_lock
) -> None:
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(_config(), "0005_compensation_adapter_identity")
        asyncio.run(_insert_adapter_actor(isolated_database_env))
        with pytest.raises(asyncpg.CheckViolationError):
            asyncio.run(
                _execute(
                    isolated_database_env,
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,service_identity,created_by) values "
                    "('00000000-0000-0000-0000-000000000006','service','active',"
                    "'manual_service_provisioning','workstream.compensation.unknown',"
                    "'00000000-0000-0000-0000-000000000005')",
                )
            )


def test_0005_downgrade_refuses_without_mutating_referenced_identity(
    isolated_database_env: str, migration_lock
) -> None:
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(_config(), "0005_compensation_adapter_identity")
        asyncio.run(_insert_adapter_actor(isolated_database_env))
        before = asyncio.run(_snapshot(isolated_database_env))
        with pytest.raises(RuntimeError, match="cannot be downgraded"):
            command.downgrade(_config(), "0004_compensation_adapter_binding_lifecycle")
        assert asyncio.run(_snapshot(isolated_database_env)) == before
