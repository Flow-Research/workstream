"""Focused proof for activated verification, authority, and deadline contracts."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from unittest.mock import AsyncMock, Mock, call

import app.interfaces.artifact_operations  # noqa: F401 - cumulative contract coverage
import app.adapters.artifacts.internal_workers as internal_worker_adapter
import app.modules.artifacts.service as artifact_service
from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.core.config import Settings, get_settings
from app.interfaces.artifacts import (
    ArtifactProviderOperationEvidence,
    ArtifactStoreNamespaceClaim,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.authorization import PreparedArtifactInternalAuthority
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactInternalResourceType,
    ArtifactPendingWorkAuthorityFacts,
    ArtifactPutAttemptAuthorityFacts,
    DenyArtifactInternalAuthority,
)
from app.modules.artifacts.service import (
    ArtifactStorageOrchestrator,
    artifact_storage_namespace_spec,
)
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.authorization.runtime import AuthorizationDenied
from tests.artifact_store_helpers import artifact_admission_limit_settings


def _scoped_worker_database(session_factory):
    @asynccontextmanager
    async def database():
        yield session_factory

    return database


def test_worker_database_composition_has_no_application_global_factory() -> None:
    assert "get_session_factory" not in vars(internal_worker_adapter)
    assert "get_session_factory" not in vars(artifact_service)
    parameter = inspect.signature(
        artifact_service.validate_artifact_storage_namespace_at_startup
    ).parameters["session_factory"]
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_production_authority_denies_prepare_and_consume() -> None:
    authority = DenyArtifactInternalAuthority()
    facts = ArtifactPutAttemptAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PUT_ATTEMPT,
        resource_id=new_record_id(),
        operation_identity="sha256:" + "1" * 64,
        namespace_fingerprint="sha256:" + "2" * 64,
        sha256="sha256:" + "3" * 64,
        byte_count=1,
        executor_id=new_record_id(),
        execution_generation=1,
    )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
            phase="claim",
            idempotency_key=new_record_id(),
        )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.consume(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
        )


@pytest.mark.asyncio
async def test_guide_continuation_query_supports_native_uuid_postgresql(
    isolated_database_env, monkeypatch,
) -> None:
    """Execute the actual query: PostgreSQL 16 does not provide min(uuid)."""
    published = []

    async def publish(identifier):
        published.append(identifier)

    assert await internal_worker_adapter.scan_guide_setup_continuations(publish) == 0
    assert published == []


@pytest.mark.asyncio
async def test_guide_continuation_scan_uses_its_own_bound_and_direct_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guide continuation recovery is independent from pending ART work paging."""

    observed: dict[str, int] = {}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def scalars(self, statement):
            observed["job_limit"] = statement._limit_clause.value
            return ["put-1", "put-2"]

    settings = SimpleNamespace(
        artifact_pending_work_scan_page_size=1,
        guide_setup_continuation_scan_page_size=2,
    )
    monkeypatch.setattr(internal_worker_adapter, "get_settings", lambda: settings)
    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Session),
    )
    published: list[str] = []

    async def publish_continuation(job_id: str) -> None:
        published.append(job_id)

    count = await internal_worker_adapter.scan_guide_setup_continuations(publish_continuation)

    assert count == 2
    assert published == ["put-1", "put-2"]
    assert observed == {"job_limit": 2}


