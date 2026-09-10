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
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    downgrade = ScriptDirectory.from_config(_config()).get_revision(revision).module.downgrade
    engine = create_async_engine(database_url)

    def run(connection):
        with Operations.context(MigrationContext.configure(connection)):
            downgrade()

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
        raise RuntimeError("isolated migration subprocess failed")
