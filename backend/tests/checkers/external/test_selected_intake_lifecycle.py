"""Shared trusted-intake scratch and cancellation cleanup proofs."""

from types import SimpleNamespace

import pytest

from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits

@pytest.mark.asyncio
@pytest.mark.parametrize("body_failure", ["deadline", "rejection", "cancellation", None])
async def test_intake_cleanup_preserves_unresolved_outcome_but_overrides_work_rejection(body_failure):
    import asyncio
    from workstream_external_services import ExternalServiceUnavailableError
    from app.modules.artifacts.api.submission_archive import (
        SubmissionArchiveFailureCode, SubmissionArchiveRejectedError,
    )
    from app.modules.artifacts.preparation import ArtifactPreparationDeadlineError
    from app.modules.artifacts.trusted_intake import prepared_trusted_intake

    cleanup = ExternalServiceUnavailableError()
    failures = {"deadline": ArtifactPreparationDeadlineError(),
                "rejection": SubmissionArchiveRejectedError(SubmissionArchiveFailureCode.MALFORMED),
                "cancellation": asyncio.CancelledError(), None: None}
    original = failures[body_failure]
    events = []

    class Session:
        def abort(self):
            events.append("abort")

        async def close(self):
            events.append("close")
            raise cleanup

    class Adapter:
        async def prepare(self, request):
            return Session()

    expected = original if body_failure in {"deadline", "cancellation"} else cleanup
    with pytest.raises(type(expected)) as raised:
        async def source():
            from types import SimpleNamespace
            from unittest.mock import AsyncMock
            return SimpleNamespace(commitment=SimpleNamespace(byte_count=1), close=AsyncMock())

        async with prepared_trusted_intake(
            Adapter(), source(), phase="pre_submit", policy_sha256="sha256:" + "a" * 64,
            limits=SubmissionArchiveLimits(), deadline=asyncio.get_running_loop().time() + 10,
        ):
            if original is not None:
                raise original
    assert raised.value is expected
    assert events == (["abort", "close"] if body_failure == "cancellation" else ["close"])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["upload_error", "deadline", "cancellation", "boot_error"])
async def test_sealed_handoff_failure_drains_real_scratch_without_leaked_reader(tmp_path, failure):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from workstream_external_services import ExternalServiceUnavailableError
    from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager, ArtifactPreparationLimits, ArtifactPreparationDeadlineError
    from app.modules.artifacts.trusted_intake import prepared_trusted_intake

    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=ArtifactPreparationLimits(minimum_free_bytes=0))
    preparation = ArtifactPreparationService(manager)
    entered = asyncio.Event()

    async def stream():
        yield b"archive bytes"
        entered.set()
        if failure == "upload_error":
            raise OSError("upload interrupted")
        if failure in {"deadline", "cancellation"}:
            await asyncio.Event().wait()

    intake = SimpleNamespace(prepare=AsyncMock(side_effect=ExternalServiceUnavailableError()))

    async def operation():
        async with prepared_trusted_intake(
            intake, preparation.prepare(stream(), media_type="application/zip"),
            phase="post_submit", policy_sha256="sha256:" + "a" * 64,
            limits=SubmissionArchiveLimits(), deadline=asyncio.get_running_loop().time() + (0.02 if failure == "deadline" else 2),
        ):
            pytest.fail("failed handoff exposed a session")

    task = asyncio.create_task(operation())
    if failure != "deadline":
        await asyncio.wait_for(entered.wait(), 2)
    if failure == "cancellation":
        task.cancel()
    from app.interfaces.artifacts import ArtifactStoreUnavailableError
    expected = {"upload_error": ArtifactStoreUnavailableError, "deadline": ArtifactPreparationDeadlineError,
                "cancellation": asyncio.CancelledError, "boot_error": ExternalServiceUnavailableError}[failure]
    with pytest.raises(expected):
        await asyncio.wait_for(task, 2)
    if failure == "boot_error":
        intake.prepare.assert_awaited_once()
        assert intake.prepare.call_args.args[0].archive_byte_count == len(b"archive bytes")
    else:
        intake.prepare.assert_not_awaited()
    assert preparation._active == {} and preparation.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_failure", ["integrity", "deadline", None])
async def test_cancellation_during_source_close_preserves_real_cleanup_failure(
    tmp_path, monkeypatch, cleanup_failure,
):
    import asyncio
    from unittest.mock import AsyncMock
    from app.modules.artifacts.preparation import (
        ArtifactPreparationDeadlineError, ArtifactPreparationLimits,
        ArtifactPreparationService, ArtifactScratchIntegrityError, ArtifactScratchManager,
    )
    from app.modules.artifacts.trusted_intake import prepared_trusted_intake

    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(minimum_free_bytes=0),
    )
    preparation = ArtifactPreparationService(manager)
    entered, finish = asyncio.Event(), asyncio.Event()
    original_release = manager.release
    errors = {"integrity": ArtifactScratchIntegrityError("release failed"),
              "deadline": ArtifactPreparationDeadlineError("release timed out"), None: None}
    error = errors[cleanup_failure]
    session = SimpleNamespace(close=AsyncMock(), abort=lambda: None)
    adapter = SimpleNamespace(prepare=AsyncMock(return_value=session))
    sources = []

    async def stream():
        yield b"sealed source"

    async def paused_release(reservation):
        entered.set()
        await finish.wait()
        if error is not None:
            raise error
        await original_release(reservation)

    async def operation():
        async with prepared_trusted_intake(
            adapter, preparation.prepare(stream(), media_type="application/zip"),
            phase="post_submit", policy_sha256="sha256:" + "a" * 64,
            limits=SubmissionArchiveLimits(), deadline=asyncio.get_running_loop().time() + 10,
        ) as (prepared, _):
            sources.append(prepared)

    monkeypatch.setattr(manager, "release", paused_release)
    task = asyncio.create_task(operation())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        finish.set()
        if error is None:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert not preparation._active
            assert (await manager.usage()).reservation_count == 0
        else:
            with pytest.raises(ArtifactScratchIntegrityError, match="trusted_intake_source_cleanup_unconfirmed") as raised:
                await asyncio.wait_for(task, 2)
            assert raised.value.__cause__ is error
            assert len(preparation._active) == 1
            assert (await manager.usage()).reservation_count == 1
        session.close.assert_awaited_once()
    finally:
        finish.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        monkeypatch.setattr(manager, "release", original_release)
        for prepared in sources:
            await prepared.close()
        assert not preparation._active
        assert (await manager.usage()).reservation_count == 0
        manager.close()