@pytest.mark.asyncio
async def test_worker_database_disposes_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    engine.dispose = AsyncMock()
    session_factory = Mock()
    create_engine = Mock(return_value=engine)
    create_sessions = Mock(return_value=session_factory)
    monkeypatch.setattr(internal_worker_adapter, "get_database_url", lambda: "postgresql+asyncpg://db")
    monkeypatch.setattr(internal_worker_adapter, "create_async_engine", create_engine)
    monkeypatch.setattr(internal_worker_adapter, "async_sessionmaker", create_sessions)

    async with internal_worker_adapter._artifact_worker_database() as yielded:
        assert yielded is session_factory

    create_engine.assert_called_once_with("postgresql+asyncpg://db", pool_pre_ping=True)
    create_sessions.assert_called_once_with(engine, expire_on_commit=False)
    engine.dispose.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_worker_database_disposes_after_failure_or_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
) -> None:
    engine = Mock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(internal_worker_adapter, "get_database_url", lambda: "postgresql+asyncpg://db")
    monkeypatch.setattr(internal_worker_adapter, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(internal_worker_adapter, "async_sessionmaker", Mock(return_value=Mock()))

    with pytest.raises(error_type):
        async with internal_worker_adapter._artifact_worker_database():
            raise error_type("stop")

    engine.dispose.assert_awaited_once_with()


def test_eager_internal_tasks_use_lazy_process_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    worker_module = importlib.import_module("app.workers.artifacts")
    monkeypatch.setitem(worker_module.celery_app.conf, "task_always_eager", True)
    monkeypatch.setitem(worker_module.celery_app.conf, "task_eager_propagates", True)
    initialize = AsyncMock(return_value=None)
    monkeypatch.setattr(
        internal_worker_adapter,
        "_initialize_artifact_internal_runtime",
        initialize,
    )

    @contextmanager
    def runtime():
        yield Mock(), Mock()

    monkeypatch.setattr(internal_worker_adapter, "_artifact_internal_runtime", runtime)
    monkeypatch.setattr(internal_worker_adapter, "get_settings", Mock(return_value=Mock()))

    class SessionContext:
        async def __aenter__(self):
            return Mock()

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock(return_value=SessionContext())),
    )
    orchestrator = Mock()
    orchestrator.resolve_put_attempt = AsyncMock(return_value="resolved")
    orchestrator.verify_object = AsyncMock(return_value="verified")
    monkeypatch.setattr(
        internal_worker_adapter,
        "ArtifactStorageOrchestrator",
        Mock(return_value=orchestrator),
    )
    task_contexts = Mock()
    task_adapters = importlib.import_module("app.adapters.tasks")
    monkeypatch.setattr(
        task_adapters,
        "task_submission_context_port",
        Mock(return_value=task_contexts),
    )
    monkeypatch.setattr(
        worker_module,
        "run_artifact_internal_operation",
        internal_worker_adapter.run_artifact_internal_operation,
    )
    continuation_delay = Mock()
    monkeypatch.setattr(worker_module.continue_guide_setup, "delay", continuation_delay)
    attempt_id, job_id = new_record_id(), new_record_id()

    worker_module.resolve_put_attempt.delay(str(attempt_id))
    worker_module.verify_object.delay(str(job_id))

    assert initialize.await_count == 2
    orchestrator.resolve_put_attempt.assert_awaited_once_with(attempt_id)
    orchestrator.verify_object.assert_awaited_once_with(
        job_id,
        submission_task_contexts=task_contexts,
    )
    continuation_delay.assert_called_once_with(str(attempt_id))
    celery_module = importlib.import_module("app.workers.celery_app")
    worker_module = importlib.import_module("app.workers.artifacts")
    celery_app = celery_module.celery_app
    assert "workstream.artifacts.resolve_put_attempt" in celery_app.tasks
    assert "workstream.artifacts.verify_object" in celery_app.tasks
    assert "workstream.artifacts.scan_pending_work" in celery_app.tasks
    assert "workstream.artifacts.continue_guide_setup" in celery_app.tasks
    assert "workstream.artifacts.scan_guide_setup_continuations" in celery_app.tasks
    scheduled_tasks = [entry["task"] for entry in celery_app.conf.beat_schedule.values()]
    assert scheduled_tasks.count("workstream.artifacts.scan_pending_work") == 1
    assert scheduled_tasks.count("workstream.artifacts.scan_guide_setup_continuations") == 1
    assert scheduled_tasks.count("workstream.artifacts.cleanup_stale_scratch") == 1
    operation = AsyncMock(return_value=None)
    scanned: list[str] = []

    async def scan(publish_put, publish_job):
        await publish_put("put-id")
        await publish_job("job-id")
        scanned.append("called")
        return 2

    async def scan_guides(publish_job):
        await publish_job("guide-put-id")
        return 1

    monkeypatch.setattr(worker_module, "run_artifact_internal_operation", operation)
    continuation_delay = Mock()
    monkeypatch.setattr(worker_module.continue_guide_setup, "delay", continuation_delay)
    monkeypatch.setattr(worker_module, "scan_artifact_pending_work", scan)
    monkeypatch.setattr(worker_module, "scan_guide_setup_continuations_page", scan_guides)
    put_delay = Mock()
    job_delay = Mock()
    monkeypatch.setattr(worker_module.resolve_put_attempt, "delay", put_delay)
    monkeypatch.setattr(worker_module.verify_object, "delay", job_delay)
    attempt_id = str(new_record_id())
    job_id = str(new_record_id())
    worker_module.resolve_put_attempt(attempt_id)
    worker_module.verify_object(job_id)
    assert operation.await_count == 2
    assert operation.await_args_list[0].args == ("put", UUID(attempt_id))
    assert operation.await_args_list[1].args == ("verification", UUID(job_id))
    continuation_delay.assert_called_once_with(attempt_id)
    assert worker_module.scan_pending_work() == 2
    assert worker_module.scan_guide_setup_continuations() == 1
    assert scanned == ["called"]
    put_delay.assert_called_once_with("put-id")
    job_delay.assert_called_once_with("job-id")
    assert continuation_delay.call_args_list == [call(attempt_id), call("guide-put-id")]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_internal_artifact_store_is_initialized_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    first_bootstrap = Mock()
    first_store = Mock()
    first_bootstrap.initialize_after_namespace_claim.return_value = first_store
    monkeypatch.setattr(internal_worker_adapter, "get_settings", Mock(return_value=Mock()))
    monkeypatch.setattr(
        internal_worker_adapter,
        "create_artifact_store_bootstrap",
        Mock(return_value=first_bootstrap),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "validate_artifact_storage_namespace_at_startup",
        AsyncMock(return_value=Mock()),
    )
    session_factory = Mock()
    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(session_factory),
    )
    first_namespace = Mock()
    monkeypatch.setattr(
        internal_worker_adapter,
        "artifact_storage_namespace_spec",
        Mock(return_value=first_namespace),
    )

    try:
        await internal_worker_adapter.initialize_artifact_internal_runtime()
        await internal_worker_adapter.initialize_artifact_internal_runtime()
        with internal_worker_adapter._artifact_internal_runtime() as runtime:
            assert runtime == (first_store, first_namespace)
        first_bootstrap.close.assert_not_called()
    finally:
        internal_worker_adapter.shutdown_artifact_internal_runtime()

    first_bootstrap.close.assert_called_once_with()
    with pytest.raises(RuntimeError, match="not initialized"):
        with internal_worker_adapter._artifact_internal_runtime():
            pass


