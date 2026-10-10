"""Populated source upgrade preserves retained truth; downgrade never deletes it."""

from tests.contributions.records.historical_support import historical_contribution_source

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from tests.checkers.execution.historical_execution import historical_completed_source
from app.db import session as db_session
from tests.contributions.records.support import (
    award_values,
    insert_award,
    insert_record,
)
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.reviews.acceptance.historical_support import (
    historical_acceptance_source,
    insert_historical_acceptance,
)
from tests.reviews.acceptance.test_migration import snapshot as parent_snapshot

pytestmark = pytest.mark.postgres_schema_contract


def test_completeness_migration_locks_writers_before_retained_data_preflight():
    source = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/0019_submitter_award_completeness.py"
    ).read_text(encoding="utf-8")
    lock = (
        '"LOCK TABLE public.contribution_records, public.compensation_awards "\n'
        '        "IN SHARE ROW EXCLUSIVE MODE"'
    )
    assert source.count(lock) == 1
    assert source.index(lock) < source.index("DO $$")


async def snapshot(connection):
    result = await parent_snapshot(connection)
    result["final_acceptances"] = await connection.fetch(
        "SELECT to_jsonb(r)::text AS value FROM public.final_acceptances r ORDER BY 1"
    )
    return result


async def test_contribution_upgrade_preserves_sources(
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
        await asyncio.to_thread(command.upgrade, _config(), "0014_final_acceptance")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_acceptance_source(
            tmp_path, isolated_database_env, completed_source_factory=historical_completed_source
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            async with h.factory() as session:
                await insert_historical_acceptance(session, h.acceptance)
                await session.commit()
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert len(before["final_acceptances"]) == 1
                assert await connection.fetchval("SELECT to_regclass('public.contribution_records')") is None
                assert await connection.fetchval("SELECT to_regclass('public.compensation_awards')") is None
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0015_contribution_awards")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                for table in ("contribution_records", "compensation_awards"):
                    assert await connection.fetchval(f"SELECT count(*) FROM public.{table}") == 0
                assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0015_contribution_awards"
            finally:
                await connection.close()
            with pytest.raises(
                RuntimeError,
                match="Workstream v0.1 migrations cannot be downgraded; recreate the database",
            ):
                await asyncio.to_thread(command.downgrade, _config(), "0014_final_acceptance")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert await connection.fetchval(
                    "SELECT version_num FROM alembic_version"
                ) == "0015_contribution_awards"
            finally:
                await connection.close()


async def _award_snapshot(connection):
    return {
        table: [row["value"] for row in await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY r.id"
        )]
        for table in ("contribution_records", "compensation_awards")
    }


async def _reset_to_0018(database_url):
    await db_session.dispose_engine()
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    finally:
        await connection.close()
    await asyncio.to_thread(command.upgrade, _config(), "0018_task_routing_request")


async def test_completeness_upgrade_preserves_complete_retained_awards(
    tmp_path, isolated_database_env, migration_lock
):
    with migration_lock():
        await _reset_to_0018(isolated_database_env)
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_contribution_source(
            tmp_path,
            isolated_database_env,
            paid=True,
            completed_source_factory=historical_completed_source,
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            async with h.factory() as session:
                await insert_record(session, h.submitter_record)
                for award in await award_values(session, h.submitter_record):
                    await insert_award(session, award)
                await session.commit()
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                before = await _award_snapshot(connection)
                assert len(before["contribution_records"]) == 1
                assert len(before["compensation_awards"]) == 2
            finally:
                await connection.close()

            await asyncio.to_thread(command.upgrade, _config(), "0019_submitter_awards")
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                assert await _award_snapshot(connection) == before
                assert await connection.fetchval(
                    "SELECT version_num FROM public.alembic_version"
                ) == "0019_submitter_awards"
                functions = await connection.fetch(
                    "SELECT p.proname, p.proconfig, pg_get_functiondef(p.oid) AS body "
                    "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' AND p.proname=ANY($1::text[]) ORDER BY p.proname",
                    [
                        "accepted_submission_award_set_is_complete",
                        "require_accepted_submission_award_set",
                    ],
                )
                assert [row["proname"] for row in functions] == [
                    "accepted_submission_award_set_is_complete",
                    "require_accepted_submission_award_set",
                ]
                for row in functions:
                    assert row["proconfig"] == ["search_path=pg_catalog, public, pg_temp"]
                bodies = {row["proname"]: row["body"] for row in functions}
                helper_body = bodies["accepted_submission_award_set_is_complete"]
                for relation in (
                    "contribution_records",
                    "contribution_rules",
                    "contribution_award_definitions",
                    "compensation_awards",
                ):
                    assert f"public.{relation}" in helper_body
                trigger_body = bodies["require_accepted_submission_award_set"]
                for relation in ("contribution_records", "compensation_awards"):
                    assert (
                        f"TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = '{relation}'"
                    ) in trigger_body
                assert (
                    "public.accepted_submission_award_set_is_complete(record_uuid)"
                ) in trigger_body
                triggers = await connection.fetch(
                    "SELECT tgname, tgdeferrable, tginitdeferred FROM pg_catalog.pg_trigger "
                    "WHERE tgname LIKE 'accepted_submission_award_set_from_%' ORDER BY tgname"
                )
                assert [tuple(row.values()) for row in triggers] == [
                    ("accepted_submission_award_set_from_award", True, True),
                    ("accepted_submission_award_set_from_contribution", True, True),
                ]
            finally:
                await connection.close()


async def test_completeness_upgrade_refuses_incomplete_retained_awards_unchanged(
    tmp_path, isolated_database_env, migration_lock
):
    with migration_lock():
        await _reset_to_0018(isolated_database_env)
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_contribution_source(
            tmp_path,
            isolated_database_env,
            paid=True,
            completed_source_factory=historical_completed_source,
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            async with h.factory() as session:
                await insert_record(session, h.submitter_record)
                await insert_award(
                    session, (await award_values(session, h.submitter_record))[0]
                )
                await session.commit()
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                before = await _award_snapshot(connection)
            finally:
                await connection.close()

            with pytest.raises(DBAPIError, match="retained accepted-submission.*incomplete"):
                await asyncio.to_thread(
                    command.upgrade, _config(), "0019_submitter_awards"
                )
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                assert await _award_snapshot(connection) == before
                assert await connection.fetchval(
                    "SELECT version_num FROM public.alembic_version"
                ) == "0018_task_routing_request"
                assert await connection.fetchval(
                    "SELECT to_regprocedure('public.accepted_submission_award_set_is_complete(uuid)')"
                ) is None
            finally:
                await connection.close()
