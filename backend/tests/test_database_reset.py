from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import AsyncMock

import asyncpg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

from conftest import (
    PROTECTED_TEST_TABLES,
    RESETTABLE_TEST_TABLES,
    TRUNCATE_GUARDED_TABLES,
    _assert_owned_test_database,
)


async def _protected_state(connection: asyncpg.Connection) -> tuple[str, str | None]:
    head = await connection.fetchval("select version_num from alembic_version")
    migration = await connection.fetchval(
        "select row_to_json(state)::text from actor_profile_migration_state state"
    )
    return head, migration


async def _assert_guards_enabled(connection: asyncpg.Connection) -> None:
    rows = await connection.fetch(
        "select c.relname as table_name, bool_and(t.tgenabled = 'O') as enabled "
        "from pg_trigger t join pg_class c on c.oid = t.tgrelid "
        "where not t.tgisinternal and c.relname = any($1::text[]) "
        "group by c.relname",
        list(TRUNCATE_GUARDED_TABLES),
    )
    assert {row["table_name"] for row in rows} == set(TRUNCATE_GUARDED_TABLES)
    assert all(row["enabled"] is True for row in rows)


def test_database_reset_preserves_schema_and_restores_guards(
    postgres_database_url: str,
    reset_test_database_state: Callable[..., Awaitable[None]],
) -> None:
    """The fast reset is complete, repeatable, and schema preserving."""

    async def exercise() -> None:
        url = postgres_database_url.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            protected_before = await _protected_state(connection)
            actual_tables = set(
                await connection.fetchval(
                    "select array_agg(tablename order by tablename) "
                    "from pg_tables where schemaname = 'public'"
                )
            )
            await connection.execute(
                "insert into api_rate_control_counters "
                "(control_scope, key_digest, window_started_at, window_expires_at, "
                "request_count, updated_at) values "
                "('first_access', decode(repeat('00', 32), 'hex'), "
                "clock_timestamp(), clock_timestamp() + interval '1 minute', 1, "
                "clock_timestamp())"
            )
        finally:
            await connection.close()

        assert actual_tables == set(PROTECTED_TEST_TABLES) | set(RESETTABLE_TEST_TABLES)
        await reset_test_database_state(postgres_database_url)
        await reset_test_database_state(postgres_database_url)

        connection = await asyncpg.connect(url)
        try:
            control = await connection.fetchrow(
                "select bootstrap_completed, bootstrap_grant_id, version "
                "from authority_control"
            )
            counter_count = await connection.fetchval(
                "select count(*) from api_rate_control_counters"
            )
            assert await _protected_state(connection) == protected_before
            await _assert_guards_enabled(connection)
        finally:
            await connection.close()

        assert dict(control) == {
            "bootstrap_completed": False,
            "bootstrap_grant_id": None,
            "version": 0,
        }
        assert counter_count == 0

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql+asyncpg://postgres:x@localhost/postgres",
        "postgresql+asyncpg://workstream:x@localhost/workstream",
        "postgresql+asyncpg://workstream_role_aaaaaaaaaaaa:x@localhost/"
        "workstream_test_bbbbbbbbbbbb",
        "postgresql://workstream_role_aaaaaaaaaaaa:x@localhost/"
        "workstream_test_aaaaaaaaaaaa",
        "postgresql+asyncpg://workstream_role_aaaaaaaaaaaa:x@example.test/"
        "workstream_test_aaaaaaaaaaaa",
        "postgresql+asyncpg://workstream_role_aaaaaaaaaaaa:x@localhost/"
        "workstream_test_aaaaaaaaaaaa?ssl=require",
        "postgresql+asyncpg://workstream_role_aaaaaaaaaaaa:x@localhost/"
        "workstream_test_aaaaaaaaaaaa#fragment",
    ),
)
def test_database_reset_rejects_non_runner_urls(database_url: str) -> None:
    """Admin, default, mismatched, and non-asyncpg URLs fail before a query."""
    connection = AsyncMock()
    with pytest.raises(RuntimeError, match="unsafe test database target"):
        asyncio.run(_assert_owned_test_database(connection, database_url))
    connection.fetchrow.assert_not_awaited()