@pytest.mark.asyncio
async def test_disabled_artifact_store_skips_process_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    monkeypatch.setattr(
        internal_worker_adapter,
        "get_settings",
        Mock(return_value=SimpleNamespace(artifact_store_backend="disabled")),
    )
    create = Mock(side_effect=AssertionError("disabled storage must not initialize"))
    monkeypatch.setattr(internal_worker_adapter, "create_artifact_store_bootstrap", create)

    await internal_worker_adapter.initialize_artifact_internal_runtime()

    create.assert_not_called()
    with pytest.raises(RuntimeError, match="not initialized"):
        with internal_worker_adapter._artifact_internal_runtime():
            pass


@pytest.mark.asyncio
async def test_process_runtime_uses_concrete_bootstrap_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    settings = Settings(
        _env_file=None,
        **artifact_admission_limit_settings(),
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=root,
        artifact_scratch_root=tmp_path / "scratch",
    )
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=root))
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    claim = ArtifactStoreNamespaceClaim(
        adapter_identity=bootstrap.identity,
        namespace_identity=bootstrap.namespace_identity,
        namespace_fingerprint=namespace.namespace_fingerprint,
    )
    monkeypatch.setattr(internal_worker_adapter, "get_settings", Mock(return_value=settings))
    monkeypatch.setattr(
        internal_worker_adapter,
        "create_artifact_store_bootstrap",
        Mock(return_value=bootstrap),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "validate_artifact_storage_namespace_at_startup",
        AsyncMock(return_value=claim),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock()),
    )

    try:
        await internal_worker_adapter.initialize_artifact_internal_runtime()
        with internal_worker_adapter._artifact_internal_runtime() as runtime:
            assert runtime[1] == namespace
            assert not hasattr(runtime[0], "namespace_identity")
    finally:
        internal_worker_adapter.shutdown_artifact_internal_runtime()


