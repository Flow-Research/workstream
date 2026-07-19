"""Composition tests for artifact startup and scratch cleanup ownership."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from app.adapters.artifacts import artifact_preparation_limits
from app.core.config import Settings, get_settings
from app.main import create_app
from app.interfaces.artifacts import ArtifactProviderLiveProofRequiredError


def _enabled_settings(tmp_path: Path, **changes: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "artifact_store_backend": "local",
        "artifact_local_root": tmp_path / "store",
        "artifact_scratch_root": tmp_path / "scratch",
    }
    values.update(changes)
    return Settings(**values)


class _Store:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def close(self) -> None:
        self.events.append("close")

    def initialize_after_namespace_claim(self, claim: object) -> _Store:
        assert claim == "claim"
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
    settings = Settings(
        environment="production",
        artifact_store_backend="s3_compatible",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_s3_provider_profile="aws_s3",
        artifact_s3_region="us-east-1",
        artifact_s3_bucket="workstream-artifacts-prod",
        artifact_s3_credential_mode="aws_workload_identity",
        artifact_s3_aws_workload_identity_method="container-role",
    )
    app = create_app(settings)
    store = _Store(events)

    def validate_auth(_settings: Settings) -> None:
        events.append("auth")

    async def validate_namespace(candidate_settings: Settings, candidate: object) -> str:
        assert candidate_settings is settings
        assert candidate is store
        events.append("namespace")
        return "claim"

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


async def test_aws_s3_startup_requires_live_provider_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep native AWS runtime-ineligible until the owned activation chunk."""
    import app.main as main_module

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "/v2/credentials/workstream-runtime",
    )
    monkeypatch.setattr(main_module, "build_auth_verifier", lambda _settings: None)
    app = create_app(
        Settings(
            environment="production",
            artifact_store_backend="s3_compatible",
            artifact_scratch_root=tmp_path / "scratch",
            artifact_s3_provider_profile="aws_s3",
            artifact_s3_region="us-east-1",
            artifact_s3_bucket="workstream-artifacts-prod",
            artifact_s3_credential_mode="aws_workload_identity",
            artifact_s3_aws_workload_identity_method="container-role",
        )
    )

    with pytest.raises(ArtifactProviderLiveProofRequiredError) as caught:
        async with app.router.lifespan_context(app):
            pass

    assert caught.value.code == "artifact_provider_live_proof_required"


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


def test_aws_s3_is_runtime_ineligible_for_celery_and_cleanup_task(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Apply the same inactive-provider guard to API and worker entry points."""
    celery_module, artifacts_module = _load_worker_modules(monkeypatch, request)
    settings = Settings(
        environment="production",
        celery_task_always_eager=True,
        artifact_store_backend="s3_compatible",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_s3_provider_profile="aws_s3",
        artifact_s3_region="us-east-1",
        artifact_s3_bucket="workstream-artifacts-prod",
        artifact_s3_credential_mode="aws_workload_identity",
        artifact_s3_aws_workload_identity_method="container-role",
    )
    monkeypatch.setattr(celery_module, "get_settings", lambda: settings)
    with pytest.raises(ArtifactProviderLiveProofRequiredError) as startup_error:
        celery_module.create_celery_app()
    assert startup_error.value.code == "artifact_provider_live_proof_required"

    monkeypatch.setattr(artifacts_module, "get_settings", lambda: settings)
    with pytest.raises(ArtifactProviderLiveProofRequiredError) as task_error:
        artifacts_module.cleanup_stale_scratch.run()
    assert task_error.value.code == "artifact_provider_live_proof_required"
