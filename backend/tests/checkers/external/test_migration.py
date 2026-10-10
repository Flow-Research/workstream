"""Registry migration remains public-schema pinned under a hostile search path."""

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command
from alembic.config import Config
from app.db import session as db_session
from scripts.run_isolated_tests import NAME_RE, ROLE_RE
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import current_schema_revision


def _config() -> Config:
    return Config("alembic.ini")


async def test_registry_upgrade_targets_public_schema_with_shadow_search_path(
    isolated_database_env,
    migration_lock,
) -> None:
    shadow = "pilot04_registry_shadow"
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(command.upgrade, _config(), "0028_lifecycle_transitions")
        connection = await asyncpg.connect(url)
        role, database = await connection.fetchrow(
            "select current_user,current_database()"
        )
        assert ROLE_RE.fullmatch(role) and NAME_RE.fullmatch(database)
        try:
            await connection.execute(f"create schema {shadow}")
            await connection.execute(
                f"create table {shadow}.audit_events "
                "(like public.audit_events including all)"
            )
            shadow_before = await connection.fetchval(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid=to_regclass($1) "
                "and conname='ck_audit_events_authorization_action_evidence'",
                f"{shadow}.audit_events",
            )
            await connection.execute(
                f'alter role "{role}" in database "{database}" '
                f"set search_path={shadow},public"
            )
        finally:
            await connection.close()

        try:
            await asyncio.to_thread(command.upgrade, _config(), "head")
            probe = await asyncpg.connect(url)
            try:
                assert await probe.fetchval(
                    "select version_num from public.alembic_version"
                ) == current_schema_revision()
                assert await probe.fetchval(
                    "select to_regclass('public.external_checker_registry_entries') "
                    "is not null"
                )
                assert await probe.fetchval(
                    "select to_regclass($1) is null", f"{shadow}.external_checker_registry_entries"
                )
                public_definition = await probe.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='public.audit_events'::regclass "
                    "and conname='ck_audit_events_authorization_action_evidence'"
                )
                shadow_after = await probe.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid=to_regclass($1) "
                    "and conname='ck_audit_events_authorization_action_evidence'",
                    f"{shadow}.audit_events",
                )
                assert "checker.registry.register" in public_definition
                assert shadow_after == shadow_before
            finally:
                await probe.close()
        finally:
            cleanup = await asyncpg.connect(url)
            try:
                await cleanup.execute(f'alter role "{role}" in database "{database}" reset search_path')
                await cleanup.execute(f"drop schema if exists {shadow} cascade")
            finally:
                await cleanup.close()
