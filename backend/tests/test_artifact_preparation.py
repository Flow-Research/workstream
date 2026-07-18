"""Proof for bounded committed artifact-source preparation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import errno
import fcntl
import hashlib
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace
import threading
import time
from typing import Any, BinaryIO

import pytest

from app.interfaces.artifacts import (
    ArtifactInputMismatchError,
    ArtifactLimitExceededError,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationDeadlineError,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchCapacityError,
    ArtifactScratchIntegrityError,
    ArtifactScratchManager,
    ArtifactScratchUsage,
)
from app.modules.artifacts.sources import (
    ArtifactCommitment,
    CommittedArtifactSource,
    PreparedArtifact,
)


async def byte_stream(*chunks: bytes) -> AsyncIterator[bytes]:
    """Yield exact source chunks."""
    for chunk in chunks:
        yield chunk


def preparation_limits(**changes: Any) -> ArtifactPreparationLimits:
    """Build fast focused-test limits while retaining full-max reservations."""
    values: dict[str, Any] = {
        "aggregate_reserved_bytes": 2 * HARD_MAXIMUM_ARTIFACT_BYTES,
        "maximum_files": 2,
        "maximum_concurrency": 2,
        "minimum_free_bytes": 0,
        "reservation_ttl_seconds": 30.0,
        "total_deadline_seconds": 10.0,
        "cleanup_margin_seconds": 5.0,
        "stream_buffer_bytes": 2,
        "maximum_source_bytes": 64,
    }
    values.update(changes)
    return ArtifactPreparationLimits(**values)


def _join_or_kill_process(
    process: multiprocessing.Process,
    *,
    timeout: float = 10,
) -> None:
    """Bound child shutdown, including the fallback wait after termination."""
    process.join(timeout=timeout)
    if process.is_alive():
        process.kill()
        process.join(timeout=timeout)
    assert not process.is_alive(), "child process did not terminate"


def _hold_cross_process_reservation(
    root: str,
    limits: ArtifactPreparationLimits,
    ready: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    """Hold one real reservation in another process."""

    async def hold() -> None:
        manager = ArtifactScratchManager(root=Path(root), limits=limits)
        reservation, descriptor = await manager.allocate()
        os.close(descriptor)
        ready.set()
        await asyncio.to_thread(release.wait, 10)
        await manager.release(reservation)
        manager.close()

    asyncio.run(hold())


def _crash_with_reservation(
    root: str,
    limits: ArtifactPreparationLimits,
    connection: multiprocessing.connection.Connection,
) -> None:
    """Leave one ledger entry and file as a crashed process would."""

    async def reserve() -> int:
        manager = ArtifactScratchManager(root=Path(root), limits=limits)
        reservation, descriptor = await manager.allocate()
        os.close(descriptor)
        return reservation.expires_at_unix_ns

    connection.send(asyncio.run(reserve()))
    connection.close()
    os._exit(0)


def _initialize_shared_scratch_root(
    root: str,
    limits: ArtifactPreparationLimits,
    start: multiprocessing.synchronize.Event,
    connection: multiprocessing.connection.Connection,
) -> None:
    """Initialize one absent scratch root concurrently in a real process."""
    start.wait(timeout=10)
    try:
        manager = ArtifactScratchManager(root=Path(root), limits=limits)
        manager.close()
        connection.send(None)
    except BaseException as exc:
        connection.send(repr(exc))
    finally:
        connection.close()


def _initialize_shared_scratch_root_with_order_probe(
    root: str,
    limits: ArtifactPreparationLimits,
    start: multiprocessing.synchronize.Event,
    child_started: multiprocessing.synchronize.Event,
    connection: multiprocessing.connection.Connection,
) -> None:
    """Report scratch lock and marker-validation order from a real child."""
    original_acquire = ArtifactScratchManager._acquire_ledger_lock
    original_validate = ArtifactScratchManager._validate_existing_root_marker

    def tracked_acquire(manager: ArtifactScratchManager, descriptor: int) -> None:
        connection.send("lock_wait_started")
        original_acquire(manager, descriptor)
        connection.send("lock_acquired")

    def tracked_validate(manager: ArtifactScratchManager) -> None:
        connection.send("marker_validation_started")
        original_validate(manager)

    start.wait(timeout=10)
    ArtifactScratchManager._acquire_ledger_lock = tracked_acquire
    ArtifactScratchManager._validate_existing_root_marker = tracked_validate
    child_started.set()
    try:
        manager = ArtifactScratchManager(root=Path(root), limits=limits)
        manager.close()
        connection.send("initialized")
    except BaseException as exc:
        connection.send(f"error:{exc!r}")
    finally:
        connection.close()


def _hold_live_ledger_publication(
    root: str,
    limits: ArtifactPreparationLimits,
    ready: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    """Hold one valid ledger temp publication under the cross-process lock."""
    manager = ArtifactScratchManager(root=Path(root), limits=limits)
    temporary = ".ledger." + "a" * 32 + ".tmp"
    with manager._locked_ledger():
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=manager._root_fd,
        )
        os.close(descriptor)
        ready.set()
        release.wait(timeout=10)
        os.unlink(temporary, dir_fd=manager._root_fd)
    manager.close()


@pytest.mark.asyncio
async def test_preparation_seals_exact_commitment_and_single_stream(tmp_path: Path) -> None:
    """Bind the server commitment to exactly one complete second-pass stream."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(
        byte_stream(b"he", b"llo"),
        media_type="text/plain",
    )
    expected = "sha256:" + hashlib.sha256(b"hello").hexdigest()
    assert prepared.commitment.sha256 == expected
    assert prepared.commitment.byte_count == 5
    assert prepared.commitment.media_type == "text/plain"
    assert (await manager.usage()).reserved_bytes == HARD_MAXIMUM_ARTIFACT_BYTES

    async with prepared as source:
        assert source.commitment is prepared.commitment
        chunks = [chunk async for chunk in source.stream()]
        assert chunks == [b"he", b"ll", b"o"]
        with pytest.raises(ArtifactScratchIntegrityError, match="already claimed"):
            _ = [chunk async for chunk in source.stream()]

    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


def test_committed_sources_cannot_be_publicly_assembled() -> None:
    """Reject caller-selected commitment and stream pairing."""
    from app.modules.artifacts.sources import _COMMITTED_SOURCE_SEAL

    commitment = ArtifactCommitment(
        sha256="sha256:" + "0" * 64,
        byte_count=0,
        media_type="application/octet-stream",
    )
    owner = SimpleNamespace()
    with pytest.raises(TypeError, match="only be created"):
        CommittedArtifactSource(
            owner=owner,
            binding=object(),
            commitment=commitment,
        )
    with pytest.raises(TypeError, match="only be created"):
        PreparedArtifact(
            owner=owner,
            binding=object(),
            commitment=commitment,
        )
    with pytest.raises(TypeError, match="only be created"):
        PreparedArtifact._from_preparation_service(
            owner=owner,
            binding=object(),
        )
    forged = object.__new__(CommittedArtifactSource)
    forged._owner = owner
    forged._binding = object()
    forged._commitment = commitment
    forged._seal = _COMMITTED_SOURCE_SEAL
    with pytest.raises(ArtifactScratchIntegrityError, match="unavailable"):
        forged.stream()


