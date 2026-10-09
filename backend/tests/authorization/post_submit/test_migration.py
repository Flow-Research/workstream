"""The actual predecessor upgrade preserves queued work and refuses invented receipts."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.checkers.execution.historical_execution import historical_lease, historical_reserve
from tests.checkers.execution.test_material_migration import retained_snapshot
from tests.historical_submission_fixtures import historical_material_fixture

pytestmark = pytest.mark.postgres_schema_contract


@pytest.mark.parametrize("unprovable_receipt", [False, True])
async def test_actual_upgrade_preserves_or_refuses_without_repair(
    tmp_path, isolated_database_env, migration_lock, unprovable_receipt
):
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_material_fixture(
            tmp_path, isolated_database_env, provision_checker=False
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            await historical_reserve(h)
            if unprovable_receipt:
                await historical_lease(h)
            before = await retained_snapshot(h.factory)
            if unprovable_receipt:
                with pytest.raises(IntegrityError, match="retained checker authorization receipts are unprovable"):
                    await asyncio.to_thread(command.upgrade, _config(), "0010_post_submit_authority")
                assert await retained_snapshot(h.factory) == before
            else:
                await asyncio.to_thread(command.upgrade, _config(), "0010_post_submit_authority")
                after = await retained_snapshot(h.factory)
                assert after[0] == before[0]
                assert after[1] == "0010_post_submit_authority"


async def test_upgrade_excludes_writer_across_receipt_preflight(
    tmp_path, isolated_database_env, migration_lock, monkeypatch
):
    import threading
    from alembic.operations import Operations
    from sqlalchemy import text

    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_material_fixture(
            tmp_path, isolated_database_env, provision_checker=False
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            reserved = await historical_reserve(h)
            scanned, resume = threading.Event(), threading.Event()
            execute = Operations.execute

            def pause_after_scan(operations, sql, *args, **kwargs):
                result = execute(operations, sql, *args, **kwargs)
                if isinstance(sql, str) and sql.lstrip().startswith("DO $$ BEGIN") and "retained checker authorization receipts" in sql:
                    scanned.set()
                    assert resume.wait(20), "receipt migration scan was not released"
                return result

            monkeypatch.setattr(Operations, "execute", pause_after_scan)
            migration = asyncio.create_task(asyncio.to_thread(command.upgrade, _config(), "0010_post_submit_authority"))
            writer = None
            writer_pid = asyncio.Queue()

            async def write_predecessor_receipt():
                from app.core.identifiers import new_record_id
                async with h.factory() as session, session.begin():
                    await writer_pid.put(await session.scalar(text("SELECT pg_backend_pid()")))
                    await session.execute(text("""UPDATE checker_runs SET status='running',
                        worker_lease_id=:lease,worker_lease_generation=1,
                        worker_lease_expires_at=clock_timestamp()+interval '300 seconds',
                        execute_evidence_id=:receipt,started_at=clock_timestamp() WHERE id=:id"""),
                        {"lease":new_record_id(),"receipt":new_record_id(),"id":reserved.attempt_id})

            try:
                assert await asyncio.to_thread(scanned.wait, 10)
                writer = asyncio.create_task(write_predecessor_receipt())
                pid = await asyncio.wait_for(writer_pid.get(), 5)
                blocked = False
                async with h.factory() as observer:
                    for _ in range(100):
                        blocked = bool(await observer.scalar(text(
                            "SELECT cardinality(pg_blocking_pids(:pid))>0"
                        ), {"pid": pid}))
                        if blocked or writer.done():
                            break
                        await asyncio.sleep(0.02)
                assert blocked and not writer.done(), "writer crossed the receipt preflight/install gap"
                resume.set()
                await asyncio.wait_for(migration, 10)
                with pytest.raises(IntegrityError, match="receipt custody|foreign key"):
                    await asyncio.wait_for(writer, 10)
                async with h.factory() as session:
                    row = (await session.execute(text("SELECT status,execute_evidence_id,worker_lease_id FROM checker_runs WHERE id=:id"), {"id": reserved.attempt_id})).one()
                    assert row == ("queued", None, None)
                from tests.checkers.execution.support import provision_checker_service

                await provision_checker_service(h.factory)
                valid = await historical_lease(h)
                assert valid.reservation.attempt_id == reserved.attempt_id
            finally:
                resume.set()
                await asyncio.gather(migration, *([writer] if writer else []), return_exceptions=True)
