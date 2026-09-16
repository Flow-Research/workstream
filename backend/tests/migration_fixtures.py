"""Canonical current-head lookup and scoped retained-evidence migration probes."""

import asyncio
import sys
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine


def _config():
    return Config(Path(__file__).resolve().parents[1] / "alembic.ini")


def current_schema_revision():
    """Require one canonical Alembic head for current-schema assertions."""
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1
    return heads[0]


async def run_guarded_revision_downgrade(database_url: str, revision: str) -> None:
    """Exercise a retained-data guard directly, without earlier guards masking it."""
    await _run_revision_body(database_url, revision, "downgrade")


async def run_scoped_revision_upgrade(database_url: str, revision: str) -> None:
    """Restore one tested revision body without traversing later schema owners."""
    await _run_revision_body(database_url, revision, "upgrade")


async def _run_revision_body(database_url: str, revision: str, direction: str) -> None:
    """Run the unchanged owned migration in one PostgreSQL transaction."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    module = ScriptDirectory.from_config(_config()).get_revision(revision).module
    operation = getattr(module, direction)
    engine = create_async_engine(database_url)

    def run(connection):
        with Operations.context(MigrationContext.configure(connection)):
            operation()

    try:
        async with engine.begin() as connection:
            await connection.run_sync(run)
    finally:
        await engine.dispose()



async def run_alembic_revision(direction, revision):
    """Keep Alembic's async engines in their own process, outside test event loops."""
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "alembic", direction, revision,
                                                   cwd=Path(__file__).resolve().parents[1])
    if await process.wait() != 0:
        raise RuntimeError(f"isolated migration subprocess failed (exit {process.returncode})")
