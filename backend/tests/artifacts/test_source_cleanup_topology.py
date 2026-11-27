"""Production cleanup routing and process-bound deletion entry."""
import os
from types import SimpleNamespace

import pytest
from celery.concurrency.prefork import TaskPool
from celery.exceptions import WorkerShutdown

from app.workers import source_cleanup_topology as topology


@pytest.fixture(autouse=True)
def cleanup_configuration(monkeypatch):
    monkeypatch.setattr(topology, "_validated_parent", None)
    monkeypatch.setattr(topology, "run_async_task", lambda operation: None)
    monkeypatch.setattr(topology, "get_settings", lambda: SimpleNamespace(
        submission_source_cleanup_profile={"maximum_candidates": 10, "run_seconds": 60, "lease_seconds": 30}))


def worker(*, queues=(topology.SOURCE_CLEANUP_QUEUE,), pool=TaskPool, eager=False):
    return SimpleNamespace(pool_cls=pool, app=SimpleNamespace(
        conf=SimpleNamespace(task_always_eager=eager),
        amqp=SimpleNamespace(queues=SimpleNamespace(consume_from=queues))))


@pytest.mark.parametrize("options", [
    {"queues": (topology.SOURCE_CLEANUP_QUEUE, "celery")},
    {"pool": "solo"}, {"pool": "threads"}, {"eager": True},
])
def test_deletion_worker_rejects_unsafe_topology(options):
    with pytest.raises(WorkerShutdown):
        topology.validate_source_cleanup_worker(worker(**options))
    assert topology._validated_parent is None


@pytest.mark.parametrize("mode", ["direct", "eager", "parent", "unvalidated", "extended_limit"])
def test_cleanup_entry_rejects_before_async_work(monkeypatch, mode):
    configured = worker()
    topology.validate_source_cleanup_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", lambda: 1 if mode == "parent" else os.getpid())
    if mode == "unvalidated":
        topology._validated_parent = None
    task = SimpleNamespace(app=configured.app, time_limit=360, request=SimpleNamespace(
        called_directly=mode == "direct", is_eager=mode == "eager",
        timelimit=(361 if mode == "extended_limit" else 360, None)))
    with pytest.raises(RuntimeError):
        topology.require_source_cleanup_worker(task)


def test_validated_child_enters_with_fixed_bound(monkeypatch):
    configured = worker(pool="prefork")
    topology.validate_source_cleanup_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    topology.require_source_cleanup_worker(SimpleNamespace(app=configured.app, time_limit=360,
        request=SimpleNamespace(called_directly=False, is_eager=False, timelimit=(360, None))))


@pytest.mark.parametrize("enabled", [False, True])
def test_schedule_requires_explicit_profile_and_routes_to_cleanup_queue(monkeypatch, enabled):
    import json
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.delenv("WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE", raising=False)
    if enabled:
        monkeypatch.setenv("WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE", json.dumps({
            "maximum_candidates": 10, "run_seconds": 60, "lease_seconds": 30}))
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    try:
        assert app.amqp.router.route({}, topology.SOURCE_CLEANUP_TASK)["queue"].name == topology.SOURCE_CLEANUP_QUEUE
        schedule = app.conf.beat_schedule.get(topology.SOURCE_CLEANUP_SCHEDULE)
        if enabled:
            assert schedule == {"task": topology.SOURCE_CLEANUP_TASK, "schedule": 12 * 60 * 60}
        else:
            assert schedule is None
    finally:
        app.close()
        get_settings.cache_clear()


def test_startup_failure_cannot_authorize_a_cleanup_child(monkeypatch):
    def unavailable(operation):
        raise RuntimeError("namespace unavailable")
    monkeypatch.setattr(topology, "run_async_task", unavailable)
    with pytest.raises(WorkerShutdown, match="startup validation failed"):
        topology.validate_source_cleanup_worker(worker())
    assert topology._validated_parent is None


@pytest.mark.parametrize("cleanup_child", [True, False])
def test_registered_foreign_task_cannot_use_cleanup_credentials(monkeypatch, cleanup_child):
    from app.core.config import get_settings
    from app.core.identifiers import new_record_id
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import artifacts
    calls = []
    async def operation(kind, identifier):
        calls.append((kind, identifier))
    monkeypatch.setattr(artifacts, "run_artifact_internal_operation", operation)
    monkeypatch.setattr(topology, "_validated_parent", os.getpid() if cleanup_child else None)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    identifier = new_record_id()
    try:
        if cleanup_child:
            with pytest.raises(RuntimeError, match="dedicated source cleanup"):
                artifacts.resolve_put_attempt.apply(args=(str(identifier),), throw=True)
            assert calls == []
        else:
            artifacts.resolve_put_attempt.apply(args=(str(identifier),), throw=True)
            assert calls == [("put", identifier)]
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("mode,principal", [
    ("aws_access_key", "arn:aws:iam::123456789012:user/upload"),
    ("aws_access_key", None),
    ("aws_workload_identity", "arn:aws:iam::123456789012:user/cleanup"),
])
def test_native_cleanup_requires_distinct_identified_principal(monkeypatch, mode, principal):
    from app.adapters import artifacts
    from app.interfaces.artifacts import ArtifactConfigurationError

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid cleanup principal reached provider construction")
    monkeypatch.setattr(artifacts, "create_artifact_store_bootstrap", forbidden)
    settings = SimpleNamespace(artifact_store_backend="s3_compatible", artifact_s3_provider_profile="aws_s3",
        artifact_s3_credential_mode=mode, artifact_s3_runtime_user_arn=principal)
    with pytest.raises(ArtifactConfigurationError, match="separate provider principal"):
        artifacts.create_submission_source_cleanup_provider(settings=settings, namespace_claim=None,
            upload_principal="arn:aws:iam::123456789012:user/upload")


def test_native_cleanup_uses_direct_user_bootstrap_without_retired_proof(monkeypatch):
    from app.adapters import artifacts

    marker, store, calls = object(), SimpleNamespace(close=lambda: None), []
    def initialize(claim):
        assert claim is marker
        calls.append(claim)
        return store
    monkeypatch.setattr(artifacts, "create_artifact_store_bootstrap", lambda settings:
        SimpleNamespace(initialize_after_namespace_claim=initialize))
    settings = SimpleNamespace(artifact_store_backend="s3_compatible", artifact_s3_provider_profile="aws_s3",
        artifact_s3_credential_mode="aws_access_key",
        artifact_s3_runtime_user_arn="arn:aws:iam::123456789012:user/cleanup")
    provider = artifacts.create_submission_source_cleanup_provider(settings=settings, namespace_claim=marker,
        upload_principal="arn:aws:iam::123456789012:user/upload")
    assert provider.identity.provider_key == "s3_compatible"
    assert calls == [marker]
    provider.close()
