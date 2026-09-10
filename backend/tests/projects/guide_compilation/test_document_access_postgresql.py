"""Real PostgreSQL lineage and canonical scratch proof for exact guide byte grants."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.modules.projects.api.guide_documents import GuideDocumentUnavailable
from app.adapters.projects import project_guide_document_scope_port
from app.adapters.artifacts import guide_document_manifest_port
from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant
from app.modules.artifacts.preparation import ArtifactPreparationLimits, ArtifactScratchManager, ArtifactPreparationService
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec, ArtifactStorageNamespaceError
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from .helpers import seed_database, context, SOURCE_BYTES, SOURCE_SHA256
from .test_hidden_orchestrator_postgresql import _authorized_attempt, _backend


class ReadStore:
    identity = SimpleNamespace(provider_key="local")

    def __init__(self):
        self.payload = SOURCE_BYTES
        self.calls = []
        self.entered = asyncio.Event()
        self.release = None
        self.closed = 0

    async def open(self, reference):
        self.calls.append(reference)
        self.entered.set()
        try:
            if self.release is not None:
                await self.release.wait()
            yield self.payload
        finally:
            self.closed += 1


class ReadAuthority:
    def __init__(self):
        self.denied = False
        self.facts = []
        self.closed = 0

    async def prepare(self, *, facts, idempotency_key):
        if self.denied:
            raise ArtifactAuthorityDeniedError("guide read denied")
        return facts

    async def consume(self, *, prepared_authorization, facts):
        assert prepared_authorization == facts
        self.facts.append(facts)

    def close(self):
        self.closed += 1


@pytest.fixture
async def grant_case(clean_postgres_database, tmp_path):
    values = await seed_database(clean_postgres_database)
    request = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    backend = _backend(sessions)
    state = await backend.load(request.attempt_id)
    assert (await backend.fence(state)).dispatch_permitted
    compilation = context(values)
    store, authority = ReadStore(), ReadAuthority()
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=ArtifactPreparationLimits(
        maximum_files=2, maximum_concurrency=2, minimum_free_bytes=0,
        reservation_ttl_seconds=30, total_deadline_seconds=10, cleanup_margin_seconds=5,
        stream_buffer_bytes=1024, maximum_source_bytes=1024 * 1024,
    ))
    grant = ScopedGuideDocumentGrant(sessions, store, ArtifactStorageNamespaceSpec(
        backend="local", adapter="local", provider_profile="test",
        namespace_descriptor={"root": "guide-compilation-fixture"}, namespace_fingerprint=SOURCE_SHA256,
    ), ArtifactPreparationService(manager), lambda session: authority,
        scope_factory=project_guide_document_scope_port, manifest_factory=guide_document_manifest_port,
        attempt_id=request.attempt_id, manifest=compilation.material,
        lifetime_seconds=30, maximum_document_bytes=1024 * 1024)
    try:
        yield grant, store, authority, manager, compilation
    finally:
        await grant.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_exact_original_is_verified_before_yield_and_scratch_released(grant_case):
    grant, store, authority, manager, compilation = grant_case
    document = compilation.material.documents[0]
    async with grant.open(compilation.material.handle_for(document)) as opened:
        assert opened.document == document
        assert opened.reader.read() == SOURCE_BYTES
        assert len(store.calls) == store.closed == 1
        assert authority.facts[0].document_version_id == document.ingest_id
        assert authority.facts[0].compilation_attempt_id == grant._attempt_id
        assert authority.facts[0].manifest_sha256 == compilation.material.sha256
    assert opened.reader.closed
    assert (await manager.usage()).reservation_count == 0
    await grant.close()
    with pytest.raises(GuideDocumentUnavailable, match="access_denied"):
        async with grant.open(compilation.material.handle_for(document)):
            pytest.fail("closed grant yielded bytes")
    assert len(store.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["foreign_handle", "other_run_handle", "expired", "over_limit", "wrong_attempt", "changed_manifest", "namespace_drift", "terminal_attempt", "denied"])
async def test_invalid_scope_or_authority_denies_before_store_access(grant_case, kind):
    grant, store, authority, manager, compilation = grant_case
    document = compilation.material.documents[0]
    handle = compilation.material.handle_for(document)
    if kind == "foreign_handle":
        handle = str(uuid4())
    elif kind == "other_run_handle":
        foreign = compilation.material.model_copy(update={"setup_run_id": uuid4()})
        handle = foreign.handle_for(document)
    elif kind == "expired":
        grant._deadline = 0
    elif kind == "over_limit":
        grant._maximum_bytes = document.byte_count - 1
    elif kind == "wrong_attempt":
        grant._attempt_id = uuid4()
    elif kind == "changed_manifest":
        grant._manifest = compilation.material.model_copy(update={"source_snapshot_hash": "sha256:" + "0" * 64})
    elif kind == "terminal_attempt":
        from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
        async with grant._sessions() as session, session.begin():
            await GuideCompilationRepository(session).mark_invalid_terminal(
                attempt_id=grant._attempt_id, failure_code="schema_invalid")
    elif kind == "namespace_drift":
        grant._namespace = replace(grant._namespace, namespace_fingerprint="sha256:" + "0" * 64)
    else:
        authority.denied = True
    with pytest.raises((GuideDocumentUnavailable, ArtifactStorageNamespaceError, ArtifactAuthorityDeniedError)):
        async with grant.open(handle):
            pytest.fail("unauthorized original yielded")
    assert not store.calls
    assert not authority.facts
    assert (await manager.usage()).reservation_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [SOURCE_BYTES[:-1], SOURCE_BYTES + b"x", b"x" * len(SOURCE_BYTES)])
async def test_changed_original_never_leaves_art_and_releases_scratch(grant_case, payload):
    grant, store, _authority, manager, compilation = grant_case
    store.payload = payload
    with pytest.raises(GuideDocumentUnavailable, match="integrity_mismatch"):
        async with grant.open(compilation.material.handle_for(compilation.material.documents[0])):
            pytest.fail("corrupted bytes left ART")
    assert len(store.calls) == store.closed == 1
    assert (await manager.usage()).reservation_count == 0


@pytest.mark.asyncio
async def test_cancellation_closes_source_and_scratch_before_return(grant_case):
    grant, store, authority, manager, compilation = grant_case
    store.release = asyncio.Event()

    async def read():
        async with grant.open(compilation.material.handle_for(compilation.material.documents[0])):
            pytest.fail("cancelled read yielded bytes")

    task = asyncio.create_task(read())
    await asyncio.wait_for(store.entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.closed == authority.closed == 1
    assert (await manager.usage()).reservation_count == 0


async def _observed_upload(sessions, document, *, defect=None):
    """Arrange a recovered put receipt without modifying retained acknowledgement."""
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactPutObservationReceipt
    async with sessions() as session, session.begin():
        put = await session.get(ArtifactPutAttempt, str(document.put_attempt_id))
        put.receipt_id = None
        put.terminal_result_code = "document_stored_observed"
        put.execution_generation = 1
        if defect != "missing_receipt":
            session.add(ArtifactPutObservationReceipt(
                id=str(uuid4()), put_attempt_id=put.id,
                execution_generation=2 if defect == "wrong_generation" else 1,
                outcome="observed_confirmed", expected_sha256=put.sha256,
                expected_byte_count=put.byte_count,
                observed_sha256="sha256:" + "f" * 64 if defect == "wrong_digest" else put.sha256,
                observed_byte_count=put.byte_count + 1 if defect == "wrong_size" else put.byte_count,
            ))


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", [None, "missing_receipt", "wrong_generation", "wrong_digest", "wrong_size"])
async def test_recovered_document_requires_exact_observation_receipt_before_read(grant_case, defect):
    grant, store, authority, manager, compilation = grant_case
    document = compilation.material.documents[0]
    await _observed_upload(grant._sessions, document, defect=defect)
    if defect is not None:
        with pytest.raises(GuideDocumentUnavailable):
            async with grant.open(compilation.material.handle_for(document)):
                pytest.fail("incomplete recovered receipt granted bytes")
        assert store.calls == []
        assert authority.facts == []
    else:
        async with grant.open(compilation.material.handle_for(document)) as opened:
            assert opened.reader.read() == SOURCE_BYTES
        assert len(store.calls) == 1
    assert (await manager.usage()).reservation_count == 0


@pytest.mark.asyncio
async def test_recovered_document_access_can_persist_through_sql_custody(clean_postgres_database):
    from app.modules.projects.api import ProjectGuideCompilationExecutionCommand, ProjectGuideCompilationExecutionClassification
    from .test_hidden_orchestrator_postgresql import _port, _Runtime

    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _observed_upload(sessions, context(values).material.documents[0])
        request = await _authorized_attempt(clean_postgres_database, values)
        runtime = _Runtime()
        outcome = await _port(sessions, runtime).execute(ProjectGuideCompilationExecutionCommand(attempt_id=request.attempt_id))
        assert outcome.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert runtime.calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_ready_result_requires_document_citation_with_valid_transition(clean_postgres_database):
    """Only missing citation rejects; removing that SQL guard admits the same row."""
    from datetime import datetime, timezone
    from sqlalchemy import text, update
    from sqlalchemy.exc import DBAPIError
    from app.interfaces.project_agents import ProjectAgentRuntimeError
    from app.modules.projects.api import ProjectGuideCompilationExecutionCommand
    from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
    from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
    from .helpers import result
    from .test_hidden_orchestrator_postgresql import _Runtime, _port

    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(ProjectAgentRuntimeError("scripted unknown outcome"))
    try:
        await _port(sessions, runtime).execute(ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id))
        assert runtime.calls == 1
        valid = result()
        missing = valid.model_copy(update={"findings": ()})

        async def transition(connection, output):
            accepted = accepted_compilation_result(output)
            await connection.execute(update(ProjectGuideCompilationAttempt).where(
                ProjectGuideCompilationAttempt.id == requested.attempt_id
            ).values(status="provider_result_accepted", canonical_result=accepted.canonical_result,
                result_hash=accepted.result_hash,
                component_hashes=accepted.component_hashes.model_dump(mode="json"),
                accepted_at=datetime.now(timezone.utc)))

        async with engine.connect() as connection:
            async with connection.begin():
                # Positive control reaches every transition guard with exact hashes.
                savepoint = await connection.begin_nested()
                await transition(connection, valid)
                await savepoint.rollback()
                savepoint = await connection.begin_nested()
                with pytest.raises(DBAPIError, match="ready compilation requires citations for all assigned documents") as error:
                    await transition(connection, missing)
                assert error.value.orig.sqlstate == "23514"
                await savepoint.rollback()
                # Mutation is transactional and affects only this isolated test DB.
                savepoint = await connection.begin_nested()
                definition = await connection.scalar(text(
                    "select pg_get_functiondef('guard_compilation_document_evidence()'::regprocedure)"))
                start = definition.rindex("if ready and exists")
                end = definition.index("end if;", start) + len("end if;")
                assert "ready compilation requires citations for all assigned documents" in definition[start:end]
                await connection.execute(text(definition[:start] + definition[end:]))
                await transition(connection, missing)
                await savepoint.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_transition_waits_for_scoped_original_staging(grant_case):
    """The owner fence stays locked while ART prepares authorized bytes."""
    from sqlalchemy import text
    from app.modules.projects.guide_compilation.repository import GuideCompilationRepository

    grant, store, authority, manager, compilation = grant_case
    store.release = asyncio.Event()
    writer_pid = asyncio.Future()
    handle = compilation.material.handle_for(compilation.material.documents[0])

    async def read():
        async with grant.open(handle) as opened:
            assert opened.reader.read() == SOURCE_BYTES

    async def terminalize():
        async with grant._sessions() as session, session.begin():
            writer_pid.set_result(await session.scalar(text("select pg_backend_pid()")))
            await GuideCompilationRepository(session).mark_invalid_terminal(
                attempt_id=grant._attempt_id, failure_code="schema_invalid")

    reader = asyncio.create_task(read())
    await asyncio.wait_for(store.entered.wait(), timeout=5)
    writer = asyncio.create_task(terminalize())
    try:
        pid = await asyncio.wait_for(writer_pid, timeout=5)
        async with asyncio.timeout(5):
            while True:
                async with grant._sessions() as observer:
                    blocked = await observer.scalar(text(
                        "select wait_event_type='Lock' from pg_stat_activity where pid=:pid"), {"pid": pid})
                if blocked:
                    break
                assert not writer.done(), "attempt transition bypassed the held byte-access fence"
                await asyncio.sleep(0.01)
        store.release.set()
        await asyncio.wait_for(asyncio.gather(reader, writer), timeout=5)
        assert len(store.calls) == len(authority.facts) == 1
        with pytest.raises(GuideDocumentUnavailable, match="access_denied"):
            async with grant.open(handle):
                pytest.fail("terminal attempt reacquired original bytes")
        assert len(store.calls) == 1
        assert (await manager.usage()).reservation_count == 0
    finally:
        store.release.set()
        for task in (reader, writer):
            if not task.done():
                task.cancel()
        await asyncio.gather(reader, writer, return_exceptions=True)


def _replace_prepared_stream(grant, payload):
    """Inject drift only after the canonical preparation has verified its source."""
    original = grant._preparation
    prepared_results = []

    async def altered_stream():
        yield payload

    async def prepare(*args, **kwargs):
        prepared = await original.prepare(*args, **kwargs)
        prepared_results.append(prepared)
        return SimpleNamespace(commitment=prepared.commitment,
            committed_source=SimpleNamespace(stream=altered_stream), close=prepared.close)

    grant._preparation = SimpleNamespace(prepare=prepare)
    return prepared_results


@pytest.mark.parametrize("payload", [SOURCE_BYTES[:-1], SOURCE_BYTES + b"x", b"x" * len(SOURCE_BYTES)],
                         ids=["truncated", "overrun", "same_size"])
async def test_post_verification_stream_drift_never_yields_bytes_and_closes_scratch(grant_case, payload):
    """Even a corrupted scratch stream after successful preparation cannot escape ART."""
    grant, store, authority, manager, compilation = grant_case
    prepared_results = _replace_prepared_stream(grant, payload)
    with pytest.raises(GuideDocumentUnavailable, match="guide_document_integrity_mismatch"):
        async with grant.open(compilation.material.handle_for(compilation.material.documents[0])):
            pytest.fail("changed scratch stream escaped the grant")
    assert len(prepared_results) == len(authority.facts) == store.closed == 1
    assert (await manager.usage()).reservation_count == 0


async def test_second_stream_digest_guard_mutant_exposes_same_size_substitution(grant_case, monkeypatch):
    """Removing only the second digest comparison admits the identical corrupted fixture."""
    import ast
    import inspect
    import textwrap
    from app.modules.artifacts import guide_document_access as owner

    grant, store, _authority, manager, compilation = grant_case
    payload = b"x" * len(SOURCE_BYTES)
    assert payload != SOURCE_BYTES
    _replace_prepared_stream(grant, payload)
    handle = compilation.material.handle_for(compilation.material.documents[0])
    with pytest.raises(GuideDocumentUnavailable, match="guide_document_integrity_mismatch"):
        async with grant.open(handle):
            pytest.fail("intact second-stream guard yielded corrupted bytes")
    assert (await manager.usage()).reservation_count == 0

    tree = ast.parse(textwrap.dedent(inspect.getsource(owner.ScopedGuideDocumentGrant.open.__wrapped__)))
    comparisons = [node for node in ast.walk(tree) if isinstance(node, ast.Compare)
                   and any(isinstance(child, ast.Attribute) and child.attr == "hexdigest" for child in ast.walk(node))]
    assert len(comparisons) == 1

    class RemoveDigestComparison(ast.NodeTransformer):
        def visit_Compare(self, node):
            if node is comparisons[0]:
                return ast.copy_location(ast.Constant(False), node)
            return self.generic_visit(node)

    mutated = ast.fix_missing_locations(RemoveDigestComparison().visit(tree))
    namespace = dict(vars(owner))
    exec(compile(mutated, "<second-stream-digest-mutant>", "exec"), namespace)
    monkeypatch.setattr(owner.ScopedGuideDocumentGrant, "open", namespace["open"])
    async with grant.open(handle) as opened:
        assert opened.reader.read() == payload
    assert store.closed == 2
    assert (await manager.usage()).reservation_count == 0
