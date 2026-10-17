"""Composition tests for artifact startup and scratch cleanup ownership."""

from __future__ import annotations

import importlib
import asyncio
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest

from app.adapters.artifacts import artifact_preparation_limits
from app.core.config import Settings, get_settings
from app.main import create_app
from app.interfaces.artifacts import ArtifactProviderLiveProofRequiredError
from tests.artifact_store_helpers import artifact_admission_limit_settings


def _enabled_settings(tmp_path: Path, **changes: object) -> Settings:
    values: dict[str, object] = {
        **artifact_admission_limit_settings(),
        "environment": "test",
        "artifact_store_backend": "local",
        "artifact_local_root": tmp_path / "store",
        "artifact_scratch_root": tmp_path / "scratch",
    }
    values.update(changes)
    return Settings(**values)


def _aws_setting_values(tmp_path: Path) -> dict[str, object]:
    """Return a syntactically complete native-AWS activation binding."""
    return {
        **artifact_admission_limit_settings(),
        "environment": "production",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "aws_s3",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_bucket": "workstream-artifacts-prod",
        "artifact_s3_credential_mode": "aws_workload_identity",
        "artifact_s3_aws_workload_identity_method": "container-role",
        "release_id": "sha256:" + "1" * 64,
        "artifact_s3_runtime_role_arn": "arn:aws:iam::123456789012:role/workstream-runtime",
        "artifact_s3_runtime_trust_policy_sha256": "sha256:" + "3" * 64,
        "artifact_s3_runtime_policy_arn": "arn:aws:iam::123456789012:policy/workstream-runtime",
        "artifact_s3_readiness_role_arn": "arn:aws:iam::123456789012:role/workstream-readiness",
        "artifact_s3_readiness_trust_policy_sha256": "sha256:" + "4" * 64,
        "artifact_s3_readiness_policy_arn": "arn:aws:iam::123456789012:policy/workstream-readiness",
        "artifact_s3_negative_role_arn": "arn:aws:iam::123456789012:role/workstream-negative",
        "artifact_s3_negative_trust_policy_sha256": "sha256:" + "5" * 64,
        "artifact_s3_bootstrap_principal_arn": "arn:aws:iam::123456789012:role/workstream-bootstrap",
        "artifact_s3_bucket_policy_sha256": "sha256:" + "2" * 64,
        "artifact_s3_operation_total_timeout_seconds": 300,
        "artifact_complete_read_deadline_seconds": 300,
        "artifact_terminal_persistence_margin_seconds": 120,
    }


class _Store:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def close(self) -> None:
        self.events.append("close")

    def initialize_after_namespace_claim(self, claim: object) -> _Store:
        assert claim == "claim" or getattr(claim, "namespace_fingerprint", None)
        self.events.append("initialize")
        return self