@pytest.mark.asyncio
async def test_live_committed_source_cannot_be_cloned(tmp_path: Path) -> None:
    """Bind validation to the exact source object minted by preparation."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    source = prepared.committed_source
    clone = object.__new__(CommittedArtifactSource)
    clone._owner = source._owner
    clone._binding = source._binding
    clone._commitment = source._commitment
    clone._seal = source._seal

    with pytest.raises(ArtifactScratchIntegrityError, match="unavailable"):
        clone.stream()
    async with prepared as committed:
        assert b"".join([chunk async for chunk in committed.stream()]) == b"data"
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["digest", "size"])
async def test_client_commitment_mismatch_prevents_provider_call(
    tmp_path: Path,
    mismatch: str,
) -> None:
    """Fail a mismatched client commitment before a future provider invocation."""
    manager = ArtifactScratchManager(
        root=tmp_path / mismatch,
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    provider_calls = 0

    async def future_provider_call(_: CommittedArtifactSource) -> None:
        nonlocal provider_calls
        provider_calls += 1

    expected_sha256 = "sha256:" + hashlib.sha256(b"wrong").hexdigest()
    expected_size = 4
    if mismatch == "digest":
        expected_size = 5
    else:
        expected_sha256 = "sha256:" + hashlib.sha256(b"hello").hexdigest()
    with pytest.raises(ArtifactInputMismatchError):
        prepared = await service.prepare(
            byte_stream(b"hello"),
            media_type="text/plain",
            expected_sha256=expected_sha256,
            expected_size=expected_size,
        )
        await future_provider_call(prepared.committed_source)
    assert provider_calls == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_preparation_rejects_oversize_and_non_byte_sources(tmp_path: Path) -> None:
    """Enforce the source ceiling and byte-only stream contract."""
    limits = preparation_limits(maximum_source_bytes=4)
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    service = ArtifactPreparationService(manager)
    with pytest.raises(ArtifactLimitExceededError):
        await service.prepare(byte_stream(b"abcde"), media_type="text/plain")

    async def invalid_stream() -> AsyncIterator[bytes]:
        yield "not-bytes"  # type: ignore[misc]

    with pytest.raises(ArtifactInputMismatchError, match="must yield bytes"):
        await service.prepare(invalid_stream(), media_type="text/plain")
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_cross_process_ledger_prevents_concurrent_oversubscription(
    tmp_path: Path,
) -> None:
    """Apply one concurrency/byte reservation across independent processes."""
    context = multiprocessing.get_context("spawn")
    limits = preparation_limits(
        aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
        maximum_files=1,
        maximum_concurrency=1,
    )
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_cross_process_reservation,
        args=(str(tmp_path / "scratch"), limits, ready, release),
    )
    process.start()
    try:
        assert await asyncio.to_thread(ready.wait, 10)
        manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
        usage = await manager.usage()
        assert usage.reservation_count == 1
        assert usage.reserved_bytes == HARD_MAXIMUM_ARTIFACT_BYTES
        with pytest.raises(ArtifactScratchCapacityError):
            await manager.allocate()
        manager.close()
    finally:
        release.set()
        await asyncio.to_thread(_join_or_kill_process, process)
    assert process.exitcode == 0


@pytest.mark.asyncio
async def test_free_space_floor_fails_before_file_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a reservation when the full hard maximum would cross the floor."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(minimum_free_bytes=1024),
    )
    monkeypatch.setattr(
        os,
        "fstatvfs",
        lambda _: SimpleNamespace(f_bavail=HARD_MAXIMUM_ARTIFACT_BYTES, f_frsize=1),
    )
    with pytest.raises(ArtifactScratchCapacityError, match="free-space"):
        await manager.allocate()
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_free_space_floor_counts_existing_full_reservations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the free-space floor across shared outstanding reservations."""
    limits = preparation_limits(minimum_free_bytes=HARD_MAXIMUM_ARTIFACT_BYTES)
    root = tmp_path / "scratch"
    first_manager = ArtifactScratchManager(root=root, limits=limits)
    first_reservation, descriptor = await first_manager.allocate()
    os.close(descriptor)
    second_manager = ArtifactScratchManager(root=root, limits=limits)
    monkeypatch.setattr(
        os,
        "fstatvfs",
        lambda _: SimpleNamespace(
            f_bavail=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
            f_frsize=1,
        ),
    )

    with pytest.raises(ArtifactScratchCapacityError, match="free-space"):
        await second_manager.allocate()
    assert (await second_manager.usage()).reservation_count == 1
    assert len(list((root / "files").iterdir())) == 1

    await first_manager.release(first_reservation)
    second_manager.close()
    first_manager.close()


def test_cross_process_root_initialization_is_race_safe(tmp_path: Path) -> None:
    """Let two processes establish the same absent private root safely."""
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes: list[multiprocessing.Process] = []
    receivers: list[multiprocessing.connection.Connection] = []
    root = tmp_path / "shared-scratch"
    for _ in range(2):
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=_initialize_shared_scratch_root,
            args=(str(root), preparation_limits(), start, sender),
        )
        process.start()
        sender.close()
        processes.append(process)
        receivers.append(receiver)
    results: list[str | None] = []
    start.set()
    try:
        for receiver in receivers:
            assert receiver.poll(10), "scratch initializer did not publish a result"
            results.append(receiver.recv())
    finally:
        for receiver in receivers:
            receiver.close()
        for process in processes:
            _join_or_kill_process(process, timeout=15)
    assert [process.exitcode for process in processes] == [0, 0]
    assert results == [None, None]
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    assert manager._root_fd >= 0
    manager.close()


def test_initializer_rejects_root_swapped_between_validation_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind the opened root descriptor to the directory that was validated."""
    root = tmp_path / "scratch"
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    parked = tmp_path / "parked"
    original_open = os.open
    swapped = False

    def swap_root_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if not swapped and dir_fd is None and Path(path) == root.resolve():
            root.rename(parked)
            replacement.rename(root)
            swapped = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_root_before_open)
    with pytest.raises(ValueError, match="changed during initialization"):
        ArtifactScratchManager(root=root, limits=preparation_limits())
    assert swapped
    assert parked.is_dir()


def test_initializer_validates_live_marker_only_after_acquiring_lock(tmp_path: Path) -> None:
    """Wait for an in-progress marker publication before validating its bytes."""
    context = multiprocessing.get_context("spawn")
    root = tmp_path / "shared-scratch"
    root.mkdir(mode=0o700)
    marker = root / ".workstream-artifact-scratch-v1"
    marker.write_bytes(b"")
    marker.chmod(0o600)
    lock = root / ".ledger.lock"
    lock.touch(mode=0o600)
    lock_descriptor = os.open(lock, os.O_RDWR)
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
    start = context.Event()
    child_started = context.Event()
    receiver, sender = context.Pipe(duplex=False)
    limits = preparation_limits()
    process = context.Process(
        target=_initialize_shared_scratch_root_with_order_probe,
        args=(str(root), limits, start, child_started, sender),
    )
    process.start()
    sender.close()
    try:
        start.set()
        assert child_started.wait(30), "scratch initializer did not start"
        assert receiver.poll(30), "scratch initializer did not attempt the ledger lock"
        assert receiver.recv() == "lock_wait_started"
        assert not receiver.poll(0.2)
        marker.write_bytes(ArtifactScratchManager._marker_content(limits))
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        events: list[str] = []
        while "initialized" not in events:
            assert receiver.poll(30), "scratch initializer did not publish its order trace"
            events.append(receiver.recv())
        assert events[:2] == ["lock_acquired", "marker_validation_started"]
        assert events[-1] == "initialized"
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)
        receiver.close()
        _join_or_kill_process(process, timeout=15)
    assert process.exitcode == 0


def test_initializer_lock_acquisition_respects_operation_deadline(tmp_path: Path) -> None:
    """Fail boundedly when scratch initialization cannot acquire its ledger lock."""
    root = tmp_path / "scratch"
    initial = ArtifactScratchManager(root=root, limits=preparation_limits())
    initial.close()
    lock_descriptor = os.open(root / ".ledger.lock", os.O_RDWR)
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
    limits = preparation_limits(
        reservation_ttl_seconds=0.2,
        total_deadline_seconds=0.05,
        cleanup_margin_seconds=0.05,
    )
    started = time.monotonic()
    try:
        with pytest.raises(ArtifactPreparationDeadlineError, match="lock deadline"):
            ArtifactScratchManager(root=root, limits=limits)
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)
    assert time.monotonic() - started < 1


def test_marker_publication_failure_rolls_back_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove a partial first marker so a later initializer can retry safely."""
    root = tmp_path / "scratch"
    original_write_all = ArtifactScratchManager._write_all

    def fail_marker_write(descriptor: int, chunk: memoryview) -> None:
        os.write(descriptor, chunk[:1])
        raise OSError("injected marker write failure")

    monkeypatch.setattr(
        ArtifactScratchManager,
        "_write_all",
        staticmethod(fail_marker_write),
    )
    with pytest.raises(OSError, match="injected marker write failure"):
        ArtifactScratchManager(root=root, limits=preparation_limits())
    assert not (root / ".workstream-artifact-scratch-v1").exists()

    monkeypatch.setattr(
        ArtifactScratchManager,
        "_write_all",
        staticmethod(original_write_all),
    )
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    assert (root / ".workstream-artifact-scratch-v1").is_file()
    manager.close()