@pytest.mark.asyncio
async def test_process_runtime_shutdown_waits_for_active_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    bootstrap, store, namespace = Mock(), Mock(), Mock()
    bootstrap.initialize_after_namespace_claim.return_value = store
    monkeypatch.setattr(
        internal_worker_adapter,
        "get_settings",
        Mock(
            return_value=SimpleNamespace(
                artifact_store_backend="local",
                artifact_s3_provider_profile=None,
            )
        ),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "create_artifact_store_bootstrap",
        Mock(return_value=bootstrap),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "artifact_storage_namespace_spec",
        Mock(return_value=namespace),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "validate_artifact_storage_namespace_at_startup",
        AsyncMock(return_value=Mock()),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock()),
    )
    await internal_worker_adapter.initialize_artifact_internal_runtime()
    shutdown_started, shutdown_finished = Event(), Event()

    def shutdown() -> None:
        shutdown_started.set()
        internal_worker_adapter.shutdown_artifact_internal_runtime()
        shutdown_finished.set()

    with internal_worker_adapter._artifact_internal_runtime():
        thread = Thread(target=shutdown)
        thread.start()
        assert shutdown_started.wait(timeout=1)
        assert not shutdown_finished.wait(timeout=0.05)

    assert shutdown_finished.wait(timeout=1)
    thread.join(timeout=1)
    assert not thread.is_alive()
    bootstrap.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_process_runtime_closes_bootstrap_when_namespace_claim_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    bootstrap = Mock()
    monkeypatch.setattr(
        internal_worker_adapter,
        "get_settings",
        Mock(
            return_value=SimpleNamespace(
                artifact_store_backend="local",
                artifact_s3_provider_profile=None,
            )
        ),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "create_artifact_store_bootstrap",
        Mock(return_value=bootstrap),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "artifact_storage_namespace_spec",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "validate_artifact_storage_namespace_at_startup",
        AsyncMock(side_effect=RuntimeError("claim failed")),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock()),
    )

    with pytest.raises(RuntimeError, match="claim failed"):
        await internal_worker_adapter.initialize_artifact_internal_runtime()

    bootstrap.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_process_runtime_closes_losing_concurrent_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    bootstraps = [Mock(), Mock()]
    for bootstrap in bootstraps:
        bootstrap.initialize_after_namespace_claim.return_value = Mock()
    both_claiming = asyncio.Event()
    release_claims = asyncio.Event()
    claim_count = 0

    async def claim_namespace(*_args: object) -> Mock:
        nonlocal claim_count
        claim_count += 1
        if claim_count == 2:
            both_claiming.set()
        await release_claims.wait()
        return Mock()

    monkeypatch.setattr(
        internal_worker_adapter,
        "get_settings",
        Mock(
            return_value=SimpleNamespace(
                artifact_store_backend="local",
                artifact_s3_provider_profile=None,
            )
        ),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "create_artifact_store_bootstrap",
        Mock(side_effect=bootstraps),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "artifact_storage_namespace_spec",
        Mock(side_effect=[Mock(), Mock()]),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "validate_artifact_storage_namespace_at_startup",
        AsyncMock(side_effect=claim_namespace),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock()),
    )

    initializers = [
        asyncio.create_task(internal_worker_adapter.initialize_artifact_internal_runtime())
        for _ in range(2)
    ]
    await asyncio.wait_for(both_claiming.wait(), timeout=1)
    release_claims.set()
    await asyncio.gather(*initializers)

    assert sum(bootstrap.close.call_count for bootstrap in bootstraps) == 1
    internal_worker_adapter.shutdown_artifact_internal_runtime()
    assert all(bootstrap.close.call_count == 1 for bootstrap in bootstraps)


