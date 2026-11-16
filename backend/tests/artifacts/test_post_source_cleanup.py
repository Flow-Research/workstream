"""Exact source readers close before failed or cancelled POST materialization returns."""

import asyncio

import pytest

from app.modules.artifacts.preparation import ArtifactScratchIntegrityError
from app.modules.checkers.api.materialization import PostSubmissionMaterializationFailure
from tests.checkers.execution.support import material_execution
from tests.post_submit_materialization_helpers import material_fixture


class _ForbiddenConsumer:
    def __init__(self):
        self.calls = 0

    async def evaluate(self, *_args):
        self.calls += 1
        pytest.fail("failed source preparation reached the consumer")


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_source_stream_closes_before_scratch_failure_returns(tmp_path, isolated_database_env, monkeypatch, provider):
    from app.modules.artifacts.preparation import ArtifactScratchCapacityError
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket
        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        execution = await material_execution(h)
        consumer = _ForbiddenConsumer()
        closed, written = [], []
        original_open, original_write = h.store.open_source, h.preparation._write_chunk

        async def observed_source(source, **kwargs):
            stream = original_open(source, **kwargs)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                await stream.aclose()
                closed.append(source.location.operation_id)

        async def failed_write(descriptor, chunk):
            await original_write(descriptor, chunk)
            written.append(len(chunk))
            raise ArtifactScratchCapacityError("injected scratch exhaustion after first source chunk")

        monkeypatch.setattr(h.store, "open_source", observed_source)
        monkeypatch.setattr(h.preparation, "_write_chunk", failed_write)
        with pytest.raises(PostSubmissionMaterializationFailure, match="material_unavailable"):
            await h.service.materialize(execution, consumer)
        assert len(written) == len(closed) == 1
        assert consumer.calls == 0 and not h.preparation._active
        assert (await h.manager.usage()).reserved_bytes == 0


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_source_close_drains_repeated_cancellation(tmp_path, isolated_database_env, monkeypatch, provider):
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket
        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        execution = await material_execution(h)
        consumer = _ForbiddenConsumer()
        written, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        closed = []
        original_open, original_write = h.store.open_source, h.preparation._write_chunk

        async def observed_source(source, **kwargs):
            stream = original_open(source, **kwargs)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                closing.set()
                await release.wait()
                await stream.aclose()
                closed.append(source.location.operation_id)

        async def paused_write(descriptor, chunk):
            await original_write(descriptor, chunk)
            written.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(h.store, "open_source", observed_source)
        monkeypatch.setattr(h.preparation, "_write_chunk", paused_write)
        operation = asyncio.create_task(h.service.materialize(execution, consumer))
        try:
            await asyncio.wait_for(written.wait(), 10)
            operation.cancel()
            await asyncio.wait_for(closing.wait(), 10)
            operation.cancel()
            await asyncio.sleep(0)
            assert not operation.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(operation, 10)
            assert len(closed) == 1 and consumer.calls == 0
            assert not h.preparation._active and (await h.manager.usage()).reserved_bytes == 0
        finally:
            release.set()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_unconfirmed_source_close_is_integrity_failure(failure):
    from app.modules.artifacts.post_submit_materialization import _close_source_stream

    async def source():
        try:
            yield b"source"
        finally:
            raise failure("injected source close failure")

    stream = source()
    assert await anext(stream) == b"source"
    with pytest.raises(ArtifactScratchIntegrityError, match="source stream cleanup is unconfirmed"):
        await _close_source_stream(stream)