def test_marker_fsync_failure_rolls_back_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove a marker whose first durability sync fails so retry remains possible."""
    root = tmp_path / "scratch"
    original_fsync = os.fsync
    fsync_calls = 0

    def fail_first_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            raise OSError("injected marker fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_first_fsync)
    with pytest.raises(OSError, match="injected marker fsync failure"):
        ArtifactScratchManager(root=root, limits=preparation_limits())
    assert not (root / ".workstream-artifact-scratch-v1").exists()

    monkeypatch.setattr(os, "fsync", original_fsync)
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    assert (root / ".workstream-artifact-scratch-v1").is_file()
    manager.close()


@pytest.mark.asyncio
async def test_initialization_waits_for_live_ledger_publication(tmp_path: Path) -> None:
    """Accept a valid transient ledger file only through the held ledger lock."""
    root = tmp_path / "shared-scratch"
    limits = preparation_limits()
    initial = ArtifactScratchManager(root=root, limits=limits)
    initial.close()
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_live_ledger_publication,
        args=(str(root), limits, ready, release),
    )
    process.start()
    try:
        assert await asyncio.to_thread(ready.wait, 10)
        construction = asyncio.create_task(
            asyncio.to_thread(ArtifactScratchManager, root=root, limits=limits)
        )
        await asyncio.sleep(0.1)
        assert not construction.done()
        release.set()
        manager = await asyncio.wait_for(construction, timeout=10)
        manager.close()
    finally:
        release.set()
        await asyncio.to_thread(_join_or_kill_process, process)
    assert process.exitcode == 0


@pytest.mark.asyncio
async def test_preparation_cancellation_releases_file_and_reservation(
    tmp_path: Path,
) -> None:
    """Release scratch state when the source is cancelled mid-preparation."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    started = asyncio.Event()
    never = asyncio.Event()

    async def slow_stream() -> AsyncIterator[bytes]:
        yield b"first"
        started.set()
        await never.wait()
        yield b"second"

    task = asyncio.create_task(service.prepare(slow_stream(), media_type="text/plain"))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_repeated_preparation_cancellation_cannot_interrupt_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect failed-prepare close and release as one ownership handoff."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    source_started = asyncio.Event()
    never = asyncio.Event()
    release_started = asyncio.Event()
    finish_release = asyncio.Event()
    original_release = manager.release

    async def blocked_stream() -> AsyncIterator[bytes]:
        yield b"first"
        source_started.set()
        await never.wait()

    async def delayed_release(reservation: object) -> None:
        release_started.set()
        await finish_release.wait()
        await original_release(reservation)

    monkeypatch.setattr(manager, "release", delayed_release)
    task = asyncio.create_task(service.prepare(blocked_stream(), media_type="text/plain"))
    await asyncio.wait_for(source_started.wait(), timeout=1)
    task.cancel()
    await asyncio.wait_for(release_started.wait(), timeout=1)
    task.cancel()
    await asyncio.sleep(0)
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    assert service._active == {}
    manager.close()


@pytest.mark.asyncio
async def test_post_seal_cancellation_releases_reader_and_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain service ownership until the sealed handle can be returned."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    exiting_timeout = asyncio.Event()
    block_exit = asyncio.Event()

    class ExitGate:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: object | None,
        ) -> None:
            exiting_timeout.set()
            await block_exit.wait()

    monkeypatch.setattr(asyncio, "timeout_at", lambda _: ExitGate())
    task = asyncio.create_task(service.prepare(byte_stream(b"sealed"), media_type="text/plain"))
    await asyncio.wait_for(exiting_timeout.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    assert service._active == {}
    manager.close()


@pytest.mark.asyncio
async def test_preparation_deadline_releases_scratch(tmp_path: Path) -> None:
    """Map a total deadline to stable infrastructure failure and cleanup."""
    limits = preparation_limits(
        reservation_ttl_seconds=0.5,
        total_deadline_seconds=0.05,
        cleanup_margin_seconds=0.1,
    )
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    service = ArtifactPreparationService(manager)

    async def slow_stream() -> AsyncIterator[bytes]:
        yield b"start"
        await asyncio.sleep(1)

    with pytest.raises(ArtifactPreparationDeadlineError):
        await service.prepare(slow_stream(), media_type="text/plain")
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_crash_reservation_is_discovered_and_cleaned_deterministically(
    tmp_path: Path,
) -> None:
    """Clean a crashed process only after its wall-clock reservation expiry."""
    context = multiprocessing.get_context("spawn")
    limits = preparation_limits()
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_crash_with_reservation,
        args=(str(tmp_path / "scratch"), limits, send),
    )
    process.start()
    send.close()
    try:
        assert await asyncio.to_thread(receive.poll, 10), (
            "crashed scratch process did not publish its reservation"
        )
        expires_at = receive.recv()
    finally:
        receive.close()
        await asyncio.to_thread(_join_or_kill_process, process)
    assert process.exitcode == 0
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    assert await manager.stale_reservation_ids(now_unix_ns=expires_at - 1) == ()
    stale = await manager.stale_reservation_ids(now_unix_ns=expires_at)
    assert len(stale) == 1
    assert await manager.cleanup_stale(now_unix_ns=expires_at) == 1
    assert await manager.cleanup_stale(now_unix_ns=expires_at) == 0
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["symlink", "directory"])
async def test_cleanup_rejects_symlink_and_non_regular_scratch_entries(
    tmp_path: Path,
    replacement: str,
) -> None:
    """Never follow or unlink an adversarial non-regular scratch entry."""
    limits = preparation_limits()
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=limits,
    )
    reservation, descriptor = await manager.allocate()
    os.close(descriptor)
    cleaner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    cleaner._owner_process_matches = lambda *_: False
    scratch_file = tmp_path / "scratch" / "files" / reservation.filename
    scratch_file.unlink()
    if replacement == "symlink":
        target = tmp_path / "outside"
        target.write_bytes(b"keep")
        scratch_file.symlink_to(target)
    else:
        scratch_file.mkdir()
    with pytest.raises(ArtifactScratchIntegrityError, match="file is invalid"):
        await cleaner.cleanup_stale(now_unix_ns=reservation.expires_at_unix_ns)
    assert (await manager.usage()).reservation_count == 1
    if replacement == "symlink":
        assert target.read_bytes() == b"keep"
        scratch_file.unlink()
    else:
        scratch_file.rmdir()
    assert await cleaner.cleanup_stale(now_unix_ns=reservation.expires_at_unix_ns) == 1
    cleaner.close()
    await manager.release(reservation)
    manager.close()


@pytest.mark.asyncio
async def test_second_pass_proves_commitment_before_bytes_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep sealed bytes anonymous and reject corruption before yielding."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"safe"), media_type="text/plain")
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    reads = iter((b"evil", b""))

    async def corrupt_verification(_: BinaryIO) -> bytes:
        return next(reads)

    monkeypatch.setattr(service, "_read_chunk", corrupt_verification)
    escaped: list[bytes] = []
    async with prepared as source:
        with pytest.raises(ArtifactScratchIntegrityError, match="changed"):
            async for chunk in source.stream():
                escaped.append(chunk)
    assert escaped == []
    assert (await manager.usage()).reservation_count == 0
    manager.close()


