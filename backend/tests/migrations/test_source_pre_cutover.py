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


def _admission_archive():
    """Read both sides of the same genuine predecessor admission consumption."""
    encoded = _ARCHIVE.with_name('pre_cutover_admissions.json.gz').read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == '37bfa6433b233fb2a82b3c60c42b2946e747168452d51ca84203c64be5fee520'
    body = json.loads(gzip.decompress(encoded))
    assert body['schema_version'] == 'workstream.pre_cutover_admissions.v1'
    assert body['source_revision'] == 'e2b926288899bcd9b05e1a560ec19b6bca8cfcfc'
    assert body['source_test'] == 'tests/test_capture_pre_cutover_admissions.py::test_capture'
    snapshots = body['snapshots']
    for state, snapshot in snapshots.items():
        assert snapshot['revision'] == '0065_claim_starts_work'
        assert [r['status'] for r in snapshot['tables']['submission_bundle_admissions']] == [state]
    assert snapshots['ready']['tables']['submission_bundle_admissions'][0]['id'] == snapshots['consumed']['tables']['submission_bundle_admissions'][0]['id']
    return snapshots


async def _retained_rows_and_functions(url, tables):
    """Compare all captured nonempty tables and all public function definitions."""
    connection = await asyncpg.connect(url.replace('+asyncpg', ''))
    try:
        rows = {}
        for table in tables:
            if table != 'alembic_version':
                rows[table] = await connection.fetchval(
                    f'SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text),\'[]\')::text FROM public."{table}" r'
                )
        functions = dict(await connection.fetch("""SELECT p.oid::regprocedure::text, pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' AND p.prokind='f'"""))
        return rows, functions
    finally:
        await connection.close()


async def _refuse_old_consumption_and_allow_stale(url, consumed):
    """Use captured consumption fields; require the new guard before other constraints."""
    from uuid import UUID

    connection = await asyncpg.connect(url.replace('+asyncpg', ''))
    try:
        row_id = UUID(consumed['id'])
        query = 'SELECT to_jsonb(a)::text FROM public.submission_bundle_admissions a WHERE id=$1'
        before = await connection.fetchval(query, row_id)
        with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError, match='new submission binding requires accepted source custody'):
            async with connection.transaction():
                await connection.execute("""UPDATE public.submission_bundle_admissions
                    SET (status,consumed_at,consumed_by_submission_id,consumed_by_submission_version)=
                      (SELECT status,consumed_at,consumed_by_submission_id,consumed_by_submission_version
                       FROM jsonb_populate_record(NULL::public.submission_bundle_admissions,$1::jsonb))
                    WHERE id=$2""", json.dumps(consumed), row_id)
        assert await connection.fetchval(query, row_id) == before
        await connection.execute("""UPDATE public.submission_bundle_admissions
            SET status='stale',stale_at=clock_timestamp(),stale_reason='submission_flow_cutover'
            WHERE id=$1""", row_id)
        after = json.loads(await connection.fetchval(query, row_id))
        assert after['status'] == 'stale' and after['stale_at'] is not None
        assert after['stale_reason'] == 'submission_flow_cutover'
        original = json.loads(before)
        mutable = {'status','stale_at','stale_reason'}
        assert {k:v for k,v in after.items() if k not in mutable} == {k:v for k,v in original.items() if k not in mutable}
    finally:
        await connection.close()


async def _upgrade_admission_guard_behind_writer(url):
    """Observe real cutover serialization before replacing the admission guard."""
    writer = await asyncpg.connect(url.replace('+asyncpg', ''))
    observer = await asyncpg.connect(url.replace('+asyncpg', ''))
    migration = None
    try:
        async with writer.transaction():
            await writer.execute('LOCK TABLE public.submission_bundle_admissions IN ROW EXCLUSIVE MODE')
            migration = asyncio.create_task(asyncio.to_thread(command.upgrade, _config(), current_schema_revision()))

            async def wait_for_lock():
                while True:
                    if migration.done():
                        await migration
                        raise AssertionError('source binding cutover did not wait for the old writer')
                    if await observer.fetchval("""SELECT EXISTS (
                        SELECT 1 FROM pg_locks WHERE relation='public.submission_bundle_admissions'::regclass
                        AND mode='AccessExclusiveLock' AND NOT granted)"""):
                        return
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(wait_for_lock(), timeout=30)
        await migration
    finally:
        await writer.close()
        await observer.close()
        if migration is not None:
            await asyncio.gather(migration, return_exceptions=True)


@pytest.mark.parametrize('state', ['ready', 'consumed'])
async def test_source_binding_cutover_preserves_history_and_closes_old_consumption(
    isolated_database_env, migration_lock, state,
):
    """Replace only the admission transition guard; never rewrite retained rows."""
    snapshots = _admission_archive()
    snapshot = snapshots[state]
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        try:
            await asyncio.to_thread(command.upgrade, _config(), snapshot['revision'])
            await _restore_validated_snapshot_rows(isolated_database_env, snapshot, expected_revision=snapshot['revision'])
            await asyncio.to_thread(command.upgrade, _config(), '0082_policy_phase_cardinality')
            await asyncio.to_thread(command.upgrade, _config(), '0083_accepted_revision')
            before, old_functions = await _retained_rows_and_functions(isolated_database_env, snapshot['tables'])
            if state == 'ready':
                await _upgrade_admission_guard_behind_writer(isolated_database_env)
            else:
                await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
            after, new_functions = await _retained_rows_and_functions(isolated_database_env, snapshot['tables'])
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
            assert await _retained_rows_and_functions(isolated_database_env, snapshot['tables']) == (after, new_functions)
            assert after == before
            assert set(old_functions) == set(new_functions)
            assert {k for k in old_functions if old_functions[k] != new_functions[k]} == {'guard_submission_bundle_admission_lineage()'}
            if state == 'ready':
                await _refuse_old_consumption_and_allow_stale(
                    isolated_database_env, snapshots['consumed']['tables']['submission_bundle_admissions'][0],
                )
        finally:
            await _drop_test_database_schema(isolated_database_env)
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
