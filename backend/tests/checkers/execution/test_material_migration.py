"""Actual 0008 upgrades preserve valid evidence and refuse unprovable custody."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.migration_fixtures import _config
from tests.post_submit_materialization_helpers import material_fixture
from types import SimpleNamespace

from app.modules.checkers.post_submit_contracts import make_post_submit_result
from tests.checkers.post_submit.support import change_request
from .predecessor_material_helpers import write_terminal
from .support import reserve
from .predecessor_support import predecessor_lease
from .test_material_lineage import terminal_facts

pytestmark = pytest.mark.postgres_schema_contract


async def predecessor_database(url):
    await db_session.dispose_engine()
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        await connection.execute("drop schema public cascade; create schema public")
    finally:
        await connection.close()
    await asyncio.to_thread(command.upgrade, _config(), "0008_checker_execution")


async def retained_snapshot(factory):
    async with factory() as session:
        rows = list((await session.scalars(text("select to_jsonb(r) from checker_runs r order by id"))).all())
        version = await session.scalar(text("select version_num from alembic_version"))
        functions = list((await session.execute(text(
            "select p.proname,pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
            "where n.nspname='public' and p.prokind='f' order by p.proname"
        ))).all())
        triggers = list((await session.execute(text(
            "select tgname,pg_get_triggerdef(oid) from pg_trigger where not tgisinternal order by tgname"
        ))).all())
        return rows, version, functions, triggers


@pytest.mark.parametrize("outcome", ["completed", "infrastructure_failed"])
@pytest.mark.parametrize("valid", [True, False])
async def test_retained_material_upgrade(tmp_path, isolated_database_env, migration_lock, outcome, valid):
    with migration_lock():
        await predecessor_database(isolated_database_env)
        async with material_fixture(tmp_path, isolated_database_env, provision_checker=False) as h:
            await reserve(h)
            lease = await predecessor_lease(h)
            facts = terminal_facts(h, lease, outcome)
            material = facts.material.model_dump(mode="json")
            if not valid:
                # A real but wrong admission is covered separately in direct SQL
                # tests. This retained 0008 row proves no fabricated ID backfill.
                material["admission_id"] = str(h.request.submission_id)
            async with h.factory() as session, session.begin():
                await write_terminal(session, facts, material)
            if valid:
                # Preserve superseded completed/failed history and a current
                # failure that never received material, plus later replica loss.
                successor = SimpleNamespace(**vars(h))
                successor.request = change_request(h.request, evaluation_generation=2,
                                                   evaluation_request_id=new_record_id())
                await reserve(successor)
                next_lease = await predecessor_lease(successor)
                empty = terminal_facts(successor, next_lease, "infrastructure_failed")
                body = empty.result.model_dump(exclude={"result_digest"})
                body["infrastructure_failure_code"] = "material_unavailable"
                empty = empty.model_copy(update={"result": make_post_submit_result(**body), "material": None})
                async with h.factory() as session, session.begin():
                    await write_terminal(session, empty, None)
                    await session.execute(text(
                        "update artifact_replicas set availability_state='unavailable', "
                        "content_id=(select id from artifact_contents where id<>:content limit 1) where id=:id"
                    ), {"id": h.replica_id, "content": facts.material.content_id})
            before = await retained_snapshot(h.factory)
            assert before[1] == "0008_checker_execution"
            if valid:
                await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
                after = await retained_snapshot(h.factory)
                assert after[0] == before[0]
                assert after[1] == "0009_checker_material_lineage"
            else:
                with pytest.raises(IntegrityError, match="retained checker material lacks canonical ART lineage"):
                    await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
                assert await retained_snapshot(h.factory) == before


async def test_upgrade_excludes_writer_until_guard_is_installed(
    tmp_path, isolated_database_env, migration_lock, monkeypatch,
):
    import threading
    from alembic.operations import Operations

    with migration_lock():
        await predecessor_database(isolated_database_env)
        async with material_fixture(tmp_path, isolated_database_env, provision_checker=False) as h:
            await reserve(h)
            lease = await predecessor_lease(h)
            facts = terminal_facts(h, lease, "completed")
            material = facts.material.model_dump(mode="json") | {"admission_id": str(h.request.submission_id)}
            scanned, resume = threading.Event(), threading.Event()
            execute = Operations.execute

            def paused_execute(operations, sql, *args, **kwargs):
                result = execute(operations, sql, *args, **kwargs)
                if isinstance(sql, str) and sql.lstrip().startswith("DO $$ BEGIN") and "retained checker material" in sql:
                    scanned.set()
                    assert resume.wait(20), "migration test did not release scan checkpoint"
                return result

            monkeypatch.setattr(Operations, "execute", paused_execute)
            migration = asyncio.create_task(asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage"))
            writer = None
            pid = asyncio.Queue()

            async def write():
                async with h.factory() as session, session.begin():
                    await pid.put(await session.scalar(text("select pg_backend_pid()")))
                    await write_terminal(session, facts, material)

            try:
                assert await asyncio.to_thread(scanned.wait, 10), "migration did not reach preflight"
                writer = asyncio.create_task(write())
                writer_pid = await asyncio.wait_for(pid.get(), 5)
                waiting = False
                async with h.factory() as observer:
                    for _ in range(100):
                        waiting = bool(await observer.scalar(text(
                            "select cardinality(pg_blocking_pids(:pid)) > 0"
                        ), {"pid": writer_pid}))
                        if waiting or writer.done():
                            break
                        await asyncio.sleep(0.02)
                assert waiting and not writer.done(), "writer entered the preflight/install gap"
                resume.set()
                await asyncio.wait_for(migration, 10)
                with pytest.raises(IntegrityError, match="checker material canonical ART lineage mismatch"):
                    await asyncio.wait_for(writer, 10)
                async with h.factory() as session:
                    assert await session.scalar(text("select status from checker_runs where id=:id"),
                                                {"id": str(facts.result.attempt_id)}) == "running"
            finally:
                resume.set()
                await asyncio.gather(migration, *([writer] if writer is not None else []), return_exceptions=True)