def test_limits_and_roots_fail_closed(tmp_path: Path) -> None:
    """Reject unsafe capacity, timing, and root combinations."""
    with pytest.raises(ValueError, match="at least 512 MiB"):
        preparation_limits(aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES - 1)
    with pytest.raises(ValueError, match="deadline"):
        preparation_limits(
            reservation_ttl_seconds=10,
            total_deadline_seconds=5,
            cleanup_margin_seconds=5,
        )
    with pytest.raises(ValueError, match="concurrency"):
        preparation_limits(maximum_files=1, maximum_concurrency=2)
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "scratch-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        ArtifactScratchManager(root=link, limits=preparation_limits())
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="not private"):
        ArtifactScratchManager(root=shared, limits=preparation_limits())
    assert shared.stat().st_mode & 0o777 == 0o755
    occupied = tmp_path / "occupied"
    occupied.mkdir(mode=0o700)
    (occupied / "unrelated").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="dedicated"):
        ArtifactScratchManager(root=occupied, limits=preparation_limits())
    assert (occupied / "unrelated").read_text(encoding="utf-8") == "keep"
    assert sorted(path.name for path in occupied.iterdir()) == ["unrelated"]

    invalid_marker_root = tmp_path / "invalid-marker"
    invalid_marker_root.mkdir(mode=0o700)
    (invalid_marker_root / ".workstream-artifact-scratch-v1").write_text(
        "not-workstream\n",
        encoding="utf-8",
    )
    (invalid_marker_root / ".ledger.lock").write_bytes(b"")
    invalid_temp = invalid_marker_root / (".ledger." + "c" * 32 + ".tmp")
    invalid_temp.write_bytes(b"keep")
    for path in invalid_marker_root.iterdir():
        path.chmod(0o600)
    before = {
        path.name: path.read_bytes()
        for path in invalid_marker_root.iterdir()
    }
    with pytest.raises(ValueError, match="marker is invalid"):
        ArtifactScratchManager(root=invalid_marker_root, limits=preparation_limits())
    assert {
        path.name: path.read_bytes()
        for path in invalid_marker_root.iterdir()
    } == before


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"maximum_files": 0}, "file limit"),
        ({"minimum_free_bytes": -1}, "free-space"),
        ({"stream_buffer_bytes": 0}, "buffer"),
        ({"maximum_source_bytes": HARD_MAXIMUM_ARTIFACT_BYTES + 1}, "512 MiB"),
        ({"reservation_ttl_seconds": True}, "durations"),
        ({"reservation_ttl_seconds": float("nan")}, "durations"),
        ({"reservation_ttl_seconds": float("inf")}, "durations"),
        ({"reservation_ttl_seconds": float("-inf")}, "durations"),
        ({"maximum_files": 1.5}, "integer limits"),
    ],
)
def test_each_preparation_limit_family_fails_closed(
    changes: dict[str, Any],
    message: str,
) -> None:
    """Exercise every independent safety limit family."""
    with pytest.raises(ValueError, match=message):
        preparation_limits(**changes)


@pytest.mark.asyncio
async def test_capacity_gates_are_independently_enforced(tmp_path: Path) -> None:
    """Enforce file/concurrency and aggregate-byte gates before a new file."""
    concurrency_manager = ArtifactScratchManager(
        root=tmp_path / "concurrency",
        limits=preparation_limits(maximum_files=2, maximum_concurrency=1),
    )
    first, descriptor = await concurrency_manager.allocate()
    os.close(descriptor)
    with pytest.raises(ArtifactScratchCapacityError, match="concurrency"):
        await concurrency_manager.allocate()
    await concurrency_manager.release(first)
    concurrency_manager.close()

    byte_manager = ArtifactScratchManager(
        root=tmp_path / "bytes",
        limits=preparation_limits(
            aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=2,
        ),
    )
    first, descriptor = await byte_manager.allocate()
    os.close(descriptor)
    with pytest.raises(ArtifactScratchCapacityError, match="byte limit"):
        await byte_manager.allocate()
    await byte_manager.release(first)
    byte_manager.close()


@pytest.mark.asyncio
async def test_file_creation_failure_rolls_back_ledger_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not strand capacity when exclusive file creation fails."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    original_open = os.open

    def fail_scratch_open(path: Any, *args: Any, **kwargs: Any) -> int:
        if isinstance(path, str) and path.startswith("prep_"):
            raise OSError("scratch create failed")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", fail_scratch_open)
    with pytest.raises(OSError, match="create failed"):
        await manager.allocate()
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_directory_fsync_failure_rolls_back_file_and_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not strand scratch state when file publication durability fails."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    original_fsync = os.fsync
    failed = False

    def fail_files_directory(descriptor: int) -> None:
        nonlocal failed
        if descriptor == manager._files_fd and not failed:
            failed = True
            raise OSError(errno.EIO, "directory fsync failed")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_files_directory)
    with pytest.raises(OSError, match="directory fsync failed"):
        await manager.allocate()
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_ledger_temp_failure_cleans_file_and_preserves_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent a failed atomic ledger write from poisoning the scratch root."""
    root = tmp_path / "scratch"
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    original_write_all = manager._write_all

    def fail_ledger_temp_write(descriptor: int, chunk: memoryview) -> None:
        target = os.readlink(f"/proc/self/fd/{descriptor}")
        if ".ledger." in target and target.endswith(".tmp"):
            raise OSError(errno.EIO, "ledger temp write failed")
        original_write_all(descriptor, chunk)

    monkeypatch.setattr(manager, "_write_all", fail_ledger_temp_write)
    with pytest.raises(OSError, match="ledger temp write failed"):
        await manager.allocate()
    assert not any(path.name.endswith(".tmp") for path in root.iterdir())
    assert (await manager.usage()).reservation_count == 0
    manager.close()
    stale = root / (".ledger." + "b" * 32 + ".tmp")
    descriptor = os.open(stale, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    reopened = ArtifactScratchManager(root=root, limits=preparation_limits())
    assert not stale.exists()
    reopened.close()


@pytest.mark.asyncio
async def test_root_fsync_failure_restores_reservation_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain retry custody when ledger rollback durability is ambiguous."""
    root = tmp_path / "scratch"
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    original_fsync = os.fsync

    def fail_root_fsync(descriptor: int) -> None:
        if descriptor == manager._root_fd:
            raise OSError(errno.EIO, "root fsync failed")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_root_fsync)
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is pending"):
        await manager.allocate()
    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 0
    assert list((root / "files").iterdir()) == []
    assert not any(path.name.endswith(".tmp") for path in root.iterdir())

    monkeypatch.setattr(os, "fsync", original_fsync)
    assert await manager.retry_pending_cleanup() == 1
    assert manager.pending_cleanup_count == 0
    manager.close()


def test_constructor_failure_closes_pinned_descriptors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close root and files descriptors when initial ledger creation fails."""
    descriptors: dict[str, int] = {}

    def fail_initial_ledger(
        manager: ArtifactScratchManager,
        _: dict[str, Any],
    ) -> None:
        descriptors["root"] = manager._root_fd
        descriptors["files"] = manager._files_fd
        raise OSError(errno.EIO, "initial ledger failed")

    monkeypatch.setattr(ArtifactScratchManager, "_write_ledger", fail_initial_ledger)
    with pytest.raises(OSError, match="initial ledger failed"):
        ArtifactScratchManager(
            root=tmp_path / "scratch",
            limits=preparation_limits(),
        )
    assert set(descriptors) == {"root", "files"}
    for descriptor in descriptors.values():
        with pytest.raises(OSError, match="Bad file descriptor"):
            os.fstat(descriptor)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EIO])
async def test_preparation_maps_filesystem_failures_without_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    """Map capacity and generic filesystem failures to stable safe errors."""
    manager = ArtifactScratchManager(
        root=tmp_path / str(error_number),
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)

    def fail_seal(reservation: object, descriptor: int) -> BinaryIO:
        del reservation
        os.close(descriptor)
        raise OSError(error_number, "private path /must/not/escape")

    monkeypatch.setattr(manager, "_seal_for_read_sync", fail_seal)
    expected_error = (
        ArtifactScratchCapacityError
        if error_number == errno.ENOSPC
        else ArtifactStoreUnavailableError
    )
    with pytest.raises(expected_error) as raised:
        await service.prepare(byte_stream(b"data"), media_type="text/plain")
    assert "/must/not/escape" not in str(raised.value)
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_invalid_cleanup_times_and_missing_release_are_idempotent(
    tmp_path: Path,
) -> None:
    """Reject invalid wall clocks and permit exact repeated release."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    with pytest.raises(ValueError, match="discovery time"):
        await manager.stale_reservation_ids(now_unix_ns=-1)
    with pytest.raises(ValueError, match="cleanup time"):
        await manager.cleanup_stale(now_unix_ns=-1)
    reservation, descriptor = await manager.allocate()
    os.close(descriptor)
    await manager.release(reservation)
    await manager.release(reservation)
    manager.close()
    manager.close()


