from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path

import asyncpg
import pytest

from app.core.config import get_settings

DDL_LOCK_DIRECTORY = Path("/tmp")
TestDatabaseReset = Callable[..., Awaitable[None]]


async def _reset_test_database_state(
    database_url: str,
    *,
    include_canonical_actors: bool = False,
) -> None:
    """Reset test-owned append-only state under explicit privileged custody."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            await connection.execute(
                "alter table audit_events disable trigger audit_events_reject_update_delete"
            )
            await connection.execute(
                "alter table audit_events disable trigger audit_events_reject_truncate"
            )
            await connection.execute(
                "alter table authority_idempotency_records disable trigger user"
            )
            await connection.execute("alter table admin_role_grants disable trigger user")
            await connection.execute("alter table authority_control disable trigger user")
            if include_canonical_actors:
                await connection.execute(
                    "alter table actor_profiles disable trigger actor_profile_history_guard"
                )
                await connection.execute(
                    "alter table actor_identity_links disable trigger "
                    "actor_identity_link_history_guard"
                )
            await connection.execute("truncate table audit_events cascade")
            await connection.execute("truncate table authority_idempotency_records cascade")
            await connection.execute(
                "truncate table authority_control, admin_role_grants cascade"
            )
            await connection.execute(
                "insert into authority_control"
                "(id, bootstrap_completed, bootstrap_grant_id, version) "
                "values (1, false, null, 0)"
            )
            await connection.execute("truncate table api_rate_control_counters")
            if include_canonical_actors:
                await connection.execute(
                    "truncate table actor_identity_links, actor_profiles cascade"
                )
                await connection.execute(
                    "alter table actor_identity_links enable trigger "
                    "actor_identity_link_history_guard"
                )
                await connection.execute(
                    "alter table actor_profiles enable trigger actor_profile_history_guard"
                )
            await connection.execute(
                "alter table audit_events enable trigger audit_events_reject_truncate"
            )
            await connection.execute("alter table authority_control enable trigger user")
            await connection.execute("alter table admin_role_grants enable trigger user")
            await connection.execute(
                "alter table authority_idempotency_records enable trigger user"
            )
            await connection.execute(
                "alter table audit_events enable trigger audit_events_reject_update_delete"
            )
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
def migration_lock(postgres_database_url: str):
    """Return a database-scoped PostgreSQL DDL lock context manager."""

    @contextmanager
    def lock() -> Iterator[None]:
        """Acquire the lock for this fixture's exact test database."""
        with postgres_ddl_lock(postgres_database_url):
            yield

    return lock


@pytest.fixture
def reset_test_database_state() -> TestDatabaseReset:
    """Return the shared privileged reset used by isolated database suites."""
    return _reset_test_database_state


@pytest.fixture
def postgres_database_url() -> str:
    value = os.environ.get("WORKSTREAM_TEST_DATABASE_URL")
    if not value:
        pytest.fail("WORKSTREAM_TEST_DATABASE_URL is required for database-backed tests")
    return value


@pytest.fixture
def isolated_database_env(monkeypatch: pytest.MonkeyPatch, postgres_database_url: str) -> str:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    get_settings.cache_clear()
    yield postgres_database_url
    get_settings.cache_clear()
