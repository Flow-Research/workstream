"""Additive Review storage preserves populated canonical evidence."""

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.checkers.execution.historical_execution import historical_completed_source
from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.reviews.decision.support import review_source

pytestmark = pytest.mark.postgres_schema_contract


async def snapshot(connection):
    return {
        table: await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY 1"
        )
        for table in (
            "submissions",
            "checker_runs",
            "checker_results",
            "artifact_bindings",
            "artifact_contents",
            "review_queue_entries",
            "review_leases",
            "review_packet_manifests",
            "review_packet_guide_items",
        )
    }


async def test_review_upgrade_preserves_owners(tmp_path, isolated_database_env, migration_lock):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0012_review_packet")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with review_source(
            tmp_path, isolated_database_env, completed_source_factory=historical_completed_source
        ):
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert await connection.fetchval("SELECT to_regclass('public.reviews')") is None
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0013_review_source")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                for table in (
                    "reviews",
                    "review_findings",
                    "finding_resolutions",
                    "review_decision_requests",
                ):
                    assert await connection.fetchval(f"SELECT count(*) FROM public.{table}") == 0
                assert (
                    await connection.fetchval("SELECT version_num FROM alembic_version")
                    == "0013_review_source"
                )
            finally:
                await connection.close()
            with pytest.raises(
                RuntimeError,
                match="Workstream v0.1 migrations cannot be downgraded; recreate the database",
            ):
                await asyncio.to_thread(command.downgrade, _config(), "0012_review_packet")