@pytest.mark.asyncio
async def test_malformed_ledger_and_layout_fail_closed(tmp_path: Path) -> None:
    """Reject malformed coordination state and a replaced files directory."""
    root = tmp_path / "scratch"
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    (root / ".ledger.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactScratchIntegrityError, match="ledger is invalid"):
        await manager.usage()
    manager.close()

    unsafe_root = tmp_path / "unsafe"
    initial = ArtifactScratchManager(root=unsafe_root, limits=preparation_limits())
    initial.close()
    (unsafe_root / "files").rmdir()
    target = tmp_path / "files-target"
    target.mkdir(mode=0o700)
    (unsafe_root / "files").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="layout is unsafe"):
        ArtifactScratchManager(root=unsafe_root, limits=preparation_limits())


@pytest.mark.asyncio
async def test_shared_scratch_root_rejects_mismatched_process_limits(tmp_path: Path) -> None:
    """Fail closed when another process is configured with different root limits."""
    root = tmp_path / "scratch"
    manager = ArtifactScratchManager(root=root, limits=preparation_limits())
    reservation, descriptor = await manager.allocate()
    os.close(descriptor)

    with pytest.raises(ValueError, match="root marker is invalid"):
        ArtifactScratchManager(
            root=root,
            limits=preparation_limits(maximum_concurrency=1),
        )

    assert (await manager.usage()).reservation_count == 1
    await manager.release(reservation)
    manager.close()


@pytest.mark.asyncio
async def test_allocation_cancellation_waits_then_releases_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean a reservation created while allocation cancellation was pending."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    started = threading.Event()
    release = threading.Event()
    original_allocate = manager._allocate_sync

    def delayed_allocate() -> tuple[object, int]:
        result = original_allocate()
        started.set()
        release.wait(timeout=5)
        return result

    monkeypatch.setattr(manager, "_allocate_sync", delayed_allocate)
    task = asyncio.create_task(manager.allocate())
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_repeated_allocation_cancellation_cannot_interrupt_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finish scratch release even when the caller cancels repeatedly."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    allocation_started = threading.Event()
    finish_allocation = threading.Event()
    release_started = threading.Event()
    finish_release = threading.Event()
    original_allocate = manager._allocate_sync
    original_release = manager._release_sync

    def delayed_allocate() -> tuple[object, int]:
        result = original_allocate()
        allocation_started.set()
        finish_allocation.wait(timeout=5)
        return result

    def delayed_release(reservation: object) -> None:
        release_started.set()
        finish_release.wait(timeout=5)
        original_release(reservation)

    monkeypatch.setattr(manager, "_allocate_sync", delayed_allocate)
    monkeypatch.setattr(manager, "_release_sync", delayed_release)
    task = asyncio.create_task(manager.allocate())
    assert await asyncio.to_thread(allocation_started.wait, 5)
    task.cancel()
    finish_allocation.set()
    assert await asyncio.to_thread(release_started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_release_cancellation_clears_durable_and_local_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clear the local shutdown owner in the same cancellation-safe handoff."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    reservation, descriptor = await manager.allocate()
    os.close(descriptor)
    release_started = threading.Event()
    finish_release = threading.Event()
    original_release = manager._release_sync

    def delayed_release(target: object) -> None:
        release_started.set()
        assert finish_release.wait(5), "release operation was not resumed"
        original_release(target)

    monkeypatch.setattr(manager, "_release_sync", delayed_release)
    task = asyncio.create_task(manager.release(reservation))
    assert await asyncio.to_thread(release_started.wait, 2), "release did not start"
    task.cancel()
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert reservation.reservation_id not in manager._owned_reservations
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_allocation_close_failure_retains_reservation_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep quota ownership when raw descriptor invalidation is unproven."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    started = threading.Event()
    finish_allocation = threading.Event()
    original_allocate = manager._allocate_sync
    original_close = os.close
    allocated_descriptor: int | None = None
    close_failed = False

    def delayed_allocate() -> tuple[object, int]:
        nonlocal allocated_descriptor
        result = original_allocate()
        allocated_descriptor = result[1]
        started.set()
        finish_allocation.wait(timeout=5)
        return result

    def fail_allocated_close(descriptor: int) -> None:
        nonlocal close_failed
        if descriptor == allocated_descriptor and not close_failed:
            close_failed = True
            raise OSError(errno.EIO, "injected descriptor close failure")
        original_close(descriptor)

    monkeypatch.setattr(manager, "_allocate_sync", delayed_allocate)
    monkeypatch.setattr(os, "close", fail_allocated_close)
    task = asyncio.create_task(manager.allocate())
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    finish_allocation.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert close_failed
    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    assert allocated_descriptor is not None
    original_close(allocated_descriptor)
    cleaner = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    cleaner._owner_process_matches = lambda *_: False
    expires_at = next(iter(manager._poisoned_reservations.values())).expires_at_unix_ns
    assert await cleaner.cleanup_stale(now_unix_ns=expires_at) == 1
    cleaner.close()
    manager._poisoned_reservations.clear()
    manager.close()


@pytest.mark.asyncio
async def test_ledger_lock_acquisition_respects_operation_deadline(tmp_path: Path) -> None:
    """Fail boundedly when another execution holds the cross-process ledger lock."""
    limits = preparation_limits(
        reservation_ttl_seconds=0.2,
        total_deadline_seconds=0.05,
        cleanup_margin_seconds=0.05,
    )
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    lock_descriptor = os.open(tmp_path / "scratch" / ".ledger.lock", os.O_RDWR)
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
    started = time.monotonic()
    try:
        with pytest.raises(ArtifactPreparationDeadlineError, match="lock deadline"):
            await manager.usage()
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)
    assert time.monotonic() - started < 1
    manager.close()