async def test_enabled_startup_validates_namespace_then_cleans_before_yield(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.main as main_module

    events: list[str] = []
    store = _Store(events)

    async def validate(settings: Settings, candidate: object) -> str:
        assert settings.artifact_store_backend == "local"
        assert candidate is store
        events.append("namespace")
        return "claim"

    def create(_settings: Settings, *, activation_guard: object) -> _Store:
        assert activation_guard is None
        events.append("construct")
        return store

    async def cleanup(settings: Settings) -> int:
        assert settings.artifact_store_backend == "local"
        events.append("cleanup")
        return 0

    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", create)
    monkeypatch.setattr(main_module, "_validate_artifact_storage_namespace_at_startup", validate)
    monkeypatch.setattr(main_module, "cleanup_stale_artifact_scratch", cleanup)
    app = create_app(_enabled_settings(tmp_path))

    async with app.router.lifespan_context(app):
        events.append("yield")

    assert events == ["construct", "namespace", "initialize", "cleanup", "close", "yield"]


async def test_production_auth_validation_precedes_artifact_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.main as main_module

    events: list[str] = []
    settings = Settings(**_aws_setting_values(tmp_path))
    app = create_app(settings)
    store = _Store(events)

    def validate_auth(_settings: Settings) -> None:
        events.append("auth")

    async def validate_namespace(candidate_settings: Settings, candidate: object) -> object:
        assert candidate_settings is settings
        assert candidate is store
        events.append("namespace")
        return SimpleNamespace(namespace_fingerprint="sha256:" + "3" * 64)

    class Guard:
        async def select_for_call(self, **_kwargs: object) -> None:
            events.append("activation")

    guard = Guard()

    def create(_settings: Settings, *, activation_guard: object) -> _Store:
        assert activation_guard is guard
        events.append("construct")
        return store

    async def cleanup(_settings: Settings) -> int:
        events.append("cleanup")
        return 0

    monkeypatch.setattr(main_module, "build_auth_verifier", validate_auth)
    monkeypatch.setattr(
        main_module,
        "artifact_provider_activation_guard",
        lambda *_args: guard,
    )
    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", create)
    monkeypatch.setattr(
        main_module,
        "_validate_artifact_storage_namespace_at_startup",
        validate_namespace,
    )
    monkeypatch.setattr(main_module, "cleanup_stale_artifact_scratch", cleanup)

    async with app.router.lifespan_context(app):
        events.append("yield")

    assert events == [
        "auth",
        "construct",
        "namespace",
        "activation",
        "initialize",
        "cleanup",
        "close",
        "yield",
    ]


async def test_disabled_startup_does_not_construct_or_clean_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.main as main_module

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("disabled artifact storage activated")

    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", unexpected)
    monkeypatch.setattr(main_module, "cleanup_stale_artifact_scratch", unexpected)
    app = create_app(Settings(environment="test"))

    async with app.router.lifespan_context(app):
        pass


async def test_aws_s3_startup_requires_live_provider_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reject native AWS after namespace lineage when fresh activation is absent."""
    import app.main as main_module

    events: list[str] = []
    store = _Store(events)

    class Guard:
        async def select_for_call(self, **_kwargs: object) -> None:
            events.append("activation")
            raise ArtifactProviderLiveProofRequiredError("proof is absent")

    guard = Guard()

    def create(_settings: Settings, *, activation_guard: object) -> _Store:
        assert activation_guard is guard
        events.append("construct")
        return store

    async def validate_namespace(*_args: object) -> object:
        events.append("namespace")
        return SimpleNamespace(namespace_fingerprint="sha256:" + "3" * 64)

    monkeypatch.setattr(main_module, "build_auth_verifier", lambda _settings: None)
    monkeypatch.setattr(
        main_module,
        "artifact_provider_activation_guard",
        lambda *_args: guard,
    )
    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", create)
    monkeypatch.setattr(
        main_module,
        "_validate_artifact_storage_namespace_at_startup",
        validate_namespace,
    )
    app = create_app(Settings(**_aws_setting_values(tmp_path)))

    with pytest.raises(ArtifactProviderLiveProofRequiredError) as caught:
        async with app.router.lifespan_context(app):
            pass

    assert caught.value.code == "artifact_provider_live_proof_required"
    assert events == ["construct", "namespace", "activation", "close"]


def test_aws_worker_guard_rebinds_to_each_sync_task_loop_and_disposes_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A process store must not retain the initialization loop's session factory."""
    from app.adapters.artifacts import internal_workers
    from app.interfaces.artifacts import ArtifactProviderActivationLease
    from app.workers.async_runner import run_async_task

    settings = Settings(**_aws_setting_values(tmp_path))
    events: list[tuple[str, int, int | None]] = []
    loops: list[asyncio.AbstractEventLoop] = []
    activation_id = UUID("0199e648-0b77-7000-8000-000000000001")

    def loop_number() -> int:
        loop = asyncio.get_running_loop()
        if loop not in loops:
            loops.append(loop)
        return loops.index(loop)

    class Engine:
        def __init__(self) -> None:
            self.identifier = len([event for event in events if event[0] == "engine"]) + 1
            events.append(("engine", self.identifier, None))

        async def dispose(self) -> None:
            events.append(("dispose", self.identifier, loop_number()))

    class Guard:
        def __init__(self, sessions: object) -> None:
            self.sessions = sessions

        async def select_for_call(self, *, namespace_fingerprint: str):
            del namespace_fingerprint
            events.append(("guard", id(self.sessions), loop_number()))
            return ArtifactProviderActivationLease(activation_id)

        async def require_for_call(self, activation_id, *, namespace_fingerprint: str):
            del namespace_fingerprint
            return ArtifactProviderActivationLease(activation_id)

    class Store(_Store):
        def __init__(self, guard) -> None:
            super().__init__([])
            self.guard = guard

        async def guarded_call(self) -> None:
            await self.guard.select_for_call(namespace_fingerprint="sha256:" + "3" * 64)

    class Bootstrap:
        def __init__(self, guard) -> None:
            self.store = Store(guard)

        def initialize_after_namespace_claim(self, _claim: object):
            return self.store

        def close(self) -> None:
            return None

    monkeypatch.setattr(internal_workers, "get_settings", lambda: settings)
    monkeypatch.setattr(internal_workers, "get_database_url", lambda: "postgresql+asyncpg://unused")
    monkeypatch.setattr(internal_workers, "create_async_engine", lambda *_a, **_k: Engine())
    monkeypatch.setattr(
        internal_workers,
        "artifact_provider_activation_guard",
        lambda _settings, sessions: Guard(sessions),
    )
    monkeypatch.setattr(
        internal_workers,
        "create_artifact_store_bootstrap",
        lambda _settings, *, activation_guard: Bootstrap(activation_guard),
    )
    monkeypatch.setattr(
        internal_workers,
        "artifact_storage_namespace_spec",
        lambda *_a: SimpleNamespace(namespace_fingerprint="sha256:" + "3" * 64),
    )
    monkeypatch.setattr(
        internal_workers,
        "validate_artifact_storage_namespace_at_startup",
        lambda *_a: _async_value(SimpleNamespace(namespace_fingerprint="sha256:" + "3" * 64)),
    )

    async def guarded_operation() -> None:
        async with internal_workers._artifact_worker_database():
            with internal_workers._artifact_internal_runtime() as (store, _namespace):
                await store.guarded_call()

    internal_workers.shutdown_artifact_internal_runtime()
    try:
        run_async_task(internal_workers.initialize_artifact_internal_runtime)
        run_async_task(guarded_operation)
        run_async_task(guarded_operation)
    finally:
        internal_workers.shutdown_artifact_internal_runtime()

    guards = [event for event in events if event[0] == "guard"]
    disposals = [event for event in events if event[0] == "dispose"]
    assert len(guards) == 3
    assert len({event[1] for event in guards}) == 3
    assert len({event[2] for event in guards}) == 3
    assert len(disposals) == 3


async def _async_value(value: object) -> object:
    return value


async def test_namespace_failure_is_fail_closed_and_skips_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.main as main_module

    events: list[str] = []
    store = _Store(events)

    async def fail_namespace(_settings: Settings, candidate: object) -> None:
        assert candidate is store
        events.append("namespace")
        raise RuntimeError("namespace mismatch")

    def create(_settings: Settings, *, activation_guard: object) -> _Store:
        assert activation_guard is None
        events.append("construct")
        return store

    async def unexpected_cleanup(_settings: Settings) -> int:
        raise AssertionError("cleanup ran after namespace failure")

    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", create)
    monkeypatch.setattr(
        main_module,
        "_validate_artifact_storage_namespace_at_startup",
        fail_namespace,
    )
    monkeypatch.setattr(main_module, "cleanup_stale_artifact_scratch", unexpected_cleanup)
    app = create_app(_enabled_settings(tmp_path))

    with pytest.raises(RuntimeError, match="namespace mismatch"):
        async with app.router.lifespan_context(app):
            pass

    assert events == ["construct", "namespace", "close"]
    assert not (tmp_path / "store").exists()


async def test_cleanup_failure_prevents_startup_and_closes_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.main as main_module

    events: list[str] = []
    store = _Store(events)

    async def validate(_settings: Settings, candidate: object) -> str:
        assert candidate is store
        events.append("namespace")
        return "claim"

    def create(_settings: Settings, *, activation_guard: object) -> _Store:
        assert activation_guard is None
        events.append("construct")
        return store

    async def fail_cleanup(_settings: Settings) -> int:
        events.append("cleanup")
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", create)
    monkeypatch.setattr(main_module, "_validate_artifact_storage_namespace_at_startup", validate)
    monkeypatch.setattr(main_module, "cleanup_stale_artifact_scratch", fail_cleanup)
    app = create_app(_enabled_settings(tmp_path))

    with pytest.raises(RuntimeError, match="cleanup failed"):
        async with app.router.lifespan_context(app):
            pass

    assert events == ["construct", "namespace", "initialize", "cleanup", "close"]


def test_preparation_limit_mapping_uses_every_canonical_setting(tmp_path: Path) -> None:
    settings = _enabled_settings(
        tmp_path,
        artifact_scratch_aggregate_reserved_bytes=3 * 512 * 1024 * 1024,
        artifact_scratch_maximum_files=7,
        artifact_scratch_maximum_concurrency=3,
        artifact_scratch_maximum_workspace_entries=4_000,
        artifact_scratch_minimum_free_bytes=123,
        artifact_scratch_reservation_ttl_seconds=3000,
        artifact_preparation_total_deadline_seconds=2000,
        artifact_scratch_cleanup_margin_seconds=400,
        artifact_stream_buffer_bytes=8192,
        artifact_maximum_bytes=64 * 1024 * 1024,
    )

    limits = artifact_preparation_limits(settings)

    assert limits.aggregate_reserved_bytes == settings.artifact_scratch_aggregate_reserved_bytes
    assert limits.maximum_files == settings.artifact_scratch_maximum_files
    assert limits.maximum_concurrency == settings.artifact_scratch_maximum_concurrency
    assert limits.maximum_workspace_entries == settings.artifact_scratch_maximum_workspace_entries
    assert limits.minimum_free_bytes == settings.artifact_scratch_minimum_free_bytes
    assert limits.reservation_ttl_seconds == settings.artifact_scratch_reservation_ttl_seconds
    assert limits.total_deadline_seconds == settings.artifact_preparation_total_deadline_seconds
    assert limits.cleanup_margin_seconds == settings.artifact_scratch_cleanup_margin_seconds
    assert limits.stream_buffer_bytes == settings.artifact_stream_buffer_bytes
    assert limits.maximum_source_bytes == settings.artifact_maximum_bytes


def _load_worker_modules(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> tuple[ModuleType, ModuleType]:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    celery_module = importlib.import_module("app.workers.celery_app")
    celery_module = importlib.reload(celery_module)
    artifacts_module = importlib.import_module("app.workers.artifacts")
    artifacts_module = importlib.reload(artifacts_module)
    return celery_module, artifacts_module


def test_celery_registers_named_task_include_and_exact_beat_cadence(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    celery_module, artifacts_module = _load_worker_modules(monkeypatch, request)
    settings = Settings(
        environment="test",
        celery_task_always_eager=True,
        artifact_scratch_cleanup_interval_seconds=137,
    )
    monkeypatch.setattr(celery_module, "get_settings", lambda: settings)

    app = celery_module.create_celery_app()
    schedule = app.conf.beat_schedule[celery_module.ARTIFACT_SCRATCH_CLEANUP_SCHEDULE]

    assert "app.workers.artifacts" in app.conf.include
    assert schedule["task"] == "workstream.artifacts.cleanup_stale_scratch"
    assert schedule["schedule"] == 137
    assert artifacts_module.cleanup_stale_scratch.name == schedule["task"]
    assert schedule["task"] in celery_module.celery_app.tasks


def test_cleanup_task_runs_shared_helper_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    _celery_module, artifacts_module = _load_worker_modules(monkeypatch, request)
    settings = _enabled_settings(tmp_path)
    calls: list[Settings] = []

    async def cleanup(candidate: Settings) -> int:
        calls.append(candidate)
        return 4

    monkeypatch.setattr(artifacts_module, "get_settings", lambda: settings)
    monkeypatch.setattr(artifacts_module, "cleanup_stale_artifact_scratch", cleanup)
    assert artifacts_module.cleanup_stale_scratch.run() == 4
    assert calls == [settings]

    async def fail_cleanup(_candidate: Settings) -> int:
        raise RuntimeError("scratch cleanup failed")

    monkeypatch.setattr(artifacts_module, "cleanup_stale_artifact_scratch", fail_cleanup)
    with pytest.raises(RuntimeError, match="scratch cleanup failed"):
        artifacts_module.cleanup_stale_scratch.run()


def test_aws_s3_celery_beat_uses_activation_startup_validator(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Keep provider activation at process startup rather than app construction."""
    celery_module, _artifacts_module = _load_worker_modules(monkeypatch, request)
    settings = Settings(**_aws_setting_values(tmp_path), celery_task_always_eager=True)
    monkeypatch.setattr(celery_module, "get_settings", lambda: settings)
    app = celery_module.create_celery_app()
    assert app.conf.task_always_eager is True

    called: list[object] = []
    monkeypatch.setattr(celery_module, "run_async_task", called.append)
    celery_module.validate_artifact_runtime_for_beat()

    assert called == [celery_module.validate_artifact_internal_runtime_startup]
