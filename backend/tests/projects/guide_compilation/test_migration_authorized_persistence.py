"""Alembic 0008 topology, schema, and guarded downgrade proof."""

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

pytestmark = pytest.mark.postgres_schema_contract
OWN_REVISION = "0008_guide_compilation_authorized_persistence"
CURRENT_HEAD = "0009_guide_compilation_projections"


def _config() -> Config:
    return Config(Path(__file__).resolve().parents[3] / "alembic.ini")


async def _schema(database_url: str) -> tuple[str, int, int, int]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return (
            await connection.fetchval("select version_num from alembic_version"),
            await connection.fetchval(
                "select count(*) from pg_proc where proname like "
                "'project_guide_compilation_request_%_digest'"
            ),
            await connection.fetchval(
                "select count(*) from pg_trigger where not tgisinternal and "
                "tgrelid='project_guide_compilation_request_operations'::regclass"
            ),
            await connection.fetchval(
                "select count(*) from pg_constraint where "
                "conrelid='project_guide_compilation_request_operations'::regclass"
            ),
        )
    finally:
        await connection.close()


async def _fresh_schema(database_url: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute("drop schema public cascade; create schema public")
    finally:
        await connection.close()


async def _version(database_url: str) -> str:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return await connection.fetchval("select version_num from alembic_version")
    finally:
        await connection.close()


def test_0008_installs_exact_request_custody_and_round_trips_empty(
    isolated_database_env: str, migration_lock
) -> None:
    assert asyncio.run(_schema(isolated_database_env)) == (CURRENT_HEAD, 2, 3, 16)
    with migration_lock():
        command.downgrade(_config(), "0007_contribution_policy_publication_custody")
        assert asyncio.run(_version(isolated_database_env)) == (
            "0007_contribution_policy_publication_custody"
        )
        asyncio.run(_fresh_schema(isolated_database_env))
        command.upgrade(_config(), OWN_REVISION)
    assert asyncio.run(_schema(isolated_database_env)) == (OWN_REVISION, 2, 3, 16)
    with migration_lock():
        command.upgrade(_config(), CURRENT_HEAD)
        command.upgrade(_config(), CURRENT_HEAD)
    assert asyncio.run(_schema(isolated_database_env)) == (CURRENT_HEAD, 2, 3, 16)


async def _seed_attempt(database_url: str) -> None:
    values = await seed_database(database_url)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await GuideCompilationRepository(session).reserve_attempt(
                identity(context(values))
            )
    finally:
        await engine.dispose()


def test_0008_refuses_downgrade_with_compilation_custody(
    isolated_database_env: str, migration_lock
) -> None:
    asyncio.run(_seed_attempt(isolated_database_env))
    with migration_lock(), pytest.raises(RuntimeError, match="custody is non-empty"):
        command.downgrade(_config(), "0007_contribution_policy_publication_custody")
    assert asyncio.run(_schema(isolated_database_env))[0] == CURRENT_HEAD
