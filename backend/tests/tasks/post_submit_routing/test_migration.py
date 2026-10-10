"""Actual predecessor upgrade proof for the route-neutral TASK source table."""

import asyncio

import asyncpg
import pytest
from alembic import command

from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config

from tests.checkers.execution.historical_execution import historical_completed_source


pytestmark = pytest.mark.postgres_schema_contract


async def _snapshot(connection, h):
    identifiers = {
        "submission": h.request.submission_id,
        "run": h.result.attempt_id,
        "execute": h.source["execute_evidence_id"],
        "finalize": h.source["finalize_evidence_id"],
        "completion": h.source["completion_event_id"],
        "task": h.request.task_id,
        "assignment": h.request.assignment_id,
    }
    return {
        "submission": await connection.fetchval(
            "select to_jsonb(row_value)::text from submissions row_value where id=$1",
            identifiers["submission"],
        ),
        "checker_run": await connection.fetchval(
            "select to_jsonb(row_value)::text from checker_runs row_value where id=$1",
            identifiers["run"],
        ),
        "checker_results": await connection.fetch(
            "select to_jsonb(row_value)::text as value from checker_results row_value "
            "where checker_run_id=$1 order by member_order",
            identifiers["run"],
        ),
        "authority": await connection.fetch(
            "select to_jsonb(row_value)::text as value from audit_events row_value "
            "where id = any($1::uuid[]) order by id",
            [identifiers["execute"], identifiers["finalize"]],
        ),
        "completion": await connection.fetchval(
            "select to_jsonb(row_value)::text from outbox_events row_value where event_id=$1",
            identifiers["completion"],
        ),
        "task": await connection.fetchval(
            "select to_jsonb(row_value)::text from workstream_tasks row_value where id=$1",
            identifiers["task"],
        ),
        "assignment": await connection.fetchval(
            "select to_jsonb(row_value)::text from task_assignments row_value where id=$1",
            identifiers["assignment"],
        ),
        "review_counts": tuple(
            await connection.fetchrow(
                "select "
                "(select count(*) from review_queue_entries),"
                "(select count(*) from review_admission_idempotency_records),"
                "(select count(*) from review_leases)"
            )
        ),
    }


async def test_upgrade_preserves_existing_sources_without_publishing(
    tmp_path, isolated_database_env, migration_lock
):
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0010_post_submit_authority")

        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_completed_source(tmp_path, isolated_database_env) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            connection = await asyncpg.connect(url)
            try:
                assert await connection.fetchval(
                    "select version_num from alembic_version"
                ) == "0010_post_submit_authority"
                assert await connection.fetchval(
                    "select to_regclass('public.task_post_submit_routing_manifests')"
                ) is None
                before = await _snapshot(connection, h)
            finally:
                await connection.close()

            await asyncio.to_thread(command.upgrade, _config(), "0011_task_routing_source")

            connection = await asyncpg.connect(url)
            try:
                assert await connection.fetchval(
                    "select version_num from alembic_version"
                ) == "0011_task_routing_source"
                assert await connection.fetchval(
                    "select count(*) from task_post_submit_routing_manifests"
                ) == 0
                assert await _snapshot(connection, h) == before
            finally:
                await connection.close()


async def test_request_upgrade_preserves_completed_owners(
    tmp_path, isolated_database_env, migration_lock
):
    """Upgrade actual predecessor data without creating a request or publishing a source."""
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0017_acceptance_source_contracts")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_completed_source(tmp_path, isolated_database_env) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            connection = await asyncpg.connect(url)
            try:
                before = await _snapshot(connection, h)
                assert await connection.fetchval("select to_regclass('public.task_post_submit_routing_requests')") is None
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0018_task_routing_request")
            connection = await asyncpg.connect(url)
            try:
                assert await _snapshot(connection, h) == before
                assert await connection.fetchval("select count(*) from public.task_post_submit_routing_requests") == 0
                assert await connection.fetchval("select count(*) from public.task_post_submit_routing_manifests") == 0
            finally:
                await connection.close()
