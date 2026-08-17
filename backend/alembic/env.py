from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_BASELINE_REVISION = "0001_v01_baseline"
_CURRENT_HEAD_REVISION = "0007_contribution_policy_publication_custody"
_RECREATE_GUIDANCE = (
    "Workstream v0.1 requires a fresh database; recreate this database before "
    "running the 0001_v01_baseline migration"
)


def get_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("WORKSTREAM_DATABASE_URL must be set before running migrations")
    return database_url


def run_migrations_offline() -> None:
    raise RuntimeError(
        "offline migration generation is disabled because the v0.1 fresh-database "
        "preflight requires a live PostgreSQL target"
    )


def do_run_migrations(connection: Connection) -> None:
    version_table_exists = bool(
        connection.scalar(text("select to_regclass('public.alembic_version') is not null"))
    )
    if version_table_exists:
        revisions = tuple(
            connection.execute(text("select version_num from public.alembic_version"))
            .scalars()
            .all()
        )
        if revisions not in (
            (),
            (_BASELINE_REVISION,),
            (_CURRENT_HEAD_REVISION,),
        ):
            raise RuntimeError(_RECREATE_GUIDANCE)
    # The read-only preflight autobegins a SQLAlchemy transaction. End that
    # transaction before Alembic establishes the migration transaction;
    # otherwise connection disposal would roll back a successful migration.
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
