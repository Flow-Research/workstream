"""Alembic topology and downgrade custody for migration 0062."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.repository import GuideCompilationRepository

from .helpers import context, identity, seed_database


def _config() -> Config:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


async def _schema_state(database_url: str) -> tuple[str, bool, int, int, int, int]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        head = await connection.fetchval("select version_num from alembic_version")
        tables = await connection.fetchval(
            "select to_regclass('project_guide_compilation_attempts') is not null"
        )
        triggers = await connection.fetchval(
            "select count(*) from pg_trigger where not tgisinternal and tgrelid in "
            "(select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relname in "
            "('project_guide_compilation_attempts','project_guide_compilations'))"
        )
        action_pairs = await connection.fetchval(
            "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authorization_action_evidence' and "
            "pg_get_constraintdef(oid) like "
            "'%project.guide_compilation.execute%'"
        )
        permission_pairs = await connection.fetchval(
            "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_registries' and "
            "pg_get_constraintdef(oid) like '%project.guide_compilation.execute%'"
        )
        resource_types = await connection.fetchval(
            "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds' and "
            "pg_get_constraintdef(oid) like '%project_guide_compilation_attempt%'"
        )
        return head, tables, triggers, action_pairs, permission_pairs, resource_types
    finally:
        await connection.close()


def test_0062_empty_round_trip_restores_exact_hidden_schema(
    isolated_database_env: str, migration_lock
) -> None:
    """An empty 0062 downgrade/re-upgrade restores its tables and four guards."""
    config = _config()
    with migration_lock():
        try:
            command.downgrade(config, "0061_submission_admission")
            assert asyncio.run(_schema_state(isolated_database_env)) == (
                "0061_submission_admission",
                False,
                0,
                0,
                0,
                0,
            )
        finally:
            command.upgrade(config, "0062_guide_compilation")
    assert asyncio.run(_schema_state(isolated_database_env)) == (
        "0062_guide_compilation",
        True,
        4,
        1,
        1,
        1,
    )


def test_0062_nonempty_attempt_blocks_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """A consumed setup generation cannot disappear through downgrade."""
    async def seed_attempt() -> None:
        values = await seed_database(isolated_database_env)
        engine = create_async_engine(isolated_database_env)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session, session.begin():
                await GuideCompilationRepository(session).reserve_attempt(
                    identity(context(values))
                )
        finally:
            await engine.dispose()

    asyncio.run(seed_attempt())
    with migration_lock(), pytest.raises(
        RuntimeError, match="cannot downgrade non-empty guide-compilation custody"
    ):
        command.downgrade(_config(), "0061_submission_admission")
    assert asyncio.run(_schema_state(isolated_database_env))[0] == (
        "0062_guide_compilation"
    )
