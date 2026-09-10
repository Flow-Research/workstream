"""Persisted provider cleanup custody, recovery selection, and exact attempt isolation."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select

from app.modules.projects.guide_compilation.models import ProjectGuideRuntimeAllocation
from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
from app.modules.projects.guide_compilation.runtime_resources import (
    SqlAlchemyGuideRuntimeCleanupCustody, SqlAlchemyGuideRuntimeCustody,
    pending_runtime_resource_cleanup,
)
from .helpers import runtime_configuration
from .test_document_access_postgresql import grant_case as grant_case
from .test_document_file_custody_postgresql import allocated_parents, attachment_intent


async def resources(grant, context):
    custody, container, file = await allocated_parents(grant, context)
    values = attachment_intent(grant, context, container, file)
    async with grant._sessions() as session, session.begin():
        await session.execute(insert(ProjectGuideRuntimeAllocation).values(**values))
    await custody.record_allocated(values['id'], 'cfile_cleanup')
    return custody, {container, file, values['id']}


async def persisted_states(grant):
    async with grant._sessions() as session:
        rows = (await session.execute(select(ProjectGuideRuntimeAllocation.id,
            ProjectGuideRuntimeAllocation.state, ProjectGuideRuntimeAllocation.deleted_at)
            .where(ProjectGuideRuntimeAllocation.attempt_id == grant._attempt_id))).all()
    return {row.id: (row.state, row.deleted_at) for row in rows}


async def test_cleanup_persists_failure_then_deletion_and_replay_after_terminal(grant_case):
    grant, _, _, _, context = grant_case
    custody, identifiers = await resources(grant, context)
    handle = context.material.handle_for(context.material.documents[0])
    await custody.record_document_open(handle)
    assert await custody.opened_handles() == {handle}
    async with grant._sessions() as session, session.begin():
        assert await pending_runtime_resource_cleanup(session) == ()
        await GuideCompilationRepository(session).mark_invalid_terminal(
            attempt_id=grant._attempt_id, failure_code='schema_invalid')
    async with grant._sessions() as session:
        selected = await pending_runtime_resource_cleanup(session)
    assert selected == ((grant._attempt_id, context.material.sha256, runtime_configuration()),)
    retained = SqlAlchemyGuideRuntimeCleanupCustody(grant._sessions, grant._attempt_id,
        context.material.sha256, runtime_configuration().runtime_key)
    rows = await retained.cleanup_resources()
    assert {row.allocation_id for row in rows} == identifiers
    assert {row.provider_id for row in rows} == {'cntr_test', 'file-test', 'cfile_cleanup'}
    for identifier in identifiers:
        await retained.record_cleanup_failed(identifier)
    assert set((state, timestamp) for state, timestamp in (await persisted_states(grant)).values()) == {('cleanup_failed', None)}
    assert {row.allocation_id for row in await retained.cleanup_resources()} == identifiers
    for identifier in identifiers:
        await retained.record_deleted(identifier)
    before = await persisted_states(grant)
    assert all(state == 'deleted' and timestamp is not None for state, timestamp in before.values())
    for identifier in identifiers:
        await retained.record_deleted(identifier)
        await retained.record_cleanup_failed(identifier)
    assert await persisted_states(grant) == before
    assert await retained.cleanup_resources() == ()
    async with grant._sessions() as session:
        assert await pending_runtime_resource_cleanup(session) == ()


@pytest.mark.parametrize('field', ['attempt', 'manifest', 'runtime'])
async def test_cleanup_rejects_wrong_scope_without_changing_owned_resources(grant_case, field):
    grant, _, _, _, context = grant_case
    _, identifiers = await resources(grant, context)
    scope = SqlAlchemyGuideRuntimeCleanupCustody(grant._sessions,
        uuid4() if field == 'attempt' else grant._attempt_id,
        'sha256:'+'a'*64 if field == 'manifest' else context.material.sha256,
        'foreign_runtime' if field == 'runtime' else runtime_configuration().runtime_key)
    before = await persisted_states(grant)
    with pytest.raises(RuntimeError, match='cleanup scope is unavailable'):
        await scope.cleanup_resources()
    for operation in (scope.record_deleted, scope.record_cleanup_failed):
        with pytest.raises(RuntimeError, match='cleanup scope is unavailable'):
            await operation(next(iter(identifiers)))
    assert await persisted_states(grant) == before


async def test_cleanup_unknown_and_foreign_allocation_never_claims_deletion(grant_case):
    grant, _, _, _, context = grant_case
    custody = SqlAlchemyGuideRuntimeCustody(grant._sessions, grant._attempt_id,
        context.material, runtime_configuration().runtime_key)
    identifier = await custody.begin_allocation(kind='container', document_handle=None,
        parent_provider_id=None, expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))
    await custody.record_uncertain(identifier)
    await custody.record_uncertain(identifier)
    assert await custody.cleanup_resources() == ()
    with pytest.raises(ValueError, match='unknown resource deletion cannot be confirmed'):
        await custody.record_deleted(identifier)
    await custody.record_cleanup_failed(identifier)
    for operation in (custody.record_deleted, custody.record_cleanup_failed):
        with pytest.raises(ValueError, match='cleanup allocation is unavailable'):
            await operation(uuid4())
    assert await persisted_states(grant) == {identifier: ('uncertain', None)}


async def test_pending_cleanup_waits_for_latest_allocation_full_run_budget(grant_case):
    grant, _, _, _, context = grant_case
    config = runtime_configuration()
    custody = SqlAlchemyGuideRuntimeCustody(grant._sessions, grant._attempt_id, context.material, config.runtime_key)
    old = datetime.now(timezone.utc)-timedelta(seconds=config.timeout_seconds+config.cleanup_timeout_seconds+60)
    identifier = uuid4()
    async with grant._sessions() as session, session.begin():
        await session.execute(insert(ProjectGuideRuntimeAllocation).values(id=identifier,
            attempt_id=grant._attempt_id, manifest_sha256=context.material.sha256,
            runtime_key=config.runtime_key, kind='container', state='allocating',
            created_at=old, expires_at=old+timedelta(minutes=20)))
    await custody.record_allocated(identifier, 'cntr_expired')
    async with grant._sessions() as session:
        assert await pending_runtime_resource_cleanup(session) == ((grant._attempt_id, context.material.sha256, config),)
    recent = await custody.begin_allocation(kind='file',
        document_handle=context.material.handle_for(context.material.documents[0]),
        parent_provider_id=None, expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))
    await custody.record_allocated(recent, 'file-recent')
    async with grant._sessions() as session:
        assert await pending_runtime_resource_cleanup(session) == ()


@pytest.mark.parametrize('fault,message', [
    ('kind','allocation is invalid'), ('handle','allocation scope is invalid'),
    ('foreign_handle','document is not granted'), ('parent','parent is invalid'),
    ('attachment','parent is unavailable'),
])
async def test_invalid_allocation_cannot_add_provider_intent(grant_case, fault, message):
    grant, _, _, _, context = grant_case
    custody, _ = await resources(grant, context)
    values = dict(kind='container', document_handle=None, parent_provider_id=None,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))
    if fault == 'kind':
        values['kind'] = 'unbounded'
    elif fault == 'handle':
        values['document_handle'] = context.material.handle_for(context.material.documents[0])
    elif fault == 'foreign_handle':
        values.update(kind='file', document_handle=str(uuid4()))
    elif fault == 'parent':
        values['parent_provider_id'] = 'cntr_foreign'
    else:
        values.update(kind='attachment', document_handle=context.material.handle_for(context.material.documents[0]),
            parent_provider_id='cntr_foreign')
    before = await persisted_states(grant)
    with pytest.raises(ValueError, match=message):
        await custody.begin_allocation(**values)
    assert await persisted_states(grant) == before


async def test_invalid_receipt_and_unstaged_document_cannot_create_evidence(grant_case):
    grant, _, _, _, context = grant_case
    custody = SqlAlchemyGuideRuntimeCustody(grant._sessions, grant._attempt_id,
        context.material, runtime_configuration().runtime_key)
    identifier = await custody.begin_allocation(kind='container', document_handle=None,
        parent_provider_id=None, expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))
    for provider in ('arbitrary-provider-id', 'file-wrong_kind'):
        with pytest.raises(ValueError, match='identity is invalid|receipt conflicts'):
            await custody.record_allocated(identifier, provider)
    with pytest.raises(ValueError, match='allocation is unavailable'):
        await custody.record_allocated(uuid4(), 'cntr_foreign')
    handle = context.material.handle_for(context.material.documents[0])
    for selected, error in ((str(uuid4()), 'document is not granted'), (handle, 'staging is unconfirmed')):
        with pytest.raises(ValueError, match=error):
            await custody.record_document_open(selected)
    assert await custody.opened_handles() == set()
    assert await persisted_states(grant) == {identifier: ('allocating', None)}
    async with grant._sessions() as session, session.begin():
        await GuideCompilationRepository(session).mark_invalid_terminal(
            attempt_id=grant._attempt_id, failure_code='schema_invalid')
    with pytest.raises(RuntimeError, match='runtime custody is unavailable'):
        await custody.begin_allocation(kind='container', document_handle=None,
            parent_provider_id=None, expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))
    assert await persisted_states(grant) == {identifier: ('allocating', None)}


async def test_cleanup_excludes_existing_other_attempt_allocations(clean_postgres_database):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from .helpers import seed_database
    from .test_repository_persistence import _accepted_attempt

    values = await seed_database(clean_postgres_database, generations=2)
    engine = create_async_engine(clean_postgres_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        first, _, first_context = await _accepted_attempt(sessions, values, generation=1)
        second, _, second_context = await _accepted_attempt(sessions, values, generation=2)
        own = SqlAlchemyGuideRuntimeCleanupCustody(sessions, first.id, first_context.material.sha256,
            runtime_configuration().runtime_key)
        foreign = SqlAlchemyGuideRuntimeCleanupCustody(sessions, second.id, second_context.material.sha256,
            runtime_configuration().runtime_key)
        own_rows, foreign_rows = await own.cleanup_resources(), await foreign.cleanup_resources()
        assert len(own_rows) == len(foreign_rows) == 3
        assert {row.allocation_id for row in own_rows}.isdisjoint(row.allocation_id for row in foreign_rows)
        for operation in (own.record_deleted, own.record_cleanup_failed):
            with pytest.raises(ValueError, match='cleanup allocation is unavailable'):
                await operation(foreign_rows[0].allocation_id)
        assert await own.cleanup_resources() == own_rows
        assert await foreign.cleanup_resources() == foreign_rows
        async with sessions() as session:
            assert {row[0] for row in await pending_runtime_resource_cleanup(session)} == {first.id, second.id}
            assert len(await pending_runtime_resource_cleanup(session, limit=1)) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize('fault', [None, 'identity', 'construction', 'cleanup'])
async def test_cleanup_composition_uses_retained_configuration_and_closes_runtime(grant_case, fault):
    from app.adapters.projects import cleanup_project_guide_runtime_resources

    grant, _, _, _, context = grant_case
    _, identifiers = await resources(grant, context)
    async with grant._sessions() as session, session.begin():
        await GuideCompilationRepository(session).mark_invalid_terminal(
            attempt_id=grant._attempt_id, failure_code='schema_invalid')
    before = await persisted_states(grant)
    constructed, cleaned, closed = [], [], []

    class Runtime:
        identity = 'wrong-runtime' if fault == 'identity' else runtime_configuration().adapter_identity

        async def cleanup_resources(self, custody):
            rows = await custody.cleanup_resources()
            assert {row.allocation_id for row in rows} == identifiers
            cleaned.append(custody)
            if fault == 'cleanup':
                raise RuntimeError('provider unavailable')
            for row in rows:
                await custody.record_deleted(row.allocation_id)
            return True

        async def aclose(self):
            closed.append(self)

    runtime = Runtime()

    def factory(configuration):
        constructed.append(configuration)
        if fault == 'construction':
            raise RuntimeError('runtime unavailable')
        return runtime

    result = await cleanup_project_guide_runtime_resources(grant._sessions, runtime_factory=factory)
    assert result == {'selected': 1, 'completed': int(fault is None)}
    assert constructed == [runtime_configuration()]
    assert len(cleaned) == int(fault in (None, 'cleanup'))
    assert closed == ([] if fault == 'construction' else [runtime])
    if fault is not None:
        assert await persisted_states(grant) == before
    else:
        assert all(state == 'deleted' and timestamp is not None
            for state, timestamp in (await persisted_states(grant)).values())
        assert await cleanup_project_guide_runtime_resources(grant._sessions, runtime_factory=factory) == {
            'selected': 0, 'completed': 0}
        assert constructed == [runtime_configuration()]
