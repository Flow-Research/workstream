"""Only exact history decision pairs are added; retained authority evidence survives."""

import asyncio
import runpy
from pathlib import Path
import re

import asyncpg
import pytest
from alembic import command

from tests.migration_fixtures import _config as config
from tests.migrations.test_task_queue_authority import insert, CONSTRAINT

pytestmark = pytest.mark.postgres_schema_contract
PAIRS = tuple((prefix + action, "project.task.manage" if prefix else "submission.read_own")
              for prefix in ("", "project.") for action in
              ("task.submission.list", "submission.read", "submission.checker_run.list", "checker_run.read"))


def test_audit_migration_preserves_prior_evidence(isolated_database_env, migration_lock):
    async def connection():
        return await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
    async def reset():
        conn = await connection()
        try:
            await conn.execute("drop schema public cascade; create schema public")
        finally:
            await conn.close()
    async def seed():
        conn = await connection()
        try:
            definition = await conn.fetchval("select pg_get_constraintdef(oid) from pg_constraint where conname=$1", CONSTRAINT)
            pairs = set(re.findall(r"\(action_id\)::text = '([^']+)'::text\) AND \(\(permission_id\)::text = '([^']+)'::text", definition))
            assert len(pairs) > 50
            assert not set(PAIRS) & pairs
            for action, permission in sorted(pairs):
                for allowed in (False, True):
                    await insert(conn, action, permission, allowed=allowed)
            return await conn.fetch("select to_jsonb(a)::text from audit_events a order by id")
        finally:
            await conn.close()
    async def probe(before):
        conn = await connection()
        try:
            assert await conn.fetch("select to_jsonb(a)::text from audit_events a order by id") == before
            for action, permission in PAIRS:
                for allowed in (False, True):
                    assert await insert(conn, action, permission, allowed=allowed)
                    with pytest.raises(asyncpg.CheckViolationError) as exc:
                        await insert(conn, action, "project.read", allowed=allowed)
                    assert exc.value.constraint_name == CONSTRAINT
            snapshot = await conn.fetch("select to_jsonb(a)::text from audit_events a order by id")
            module = runpy.run_path(str(Path(__file__).resolve().parents[3] / "alembic/versions/0006_history_read_authority.py"))
            with pytest.raises(RuntimeError, match="cannot be downgraded"):
                module["downgrade"]()
            assert await conn.fetch("select to_jsonb(a)::text from audit_events a order by id") == snapshot
        finally:
            await conn.close()
    cfg = config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[3] / "alembic"))
    with migration_lock():
        asyncio.run(reset())
        command.upgrade(cfg, "0005_task_evidence_authority")
        before = asyncio.run(seed())
        command.upgrade(cfg, "head")
        asyncio.run(probe(before))


async def test_archived_private_attestation_stays_out_of_history_projection(
    tmp_path, isolated_database_env, migration_lock,
):
    """Read a genuine old packet after upgrade without selecting its private text."""
    from uuid import UUID

    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine

    from app.adapters.tasks import submission_history_repository
    from app.db import session as db_session
    from tests.historical_submission_fixtures import historical_material_fixture
    from tests.migration_fixtures import current_schema_revision

    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, config(), "0024_require_second_review_false")
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            async with h.factory() as session:
                old = (await session.execute(text("""
                    SELECT to_jsonb(s) AS packet,t.project_id,s.contributor_id
                    FROM public.submissions s
                    JOIN public.workstream_tasks t ON t.id=s.task_id
                    WHERE s.id=:id
                """), {"id": h.created["submission_id"]})).one()
            packet = old.packet
            private_attestation = packet["worker_attestation"]
            assert private_attestation and packet["summary"]
            await asyncio.to_thread(command.upgrade, config(), current_schema_revision())
            captured = []

            def capture(_connection, _cursor, _statement, _parameters, context, _many):
                compiled = getattr(context, "compiled", None)
                selected = getattr(getattr(compiled, "statement", None), "selected_columns", ())
                captured.extend(selected or ())

            event.listen(Engine, "before_cursor_execute", capture)
            try:
                async with h.factory() as session:
                    current = await session.scalar(text(
                        "SELECT to_jsonb(s) FROM public.submissions s WHERE s.id=:id"
                    ), {"id": h.created["submission_id"]})
                    assert current.pop("feedback") is None
                    assert {key: current[key] for key in packet} == packet
                    reader = submission_history_repository(session)
                    target = await reader.resolve_submission(
                        UUID(h.created["submission_id"]),
                        project_id=UUID(str(old.project_id)),
                        contributor_id=UUID(str(old.contributor_id)),
                    )
                    assert target is not None
                    rows, more = await reader.read(
                        target, manager=False,
                        submission_id=UUID(h.created["submission_id"]),
                    )
                    assert len(rows) == 1 and not more
                    assert private_attestation not in rows[0].model_dump_json()
                    owned = [column for column in captured
                             if getattr(getattr(column, "table", None), "name", None) == "submissions"]
                    assert owned
                    assert "worker_attestation" not in {column.name for column in owned}
            finally:
                event.remove(Engine, "before_cursor_execute", capture)


# The superseded checker-column migration probes are replaced by the actual
# predecessor refusal in checkers/execution/test_migration.py. The new execution
# owner cannot invent request/lease evidence for retained old runs. Authority
# decision-pair preservation above remains required across the full migration chain.
