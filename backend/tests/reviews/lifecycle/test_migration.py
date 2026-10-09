"""Disabled controller installation preserves populated contribution sources."""

import asyncio
from uuid import UUID

import asyncpg
import pytest
from alembic import command

from tests.historical_submission_fixtures import historical_material_fixture
from app.db import session as db_session
from tests.contributions.records.support import (
    award_values,
    contribution_source,
    insert_award,
    insert_record,
)
from tests.contributions.records.test_migration import snapshot as source_snapshot
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config

pytestmark = pytest.mark.postgres_schema_contract


async def snapshot(connection):
    retained = await source_snapshot(connection)
    for table in ("contribution_records", "compensation_awards"):
        retained[table] = await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY 1"
        )
    return retained


async def test_lifecycle_upgrade_preserves_sources(tmp_path, isolated_database_env, migration_lock):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0015_contribution_awards")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with contribution_source(tmp_path, isolated_database_env, paid=True, material_source=historical_material_fixture) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            async with h.factory() as session:
                for record in (h.reviewer_record, h.submitter_record):
                    await insert_record(session, record)
                    for values in await award_values(session, record):
                        await insert_award(session, values)
                await session.commit()
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert len(before["contribution_records"]) == 2
                assert len(before["compensation_awards"]) == 4
                lower_time = await connection.fetchval("SELECT clock_timestamp()")
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass('public.joint_lifecycle_release_control')"
                    )
                    is None
                )
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0016_review_lifecycle_fence")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                rows = await connection.fetch(
                    "SELECT * FROM public.joint_lifecycle_release_control"
                )
                assert len(rows) == 1
                row = dict(rows[0])
                assert UUID(str(row["id"])).version == 7
                assert row["singleton"] is True
                assert row["phase"] == "disabled" and row["generation"] == 0
                assert (
                    lower_time
                    <= row["created_at"]
                    <= await connection.fetchval("SELECT clock_timestamp()")
                )
            finally:
                await connection.close()
            with pytest.raises(
                RuntimeError,
                match="Workstream v0.1 migrations cannot be downgraded; recreate the database",
            ):
                await asyncio.to_thread(command.downgrade, _config(), "0015_contribution_awards")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert (
                    dict(
                        await connection.fetchrow(
                            "SELECT * FROM public.joint_lifecycle_release_control"
                        )
                    )
                    == row
                )
                assert (
                    await connection.fetchval("SELECT version_num FROM public.alembic_version")
                    == "0016_review_lifecycle_fence"
                )
            finally:
                await connection.close()


async def test_transition_upgrade_preserves_genesis_and_retained_sources(
    tmp_path, isolated_database_env, migration_lock,
):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0027_markdown_guide_media")
        async with contribution_source(
            tmp_path, isolated_database_env, paid=True,
        ):
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                genesis = dict(await connection.fetchrow(
                    "SELECT * FROM public.joint_lifecycle_release_control"
                ))
                await asyncio.to_thread(command.upgrade, _config(), "0028_lifecycle_transitions")
                assert await snapshot(connection) == before
                assert dict(await connection.fetchrow(
                    "SELECT * FROM public.joint_lifecycle_release_control"
                )) == genesis | {"transition_id": None}
                assert await connection.fetchval(
                    "SELECT count(*) FROM public.joint_lifecycle_transitions"
                ) == 0
                with pytest.raises(asyncpg.CheckViolationError, match="transition custody invalid"):
                    await connection.execute(
                        "UPDATE public.joint_lifecycle_release_control SET phase='live',generation=1"
                    )
            finally:
                await connection.close()
