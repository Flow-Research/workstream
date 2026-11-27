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


@pytest.mark.parametrize("case", ["unknown", "before_send", "scratch_failure", "material_failure"])
async def test_outer_post_deadline_drains_source_and_preserves_invocation_custody(monkeypatch, case):
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.core.identifiers import new_record_id
    from app.interfaces.external_checker_execution import ExternalCheckerExecutionOutcomeUnknown
    from app.modules.artifacts import post_submit_materialization as materialization
    from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
    from app.modules.checkers.api.execution import EvaluationReservation, ExecuteFacts, ExecutionLease
    from tests.checkers.execution.support import selected_request

    request = selected_request()
    facts = ExecuteFacts(request=request, lease=ExecutionLease(
        reservation=EvaluationReservation(
            request_id=request.evaluation_request_id, request_digest=request.request_sha256,
            attempt_id=new_record_id(), result_id=new_record_id(), evaluation_generation=1,
        ),
        lease_id=new_record_id(), lease_generation=1, expires_at=datetime.now(UTC) + timedelta(minutes=1),
    ))
    selected = SimpleNamespace(current=SimpleNamespace(
        sealed_source="fixture-source", media_type="application/zip", sha256=request.content_sha256,
        byte_count=1, semantic_manifest_sha256=request.content_sha256,
    ))
    closing, release, drained = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def source(reference):
        assert reference == selected.current.sealed_source
        try:
            yield b"x"
        finally:
            closing.set()
            await release.wait()
            drained.set()
            if case == "scratch_failure":
                raise RuntimeError("controlled source close failure")

    async def prepare(stream, **_kwargs):
        assert await anext(stream) == b"x"
        return SimpleNamespace(commitment=object(), inspect=AsyncMock())

    @asynccontextmanager
    async def prepared_intake(_adapter, preparation, **_kwargs):
        try:
            yield await preparation, SimpleNamespace(abort=Mock())
        finally:
            if case == "material_failure":
                raise PostSubmissionMaterializationFailure("controlled material cleanup failure")

    original_error = (PostSubmissionMaterializationFailure("before_send") if case == "before_send"
                      else ExternalCheckerExecutionOutcomeUnknown())
    processor = AsyncMock(side_effect=original_error)
    owner = materialization.PostSubmissionMaterializer(
        sessions=None, tasks=None, store=SimpleNamespace(open_source=source), namespace=None,
        preparation=SimpleNamespace(prepare=prepare, _process_prepared_post_submission=processor),
        intake=None, archive_limits=SubmissionArchiveLimits(), artifact_deadline_ms=30_000,
        authority=None, current_execution=None, revision_tasks=None, revision_feedback=None,
    )
    read = AsyncMock(return_value=(selected, new_record_id()))
    monkeypatch.setattr(owner, "_select", read)
    monkeypatch.setattr(owner, "_authority_facts", Mock(return_value=SimpleNamespace(predecessor=None)))
    monkeypatch.setattr(materialization, "prepared_trusted_intake", prepared_intake)
    monkeypatch.setattr(materialization, "build_submission_manifest", Mock(return_value=SimpleNamespace(
        sha256=request.content_sha256, total_expanded_bytes=1, entry_count=1,
    )))

    deadline = asyncio.timeout(None)

    async def execute():
        async with deadline:
            return await owner.materialize(facts, _ForbiddenConsumer())

    operation = asyncio.create_task(execute())
    try:
        await asyncio.wait_for(closing.wait(), 2)
        processor.assert_awaited_once()
        if case != "material_failure":
            deadline.reschedule(asyncio.get_running_loop().time())
            await asyncio.sleep(0)
            assert operation.cancelling()
        assert not operation.done() and not drained.is_set()
        release.set()
        expected = {
            "unknown": ExternalCheckerExecutionOutcomeUnknown,
            "before_send": TimeoutError,
            "scratch_failure": ArtifactScratchIntegrityError,
            "material_failure": ExternalCheckerExecutionOutcomeUnknown,
        }[case]
        with pytest.raises(expected) as result:
            await asyncio.wait_for(operation, 2)
        assert deadline.expired() == (case != "material_failure")
        assert drained.is_set()
        if case in {"unknown", "material_failure"}:
            assert result.value is original_error
        assert read.await_count == (2 if case == "before_send" else 1)
    finally:
        release.set()
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
