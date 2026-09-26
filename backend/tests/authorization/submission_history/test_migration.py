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


async def _before_custody(connection):
    """Restore only this unmerged migration's predecessor checker schema in a transaction."""
    from sqlalchemy import text
    for table, owner in (("checker_runs", "run"), ("checker_results", "result")):
        for suffix in ("custody", "no_truncate"):
            await connection.execute(text(f"drop trigger checker_{owner}_{suffix} on {table}"))
        await connection.execute(text(f"drop function protect_checker_{owner}_custody()"))
    for table, name in (("checker_results", "fk_checker_results_run_ownership"),
                        ("checker_runs", "fk_checker_runs_predecessor_ownership"),
                        ("checker_runs", "uq_checker_runs_ownership")):
        await connection.execute(text(f"alter table {table} drop constraint {name}"))
    for table, column, parent in (
        ("checker_runs", "supersedes_checker_run_id", "checker_runs"),
        ("checker_results", "checker_run_id", "checker_runs"),
        ("checker_results", "task_id", "workstream_tasks"),
        ("checker_results", "submission_id", "submissions"),
    ):
        await connection.execute(text(f"alter table {table} add constraint fk_{table}_{column}_{parent} foreign key ({column}) references {parent}(id)"))


def _upgrade_custody(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = runpy.run_path(str(Path(__file__).resolve().parents[3] / "alembic/versions/0006_history_read_authority.py"))
    with Operations.context(MigrationContext.configure(connection)):
        module["upgrade"]()


@pytest.mark.parametrize("damage", [None, "result", "predecessor"])
async def test_checker_migration_preserves_or_refuses_retained_rows(task_client, monkeypatch, damage):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.db import session as db_session
    from .test_storage import retained_pair
    case, other = await retained_pair(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        connection = await session.connection()
        await _before_custody(connection)
        if damage == "result":
            await connection.execute(text("update checker_results set checker_run_id=:run where checker_run_id=:source"), {"run": case[3], "source": other[2]})
        elif damage == "predecessor":
            await connection.execute(text("update checker_runs set supersedes_checker_run_id=:run where id=:source"), {"run": case[3], "source": other[2]})
        async def snapshot():
            return [(await connection.execute(text(f"select to_jsonb(r) from {table} r order by id"))).scalars().all()
                    for table in ("checker_runs", "checker_results")]
        before = await snapshot()
        if damage:
            with pytest.raises(IntegrityError, match="retained checker ownership is inconsistent"):
                async with connection.begin_nested():
                    await connection.run_sync(_upgrade_custody)
            assert await connection.scalar(text("select count(*) from pg_trigger where tgname='checker_run_custody'")) == 0
            assert await connection.scalar(text("select count(*) from pg_constraint where conname='uq_checker_runs_ownership'")) == 0
        else:
            await connection.run_sync(_upgrade_custody)
            assert await connection.scalar(text("select count(*) from pg_trigger where tgname='checker_run_custody'")) == 1
        assert await snapshot() == before
        await session.rollback()


async def test_checker_migration_locks_out_coherent_rebinding(task_client, monkeypatch):
    """A writer queued during preflight observes installed custody after commit."""
    from alembic import op
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.db import session as db_session
    from .test_storage import retained_pair
    case, other = await retained_pair(task_client, monkeypatch)
    factory = db_session.get_session_factory()
    async with factory() as prepare:
        audit_definition = await prepare.scalar(text("select pg_get_constraintdef(oid) from pg_constraint where conname=:name"), {"name": CONSTRAINT})
        await _before_custody(await prepare.connection())
        await prepare.commit()
    preflight = asyncio.Event()
    original_execute = op.execute
    def pause_after_preflight(sql, *args, **kwargs):
        result = original_execute(sql, *args, **kwargs)
        if isinstance(sql, str) and 'DO $$ BEGIN' in sql:
            preflight.set()
            original_execute('select pg_advisory_xact_lock(447006)')
        return result
    monkeypatch.setattr(op, 'execute', pause_after_preflight)
    async def upgrade():
        async with factory() as session, session.begin():
            await (await session.connection()).run_sync(_upgrade_custody)
    async def rebind():
        async with factory() as session:
            await session.execute(text("update checker_runs set task_id=:task, submission_id=:submission, attempt_number=2, is_current_for_submission=false where id=:run"),
                                  {"task": other[0], "submission": other[1], "run": case[3]})
            await session.commit()
    async with factory() as gate:
        await gate.execute(text('select pg_advisory_xact_lock(447006)'))
        migration = asyncio.create_task(upgrade())
        writer = None
        try:
            await asyncio.wait_for(preflight.wait(), timeout=5)
            writer = asyncio.create_task(rebind())
            # Poll actual lock waiting, rather than infer blocking from a slow coroutine.
            waiting = False
            for _ in range(100):
                waiting = bool(await gate.scalar(text("select exists(select 1 from pg_locks where relation='checker_runs'::regclass and not granted)")))
                if waiting:
                    break
                if writer.done():
                    writer.result()
                    break
                await asyncio.sleep(0.02)
            assert waiting, 'coherent writer was not blocked by migration custody lock'
            await gate.rollback()
            await asyncio.wait_for(migration, timeout=5)
            with pytest.raises(IntegrityError, match='checker run custody is immutable'):
                await asyncio.wait_for(writer, timeout=5)
        finally:
            await gate.rollback()
            for task in (migration, writer):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (migration, writer) if task is not None), return_exceptions=True)
    async with factory() as session:
        row = (await session.execute(text('select task_id,submission_id from checker_runs where id=:id'), {'id': case[3]})).one()
        assert str(row.task_id) == case[1] and str(row.submission_id) == case[2]
        await session.execute(text(f"alter table audit_events drop constraint {CONSTRAINT}"))
        await session.execute(text(f"alter table audit_events add constraint {CONSTRAINT} {audit_definition}"))
        await session.commit()
