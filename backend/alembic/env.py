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

_BASELINE_REVISION = "0001_uuid7_v01"
_CURRENT_HEAD_REVISION = "0030_routing_outcomes"
_RECREATE_GUIDANCE = (
    "Workstream v0.1 requires a fresh database; recreate this database before "
    "running the 0001_uuid7_v01 migration"
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
            ("0002_task_queue_authority",),
            ("0003_task_read_authority",),
            ("0004_task_context_authority",),
            ("0005_task_evidence_authority",),
            ("0006_history_read_authority",),
            ("0007_checker_output_custody",),
            ("0008_checker_execution",),
            ("0009_checker_material_lineage",),
            ("0010_post_submit_authority",),
            ("0011_task_routing_source",),
            ("0012_review_packet",),
            ("0013_review_source",),
            ("0014_final_acceptance",),
            ("0015_contribution_awards",),
            ("0016_review_lifecycle_fence",),
            ("0017_acceptance_source_contracts",),
            ("0018_task_routing_request",),
            ("0019_submitter_awards",),
            ("0020_review_admission_lock_order",),
            ("0021_submission_manifest",),
            ("0022_submission_packet_custody",),
            ("0023_remove_task_payment_policy",),
            ("0024_require_second_review_false",),
            ("0025_submission_dispatch",),
            ("0026_task_guide_read",),
            ("0027_markdown_guide_media",),
            ("0028_lifecycle_transitions",),
            ("0029_external_checker_registry",),
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
