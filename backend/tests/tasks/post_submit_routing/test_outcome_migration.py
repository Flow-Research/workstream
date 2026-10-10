"""Upgrade preserves unfinished work and refuses unprovable retained outcomes."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from tests.checkers.execution.historical_execution import (
    historical_completed_source,
    historical_reserve,
)
from tests.historical_submission_fixtures import historical_material_fixture
from tests.migration_fixtures import (
    _config,
)

pytestmark = pytest.mark.postgres_schema_contract


async def snapshot(connection):
    tables = (
        "submissions",
        "checker_runs",
        "checker_results",
        "audit_events",
        "outbox_events",
        "task_post_submit_routing_manifests",
        "final_acceptances",
        "workstream_tasks",
        "task_assignments",
    )
    return {
        table: await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY 1"
        )
        for table in tables
    }


@pytest.mark.parametrize(
    "terminal", [False, True], ids=("unfinished-preserved", "unproven-terminal-refused")
)
async def test_pre_authority_rows_refuse_upgrade_without_rewriting(
    tmp_path, isolated_database_env, migration_lock, terminal
):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0024_require_second_review_false")
        factory = historical_completed_source if terminal else historical_material_fixture
        async with factory(tmp_path, isolated_database_env) as h:
            if not terminal:
                await historical_reserve(h)
            await asyncio.to_thread(command.upgrade, _config(), "0029_external_checker_registry")
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                if terminal:
                    with pytest.raises(
                        IntegrityError,
                        match="retained outcome or terminal material lacks required source authority",
                    ):
                        await asyncio.to_thread(command.upgrade, _config(), "0030_routing_outcomes")
                    assert (
                        await connection.fetchval("SELECT version_num FROM public.alembic_version")
                        == "0029_external_checker_registry"
                    )
                    assert await snapshot(connection) == before
                    assert not await connection.fetchval("""SELECT EXISTS(SELECT 1 FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='checker_runs'
                          AND column_name='input_materialization_evidence_id')""")
                else:
                    await asyncio.to_thread(command.upgrade, _config(), "0030_routing_outcomes")
                    assert (
                        await connection.fetchval("SELECT version_num FROM public.alembic_version")
                        == "0030_routing_outcomes"
                    )
                    after = await snapshot(connection)
                    after["checker_runs"] = await connection.fetch(
                        "SELECT (to_jsonb(r)-'input_materialization_evidence_id')::text AS value FROM public.checker_runs r ORDER BY 1"
                    )
                    assert after == before
                    assert (
                        await connection.fetchval(
                            "SELECT count(*) FROM public.checker_runs WHERE input_materialization_evidence_id IS NOT NULL"
                        )
                        == 0
                    )
            finally:
                await connection.close()
