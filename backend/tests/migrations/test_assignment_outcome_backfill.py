"""Isolated PostgreSQL proof of0049's assignment fragment and0048's exact guard."""

import json
import runpy
from datetime import timedelta
from pathlib import Path

import asyncpg
import pytest

from app.core.identifiers import new_record_id
from scripts.schema_baseline_sql import split_sql_statements
from tests.conftest import _assert_owned_test_database, _drop_test_database_schema

pytestmark = pytest.mark.postgres_schema_contract
VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


async def _snapshot(connection):
    return {table: [row[0] for row in await connection.fetch(
        f"SELECT to_jsonb(a)::text FROM public.{table} a ORDER BY id"
    )] for table in ("task_assignments", "audit_events")}


async def test_assignment_backfill_preserves_terminal_guarded_rows(isolated_database_env, migration_lock):
    """Test the exact SQL fragment, not a complete historical upgrade or product state."""
    url = isolated_database_env
    guard_sql = runpy.run_path(str(VERSIONS / "0048_revision_exhaustion.py"))["EXHAUSTION_TRANSITION_GUARDS"]
    backfill = runpy.run_path(str(VERSIONS / "0049_attempt_outcome_findings.py"))["BACKFILL_ASSIGNMENT_STARTS"]
    with migration_lock():
        await _drop_test_database_schema(url)
        connection = await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql", 1))
        try:
            await _assert_owned_test_database(connection, url)
            await connection.execute("""CREATE TABLE public.task_assignments (
                id uuid PRIMARY KEY,task_id uuid NOT NULL,status text NOT NULL,
                assigned_at timestamptz NOT NULL,started_at timestamptz,released_at timestamptz,updated_at timestamptz);
                CREATE TABLE public.audit_events (id uuid PRIMARY KEY,entity_type text,entity_id uuid,event_type text,created_at timestamptz);""")
            for statement in split_sql_statements(guard_sql):
                if statement.startswith("CREATE FUNCTION") or statement.startswith("CREATE TRIGGER a_revision_terminal_assignment_immutable"):
                    await connection.execute(statement)
            base = await connection.fetchval("SELECT clock_timestamp()-interval '1 day'")
            expected = {}
            for status in ("active", "revision_exhausted", "revision_expired"):
                identity, task = new_record_id(), new_record_id()
                released = None if status == "active" else base+timedelta(seconds=600)
                await connection.execute("INSERT INTO public.task_assignments VALUES ($1,$2,$3,$4,NULL,$5,$4)",
                                         identity, task, status, base, released)
                expected[identity] = base+timedelta(seconds=3)
                for seconds, event in ((-10,"TaskStarted"),(3,"TaskStarted"),(5,"TaskStartOverridden"),(700,"TaskStarted")):
                    await connection.execute("INSERT INTO public.audit_events VALUES ($1,'task',$2,$3,$4)",
                                             new_record_id(), task, event, base+timedelta(seconds=seconds))
            terminal = next(row["id"] for row in await connection.fetch("SELECT id FROM public.task_assignments WHERE status='revision_exhausted'"))

            async def protected():
                with pytest.raises(asyncpg.CheckViolationError, match="exhausted assignment is immutable"):
                    await connection.execute("UPDATE public.task_assignments SET started_at=assigned_at WHERE id=$1", terminal)

            async def enabled():
                assert await connection.fetchval("SELECT tgenabled::text FROM pg_trigger WHERE tgname='a_revision_terminal_assignment_immutable'") == "O"

            await protected()
            before = await _snapshot(connection)
            # Fail within the exact statements after disable, then prove complete rollback.
            with pytest.raises(asyncpg.CheckViolationError, match="probe_reject_backfill"):
                async with connection.transaction():
                    await connection.execute("ALTER TABLE public.task_assignments ADD CONSTRAINT probe_reject_backfill CHECK (started_at IS NULL)")
                    for index, statement in enumerate(split_sql_statements(backfill)):
                        await connection.execute(statement)
                        if index == 0:
                            assert await connection.fetchval("SELECT tgenabled::text FROM pg_trigger WHERE tgname='a_revision_terminal_assignment_immutable'") == "D"
            assert await _snapshot(connection) == before
            await enabled()
            await protected()
            async with connection.transaction():
                for statement in split_sql_statements(backfill):
                    await connection.execute(statement)
            await enabled()
            after = await _snapshot(connection)
            assert after["audit_events"] == before["audit_events"]
            for old, new in zip(before["task_assignments"], after["task_assignments"], strict=True):
                old, new = json.loads(old), json.loads(new)
                assert {k:v for k,v in old.items() if k not in {"started_at","updated_at"}} == {
                    k:v for k,v in new.items() if k not in {"started_at","updated_at"}}
            for row in await connection.fetch("SELECT * FROM public.task_assignments"):
                assert row["started_at"] == expected[row["id"]]
                assert row["updated_at"] == (row["released_at"] or row["started_at"])
            await protected()
        finally:
            await connection.close()