@pytest.mark.parametrize(
    ("override", "expected"),
    (
        ({"database_name": "workstream_test_bbbbbbbbbbbb"}, "custody"),
        ({"session_role": "workstream_role_bbbbbbbbbbbb"}, "custody"),
        ({"owner_role": "workstream_role_bbbbbbbbbbbb"}, "custody"),
        ({"rolsuper": True}, "custody"),
        ({"rolcreatedb": True}, "custody"),
        ({"rolcreaterole": True}, "custody"),
        ({"rolinherit": True}, "custody"),
        ({"rolreplication": True}, "custody"),
        ({"rolbypassrls": True}, "custody"),
        ({"membership_count": 1}, "custody"),
    ),
)
def test_database_reset_rejects_invalid_live_custody(
    override: dict[str, object], expected: str
) -> None:
    """The connected database, owner, role, and privileges are authoritative."""
    custody: dict[str, object] = {
        "database_name": "workstream_test_aaaaaaaaaaaa",
        "session_role": "workstream_role_aaaaaaaaaaaa",
        "owner_role": "workstream_role_aaaaaaaaaaaa",
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolinherit": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "membership_count": 0,
    }
    custody.update(override)
    connection = AsyncMock()
    connection.fetchrow.return_value = custody
    with pytest.raises(RuntimeError, match=expected):
        asyncio.run(
            _assert_owned_test_database(
                connection,
                "postgresql+asyncpg://workstream_role_aaaaaaaaaaaa:x@localhost/"
                "workstream_test_aaaaaaaaaaaa",
            )
        )


def test_database_reset_rejects_unexpected_table_before_mutation(
    postgres_database_url: str,
    reset_test_database_state: Callable[..., Awaitable[None]],
) -> None:
    """Schema drift fails before guarded triggers or existing rows are touched."""

    async def exercise() -> None:
        url = postgres_database_url.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("create table unexpected_reset_target (id integer)")
            await connection.execute("insert into unexpected_reset_target values (1)")
            with pytest.raises(RuntimeError, match="unexpected=unexpected_reset_target"):
                await reset_test_database_state(postgres_database_url)
            assert await connection.fetchval(
                "select count(*) from unexpected_reset_target"
            ) == 1
            await _assert_guards_enabled(connection)
        finally:
            await connection.execute("drop table if exists unexpected_reset_target")
            await connection.close()

    asyncio.run(exercise())


def test_database_reset_rejects_unexpected_non_table_object(
    postgres_database_url: str,
    reset_test_database_state: Callable[..., Awaitable[None]],
) -> None:
    """A public function outside the canonical fingerprint blocks reset."""

    async def exercise() -> None:
        url = postgres_database_url.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute(
                "create function unexpected_reset_function() returns integer "
                "language sql immutable as 'select 1'"
            )
            with pytest.raises(
                RuntimeError, match="unexpected public schema object fingerprint"
            ):
                await reset_test_database_state(postgres_database_url)
            assert await connection.fetchval("select unexpected_reset_function()") == 1
            await _assert_guards_enabled(connection)
        finally:
            await connection.execute("drop function if exists unexpected_reset_function()")
            await connection.close()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("create_sql", "exists_sql", "drop_sql"),
    (
        (
            "create type unexpected_reset_composite as (value integer)",
            "select exists (select 1 from pg_type t join pg_namespace n "
            "on n.oid = t.typnamespace where n.nspname = 'public' "
            "and t.typname = 'unexpected_reset_composite')",
            "drop type if exists unexpected_reset_composite",
        ),
        (
            'create collation unexpected_reset_collation from "C"',
            "select exists (select 1 from pg_collation c join pg_namespace n "
            "on n.oid = c.collnamespace where n.nspname = 'public' "
            "and c.collname = 'unexpected_reset_collation')",
            "drop collation if exists unexpected_reset_collation",
        ),
        (
            "alter table api_rate_control_counters "
            "add column unexpected_reset_column integer",
            "select exists (select 1 from information_schema.columns "
            "where table_schema = 'public' "
            "and table_name = 'api_rate_control_counters' "
            "and column_name = 'unexpected_reset_column')",
            "alter table api_rate_control_counters "
            "drop column if exists unexpected_reset_column",
        ),
        (
            "create trigger unexpected_reset_trigger before truncate "
            "on api_rate_control_counters for each statement "
            "execute function reject_audit_event_mutation()",
            "select exists (select 1 from pg_trigger "
            "where tgname = 'unexpected_reset_trigger')",
            "drop trigger if exists unexpected_reset_trigger "
            "on api_rate_control_counters",
        ),
    ),
)
def test_database_reset_rejects_structural_schema_drift(
    postgres_database_url: str,
    reset_test_database_state: Callable[..., Awaitable[None]],
    create_sql: str,
    exists_sql: str,
    drop_sql: str,
) -> None:
    """Types, collations, columns, and triggers outside the schema block reset."""

    async def exercise() -> None:
        url = postgres_database_url.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute(create_sql)
            with pytest.raises(
                RuntimeError, match="unexpected public schema object fingerprint"
            ):
                await reset_test_database_state(postgres_database_url)
            assert await connection.fetchval(exists_sql) is True
            await _assert_guards_enabled(connection)
        finally:
            await connection.execute(drop_sql)
            await connection.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", (RuntimeError("injected"), asyncio.CancelledError()))
