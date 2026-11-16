"""Real predecessor PRE jobs must drain before their evidence becomes read-only."""

import asyncio
import gzip
import hashlib
import json
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitTerminal
from tests.conftest import _drop_test_database_schema
from tests.historical_submission_fixtures import _restore_validated_snapshot_rows
from tests.migration_fixtures import _config, current_schema_revision

pytestmark = pytest.mark.postgres_schema_contract
_ARCHIVE = Path(__file__).resolve().parents[1] / 'fixtures' / 'pre_cutover_rows.json.gz'
_ARCHIVE_SHA256 = '49156dd714478ba5d9b446440842b6b40d8372c4f05dcd38e7edb3b6e59f4b59'
_PREDECESSOR = '0070_submission_intake_authority'


def _snapshot(state):
    """Load immutable captures from actual pre-cutover reserve/claim/finalize owners."""
    encoded = _ARCHIVE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == _ARCHIVE_SHA256
    body = json.loads(gzip.decompress(encoded))
    assert body['source_revision'] == 'e2b926288899bcd9b05e1a560ec19b6bca8cfcfc'
    assert body['schema_version'] == 'workstream.pre_cutover_rows.v1'
    snapshot = body['snapshots'][state]
    assert snapshot['revision'] == '0065_claim_starts_work'
    assert [r['status'] for r in snapshot['tables']['selected_pre_submit_runs']] == [state]
    return snapshot


async def _state(url):
    """Observe rows and guard definitions so a refusal cannot hide partial DDL."""
    connection = await asyncpg.connect(url.replace('+asyncpg', ''))
    try:
        return (
            await connection.fetchval('SELECT version_num FROM public.alembic_version'),
            json.loads(await connection.fetchval('SELECT jsonb_agg(to_jsonb(r))::text FROM public.selected_pre_submit_runs r')),
            await connection.fetchval("SELECT pg_get_functiondef('public.guard_selected_pre_submit_run()'::regprocedure)"),
            await connection.fetchval("SELECT array_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='public' AND table_name='selected_pre_submit_runs'"),
        )
    finally:
        await connection.close()


async def _refuse_after_writer_releases(url):
    """Require preflight to wait for an old writer before inspecting live rows."""
    writer = await asyncpg.connect(url.replace('+asyncpg', ''))
    observer = await asyncpg.connect(url.replace('+asyncpg', ''))
    migration = None
    try:
        async with writer.transaction():
            await writer.execute('LOCK TABLE public.selected_pre_submit_runs IN ROW EXCLUSIVE MODE')
            migration = asyncio.create_task(asyncio.to_thread(
                command.upgrade, _config(), '0071_source_first_pre',
            ))

            async def wait_for_lock():
                while True:
                    assert not migration.done(), 'cutover checked rows before excluding old writers'
                    waiting = await observer.fetchval("""SELECT EXISTS (
                        SELECT 1 FROM pg_locks WHERE relation='public.selected_pre_submit_runs'::regclass
                        AND mode='AccessExclusiveLock' AND NOT granted)""")
                    if waiting:
                        return
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(wait_for_lock(), timeout=30)
        with pytest.raises(DBAPIError, match='drain historical PRE runs before source-first cutover'):
            await migration
    finally:
        await writer.close()
        await observer.close()
        if migration is not None:
            await asyncio.gather(migration, return_exceptions=True)


@pytest.mark.parametrize('state', ['queued', 'running', 'completed'])
async def test_source_pre_cutover_preserves_or_refuses_historical_run(
    isolated_database_env, migration_lock, state,
):
    """Refuse live historical owners atomically; retain completed evidence unchanged."""
    snapshot = _snapshot(state)
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        try:
            await asyncio.to_thread(command.upgrade, _config(), snapshot['revision'])
            await _restore_validated_snapshot_rows(
                isolated_database_env, snapshot, expected_revision=snapshot['revision'],
            )
            await asyncio.to_thread(command.upgrade, _config(), _PREDECESSOR)
            before = await _state(isolated_database_env)
            assert before[0] == _PREDECESSOR
            if state != 'completed':
                if state == 'queued':
                    await _refuse_after_writer_releases(isolated_database_env)
                else:
                    with pytest.raises(DBAPIError, match='drain historical PRE runs before source-first cutover'):
                        await asyncio.to_thread(command.upgrade, _config(), '0071_source_first_pre')
                assert await _state(isolated_database_env) == before
            else:
                await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
                after = await _state(isolated_database_env)
                assert after[0] == current_schema_revision()
                assert len(after[1]) == 1
                retained = dict(after[1][0])
                assert retained.pop('source_operation_id') is None
                assert [retained] == before[1]
                terminal = HistoricalSelectedPreSubmitTerminal.from_canonical_body(retained['terminal_json'])
                assert terminal.terminal_digest == retained['terminal_digest']
        finally:
            # Return a clean current schema; never force a historical live row terminal.
            await _drop_test_database_schema(isolated_database_env)
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
