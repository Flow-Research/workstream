"""Composition tests for artifact startup and scratch cleanup ownership."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.adapters.artifacts import artifact_preparation_limits
from app.core.config import ARTIFACT_DIRECT_USER_IDENTITY_TIMEOUT_SECONDS, Settings, get_settings
from app.interfaces.artifacts import ArtifactConfigurationError
from app.main import create_app
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
    """Return a native AWS role credential configuration."""
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

    def create(_settings: Settings) -> _Store:
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

    def create(_settings: Settings) -> _Store:
        events.append("construct")
        return store

    async def cleanup(_settings: Settings) -> int:
        events.append("cleanup")
        return 0

    monkeypatch.setattr(main_module, "build_auth_verifier", validate_auth)
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


async def test_missing_direct_user_key_refuses_api_startup_after_namespace_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.main as main_module

    settings = Settings(**(_aws_setting_values(tmp_path) | {
        "artifact_s3_credential_mode": "aws_access_key",
        "artifact_s3_aws_workload_identity_method": None,
        "artifact_s3_runtime_user_arn": "arn:aws:iam::123456789012:user/workstream-artifacts",
        "artifact_s3_direct_user_credential_file": tmp_path / "missing.json",
    }))
    events: list[str] = []
    store = _Store(events)

    async def validate_namespace(_settings: Settings, candidate: object) -> str:
        assert candidate is store
        events.append("namespace")
        return "claim"

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_module, "build_auth_verifier", lambda _settings: None)
    monkeypatch.setattr(main_module, "create_artifact_store_bootstrap", lambda _settings: store)
    monkeypatch.setattr(main_module, "_validate_artifact_storage_namespace_at_startup", validate_namespace)
    app = create_app(settings)

    with pytest.raises(ArtifactConfigurationError, match="AWS credentials could not be resolved"):
        async with app.router.lifespan_context(app):
            pytest.fail("API startup accepted the unavailable direct IAM user key")

    assert events == ["namespace", "close"]


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

    def create(_settings: Settings) -> _Store:
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

    def create(_settings: Settings) -> _Store:
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


def test_celery_prefork_allows_direct_iam_user_startup_verification(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    celery_module, _artifacts_module = _load_worker_modules(monkeypatch, request)
    base = _aws_setting_values(tmp_path) | {"celery_task_always_eager": True}
    workload = Settings(**base)
    direct_user = Settings(**(base | {
        "artifact_s3_credential_mode": "aws_access_key",
        "artifact_s3_aws_workload_identity_method": None,
        "artifact_s3_runtime_user_arn": "arn:aws:iam::123456789012:user/workstream-artifacts",
        "artifact_s3_direct_user_credential_file": tmp_path / "aws-access-key.json",
    }))

    monkeypatch.setattr(celery_module, "get_settings", lambda: workload)
    prior_child_budget = celery_module.create_celery_app().conf.worker_proc_alive_timeout
    monkeypatch.setattr(celery_module, "get_settings", lambda: direct_user)
    direct_child_budget = celery_module.create_celery_app().conf.worker_proc_alive_timeout

    assert direct_child_budget == prior_child_budget + ARTIFACT_DIRECT_USER_IDENTITY_TIMEOUT_SECONDS


def test_aws_s3_celery_beat_uses_namespace_startup_validator(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Check provider namespace at process startup."""
    celery_module, _artifacts_module = _load_worker_modules(monkeypatch, request)
    settings = Settings(**_aws_setting_values(tmp_path), celery_task_always_eager=True)
    monkeypatch.setattr(celery_module, "get_settings", lambda: settings)
    app = celery_module.create_celery_app()
    assert app.conf.task_always_eager is True

    called: list[object] = []
    monkeypatch.setattr(celery_module, "run_async_task", called.append)
    celery_module.validate_artifact_runtime_for_beat()

    assert called == [celery_module.validate_artifact_internal_runtime_startup]
