"""The acceptance foundation preserves retained Review and artifact sources."""

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.checkers.execution.historical_execution import historical_completed_source
from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.reviews.acceptance.historical_support import historical_acceptance_source
from tests.reviews.decision.test_migration import snapshot as source_snapshot

pytestmark = pytest.mark.postgres_schema_contract


async def snapshot(connection):
    retained = await source_snapshot(connection)
    for table in ("reviews", "review_findings", "finding_resolutions", "review_decision_requests"):
        retained[table] = await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY 1"
        )
    return retained


async def test_acceptance_upgrade_preserves_owners(tmp_path, isolated_database_env, migration_lock):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0013_review_source")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_acceptance_source(
            tmp_path, isolated_database_env, completed_source_factory=historical_completed_source
        ):
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert len(before["reviews"]) == 1
                assert (
                    await connection.fetchval("SELECT to_regclass('public.final_acceptances')")
                    is None
                )
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0014_final_acceptance")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert (
                    await connection.fetchval("SELECT count(*) FROM public.final_acceptances") == 0
                )
                assert (
                    await connection.fetchval("SELECT version_num FROM alembic_version")
                    == "0014_final_acceptance"
                )
            finally:
                await connection.close()
            with pytest.raises(
                RuntimeError,
                match="Workstream v0.1 migrations cannot be downgraded; recreate the database",
            ):
                await asyncio.to_thread(command.downgrade, _config(), "0013_review_source")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert (
                    await connection.fetchval("SELECT version_num FROM alembic_version")
                    == "0014_final_acceptance"
                )
            finally:
                await connection.close()
