"""The hidden request handler using the Celery child's real ART provider lease."""

import asyncio
import json

import pytest
from sqlalchemy import select, func

from app.adapters.artifacts import worker_post_submission_materialization
from app.adapters.artifacts import internal_workers
from app.adapters.outbox import production_outbox_delivery
from app.interfaces.artifacts import ArtifactObjectMissingError
from app.modules.checkers.api.execution import REQUEST_EVENT
from app.modules.outbox.models import OutboxEvent
from tests.checkers.execution.support import material_execution
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_post_submit_materialization import Consumer
from tests.test_s3_artifact_store import provision_minio_bucket
from .support import delivery_fixture, outcome, state


def _worker_port(h, monkeypatch):
    """Keep the real child runtime on the fixture's exact claimed namespace."""
    import app.core.config as config
    import app.modules.artifacts.service as artifact_service

    assert internal_workers._runtime is None
    monkeypatch.setattr(config, "get_settings", lambda: h.settings)
    monkeypatch.setattr(internal_workers, "get_settings", lambda: h.settings)
    monkeypatch.setattr(artifact_service, "get_session_factory", lambda: h.factory)
    port = worker_post_submission_materialization(sessions=h.factory)
    assert internal_workers._runtime is None
    assert internal_workers._runtime_active_operations == 0
    return port


def _scratch_is_empty(h):
    root = h.settings.artifact_scratch_root
    assert root is not None
    assert list((root / "workspaces").iterdir()) == []
    assert internal_workers._runtime_active_operations == 0


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_worker_art_lease_executes_exact_hidden_request(
    tmp_path, isolated_database_env, monkeypatch, provider,
):
    if provider == "minio":
        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        port = _worker_port(h, monkeypatch)
        try:
            d = await delivery_fixture(h, materialization=port)
            assert (REQUEST_EVENT, 1) not in production_outbox_delivery(h.factory)._registry.keys
            receipt = await d.delivery.deliver(
                h.created.evaluation_event_id, h.request.project_id, "worker-runtime",
            )
            assert outcome(receipt)["delivery_state"] == "acknowledged"
            saved = await state(h)
            assert saved["run"]["status"] == "completed"
            assert saved["run"]["material_custody"]["content_sha256"] == h.request.content_sha256
            assert saved["events"] == 1
            assert internal_workers._runtime is not None
            _scratch_is_empty(h)
            _scratch_is_empty(h)
        finally:
            internal_workers.shutdown_artifact_internal_runtime()
        assert internal_workers._runtime is None


@pytest.mark.parametrize("stage", ["stream", "consumer"])
async def test_worker_art_lease_cancellation_revokes_view_and_scratch(
    tmp_path, isolated_database_env, monkeypatch, stage,
):
    from app.adapters.artifacts.local import LocalStorageAdapter

    async with material_fixture(tmp_path, isolated_database_env) as h:
        port = _worker_port(h, monkeypatch)
        try:
            consumer = Consumer(h.files)
            consumer.release = asyncio.Event()
            stream_entered, stream_release = asyncio.Event(), asyncio.Event()
            original_open = LocalStorageAdapter.open

            async def paused_stream(store, reference):
                async for chunk in original_open(store, reference):
                    stream_entered.set()
                    await stream_release.wait()
                    yield chunk

            with monkeypatch.context() as patch:
                if stage == "stream":
                    patch.setattr(LocalStorageAdapter, "open", paused_stream)
                operation = asyncio.create_task(port.materialize(await material_execution(h), consumer))
                try:
                    entered = stream_entered if stage == "stream" else consumer.entered
                    await asyncio.wait_for(entered.wait(), 20)
                    assert internal_workers._runtime_active_operations == 1
                    operation.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await operation
                finally:
                    stream_release.set()
                    consumer.release.set()
                    if not operation.done():
                        operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
            if stage == "consumer":
                with pytest.raises(RuntimeError, match="closed"):
                    _ = consumer.view.entries
            else:
                assert consumer.calls == 0 and consumer.view is None
            _scratch_is_empty(h)
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def test_worker_bootstrap_unavailable_has_no_trusted_result(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        port = _worker_port(h, monkeypatch)
        async def unavailable():
            raise RuntimeError("controlled provider bootstrap outage")

        try:
            d = await delivery_fixture(h, materialization=port)
            monkeypatch.setattr(internal_workers, "initialize_artifact_internal_runtime", unavailable)
            receipt = await d.delivery.deliver(
                h.created.evaluation_event_id, h.request.project_id, "unavailable-runtime",
            )
            assert outcome(receipt)["invocation_unknown"] is True
            saved = await state(h)
            assert saved["run"]["result_json"] is None
            assert saved["events"] == 0
            assert internal_workers._runtime is None
            assert internal_workers._runtime_active_operations == 0
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def test_worker_scratch_construction_failure_releases_provider_lease(
    tmp_path, isolated_database_env, monkeypatch,
):
    import app.adapters.artifacts as artifact_adapter

    async with material_fixture(tmp_path, isolated_database_env) as h:
        port = _worker_port(h, monkeypatch)
        execution = await material_execution(h)

        def unavailable(_settings):
            raise RuntimeError("controlled scratch construction outage")

        try:
            with monkeypatch.context() as patch:
                patch.setattr(artifact_adapter, "create_artifact_scratch_manager", unavailable)
                with pytest.raises(RuntimeError, match="scratch construction outage"):
                    await port.materialize(execution, Consumer(h.files))
            assert internal_workers._runtime is not None
            assert internal_workers._runtime_active_operations == 0
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def test_worker_known_missing_object_records_infrastructure_result(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.adapters.artifacts.local import LocalStorageAdapter

    async with material_fixture(tmp_path, isolated_database_env) as h:
        port = _worker_port(h, monkeypatch)

        def missing(_store, _reference):
            raise ArtifactObjectMissingError("controlled verified object loss")

        try:
            d = await delivery_fixture(h, materialization=port)
            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "open", missing)
                receipt = await d.delivery.deliver(
                    h.created.evaluation_event_id, h.request.project_id, "missing-object",
                )
            assert outcome(receipt)["delivery_state"] == "acknowledged"
            saved = await state(h)
            assert saved["run"]["status"] == "infrastructure_failed"
            assert json.loads(saved["run"]["result_json"])["infrastructure_failure_code"] == "material_unavailable"
            assert saved["events"] == 0
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
            _scratch_is_empty(h)
        finally:
            internal_workers.shutdown_artifact_internal_runtime()
