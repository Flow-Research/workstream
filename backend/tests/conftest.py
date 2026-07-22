from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
import asyncio
import fcntl
from functools import partial
import hashlib
import os
from pathlib import Path

from alembic import command  # type: ignore[import-not-found,attr-defined]
from alembic.config import Config  # type: ignore[import-not-found]
import asyncpg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

from app.core.config import get_settings
from app.db import session as db_session

DDL_LOCK_DIRECTORY = Path("/tmp")
TRUNCATE_GUARDED_TABLES = (
    "admin_role_grants",
    "audit_events",
    "authority_control",
    "authority_idempotency_records",
    "outbox_events",
    "project_role_grants",
    "project_role_qualification_snapshots",
)
TestDatabaseReset = Callable[..., Awaitable[None]]
DatabaseLock = Callable[[], AbstractContextManager[None]]


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


async def _drop_test_database_schema(database_url: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute("drop schema if exists public cascade")
        await connection.execute("create schema public")
    finally:
        await connection.close()


def _rebuild_test_database_schema(database_url: str) -> None:
    with postgres_ddl_lock(database_url):
        asyncio.run(_drop_test_database_schema(database_url))
        command.upgrade(_alembic_config(), "head")


async def _reset_test_database_state(
    database_url: str,
    *,
    include_canonical_actors: bool = False,
) -> None:
    """Restore the already-migrated isolated database to its empty baseline."""
    del include_canonical_actors
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            rows = await connection.fetch(
                "select tablename, quote_ident(tablename) as identifier "
                "from pg_tables where schemaname = 'public' "
                "and tablename not in ('alembic_version', 'actor_profile_migration_state') "
                "order by tablename"
            )
            tables = {row["tablename"]: row["identifier"] for row in rows}
            missing_tables = set(TRUNCATE_GUARDED_TABLES) - tables.keys()
            if not tables or missing_tables:
                missing = ",".join(sorted(missing_tables)) or "all"
                raise RuntimeError(
                    f"test database is not migrated to the expected schema: {missing}"
                )
            for name in TRUNCATE_GUARDED_TABLES:
                await connection.execute(f"alter table {tables[name]} disable trigger user")
            await connection.execute(
                f"truncate table {', '.join(tables.values())} restart identity cascade"
            )
            await connection.execute(
                "insert into authority_control"
                "(id, bootstrap_completed, bootstrap_grant_id, version) "
                "values (1, false, null, 0)"
            )
            for name in TRUNCATE_GUARDED_TABLES:
                await connection.execute(f"alter table {tables[name]} enable trigger user")
    finally:
        await connection.close()


@contextmanager
def postgres_ddl_lock(database_url: str) -> Iterator[None]:
    """Serialize Alembic resets only for processes sharing one database."""
    database_key = hashlib.sha256(database_url.encode("utf-8")).hexdigest()[:16]
    lock_path = DDL_LOCK_DIRECTORY / f"workstream-postgres-ddl-{database_key}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@pytest.fixture
def migration_lock(postgres_database_url: str) -> DatabaseLock:
    """Return a database-scoped PostgreSQL DDL lock context manager."""
    return partial(postgres_ddl_lock, postgres_database_url)


@pytest.fixture
def reset_test_database_state() -> TestDatabaseReset:
    """Return the shared privileged reset used by isolated database suites."""
    return _reset_test_database_state


@pytest.fixture
def clean_postgres_database(
    postgres_database_url: str,
    request: pytest.FixtureRequest,
) -> Iterator[str]:
    """Provide an isolated migrated database baseline per test."""
    owns_schema = request.node.get_closest_marker("postgres_schema_contract") is not None
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())
    if owns_schema:
        _rebuild_test_database_schema(postgres_database_url)
    else:
        asyncio.run(_reset_test_database_state(postgres_database_url))
    try:
        yield postgres_database_url
    finally:
        asyncio.run(db_session.dispose_engine())
        if owns_schema:
            with postgres_ddl_lock(postgres_database_url):
                command.upgrade(_alembic_config(), "head")
        get_settings.cache_clear()


@pytest.fixture
def postgres_database_url() -> str:
    value = os.environ.get("WORKSTREAM_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("WORKSTREAM_TEST_DATABASE_URL is required for database-backed tests")
    return value


@pytest.fixture
def isolated_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    yield clean_postgres_database
    get_settings.cache_clear()
