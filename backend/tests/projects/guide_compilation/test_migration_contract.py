"""Current-schema custody proof for guide-compilation persistence."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

pytestmark = pytest.mark.postgres_schema_contract


async def _schema_state(database_url: str) -> tuple[str, bool, int, int, int, int]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return (
            await connection.fetchval("select version_num from alembic_version"),
            await connection.fetchval(
                "select to_regclass('project_guide_compilation_attempts') is not null"
            ),
            await connection.fetchval(
                "select count(*) from pg_trigger where not tgisinternal and tgrelid in "
                "(select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname in "
                "('project_guide_compilation_attempts','project_guide_compilations'))"
            ),
            await connection.fetchval(
                "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authorization_action_evidence' and "
                "pg_get_constraintdef(oid) like '%project.guide_compilation.execute%'"
            ),
            await connection.fetchval(
                "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authority_registries' and "
                "pg_get_constraintdef(oid) like '%project.guide_compilation.execute%'"
            ),
            await connection.fetchval(
                "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authority_privacy_bounds' and "
                "pg_get_constraintdef(oid) like '%project_guide_compilation_attempt%'"
            ),
        )
    finally:
        await connection.close()


def test_current_schema_preserves_guide_compilation_schema(
    isolated_database_env: str,
) -> None:
    assert asyncio.run(_schema_state(isolated_database_env)) == (
        "0008_guide_compilation_authorized_persistence",
        True,
        4,
        1,
        1,
        1,
    )