def test_database_reset_rolls_back_after_trigger_disable(
    postgres_database_url: str,
    reset_test_database_state: Callable[..., Awaitable[None]],
    failure: BaseException,
) -> None:
    """Exceptions and cancellation roll back trigger and protected-state changes."""

    async def exercise() -> None:
        url = postgres_database_url.replace("+asyncpg", "")
        digest_octet = "11" if isinstance(failure, RuntimeError) else "12"
        connection = await asyncpg.connect(url)
        try:
            protected_before = await _protected_state(connection)
            await connection.execute(
                "insert into api_rate_control_counters "
                "(control_scope, key_digest, window_started_at, window_expires_at, "
                "request_count, updated_at) values "
                f"('first_access', decode(repeat('{digest_octet}', 32), 'hex'), "
                "clock_timestamp(), clock_timestamp() + interval '1 minute', 1, "
                "clock_timestamp())"
            )
        finally:
            await connection.close()

        async def fail() -> None:
            raise failure

        with pytest.raises(type(failure)):
            await reset_test_database_state(postgres_database_url, after_disable=fail)

        connection = await asyncpg.connect(url)
        try:
            assert await _protected_state(connection) == protected_before
            assert await connection.fetchval(
                "select count(*) from api_rate_control_counters "
                f"where key_digest = decode(repeat('{digest_octet}', 32), 'hex')"
            ) == 1
            await _assert_guards_enabled(connection)
        finally:
            await connection.close()

    asyncio.run(exercise())


def test_database_reset_signal_rolls_back_disabled_triggers(
    postgres_database_url: str,
) -> None:
    """Terminating a real reset process leaves PostgreSQL trigger state enabled."""
    marker = Path(os.environ["PYTEST_TMPDIR"]) / "reset-disabled" if os.environ.get(
        "PYTEST_TMPDIR"
    ) else Path("/tmp") / f"workstream-reset-disabled-{os.getpid()}"
    marker.unlink(missing_ok=True)

    async def seed() -> tuple[str, str | None]:
        connection = await asyncpg.connect(postgres_database_url.replace("+asyncpg", ""))
        try:
            protected = await _protected_state(connection)
            await connection.execute(
                "insert into api_rate_control_counters "
                "(control_scope, key_digest, window_started_at, window_expires_at, "
                "request_count, updated_at) values "
                "('first_access', decode(repeat('22', 32), 'hex'), "
                "clock_timestamp(), clock_timestamp() + interval '1 minute', 1, "
                "clock_timestamp())"
            )
            return protected
        finally:
            await connection.close()

    protected_before = asyncio.run(seed())
    child_code = """
import asyncio
import os
from pathlib import Path
import runpy

reset = runpy.run_path("tests/conftest.py")["_reset_test_database_state"]

async def pause():
    Path(os.environ["RESET_MARKER"]).write_text("ready", encoding="utf-8")
    await asyncio.sleep(3600)

asyncio.run(reset(os.environ["WORKSTREAM_TEST_DATABASE_URL"], after_disable=pause))
"""
    child_env = dict(os.environ)
    child_env["WORKSTREAM_TEST_DATABASE_URL"] = postgres_database_url
    child_env["RESET_MARKER"] = str(marker)
    process = subprocess.Popen([sys.executable, "-c", child_code], env=child_env)
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "reset child did not reach the disabled-trigger checkpoint"
        process.terminate()
        process.wait(timeout=10)

        async def verify() -> None:
            connection = await asyncpg.connect(postgres_database_url.replace("+asyncpg", ""))
            try:
                assert await _protected_state(connection) == protected_before
                assert await connection.fetchval(
                    "select count(*) from api_rate_control_counters "
                    "where key_digest = decode(repeat('22', 32), 'hex')"
                ) == 1
                await _assert_guards_enabled(connection)
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        marker.unlink(missing_ok=True)
