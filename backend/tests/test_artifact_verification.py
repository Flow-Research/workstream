"""Focused proof for activated verification, authority, and deadline contracts."""

from __future__ import annotations

import asyncio
import importlib
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock, Mock

import app.interfaces.artifact_operations  # noqa: F401 - cumulative contract coverage
import app.adapters.artifacts.internal_workers as internal_worker_adapter
from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.core.config import Settings, get_settings
from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
from app.modules.actors.service_identities import ServiceIdentity
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


@pytest.mark.asyncio
async def test_production_authority_denies_prepare_and_consume() -> None:
    authority = DenyArtifactInternalAuthority()
    facts = ArtifactPutAttemptAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PUT_ATTEMPT,
        resource_id=uuid4(),
        operation_identity="sha256:" + "1" * 64,
        namespace_fingerprint="sha256:" + "2" * 64,
        sha256="sha256:" + "3" * 64,
        byte_count=1,
        executor_id=uuid4(),
        execution_generation=1,
    )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
            phase="claim",
            idempotency_key=uuid4(),
        )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
            )


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
        "initialize_artifact_internal_runtime",
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
        "get_session_factory",
        Mock(return_value=Mock(return_value=SessionContext())),
    )
    monkeypatch.setattr(
        internal_worker_adapter,
        "PreparedArtifactInternalAuthority",
        Mock(),
    )
    orchestrator = Mock()
    orchestrator.resolve_put_attempt = AsyncMock(return_value="resolved")
    orchestrator.verify_object = AsyncMock(return_value="verified")
    monkeypatch.setattr(
        internal_worker_adapter,
        "ArtifactStorageOrchestrator",
        Mock(return_value=orchestrator),
    )
    monkeypatch.setattr(
        worker_module,
        "run_artifact_internal_operation",
        internal_worker_adapter.run_artifact_internal_operation,
    )
    attempt_id, job_id = uuid4(), uuid4()

    worker_module.resolve_put_attempt.delay(str(attempt_id))
    worker_module.verify_object.delay(str(job_id))

    assert initialize.await_count == 2
    orchestrator.resolve_put_attempt.assert_awaited_once_with(attempt_id)
    orchestrator.verify_object.assert_awaited_once_with(job_id)
    celery_module = importlib.import_module("app.workers.celery_app")
    worker_module = importlib.import_module("app.workers.artifacts")
    celery_app = celery_module.celery_app
    assert "workstream.artifacts.resolve_put_attempt" in celery_app.tasks
    assert "workstream.artifacts.verify_object" in celery_app.tasks
    assert "workstream.artifacts.scan_pending_work" in celery_app.tasks
    scheduled_tasks = [entry["task"] for entry in celery_app.conf.beat_schedule.values()]
    assert scheduled_tasks.count("workstream.artifacts.scan_pending_work") == 1
    assert scheduled_tasks.count("workstream.artifacts.cleanup_stale_scratch") == 1
    operation = AsyncMock(return_value=None)
    scanned: list[str] = []

    async def scan(publish_put, publish_job):
        await publish_put("put-id")
        await publish_job("job-id")
        scanned.append("called")
        return 2

    monkeypatch.setattr(worker_module, "run_artifact_internal_operation", operation)
    monkeypatch.setattr(worker_module, "scan_artifact_pending_work", scan)
    put_delay = Mock()
    job_delay = Mock()
    monkeypatch.setattr(worker_module.resolve_put_attempt, "delay", put_delay)
    monkeypatch.setattr(worker_module.verify_object, "delay", job_delay)
    attempt_id = str(uuid4())
    job_id = str(uuid4())
    worker_module.resolve_put_attempt(attempt_id)
    worker_module.verify_object(job_id)
    assert operation.await_count == 2
    assert operation.await_args_list[0].args == ("put", UUID(attempt_id))
    assert operation.await_args_list[1].args == ("verification", UUID(job_id))
    assert worker_module.scan_pending_work() == 2
    assert scanned == ["called"]
    put_delay.assert_called_once_with("put-id")
    job_delay.assert_called_once_with("job-id")
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
        "require_artifact_runtime_eligible",
        Mock(),
    )
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
        Mock(return_value=SimpleNamespace(artifact_store_backend="local")),
    )
    monkeypatch.setattr(internal_worker_adapter, "require_artifact_runtime_eligible", Mock())
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
        Mock(return_value=SimpleNamespace(artifact_store_backend="local")),
    )
    monkeypatch.setattr(internal_worker_adapter, "require_artifact_runtime_eligible", Mock())
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
        Mock(return_value=SimpleNamespace(artifact_store_backend="local")),
    )
    monkeypatch.setattr(internal_worker_adapter, "require_artifact_runtime_eligible", Mock())
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
        await internal_worker_adapter.run_artifact_internal_operation("unknown", uuid4())

    monkeypatch.setattr(
        internal_worker_adapter,
        "initialize_artifact_internal_runtime",
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
        "get_session_factory",
        Mock(return_value=Mock(return_value=SessionContext())),
    )
    authority = Mock()
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
        await internal_worker_adapter.run_artifact_internal_operation("put", uuid4())

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
        "get_session_factory",
        Mock(return_value=Mock(return_value=SessionContext())),
    )
    monkeypatch.setattr(internal_worker_adapter, "get_settings", Mock(return_value=Mock()))
    authority = Mock()
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

    assert (
        await internal_worker_adapter.scan_artifact_pending_work(
            publish_put, publish_job
        )
        == 3
    )

    scanner.scan.side_effect = AuthorizationDenied(
        SimpleNamespace(allowed=False, denial_code="denied")  # type: ignore[arg-type]
    )
    with pytest.raises(ArtifactAuthorityDeniedError, match="authority denied"):
        await internal_worker_adapter.scan_artifact_pending_work(
            publish_put, publish_job
        )

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
        def open(self, _provider_object_ref: str):
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
        await orchestrator._read_complete("sha256/" + "a" * 64)


def test_pending_work_facts_are_closed_and_bounded_by_construction() -> None:
    facts = ArtifactPendingWorkAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PENDING_WORK,
        resource_id="workstream:artifact_pending_work",
        scanner_kind="put_resolution",
        database_cutoff_iso=datetime.now(UTC).isoformat(),
        page_size=100,
    )
    assert facts.resource_id == "workstream:artifact_pending_work"
