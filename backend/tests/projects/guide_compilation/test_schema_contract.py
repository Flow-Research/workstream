"""Current-schema custody proof for guide-compilation persistence."""

from __future__ import annotations

import asyncio
from tests.migration_fixtures import current_schema_revision

import asyncpg
import pytest

pytestmark = pytest.mark.postgres_schema_contract


async def _schema_state(database_url: str) -> tuple[str, bool, set[str], int, int, int]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return (
            await connection.fetchval("select version_num from alembic_version"),
            await connection.fetchval(
                "select to_regclass('project_guide_compilation_attempts') is not null"
            ),
            {row["tgname"] for row in await connection.fetch(
                "select tgname from pg_trigger where not tgisinternal and tgenabled='O' and tgrelid in "
                "(select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname in "
                "('project_guide_compilation_attempts','project_guide_compilations'))"
            )},
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
        current_schema_revision(),
        True,
        {
            "compilation_document_evidence_guard",
            "project_guide_runtime_configuration_guard",
            "trg_compilation_attempt_delete",
            "trg_compilation_attempt_update",
            "trg_compilation_insert",
            "trg_compilation_mutation",
            "guide_specification_attempt_insert",
            "current_guide_compilation_insert",
        },
        1,
        1,
        1,
    )
