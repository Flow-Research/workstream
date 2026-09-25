"""Add exact task read evidence pairs without rewriting previous authority."""
import asyncio

import asyncpg
from alembic import command
import pytest

from tests.migration_fixtures import _config as config
from tests.migrations.test_task_queue_authority import insert, CONSTRAINT

pytestmark = pytest.mark.postgres_schema_contract
PAIRS = (
    ("project.task.locked_context.read", "project.task.manage"),
    ("operations.task.locked_context.read", "operations.status.read"),
    ("audit.task.locked_context.read", "audit.read"),
)


def test_task_context_migration(isolated_database_env, migration_lock):
    with migration_lock():
        async def reset():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                await connection.execute("drop schema public cascade; create schema public")
            finally:
                await connection.close()
        asyncio.run(reset())
        command.upgrade(config(), "0003_task_read_authority")
        async def seed():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                await insert(connection, "project.read", "project.read")
                await insert(connection, "task.queue.read", "task.queue.read")
                for action, permission in (
                    ("task.read", "task.queue.read"),
                    ("task.submission_requirements.read", "task.queue.read"),
                    ("project.task.read", "project.task.manage"),
                    ("project.task.submission_requirements.read", "project.task.manage"),
                ):
                    for allowed in (False, True):
                        await insert(connection, action, permission, allowed=allowed)
            finally:
                await connection.close()
        async def snapshot():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                return await connection.fetch("select to_jsonb(a)::text as value from audit_events a order by id")
            finally:
                await connection.close()
        asyncio.run(seed())
        before = asyncio.run(snapshot())
        command.upgrade(config(), "0004_task_context_authority")
        assert asyncio.run(snapshot()) == before
        command.upgrade(config(), "head")
        assert asyncio.run(snapshot()) == before


@pytest.mark.parametrize("remove_guard", [False, True])
def test_task_context_migration_exact_pairs(isolated_database_env, migration_lock, remove_guard):
    with migration_lock():
        async def probe():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                if remove_guard:
                    await connection.execute(f"alter table audit_events drop constraint {CONSTRAINT}")
                for action,permission in PAIRS:
                    for allowed in (False,True):
                        assert await insert(connection, action, permission, allowed=allowed)
                        with pytest.raises(asyncpg.CheckViolationError) as error:
                            await insert(connection, action, "project.read", allowed=allowed)
                        assert error.value.constraint_name == CONSTRAINT
            finally:
                await connection.close()
        if remove_guard:
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                asyncio.run(probe())
        else:
            asyncio.run(probe())
