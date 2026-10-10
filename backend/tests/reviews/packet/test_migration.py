"""Populated predecessor upgrade preserves canonical owners without inventing packets."""

import asyncio
from uuid import uuid4

import asyncpg
import pytest
from alembic import command

from tests.checkers.execution.historical_execution import historical_completed_source
from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.migration_fixtures import current_schema_revision
from tests.reviews.packet.support import packet_source

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
            "guide_source_artifact_ingests",
            "project_guides",
            "guide_source_snapshot_items",
            "review_queue_entries",
            "review_leases",
        )
    }


async def test_packet_upgrade_preserves_existing_owners(
    tmp_path, isolated_database_env, migration_lock
):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0011_task_routing_source")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with packet_source(
            tmp_path, isolated_database_env, completed_source_factory=historical_completed_source
        ):
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass('public.review_packet_manifests')"
                    )
                    is None
                )
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0012_review_packet")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert (
                    await connection.fetchval("SELECT count(*) FROM public.review_packet_manifests")
                    == 0
                )
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM public.review_packet_guide_items"
                    )
                    == 0
                )
            finally:
                await connection.close()


async def test_markdown_media_upgrade_changes_only_the_closed_packet_check(
    isolated_database_env, migration_lock
):
    url = isolated_database_env.replace("+asyncpg", "")
    insert = (
        "INSERT INTO public.review_packet_guide_items "
        "(packet_id,source_item_id,ingest_id,item_order,logical_role,media_type) "
        "VALUES ($1,$2,$3,0,'guide_source_original',$4)"
    )
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0026_task_guide_read")
        connection = await asyncpg.connect(url)
        try:
            selectors = tuple(uuid4() for _ in range(3))
            with pytest.raises(asyncpg.CheckViolationError) as predecessor:
                await connection.execute(insert, *selectors, "text/markdown")
            assert predecessor.value.constraint_name == (
                "ck_review_packet_guide_items_guide_media"
            )
        finally:
            await connection.close()

        await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
        connection = await asyncpg.connect(url)
        try:
            with pytest.raises(asyncpg.ForeignKeyViolationError) as accepted_media:
                await connection.execute(insert, *selectors, "text/markdown")
            assert accepted_media.value.constraint_name.startswith(
                "fk_review_packet_guide_items_"
            )
            with pytest.raises(asyncpg.CheckViolationError) as unsupported_media:
                await connection.execute(insert, *selectors, "text/html")
            assert unsupported_media.value.constraint_name == (
                "ck_review_packet_guide_items_guide_media"
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM public.review_packet_guide_items"
                )
                == 0
            )
        finally:
            await connection.close()