@pytest.mark.asyncio
async def test_cancelled_allocation_retains_failed_release_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep cleanup ownership when cancellation-time ledger release fails."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    allocation_started = threading.Event()
    finish_allocation = threading.Event()
    original_allocate = manager._allocate_sync
    original_release = manager._release_sync
    release_attempts = 0

    def delayed_allocate() -> tuple[object, int]:
        result = original_allocate()
        allocation_started.set()
        finish_allocation.wait(timeout=5)
        return result

    def fail_release_once(reservation: object) -> None:
        nonlocal release_attempts
        release_attempts += 1
        if release_attempts == 1:
            raise OSError(errno.EIO, "injected allocation release failure")
        original_release(reservation)

    monkeypatch.setattr(manager, "_allocate_sync", delayed_allocate)
    monkeypatch.setattr(manager, "_release_sync", fail_release_once)
    task = asyncio.create_task(manager.allocate())
    assert await asyncio.to_thread(allocation_started.wait, 5)
    task.cancel()
    finish_allocation.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    assert await manager.retry_pending_cleanup() == 1
    assert manager.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_cancelled_seal_closes_read_descriptor_after_write_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve cancellation and dispose the anonymous read descriptor once."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    reservation, write_descriptor = await manager.allocate()
    original_close = os.close
    close_started = threading.Event()
    finish_close = threading.Event()
    write_close_failed = False
    closed_after_failure: list[int] = []

    def close_then_fail(descriptor: int) -> None:
        nonlocal write_close_failed
        if descriptor == write_descriptor and not write_close_failed:
            close_started.set()
            finish_close.wait(timeout=5)
            original_close(descriptor)
            write_close_failed = True
            raise OSError(errno.EIO, "ambiguous write descriptor close failure")
        if write_close_failed:
            closed_after_failure.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(os, "close", close_then_fail)
    task = asyncio.create_task(manager.seal_for_read(reservation, write_descriptor))
    assert await asyncio.to_thread(close_started.wait, 5)
    task.cancel()
    finish_close.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert write_close_failed
    assert len(closed_after_failure) == 1
    with pytest.raises(OSError) as closed_error:
        os.fstat(closed_after_failure[0])
    assert closed_error.value.errno == errno.EBADF
    await manager.release(reservation)
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_seal_retains_custody_when_write_descriptor_remains_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poison quota ownership when sealing cannot prove raw-fd invalidation."""
    limits = preparation_limits()
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    reservation, write_descriptor = await manager.allocate()
    original_close = os.close
    failed = False
    closed_after_failure: list[int] = []

    def fail_before_write_close(descriptor: int) -> None:
        nonlocal failed
        if descriptor == write_descriptor and not failed:
            failed = True
            raise OSError(errno.EIO, "injected pre-close failure")
        if failed:
            closed_after_failure.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(os, "close", fail_before_write_close)
    with pytest.raises(ArtifactScratchIntegrityError, match="ownership is uncertain"):
        await manager.seal_for_read(reservation, write_descriptor)
    assert failed
    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    assert closed_after_failure
    for descriptor in closed_after_failure:
        with pytest.raises(OSError) as closed_error:
            os.fstat(descriptor)
        assert closed_error.value.errno == errno.EBADF

    original_close(write_descriptor)
    cleaner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    cleaner._owner_process_matches = lambda *_: False
    assert await cleaner.cleanup_stale(now_unix_ns=reservation.expires_at_unix_ns) == 1
    cleaner.close()
    manager._poisoned_reservations.clear()
    await manager.release(reservation)
    manager.close()


@pytest.mark.asyncio
async def test_seal_failure_closes_first_pass_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep write-descriptor ownership inside sealing on every failure path."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    reservation, write_descriptor = await manager.allocate()
    original_fsync = os.fsync
    failed = False

    def fail_first_pass_sync(descriptor: int) -> None:
        nonlocal failed
        if descriptor == write_descriptor and not failed:
            failed = True
            raise OSError(errno.EIO, "injected first-pass sync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_first_pass_sync)
    with pytest.raises(OSError, match="first-pass sync failure"):
        await manager.seal_for_read(reservation, write_descriptor)
    assert failed
    with pytest.raises(OSError) as closed_error:
        os.fstat(write_descriptor)
    assert closed_error.value.errno == errno.EBADF

    await manager.release(reservation)
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_fdopen_failure_closes_anonymous_read_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispose sealed bytes if the read-file wrapper cannot be constructed."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    reservation, write_descriptor = await manager.allocate()
    read_descriptor: int | None = None

    def fail_fdopen(descriptor: int, *_: object, **__: object) -> BinaryIO:
        nonlocal read_descriptor
        read_descriptor = descriptor
        raise OSError(errno.EIO, "injected fdopen failure")

    monkeypatch.setattr(os, "fdopen", fail_fdopen)
    with pytest.raises(OSError, match="fdopen failure"):
        await manager.seal_for_read(reservation, write_descriptor)
    assert read_descriptor is not None
    with pytest.raises(OSError) as closed_error:
        os.fstat(read_descriptor)
    assert closed_error.value.errno == errno.EBADF

    await manager.release(reservation)
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_cancelled_seal_retains_failed_reader_close_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain the sealed reader when cancellation-time close fails."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    reservation, write_descriptor = await manager.allocate()
    original_seal = manager._seal_for_read_sync
    seal_finished = threading.Event()
    finish_handoff = threading.Event()

    class FailOnceReader:
        def __init__(self, reader: BinaryIO) -> None:
            self.reader = reader
            self.close_attempts = 0

        def close(self) -> None:
            self.close_attempts += 1
            if self.close_attempts == 1:
                raise OSError(errno.EIO, "injected reader close failure")
            self.reader.close()

    wrapped: FailOnceReader | None = None

    def delayed_seal(reservation_value: object, descriptor: int) -> Any:
        nonlocal wrapped
        reader = original_seal(reservation_value, descriptor)
        wrapped = FailOnceReader(reader)
        seal_finished.set()
        finish_handoff.wait(timeout=5)
        return wrapped

    monkeypatch.setattr(manager, "_seal_for_read_sync", delayed_seal)
    task = asyncio.create_task(manager.seal_for_read(reservation, write_descriptor))
    assert await asyncio.to_thread(seal_finished.wait, 5)
    task.cancel()
    finish_handoff.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert wrapped is not None
    assert wrapped.close_attempts == 1
    assert service.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    with pytest.raises(ArtifactScratchIntegrityError, match="reader cleanup"):
        await manager.release(reservation)
    assert await service.retry_pending_cleanup() == 1
    assert wrapped.close_attempts == 2
    assert wrapped.reader.closed
    assert service.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_allocation_rollback_continues_after_descriptor_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove the file and ledger reservation after a late close error."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    original_fsync = os.fsync
    original_close = os.close
    sync_failed = False
    close_failed = False

    def fail_file_directory_sync(descriptor: int) -> None:
        nonlocal sync_failed
        if descriptor == manager._files_fd and not sync_failed:
            sync_failed = True
            raise OSError(errno.EIO, "injected file directory sync failure")
        original_fsync(descriptor)

    def close_then_fail(descriptor: int) -> None:
        nonlocal close_failed
        if sync_failed and not close_failed:
            original_close(descriptor)
            close_failed = True
            raise OSError(errno.EIO, "injected rollback close failure")
        original_close(descriptor)

    monkeypatch.setattr(os, "fsync", fail_file_directory_sync)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(OSError, match="file directory sync failure"):
        await manager.allocate()
    assert sync_failed and close_failed
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_allocation_rollback_failure_is_retained_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain a published reservation when rollback ledger persistence fails."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    original_fsync = os.fsync
    original_write_ledger = manager._write_ledger
    sync_failed = False
    rollback_failed = False

    def fail_file_directory_sync(descriptor: int) -> None:
        nonlocal sync_failed
        if descriptor == manager._files_fd and not sync_failed:
            sync_failed = True
            raise OSError(errno.EIO, "injected file directory sync failure")
        original_fsync(descriptor)

    def fail_rollback_ledger(payload: dict[str, object]) -> None:
        nonlocal rollback_failed
        if sync_failed and payload.get("reservations") == [] and not rollback_failed:
            rollback_failed = True
            raise OSError(errno.EIO, "injected rollback ledger failure")
        original_write_ledger(payload)

    monkeypatch.setattr(os, "fsync", fail_file_directory_sync)
    monkeypatch.setattr(manager, "_write_ledger", fail_rollback_ledger)
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is pending"):
        await manager.allocate()
    assert sync_failed and rollback_failed
    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    assert list((tmp_path / "scratch" / "files").iterdir()) == []

    monkeypatch.setattr(manager, "_write_ledger", original_write_ledger)
    assert await manager.retry_pending_cleanup() == 1
    assert manager.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_allocation_rollback_sync_failure_retains_ledger_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep retry custody until rollback deletion is directory-durable."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    original_fsync = os.fsync
    file_directory_syncs = 0

    def fail_publication_and_rollback_sync(descriptor: int) -> None:
        nonlocal file_directory_syncs
        if descriptor == manager._files_fd:
            file_directory_syncs += 1
            if file_directory_syncs <= 2:
                raise OSError(errno.EIO, "injected file directory sync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_publication_and_rollback_sync)
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is pending"):
        await manager.allocate()
    assert file_directory_syncs == 2
    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    assert list((tmp_path / "scratch" / "files").iterdir()) == []

    assert await manager.retry_pending_cleanup() == 1
    assert file_directory_syncs == 3
    assert manager.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_ambiguous_ledger_publication_is_retained_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain ownership when ledger publication and rollback both fail."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    original_write_ledger = manager._write_ledger
    publication_failed = False
    rollback_failed = False

    def fail_after_publication_then_fail_rollback(payload: dict[str, object]) -> None:
        nonlocal publication_failed, rollback_failed
        reservations = payload.get("reservations")
        if reservations and not publication_failed:
            original_write_ledger(payload)
            publication_failed = True
            raise OSError(errno.EIO, "injected ambiguous publication failure")
        if publication_failed and reservations == [] and not rollback_failed:
            rollback_failed = True
            raise OSError(errno.EIO, "injected publication rollback failure")
        original_write_ledger(payload)

    monkeypatch.setattr(manager, "_write_ledger", fail_after_publication_then_fail_rollback)
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is pending"):
        await manager.allocate()
    assert publication_failed and rollback_failed
    assert manager.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1

    monkeypatch.setattr(manager, "_write_ledger", original_write_ledger)
    assert await manager.retry_pending_cleanup() == 1
    assert manager.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_manager_close_rejects_live_prepared_reservation(tmp_path: Path) -> None:
    """Do not invalidate directory ownership while a prepared handle is live."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is still pending"):
        manager.close()

    await prepared.close()
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_stale_cleanup_preserves_live_preparation_shutdown_ownership(
    tmp_path: Path,
) -> None:
    """Keep a local live handle as shutdown owner after shared stale cleanup."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    expires_at = next(iter(manager._owned_reservations.values())).expires_at_unix_ns

    assert await manager.cleanup_stale(now_unix_ns=expires_at) == 0
    assert (await manager.usage()).reservation_count == 1
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is still pending"):
        manager.close()

    await prepared.close()
    manager.close()


@pytest.mark.asyncio
async def test_stale_cleanup_preserves_other_live_process_custody(tmp_path: Path) -> None:
    """Do not free expired quota while another manager's owner PID is alive."""
    limits = preparation_limits()
    owner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    reservation, descriptor = await owner.allocate()
    os.close(descriptor)
    cleaner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)

    assert await cleaner.cleanup_stale(now_unix_ns=reservation.expires_at_unix_ns) == 0
    assert (await cleaner.usage()).reservation_count == 1
    cleaner.close()
    await owner.release(reservation)
    owner.close()


