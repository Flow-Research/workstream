from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import asyncpg  # type: ignore[import-not-found]

TRUNCATE_GUARDED_TABLES = {
    "admin_role_grants",
    "audit_events",
    "authority_control",
    "authority_idempotency_records",
    "outbox_events",
}


def test_database_reset_preserves_schema_and_restores_guards(
    postgres_database_url: str,
    reset_test_database_state: Callable[..., Awaitable[None]],
) -> None:
    """The fast reset is complete, repeatable, and schema preserving."""

    async def exercise() -> None:
        url = postgres_database_url.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            head_before = await connection.fetchval("select version_num from alembic_version")
            migration_before = await connection.fetchrow(
                "select * from actor_profile_migration_state"
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

        await reset_test_database_state(postgres_database_url)
        await reset_test_database_state(postgres_database_url)

        connection = await asyncpg.connect(url)
        try:
            control = await connection.fetchrow(
                "select bootstrap_completed, bootstrap_grant_id, version from authority_control"
            )
            head_after = await connection.fetchval("select version_num from alembic_version")
            migration_after = await connection.fetchrow(
                "select * from actor_profile_migration_state"
            )
            counter_count = await connection.fetchval(
                "select count(*) from api_rate_control_counters"
            )
            trigger_rows = await connection.fetch(
                "select c.relname as table_name, bool_and(t.tgenabled = 'O') as enabled "
                "from pg_trigger t join pg_class c on c.oid = t.tgrelid "
                "where not t.tgisinternal and c.relname = any($1::text[]) "
                "group by c.relname",
                sorted(TRUNCATE_GUARDED_TABLES),
            )
        finally:
            await connection.close()

        assert dict(control) == {
            "bootstrap_completed": False,
            "bootstrap_grant_id": None,
            "version": 0,
        }
        assert counter_count == 0
        assert head_after == head_before
        assert migration_after == migration_before
        assert {row["table_name"] for row in trigger_rows} == TRUNCATE_GUARDED_TABLES
        assert all(row["enabled"] for row in trigger_rows)

    asyncio.run(exercise())