@pytest.mark.asyncio
async def test_internal_operation_rejects_kind_and_restages_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="unsupported artifact internal operation"):
        await internal_worker_adapter.run_artifact_internal_operation("unknown", new_record_id())

    monkeypatch.setattr(
        internal_worker_adapter,
        "_initialize_artifact_internal_runtime",
        AsyncMock(return_value=None),
    )

    @contextmanager
    def runtime():
        yield Mock(), Mock()

    monkeypatch.setattr(internal_worker_adapter, "_artifact_internal_runtime", runtime)
    monkeypatch.setattr(internal_worker_adapter, "get_settings", Mock(return_value=Mock()))
    order: list[str] = []

    async def rollback() -> None:
        order.append("rollback")

    async def persist_denial() -> None:
        order.append("restage")

    session = Mock()
    session.rollback = AsyncMock(side_effect=rollback)

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock(return_value=SessionContext())),
    )
    authority = PreparedArtifactInternalAuthority(
        session, service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    authority.persist_denial = AsyncMock(side_effect=persist_denial)
    monkeypatch.setattr(
        internal_worker_adapter,
        "PreparedArtifactInternalAuthority",
        Mock(return_value=authority),
    )
    orchestrator = Mock()
    orchestrator.resolve_put_attempt = AsyncMock(
        side_effect=AuthorizationDenied(
            SimpleNamespace(allowed=False, denial_code="denied")  # type: ignore[arg-type]
        )
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "ArtifactStorageOrchestrator",
        Mock(return_value=orchestrator),
    )

    with pytest.raises(ArtifactAuthorityDeniedError, match="authority denied"):
        await internal_worker_adapter.run_artifact_internal_operation("put", new_record_id())

    session.rollback.assert_awaited_once_with()
    authority.persist_denial.assert_awaited_once_with()
    assert order == ["rollback", "restage"]


@pytest.mark.asyncio
async def test_pending_scan_returns_count_and_restages_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    async def rollback() -> None:
        order.append("rollback")

    async def persist_denial() -> None:
        order.append("restage")

    session = Mock()
    session.rollback = AsyncMock(side_effect=rollback)

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        internal_worker_adapter,
        "_artifact_worker_database",
        _scoped_worker_database(Mock(return_value=SessionContext())),
    )
    monkeypatch.setattr(internal_worker_adapter, "get_settings", Mock(return_value=Mock()))
    authority = PreparedArtifactInternalAuthority(
        session, service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    authority.persist_denial = AsyncMock(side_effect=persist_denial)
    monkeypatch.setattr(
        internal_worker_adapter,
        "PreparedArtifactInternalAuthority",
        Mock(return_value=authority),
    )
    scanner = Mock()
    scanner.scan = AsyncMock(return_value=3)
    monkeypatch.setattr(
        internal_worker_adapter,
        "ArtifactPendingWorkScanner",
        Mock(return_value=scanner),
    )
    publish_put, publish_job = AsyncMock(), AsyncMock()

    assert await internal_worker_adapter.scan_artifact_pending_work(publish_put, publish_job) == 3

    scanner.scan.side_effect = AuthorizationDenied(
        SimpleNamespace(allowed=False, denial_code="denied")  # type: ignore[arg-type]
    )
    with pytest.raises(ArtifactAuthorityDeniedError, match="authority denied"):
        await internal_worker_adapter.scan_artifact_pending_work(publish_put, publish_job)

    session.rollback.assert_awaited_once_with()
    authority.persist_denial.assert_awaited_once_with()
    assert order == ["rollback", "restage"]


def test_internal_artifact_actions_are_active() -> None:
    assert {
        action_id: ACTION_BY_ID[action_id].availability
        for action_id in {
            ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            ActionId.ARTIFACT_VERIFICATION_EXECUTE,
            ActionId.ARTIFACT_PENDING_WORK_SCAN,
        }
    } == {
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE: ActionAvailability.ACTIVE,
        ActionId.ARTIFACT_VERIFICATION_EXECUTE: ActionAvailability.ACTIVE,
        ActionId.ARTIFACT_PENDING_WORK_SCAN: ActionAvailability.ACTIVE,
    }


def test_verification_deadline_and_margin_must_fit_lease() -> None:
    with pytest.raises(ValueError, match="must fit within lease"):
        Settings(
            artifact_execution_lease_seconds=100,
            artifact_complete_read_deadline_seconds=80,
            artifact_terminal_persistence_margin_seconds=20,
        )


@pytest.mark.asyncio
async def test_complete_read_uses_total_deadline_for_progressing_stream() -> None:
    class SlowStore:
        def open(self, _provider_object_ref: str, **_kwargs):
            async def chunks():
                while True:
                    await asyncio.sleep(0.02)
                    yield b"x"

            return chunks()

    orchestrator = object.__new__(ArtifactStorageOrchestrator)
    orchestrator._store = SlowStore()  # type: ignore[attr-defined]
    orchestrator._settings = Settings(  # type: ignore[attr-defined]
        artifact_execution_lease_seconds=1,
        artifact_complete_read_deadline_seconds=0.05,
        artifact_terminal_persistence_margin_seconds=0.1,
    )
    with pytest.raises(TimeoutError):
        await orchestrator._read_complete(
            "sha256/" + "a" * 64,
            operation_evidence=ArtifactProviderOperationEvidence(),
        )


def test_pending_work_facts_are_closed_and_bounded_by_construction() -> None:
    facts = ArtifactPendingWorkAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PENDING_WORK,
        resource_id="workstream:artifact_pending_work",
        scanner_kind="put_resolution",
        database_cutoff_iso=datetime.now(UTC).isoformat(),
        page_size=100,
    )
    assert facts.resource_id == "workstream:artifact_pending_work"