@pytest.mark.asyncio
async def test_stale_cleanup_reclaims_reservation_after_pid_reuse(tmp_path: Path) -> None:
    """Treat a live reused PID with a different process start as a dead owner."""
    limits = preparation_limits()
    owner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    reservation, descriptor = await owner.allocate()
    os.close(descriptor)
    cleaner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    cleaner._read_process_identity = lambda _: "f" * 64

    assert await cleaner.cleanup_stale(
        now_unix_ns=reservation.expires_at_unix_ns
    ) == 1
    assert (await cleaner.usage()).reservation_count == 0
    cleaner.close()
    owner._owned_reservations.clear()
    owner.close()


@pytest.mark.asyncio
async def test_manager_close_rejects_in_flight_operation_and_closed_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fence directory descriptors across operations and final shutdown."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    original_usage = manager._usage_sync
    started = threading.Event()
    unblock = threading.Event()

    def blocked_usage() -> ArtifactScratchUsage:
        started.set()
        assert unblock.wait(5), "usage operation was not released"
        return original_usage()

    monkeypatch.setattr(manager, "_usage_sync", blocked_usage)
    usage_task = asyncio.create_task(manager.usage())
    assert await asyncio.to_thread(started.wait, 2), "usage operation did not start"
    with pytest.raises(ArtifactScratchIntegrityError, match="cleanup is still pending"):
        manager.close()
    unblock.set()
    assert (await usage_task).reservation_count == 0

    manager.close()
    with pytest.raises(ArtifactScratchIntegrityError, match="manager is closed"):
        await manager.usage()


def test_manager_close_never_retries_ambiguous_directory_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poison directory fd slots before an ambiguous close can be retried."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    original_close = os.close
    target = manager._files_fd
    failed = False

    def close_then_fail(descriptor: int) -> None:
        nonlocal failed
        if descriptor == target and not failed:
            original_close(descriptor)
            failed = True
            raise OSError(errno.EIO, "injected directory close failure")
        original_close(descriptor)

    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(OSError, match="directory close failure"):
        manager.close()
    reused_descriptor = os.open("/dev/null", os.O_RDONLY)
    try:
        manager.close()
        os.fstat(reused_descriptor)
    finally:
        os.close(reused_descriptor)


@pytest.mark.asyncio
async def test_unhanded_reader_remains_owned_until_close_succeeds(tmp_path: Path) -> None:
    """Retry a sealed reader close before clearing its pending owner."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    reservation, descriptor = await manager.allocate()
    reader = await manager.seal_for_read(reservation, descriptor)

    class FailOnceReader:
        def __init__(self, wrapped: BinaryIO) -> None:
            self.wrapped = wrapped
            self.close_attempts = 0

        def close(self) -> None:
            self.close_attempts += 1
            if self.close_attempts == 1:
                raise OSError(errno.EIO, "injected unhanded reader close failure")
            self.wrapped.close()

    failing_reader = FailOnceReader(reader)
    pending = SimpleNamespace(
        reservation=reservation,
        descriptor=None,
        reader=failing_reader,
    )
    assert not await service._release_unhanded_preparation(pending)
    assert pending.reader is failing_reader
    assert service.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1
    assert await service.retry_pending_cleanup() == 1
    assert pending.reader is None
    assert failing_reader.close_attempts == 2
    assert failing_reader.wrapped.closed
    assert service.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_closed_preparation_rejects_stream_and_is_idempotent(tmp_path: Path) -> None:
    """Make closed source handles unusable without duplicating cleanup."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    source = prepared.committed_source
    assert "PreparedArtifact" in repr(prepared)
    assert "CommittedArtifactSource" in repr(source)
    await prepared.close()
    await prepared.close()
    with pytest.raises(RuntimeError, match="closed"):
        _ = prepared.committed_source
    with pytest.raises(ArtifactScratchIntegrityError, match="unavailable"):
        _ = [chunk async for chunk in source.stream()]
    manager.close()


