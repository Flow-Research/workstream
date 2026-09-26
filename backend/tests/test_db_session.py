from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

from app.core.config import get_settings


async def test_async_database_session_executes_simple_query(
    isolated_database_env: str,
) -> None:
    get_settings.cache_clear()
    db_session = importlib.reload(importlib.import_module("app.db.session"))
    session_iterator = db_session.get_db_session()

    try:
        session = await anext(session_iterator)
        result = await session.execute(text("SELECT 1"))

        assert result.scalar_one() == 1
    finally:
        await session_iterator.aclose()
        await db_session.dispose_engine()
        get_settings.cache_clear()


async def test_get_database_url_requires_workstream_database_url(monkeypatch) -> None:
    monkeypatch.delenv("WORKSTREAM_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    db_session = importlib.reload(importlib.import_module("app.db.session"))

    try:
        with pytest.raises(RuntimeError, match="WORKSTREAM_DATABASE_URL must be set"):
            db_session.get_database_url()
    finally:
        await db_session.dispose_engine()
        get_settings.cache_clear()


async def test_get_engine_requires_workstream_database_url(monkeypatch) -> None:
    monkeypatch.delenv("WORKSTREAM_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    db_session = importlib.reload(importlib.import_module("app.db.session"))

    try:
        with pytest.raises(RuntimeError, match="WORKSTREAM_DATABASE_URL must be set"):
            db_session.get_engine()
    finally:
        await db_session.dispose_engine()
        get_settings.cache_clear()


@pytest.mark.parametrize("entrypoint", [
    "app.main", "app.workers.project_setup", "app.workers.post_policy",
])
def test_fresh_runtime_process_resolves_model_graph(entrypoint):
    """API and worker startup must not depend on pytest or Alembic model imports."""
    from pathlib import Path
    import os
    import subprocess
    import sys

    code = (
        "import importlib; importlib.import_module(" + repr(entrypoint) + "); "
        "from app.db.base import Base; "
        "[foreign_key.column for table in Base.metadata.tables.values() "
        "for foreign_key in table.foreign_keys]; "
        "from sqlalchemy.orm import configure_mappers; configure_mappers()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "WORKSTREAM_CELERY_BROKER_URL": "memory://"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
