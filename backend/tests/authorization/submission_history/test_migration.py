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