@pytest.mark.asyncio
async def test_prepared_artifact_release_can_retry_after_transient_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain ownership until scratch release succeeds so cleanup is retryable."""
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    source = prepared.committed_source
    original_release = manager.release
    release_attempts = 0

    async def fail_once(reservation: object) -> None:
        nonlocal release_attempts
        release_attempts += 1
        if release_attempts == 1:
            raise OSError(errno.EIO, "transient scratch release failure")
        await original_release(reservation)

    monkeypatch.setattr(manager, "release", fail_once)
    with pytest.raises(OSError, match="transient scratch release failure"):
        await prepared.close()
    assert (await manager.usage()).reservation_count == 1

    await prepared.close()
    assert release_attempts == 2
    assert (await manager.usage()).reservation_count == 0
    with pytest.raises(RuntimeError, match="closed"):
        _ = prepared.committed_source
    with pytest.raises(ArtifactScratchIntegrityError, match="unavailable"):
        _ = [chunk async for chunk in source.stream()]
    manager.close()


@pytest.mark.asyncio
async def test_failed_preparation_retains_cleanup_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the primary input error and retain failed cleanup ownership."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    original_release = manager.release
    release_attempts = 0

    async def fail_once(reservation: object) -> None:
        nonlocal release_attempts
        release_attempts += 1
        if release_attempts == 1:
            raise OSError(errno.EIO, "transient scratch release failure")
        await original_release(reservation)

    monkeypatch.setattr(manager, "release", fail_once)
    with pytest.raises(ArtifactInputMismatchError, match="expected digest"):
        await service.prepare(
            byte_stream(b"data"),
            media_type="text/plain",
            expected_sha256="sha256:" + "0" * 64,
        )
    assert service.pending_cleanup_count == 1
    assert (await manager.usage()).reservation_count == 1

    assert await service.retry_pending_cleanup() == 1
    assert service.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    assert release_attempts == 2
    manager.close()


@pytest.mark.asyncio
async def test_pending_cleanup_retry_preserves_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finish a retained cleanup retry without converting cancellation to success."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    original_release = manager.release
    release_attempts = 0

    async def fail_once(reservation: object) -> None:
        nonlocal release_attempts
        release_attempts += 1
        if release_attempts == 1:
            raise OSError(errno.EIO, "transient scratch release failure")
        await original_release(reservation)

    monkeypatch.setattr(manager, "release", fail_once)
    with pytest.raises(ArtifactInputMismatchError, match="expected digest"):
        await service.prepare(
            byte_stream(b"data"),
            media_type="text/plain",
            expected_sha256="sha256:" + "0" * 64,
        )
    assert service.pending_cleanup_count == 1

    cleanup_started = asyncio.Event()
    finish_cleanup = asyncio.Event()
    original_cleanup = service._release_unhanded_preparation

    async def delayed_cleanup(pending: object) -> bool:
        cleanup_started.set()
        await finish_cleanup.wait()
        return await original_cleanup(pending)

    monkeypatch.setattr(service, "_release_unhanded_preparation", delayed_cleanup)
    retry_task = asyncio.create_task(service.retry_pending_cleanup())
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)
    retry_task.cancel()
    await asyncio.sleep(0)
    retry_task.cancel()
    finish_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await retry_task

    assert service.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_failed_descriptor_close_is_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not retain a raw fd after close reports an ambiguous POSIX failure."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    original_close = service._close_descriptor

    async def close_then_fail(descriptor: int) -> None:
        await original_close(descriptor)
        raise OSError(errno.EIO, "ambiguous descriptor close failure")

    monkeypatch.setattr(service, "_close_descriptor", close_then_fail)
    with pytest.raises(ArtifactInputMismatchError, match="expected digest"):
        await service.prepare(
            byte_stream(b"data"),
            media_type="text/plain",
            expected_sha256="sha256:" + "0" * 64,
        )
    assert service.pending_cleanup_count == 1
    reused_descriptor = os.open("/dev/null", os.O_RDONLY)
    try:
        assert await service.retry_pending_cleanup() == 1
        os.fstat(reused_descriptor)
    finally:
        os.close(reused_descriptor)
    assert service.pending_cleanup_count == 0
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_unhanded_open_descriptor_retains_service_and_quota_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep failed preparation custody when raw close never reached the kernel."""
    limits = preparation_limits()
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    service = ArtifactPreparationService(manager)
    open_descriptor: int | None = None

    async def fail_before_close(descriptor: int) -> None:
        nonlocal open_descriptor
        open_descriptor = descriptor
        raise OSError(errno.EIO, "injected pre-close failure")

    monkeypatch.setattr(service, "_close_descriptor", fail_before_close)
    with pytest.raises(ArtifactInputMismatchError, match="expected digest"):
        await service.prepare(
            byte_stream(b"data"),
            media_type="text/plain",
            expected_sha256="sha256:" + "0" * 64,
        )
    assert open_descriptor is not None
    assert service.pending_cleanup_count == 2
    assert (await manager.usage()).reservation_count == 1

    os.close(open_descriptor)
    reservation = next(iter(manager._poisoned_reservations.values()))
    cleaner = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    cleaner._owner_process_matches = lambda *_: False
    assert await cleaner.cleanup_stale(now_unix_ns=reservation.expires_at_unix_ns) == 1
    cleaner.close()
    manager._poisoned_reservations.clear()
    assert await service.retry_pending_cleanup() == 1
    assert service.pending_cleanup_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_cancelled_close_finishes_cleanup_and_closes_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-raise cancellation only after prepared ownership is finalized."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    source = prepared.committed_source
    release_started = asyncio.Event()
    finish_release = asyncio.Event()
    original_release = manager.release

    async def delayed_release(reservation: object) -> None:
        release_started.set()
        await finish_release.wait()
        await original_release(reservation)

    monkeypatch.setattr(manager, "release", delayed_release)
    close_task = asyncio.create_task(prepared.close())
    await asyncio.wait_for(release_started.wait(), timeout=1)
    close_task.cancel()
    await asyncio.sleep(0)
    close_task.cancel()
    await asyncio.sleep(0)
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await close_task

    assert prepared._closed
    assert service._active == {}
    assert (await manager.usage()).reservation_count == 0
    with pytest.raises(RuntimeError, match="closed"):
        _ = prepared.committed_source
    with pytest.raises(ArtifactScratchIntegrityError, match="unavailable"):
        _ = [chunk async for chunk in source.stream()]
    manager.close()


@pytest.mark.asyncio
async def test_cancelled_close_preserves_cancellation_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep retryable ownership while cancellation remains the caller result."""
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=preparation_limits())
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    original_release = manager.release
    release_started = asyncio.Event()
    finish_release = asyncio.Event()

    async def delayed_failure(_: object) -> None:
        release_started.set()
        await finish_release.wait()
        raise OSError(errno.EIO, "injected release failure")

    monkeypatch.setattr(manager, "release", delayed_failure)
    close_task = asyncio.create_task(prepared.close())
    await asyncio.wait_for(release_started.wait(), timeout=1)
    close_task.cancel()
    await asyncio.sleep(0)
    close_task.cancel()
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await close_task

    assert not prepared._closed
    assert len(service._active) == 1
    assert (await manager.usage()).reservation_count == 1
    monkeypatch.setattr(manager, "release", original_release)
    await prepared.close()
    assert prepared._closed
    assert service._active == {}
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_second_pass_deadline_is_enforced(tmp_path: Path) -> None:
    """Keep the provider-consumption deadline shorter than reservation TTL."""
    limits = preparation_limits(
        reservation_ttl_seconds=1.0,
        total_deadline_seconds=0.5,
        cleanup_margin_seconds=0.1,
    )
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=limits)
    service = ArtifactPreparationService(manager)
    prepared = await service.prepare(byte_stream(b"data"), media_type="text/plain")
    await asyncio.sleep(0.55)
    async with prepared as source:
        with pytest.raises(ArtifactPreparationDeadlineError):
            _ = [chunk async for chunk in source.stream()]
    manager.close()


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"sha256": "invalid"}, "digest"),
        ({"byte_count": -1}, "byte count"),
        ({"media_type": ""}, "media type"),
    ],
)
def test_commitment_value_validation(values: dict[str, Any], message: str) -> None:
    """Reject noncanonical commitment values independently."""
    fields: dict[str, Any] = {
        "sha256": "sha256:" + "0" * 64,
        "byte_count": 0,
        "media_type": "application/octet-stream",
    }
    fields.update(values)
    with pytest.raises(ValueError, match=message):
        ArtifactCommitment(**fields)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"media_type": ""}, "media type"),
        ({"media_type": "text/plain", "expected_sha256": "bad"}, "digest"),
        ({"media_type": "text/plain", "expected_size": -1}, "size"),
    ],
)
async def test_client_commitment_shape_is_rejected_before_reservation(
    tmp_path: Path,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    """Reject malformed client commitments without touching scratch."""
    manager = ArtifactScratchManager(
        root=tmp_path / message.replace(" ", "-"),
        limits=preparation_limits(),
    )
    service = ArtifactPreparationService(manager)
    with pytest.raises(ArtifactInputMismatchError, match=message):
        await service.prepare(byte_stream(b"data"), **kwargs)
    assert (await manager.usage()).reservation_count == 0
    manager.close()
