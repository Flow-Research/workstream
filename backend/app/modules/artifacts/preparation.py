"""Bounded private scratch preparation for immutable artifact bytes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat as stat_module
import threading
import time
from typing import Any, BinaryIO
from uuid import uuid4

from app.interfaces.artifacts import (
    ArtifactInputMismatchError,
    ArtifactIntegrityError,
    ArtifactLimitExceededError,
    ArtifactStoreUnavailableError,
)
from app.core.cancellation import (
    await_completion_preserving_cancellation,
    await_cancellation_resistant,
    run_blocking_cancellation_resistant,
)
from app.core.file_locks import acquire_exclusive_file_lock
from app.modules.artifacts.sources import (
    ArtifactCommitment,
    CommittedArtifactSource,
    PreparedArtifact,
)


HARD_MAXIMUM_ARTIFACT_BYTES = 512 * 1024 * 1024
_LEDGER_VERSION = 2
_LEDGER_MAXIMUM_BYTES = 1024 * 1024
_RESERVATION_ID = re.compile(r"^[0-9a-f]{32}$")
_SCRATCH_FILE = re.compile(r"^prep_([0-9a-f]{32})\.bin$")
_LEDGER_TEMP_FILE = re.compile(r"^\.ledger\.[0-9a-f]{32}\.tmp$")
_PROCESS_IDENTITY = re.compile(r"^[0-9a-f]{64}$")
_ROOT_MARKER = ".workstream-artifact-scratch-v1"
_ROOT_MARKER_PREFIX = b"workstream-artifact-scratch-v1:"


class ArtifactScratchCapacityError(ArtifactStoreUnavailableError):
    """Raised when bounded scratch capacity cannot admit another source."""

    code = "artifact_scratch_capacity_exhausted"


class ArtifactPreparationDeadlineError(ArtifactStoreUnavailableError):
    """Raised when preparation or second-pass streaming exceeds its deadline."""

    code = "artifact_preparation_deadline_exceeded"


class ArtifactScratchIntegrityError(ArtifactIntegrityError):
    """Raised when private scratch state violates its filesystem contract."""

    code = "artifact_scratch_integrity_failure"


@dataclass(frozen=True, slots=True)
class ArtifactPreparationLimits:
    """Fixed process-independent limits for one scratch root."""

    aggregate_reserved_bytes: int = 4 * HARD_MAXIMUM_ARTIFACT_BYTES
    maximum_files: int = 8
    maximum_concurrency: int = 4
    minimum_free_bytes: int = HARD_MAXIMUM_ARTIFACT_BYTES
    reservation_ttl_seconds: float = 2400.0
    total_deadline_seconds: float = 1800.0
    cleanup_margin_seconds: float = 300.0
    stream_buffer_bytes: int = 1024 * 1024
    maximum_source_bytes: int = HARD_MAXIMUM_ARTIFACT_BYTES

    def __post_init__(self) -> None:
        """Reject limits that cannot enforce the v0.1 scratch contract."""
        integer_fields = (
            self.aggregate_reserved_bytes,
            self.maximum_files,
            self.maximum_concurrency,
            self.minimum_free_bytes,
            self.stream_buffer_bytes,
            self.maximum_source_bytes,
        )
        if any(type(value) is not int for value in integer_fields):
            raise ValueError("artifact preparation integer limits are invalid")
        if self.aggregate_reserved_bytes < HARD_MAXIMUM_ARTIFACT_BYTES:
            raise ValueError("artifact scratch aggregate must reserve at least 512 MiB")
        if self.maximum_files <= 0 or self.maximum_files > 1024:
            raise ValueError("artifact scratch file limit is invalid")
        if self.maximum_concurrency <= 0 or self.maximum_concurrency > self.maximum_files:
            raise ValueError("artifact scratch concurrency limit is invalid")
        if self.minimum_free_bytes < 0:
            raise ValueError("artifact scratch free-space floor is invalid")
        if self.stream_buffer_bytes <= 0 or self.stream_buffer_bytes > 1024 * 1024:
            raise ValueError("artifact preparation buffer must be between 1 byte and 1 MiB")
        if self.maximum_source_bytes <= 0 or (
            self.maximum_source_bytes > HARD_MAXIMUM_ARTIFACT_BYTES
        ):
            raise ValueError("artifact preparation source limit exceeds 512 MiB")
        durations = (
            self.reservation_ttl_seconds,
            self.total_deadline_seconds,
            self.cleanup_margin_seconds,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            or (isinstance(value, float) and not math.isfinite(value))
            for value in durations
        ):
            raise ValueError("artifact preparation durations are invalid")
        if (
            self.total_deadline_seconds + self.cleanup_margin_seconds
            >= self.reservation_ttl_seconds
        ):
            raise ValueError("artifact preparation deadline must expire before scratch TTL")


@dataclass(frozen=True, slots=True)
class ArtifactScratchUsage:
    """Bounded non-sensitive observation of scratch reservations."""

    reservation_count: int
    reserved_bytes: int


@dataclass(frozen=True, slots=True)
class _ScratchReservation:
    """Identify one ledger-owned scratch file and its cleanup deadline."""

    reservation_id: str
    filename: str
    expires_at_unix_ns: int


@dataclass(slots=True)
class _ActivePreparation:
    """Track one sealed preparation until its source is consumed and released."""

    reservation: _ScratchReservation
    reader: BinaryIO
    commitment: ArtifactCommitment
    deadline: float
    handle_issued: bool = False
    stream_claimed: bool = False
    source: CommittedArtifactSource | None = None


@dataclass(slots=True)
class _PendingPreparationCleanup:
    """Retain partial preparation resources that still require cleanup."""

    reservation: _ScratchReservation
    descriptor: int | None
    reader: BinaryIO | None


@dataclass(slots=True)
class _PendingReaderCleanup:
    """Bind a retained anonymous reader to its durable quota reservation."""

    reservation: _ScratchReservation
    reader: BinaryIO


class _AllocationCleanupRequired(ArtifactScratchIntegrityError):
    """Carry a failed allocation reservation into manager-owned retry state."""

    def __init__(self, reservation: _ScratchReservation) -> None:
        """Preserve the reservation whose rollback could not be proven."""
        super().__init__("failed artifact scratch allocation cleanup is pending")
        self.reservation = reservation


class _DescriptorOwnershipUncertain(ArtifactScratchIntegrityError):
    """Carry a reservation whose raw descriptor close cannot be proven."""

    def __init__(self, reservation: _ScratchReservation) -> None:
        """Preserve quota ownership until the process is restarted."""
        super().__init__("artifact descriptor ownership is uncertain")
        self.reservation = reservation


class ArtifactScratchManager:
    """Coordinate bounded scratch files across API and Celery processes."""

    def __init__(self, *, root: Path, limits: ArtifactPreparationLimits) -> None:
        """Create or validate one private database-independent scratch root."""
        self._root = root.resolve(strict=False)
        self._limits = limits
        self._root_marker_content = self._marker_content(limits)
        owner_process_identity = self._read_process_identity(os.getpid())
        if owner_process_identity is None:
            raise ArtifactScratchIntegrityError("artifact owner process identity is unavailable")
        self._owner_process_identity = owner_process_identity
        self._lifecycle_lock = threading.Lock()
        self._in_flight_operations = 0
        self._closed = False
        self._owned_reservations: dict[str, _ScratchReservation] = {}
        self._poisoned_reservations: dict[str, _ScratchReservation] = {}
        self._pending_allocation_releases: dict[str, _ScratchReservation] = {}
        self._pending_readers: dict[str, _PendingReaderCleanup] = {}
        expected_root = self._initialize_root(root)
        self._root_fd = os.open(
            self._root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        self._files_fd = -1
        try:
            self._assert_opened_root(self._root_fd, expected_root=expected_root)
            self._initialize_layout()
            self._files_fd = self._open_directory("files")
            with self._locked_ledger():
                if self._read_ledger_optional() is None:
                    self._write_ledger({"version": _LEDGER_VERSION, "reservations": []})
        except BaseException:
            if self._files_fd >= 0:
                os.close(self._files_fd)
                self._files_fd = -1
            os.close(self._root_fd)
            self._root_fd = -1
            raise

    @property
    def limits(self) -> ArtifactPreparationLimits:
        """Return immutable limits shared by every process using this root."""
        return self._limits

    @property
    def pending_cleanup_count(self) -> int:
        """Return manager-owned cleanup retained before service handoff."""
        return (
            len(self._pending_allocation_releases)
            + len(self._pending_readers)
            + len(self._poisoned_reservations)
        )

    async def allocate(self) -> tuple[_ScratchReservation, int]:
        """Reserve the full hard maximum before creating one private file."""
        with self._tracked_operation():
            task = asyncio.create_task(asyncio.to_thread(self._allocate_sync))
            try:
                reservation, descriptor = await asyncio.shield(task)
            except asyncio.CancelledError as cancellation:
                try:
                    reservation, descriptor = await await_cancellation_resistant(task)
                except _DescriptorOwnershipUncertain as exc:
                    self._retain_uncertain_descriptor(exc.reservation)
                    raise cancellation from None
                except _AllocationCleanupRequired as exc:
                    self._pending_allocation_releases[exc.reservation.reservation_id] = (
                        exc.reservation
                    )
                    raise cancellation from None
                except BaseException:
                    raise cancellation from None
                descriptor_ownership_uncertain = False
                try:
                    os.close(descriptor)
                except BaseException:
                    if not self._descriptor_is_closed(descriptor):
                        self._retain_uncertain_descriptor(reservation)
                        descriptor_ownership_uncertain = True
                if not descriptor_ownership_uncertain:
                    try:
                        await await_cancellation_resistant(
                            asyncio.to_thread(self._release_sync, reservation)
                        )
                    except BaseException:
                        self._pending_allocation_releases[
                            reservation.reservation_id
                        ] = reservation
                raise cancellation
            except _AllocationCleanupRequired as exc:
                self._pending_allocation_releases[exc.reservation.reservation_id] = (
                    exc.reservation
                )
                raise
            except _DescriptorOwnershipUncertain as exc:
                self._retain_uncertain_descriptor(exc.reservation)
                raise
            self._owned_reservations[reservation.reservation_id] = reservation
            return reservation, descriptor

    async def seal_for_read(self, reservation: _ScratchReservation, descriptor: int) -> BinaryIO:
        """Close the first pass and pin one private read-only second-pass file."""
        with self._tracked_operation():
            task = asyncio.create_task(
                asyncio.to_thread(self._seal_for_read_sync, reservation, descriptor)
            )
            reader: BinaryIO | None = None
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError as cancellation:
                try:
                    reader = await await_cancellation_resistant(task)
                    await await_cancellation_resistant(asyncio.to_thread(reader.close))
                except _DescriptorOwnershipUncertain as exc:
                    self._retain_uncertain_descriptor(exc.reservation)
                    raise cancellation from None
                except BaseException:
                    if reader is not None:
                        self._pending_readers[reservation.reservation_id] = (
                            _PendingReaderCleanup(reservation=reservation, reader=reader)
                        )
                    raise cancellation from None
                raise
            except _DescriptorOwnershipUncertain as exc:
                self._retain_uncertain_descriptor(exc.reservation)
                raise

    async def release(self, reservation: _ScratchReservation) -> None:
        """Remove one scratch file and reservation under the ledger lock."""
        with self._tracked_operation():
            if reservation.reservation_id in self._poisoned_reservations:
                raise ArtifactScratchIntegrityError(
                    "artifact descriptor ownership is uncertain"
                )
            if reservation.reservation_id in self._pending_readers:
                raise ArtifactScratchIntegrityError(
                    "artifact reader cleanup is still pending"
                )

            async def release_and_forget() -> None:
                """Durably release and clear local ownership as one handoff."""
                await self._run_io(self._release_sync, reservation)
                self._owned_reservations.pop(reservation.reservation_id, None)

            await await_completion_preserving_cancellation(release_and_forget())

    async def usage(self) -> ArtifactScratchUsage:
        """Return aggregate reservation facts without filenames or paths."""
        with self._tracked_operation():
            return await self._run_io(self._usage_sync)

    async def stale_reservation_ids(self, *, now_unix_ns: int | None = None) -> tuple[str, ...]:
        """Discover expired reservation IDs without changing scratch state."""
        now = time.time_ns() if now_unix_ns is None else now_unix_ns
        if type(now) is not int or now < 0:
            raise ValueError("scratch discovery time is invalid")
        with self._tracked_operation():
            return await self._run_io(self._stale_reservation_ids_sync, now)

    async def cleanup_stale(self, *, now_unix_ns: int | None = None) -> int:
        """Remove expired ledger entries and regular scratch files under lock."""
        now = time.time_ns() if now_unix_ns is None else now_unix_ns
        if type(now) is not int or now < 0:
            raise ValueError("scratch cleanup time is invalid")
        with self._tracked_operation():
            protected_reservation_ids = frozenset(
                self._owned_reservations | self._poisoned_reservations
            )
            cleaned_reservation_ids = await self._run_io(
                self._cleanup_stale_sync,
                now,
                protected_reservation_ids,
            )
            for reservation_id in cleaned_reservation_ids:
                self._pending_allocation_releases.pop(reservation_id, None)
            return len(cleaned_reservation_ids)

    async def retry_pending_cleanup(self) -> int:
        """Retry manager-owned cleanup retained before service handoff."""
        with self._tracked_operation():
            cleaned = 0
            for reservation_id, pending in tuple(self._pending_readers.items()):

                async def close_reader_and_release() -> None:
                    """Close retained bytes before clearing durable quota ownership."""
                    await self._run_io(pending.reader.close)
                    await self._run_io(self._release_sync, pending.reservation)
                    self._owned_reservations.pop(reservation_id, None)
                    self._pending_readers.pop(reservation_id, None)

                try:
                    await await_completion_preserving_cancellation(
                        close_reader_and_release()
                    )
                except Exception:
                    continue
                else:
                    cleaned += 1
            for reservation_id, reservation in tuple(
                self._pending_allocation_releases.items()
            ):

                async def release_reservation() -> None:
                    """Release one retained reservation and clear manager ownership."""
                    await self._run_io(self._release_sync, reservation)
                    self._pending_allocation_releases.pop(reservation_id, None)

                try:
                    await await_completion_preserving_cancellation(release_reservation())
                except Exception:
                    continue
                else:
                    cleaned += 1
            return cleaned

    def close(self) -> None:
        """Release pinned scratch directory descriptors."""
        with self._lifecycle_lock:
            if self._closed:
                return
            if (
                self._in_flight_operations
                or self.pending_cleanup_count
                or self._owned_reservations
            ):
                raise ArtifactScratchIntegrityError("artifact scratch cleanup is still pending")
            self._closed = True
            files_fd = getattr(self, "_files_fd", -1)
            root_fd = getattr(self, "_root_fd", -1)
            self._files_fd = -1
            self._root_fd = -1
        failure: BaseException | None = None
        for descriptor in (files_fd, root_fd):
            if descriptor < 0:
                continue
            try:
                os.close(descriptor)
            except BaseException as exc:
                failure = failure or exc
        if failure is not None:
            raise failure

    @contextmanager
    def _tracked_operation(self) -> Iterator[None]:
        """Prevent descriptor shutdown while one manager operation is active."""
        with self._lifecycle_lock:
            if self._closed:
                raise ArtifactScratchIntegrityError("artifact scratch manager is closed")
            self._in_flight_operations += 1
        try:
            yield
        finally:
            with self._lifecycle_lock:
                self._in_flight_operations -= 1

    def _retain_uncertain_descriptor(self, reservation: _ScratchReservation) -> None:
        """Keep permanent process-local custody after an ambiguous raw close."""
        self._poisoned_reservations[reservation.reservation_id] = reservation

    @staticmethod
    def _descriptor_is_closed(descriptor: int) -> bool:
        """Return whether a failed close nevertheless invalidated the descriptor."""
        try:
            os.fstat(descriptor)
        except OSError as exc:
            return exc.errno == errno.EBADF
        return False

    def _initialize_root(self, configured_root: Path) -> os.stat_result:
        """Create or validate the dedicated private scratch-root directory."""
        if configured_root.is_symlink():
            raise ValueError("artifact scratch root must not be a symlink")
        created = False
        try:
            configured_root.mkdir(parents=True, mode=0o700)
            created = True
        except FileExistsError:
            pass
        if created:
            os.chmod(configured_root, 0o700)
        details = configured_root.stat(follow_symlinks=False)
        if (
            not stat_module.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o777 != 0o700
        ):
            raise ValueError("existing artifact scratch root is not private")
        if configured_root.resolve() != self._root or not configured_root.is_dir():
            raise ValueError("artifact scratch root must be a dedicated directory")
        return details

    @staticmethod
    def _assert_opened_root(descriptor: int, *, expected_root: os.stat_result) -> None:
        """Verify a pinned descriptor still identifies the validated root."""
        details = os.fstat(descriptor)
        if (
            not stat_module.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o777 != 0o700
            or details.st_dev != expected_root.st_dev
            or details.st_ino != expected_root.st_ino
        ):
            raise ValueError("artifact scratch root changed during initialization")

    def _initialize_layout(self) -> None:
        """Serialize scratch layout initialization behind the ledger lock."""
        entries = set(os.listdir(self._root_fd))
        if _ROOT_MARKER in entries:
            if ".ledger.lock" not in entries:
                raise ValueError("artifact scratch root marker is invalid")
        self._validate_layout_entries(
            entries,
            allow_marked_ledger_temps=True,
        )
        descriptor = os.open(
            ".ledger.lock",
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=self._root_fd,
        )
        try:
            self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
            self._acquire_ledger_lock(descriptor)
            self._initialize_layout_locked()
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _initialize_layout_locked(self) -> None:
        """Create or validate marker, ledger support files, and data directory."""
        entries = set(os.listdir(self._root_fd))
        if _ROOT_MARKER in entries:
            self._validate_existing_root_marker()
        self._cleanup_ledger_temps_locked()
        entries = set(os.listdir(self._root_fd))
        self._validate_layout_entries(entries, allow_marked_ledger_temps=False)
        marker_created = False

        try:
            descriptor = os.open(
                _ROOT_MARKER,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self._root_fd,
            )
            marker_created = True
        except FileExistsError:
            descriptor = os.open(
                _ROOT_MARKER,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=self._root_fd,
            )
        if marker_created:
            try:
                self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
                self._write_all(descriptor, memoryview(self._root_marker_content))
                os.fsync(descriptor)
            except BaseException:
                os.close(descriptor)
                try:
                    os.unlink(_ROOT_MARKER, dir_fd=self._root_fd)
                finally:
                    os.fsync(self._root_fd)
                raise
            else:
                os.close(descriptor)
            os.fsync(self._root_fd)
        else:
            os.close(descriptor)
        if "files" not in entries:
            try:
                os.mkdir("files", mode=0o700, dir_fd=self._root_fd)
            except FileExistsError:
                pass
            os.fsync(self._root_fd)

    def _validate_existing_root_marker(self) -> None:
        """Require the root marker to match this manager's canonical limits."""
        descriptor = os.open(
            _ROOT_MARKER,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=self._root_fd,
        )
        try:
            self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
            marker = os.read(descriptor, len(self._root_marker_content) + 1)
            if marker != self._root_marker_content:
                raise ValueError("artifact scratch root marker is invalid")
        finally:
            os.close(descriptor)

    @staticmethod
    def _marker_content(limits: ArtifactPreparationLimits) -> bytes:
        """Bind one scratch root to a single canonical cross-process limit set."""
        payload = {
            "aggregate_reserved_bytes": limits.aggregate_reserved_bytes,
            "cleanup_margin_seconds": float(limits.cleanup_margin_seconds),
            "maximum_concurrency": limits.maximum_concurrency,
            "maximum_files": limits.maximum_files,
            "maximum_source_bytes": limits.maximum_source_bytes,
            "minimum_free_bytes": limits.minimum_free_bytes,
            "reservation_ttl_seconds": float(limits.reservation_ttl_seconds),
            "stream_buffer_bytes": limits.stream_buffer_bytes,
            "total_deadline_seconds": float(limits.total_deadline_seconds),
        }
        canonical = json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return _ROOT_MARKER_PREFIX + hashlib.sha256(canonical).hexdigest().encode("ascii") + b"\n"

    @staticmethod
    def _validate_layout_entries(
        entries: set[str],
        *,
        allow_marked_ledger_temps: bool,
    ) -> None:
        """Reject unrecognized or unsafe entries in the dedicated root."""
        allowed = {
            _ROOT_MARKER,
            "files",
            ".ledger.lock",
            ".ledger.json",
        }
        temporary_entries = {
            entry for entry in entries if _LEDGER_TEMP_FILE.fullmatch(entry)
        }
        allowed_temps = (
            temporary_entries
            if allow_marked_ledger_temps and _ROOT_MARKER in entries
            else set()
        )
        non_bootstrap_entries = entries - {".ledger.lock"} - allowed_temps
        if entries - allowed - allowed_temps or (
            _ROOT_MARKER not in entries and non_bootstrap_entries
        ):
            raise ValueError("artifact scratch root must be a dedicated directory")

    def _cleanup_ledger_temps_locked(self) -> None:
        """Remove validated abandoned ledger temporaries while exclusively locked."""
        removed = False
        for filename in sorted(os.listdir(self._root_fd)):
            if _LEDGER_TEMP_FILE.fullmatch(filename) is None:
                continue
            descriptor = os.open(
                filename,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=self._root_fd,
            )
            try:
                self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
            finally:
                os.close(descriptor)
            os.unlink(filename, dir_fd=self._root_fd)
            removed = True
        if removed:
            os.fsync(self._root_fd)

    def _allocate_sync(self) -> tuple[_ScratchReservation, int]:
        """Publish one bounded reservation before creating its private file."""
        reservation_id = uuid4().hex
        filename = f"prep_{reservation_id}.bin"
        now = time.time_ns()
        ttl_ns = int(self._limits.reservation_ttl_seconds * 1_000_000_000)
        reservation = _ScratchReservation(
            reservation_id=reservation_id,
            filename=filename,
            expires_at_unix_ns=now + ttl_ns,
        )
        with self._locked_ledger():
            ledger = self._read_ledger()
            entries = list(ledger["reservations"])
            previous_entries = list(entries)
            reserved_bytes = sum(entry["reserved_bytes"] for entry in entries)
            if len(entries) >= self._limits.maximum_files:
                raise ArtifactScratchCapacityError("artifact scratch file limit reached")
            if len(entries) >= self._limits.maximum_concurrency:
                raise ArtifactScratchCapacityError("artifact scratch concurrency limit reached")
            if reserved_bytes + HARD_MAXIMUM_ARTIFACT_BYTES > self._limits.aggregate_reserved_bytes:
                raise ArtifactScratchCapacityError("artifact scratch byte limit reached")
            filesystem = os.fstatvfs(self._files_fd)
            available = filesystem.f_bavail * filesystem.f_frsize
            required = (
                reserved_bytes
                + HARD_MAXIMUM_ARTIFACT_BYTES
                + self._limits.minimum_free_bytes
            )
            if available < required:
                raise ArtifactScratchCapacityError("artifact scratch free-space floor reached")
            entries.append(
                {
                    "reservation_id": reservation.reservation_id,
                    "filename": reservation.filename,
                    "reserved_bytes": HARD_MAXIMUM_ARTIFACT_BYTES,
                    "created_at_unix_ns": now,
                    "expires_at_unix_ns": reservation.expires_at_unix_ns,
                    "owner_pid": os.getpid(),
                    "owner_process_identity": self._owner_process_identity,
                }
            )
            try:
                self._write_ledger({"version": _LEDGER_VERSION, "reservations": entries})
            except BaseException:
                try:
                    self._restore_failed_reservation_ledger(
                        reservation.reservation_id,
                        previous_entries,
                    )
                except BaseException as cleanup_error:
                    raise _AllocationCleanupRequired(reservation) from cleanup_error
                raise
            descriptor: int | None = None
            try:
                descriptor = os.open(
                    filename,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=self._files_fd,
                )
                self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
                os.fsync(self._files_fd)
            except BaseException:
                file_created = descriptor is not None
                if descriptor is not None:
                    descriptor_to_close = descriptor
                    descriptor = None
                    try:
                        os.close(descriptor_to_close)
                    except BaseException as close_error:
                        if not self._descriptor_is_closed(descriptor_to_close):
                            raise _DescriptorOwnershipUncertain(reservation) from close_error
                try:
                    if file_created:
                        self._unlink_regular_optional(filename)
                    remaining = [
                        entry
                        for entry in entries
                        if entry["reservation_id"] != reservation.reservation_id
                    ]
                    self._write_ledger(
                        {"version": _LEDGER_VERSION, "reservations": remaining}
                    )
                except BaseException as cleanup_error:
                    raise _AllocationCleanupRequired(reservation) from cleanup_error
                raise
            return reservation, descriptor

    def _restore_failed_reservation_ledger(
        self,
        reservation_id: str,
        previous_entries: list[dict[str, Any]],
    ) -> None:
        """Prove an ambiguously published reservation was durably removed."""
        current = self._read_ledger()["reservations"]
        if not any(entry["reservation_id"] == reservation_id for entry in current):
            return
        try:
            self._write_ledger(
                {"version": _LEDGER_VERSION, "reservations": previous_entries}
            )
        except BaseException as exc:
            raise ArtifactScratchIntegrityError(
                "failed artifact scratch reservation could not be rolled back"
            ) from exc
        current = self._read_ledger()["reservations"]
        if any(entry["reservation_id"] == reservation_id for entry in current):
            raise ArtifactScratchIntegrityError(
                "failed artifact scratch reservation could not be rolled back"
            )

    def _seal_for_read_sync(self, reservation: _ScratchReservation, descriptor: int) -> BinaryIO:
        """Durably seal a write descriptor and return an anonymous read handle."""
        read_descriptor: int | None = None
        try:
            with self._locked_ledger():
                self._validate_reservation(reservation)
                matching = [
                    entry
                    for entry in self._read_ledger()["reservations"]
                    if entry["reservation_id"] == reservation.reservation_id
                ]
                if len(matching) != 1 or matching[0]["filename"] != reservation.filename:
                    raise ArtifactScratchIntegrityError(
                        "artifact scratch reservation is invalid"
                    )
                os.fsync(descriptor)
                os.fchmod(descriptor, 0o400)
                read_descriptor = os.open(
                    reservation.filename,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=self._files_fd,
                )
                self._assert_private_file_descriptor(read_descriptor, expected_mode=0o400)
                os.unlink(reservation.filename, dir_fd=self._files_fd)
                os.fsync(self._files_fd)
        except BaseException as operation_error:
            if read_descriptor is not None:
                descriptor_to_close = read_descriptor
                read_descriptor = None
                self._close_raw_descriptor_sync(reservation, descriptor_to_close)
            self._close_raw_descriptor_sync(reservation, descriptor)
            raise operation_error
        try:
            close_error = self._close_raw_descriptor_sync(reservation, descriptor)
        except _DescriptorOwnershipUncertain:
            if read_descriptor is not None:
                descriptor_to_close = read_descriptor
                read_descriptor = None
                self._close_raw_descriptor_sync(reservation, descriptor_to_close)
            raise
        if close_error is not None:
            if read_descriptor is not None:
                descriptor_to_close = read_descriptor
                read_descriptor = None
                self._close_raw_descriptor_sync(reservation, descriptor_to_close)
            raise close_error
        assert read_descriptor is not None
        try:
            return os.fdopen(read_descriptor, "rb", buffering=0)
        except BaseException as operation_error:
            self._close_raw_descriptor_sync(reservation, read_descriptor)
            raise operation_error

    def _close_raw_descriptor_sync(
        self,
        reservation: _ScratchReservation,
        descriptor: int,
    ) -> BaseException | None:
        """Close once and poison custody when descriptor invalidation is unproven."""
        try:
            os.close(descriptor)
        except BaseException as close_error:
            if not self._descriptor_is_closed(descriptor):
                raise _DescriptorOwnershipUncertain(reservation) from close_error
            return close_error
        return None

    def _release_sync(self, reservation: _ScratchReservation) -> None:
        """Durably delete scratch bytes before removing their ledger owner."""
        self._validate_reservation(reservation)
        with self._locked_ledger():
            ledger = self._read_ledger()
            entries = list(ledger["reservations"])
            matching = [
                entry for entry in entries if entry["reservation_id"] == reservation.reservation_id
            ]
            if not matching:
                os.fsync(self._root_fd)
                return
            if len(matching) != 1 or matching[0]["filename"] != reservation.filename:
                raise ArtifactScratchIntegrityError("artifact scratch reservation is invalid")
            self._unlink_regular_optional(reservation.filename)
            remaining = [
                entry for entry in entries if entry["reservation_id"] != reservation.reservation_id
            ]
            self._write_ledger({"version": _LEDGER_VERSION, "reservations": remaining})

    def _usage_sync(self) -> ArtifactScratchUsage:
        """Read aggregate ledger usage while holding the cross-process lock."""
        with self._locked_ledger():
            entries = self._read_ledger()["reservations"]
            return ArtifactScratchUsage(
                reservation_count=len(entries),
                reserved_bytes=sum(entry["reserved_bytes"] for entry in entries),
            )

    def _stale_reservation_ids_sync(self, now_unix_ns: int) -> tuple[str, ...]:
        """List deterministic expired reservation IDs without modifying state."""
        with self._locked_ledger():
            entries = self._read_ledger()["reservations"]
            return tuple(
                sorted(
                    entry["reservation_id"]
                    for entry in entries
                    if entry["expires_at_unix_ns"] <= now_unix_ns
                )
            )

    def _cleanup_stale_sync(
        self,
        now_unix_ns: int,
        protected_reservation_ids: frozenset[str],
    ) -> tuple[str, ...]:
        """Durably remove expired files before deleting their ledger entries."""
        with self._locked_ledger():
            ledger = self._read_ledger()
            entries = list(ledger["reservations"])
            stale = sorted(
                (
                    entry
                    for entry in entries
                    if entry["expires_at_unix_ns"] <= now_unix_ns
                    and entry["reservation_id"] not in protected_reservation_ids
                    and not self._owner_process_matches(
                        entry["owner_pid"],
                        entry["owner_process_identity"],
                    )
                ),
                key=lambda entry: entry["reservation_id"],
            )
            for entry in stale:
                self._unlink_regular_optional(entry["filename"])
            if stale:
                stale_ids = {entry["reservation_id"] for entry in stale}
                self._write_ledger(
                    {
                        "version": _LEDGER_VERSION,
                        "reservations": [
                            entry for entry in entries if entry["reservation_id"] not in stale_ids
                        ],
                    }
                )
            return tuple(entry["reservation_id"] for entry in stale)

    def _owner_process_matches(self, owner_pid: int, expected_identity: str) -> bool:
        """Retain custody only while PID and process-start identity still match."""
        try:
            current_identity = self._read_process_identity(owner_pid)
        except OSError:
            return True
        return current_identity == expected_identity

    @staticmethod
    def _read_process_identity(owner_pid: int) -> str | None:
        """Bind a Linux PID to its boot and process-start identity."""
        try:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
                encoding="ascii"
            ).strip()
            process_stat = Path(f"/proc/{owner_pid}/stat").read_text(
                encoding="ascii"
            )
        except FileNotFoundError:
            return None
        _, separator, remainder = process_stat.rpartition(")")
        fields = remainder.strip().split()
        if separator != ")" or len(fields) <= 19 or not fields[19].isdigit():
            raise OSError("process identity is malformed")
        material = f"{boot_id}:{fields[19]}".encode("ascii")
        return hashlib.sha256(material).hexdigest()

    def _acquire_ledger_lock(self, descriptor: int) -> None:
        """Acquire the scratch lock within the configured operation deadline."""
        try:
            acquire_exclusive_file_lock(
                descriptor,
                timeout_seconds=self._limits.total_deadline_seconds,
            )
        except TimeoutError:
            raise ArtifactPreparationDeadlineError(
                "artifact scratch ledger lock deadline exceeded"
            ) from None

    @contextmanager
    def _locked_ledger(self) -> Iterator[None]:
        """Hold the cross-process ledger lock for one complete state transition."""
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(".ledger.lock", flags, 0o600, dir_fd=self._root_fd)
        locked = False
        try:
            self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
            self._acquire_ledger_lock(descriptor)
            locked = True
            yield
        finally:
            try:
                if locked:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _read_ledger_optional(self) -> dict[str, Any] | None:
        """Read and validate the ledger when it exists."""
        try:
            descriptor = os.open(
                ".ledger.json",
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=self._root_fd,
            )
        except FileNotFoundError:
            return None
        try:
            self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
            raw = os.read(descriptor, _LEDGER_MAXIMUM_BYTES + 1)
            if len(raw) > _LEDGER_MAXIMUM_BYTES or os.read(descriptor, 1):
                raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
        finally:
            os.close(descriptor)
        try:
            ledger = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid") from exc
        self._validate_ledger(ledger)
        return ledger

    def _read_ledger(self) -> dict[str, Any]:
        """Read the required validated scratch ledger."""
        ledger = self._read_ledger_optional()
        if ledger is None:
            raise ArtifactScratchIntegrityError("artifact scratch ledger is missing")
        return ledger

    def _write_ledger(self, ledger: dict[str, Any]) -> None:
        """Atomically replace and directory-sync one validated ledger."""
        self._validate_ledger(ledger)
        raw = json.dumps(
            ledger,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > _LEDGER_MAXIMUM_BYTES:
            raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
        temporary = f".ledger.{uuid4().hex}.tmp"
        descriptor: int | None = None
        replaced = False
        try:
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self._root_fd,
            )
            self._assert_private_file_descriptor(descriptor, expected_mode=0o600)
            self._write_all(descriptor, memoryview(raw))
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(
                temporary,
                ".ledger.json",
                src_dir_fd=self._root_fd,
                dst_dir_fd=self._root_fd,
            )
            replaced = True
            os.fsync(self._root_fd)
        except BaseException:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if not replaced:
                try:
                    os.unlink(temporary, dir_fd=self._root_fd)
                except FileNotFoundError:
                    pass
            raise

    def _validate_ledger(self, ledger: object) -> None:
        """Validate the complete bounded ledger schema and reservation set."""
        if not isinstance(ledger, dict) or set(ledger) != {"version", "reservations"}:
            raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
        if type(ledger["version"]) is not int or ledger["version"] != _LEDGER_VERSION:
            raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
        reservations = ledger["reservations"]
        if not isinstance(reservations, list) or len(reservations) > 1024:
            raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
        seen: set[str] = set()
        expected = {
            "reservation_id",
            "filename",
            "reserved_bytes",
            "created_at_unix_ns",
            "expires_at_unix_ns",
            "owner_pid",
            "owner_process_identity",
        }
        for entry in reservations:
            if not isinstance(entry, dict) or set(entry) != expected:
                raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
            reservation_id = entry["reservation_id"]
            if (
                not isinstance(reservation_id, str)
                or not _RESERVATION_ID.fullmatch(reservation_id)
                or reservation_id in seen
                or entry["filename"] != f"prep_{reservation_id}.bin"
            ):
                raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
            seen.add(reservation_id)
            integer_values = (
                entry["reserved_bytes"],
                entry["created_at_unix_ns"],
                entry["expires_at_unix_ns"],
                entry["owner_pid"],
            )
            if any(type(value) is not int or value < 0 for value in integer_values):
                raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")
            if (
                entry["reserved_bytes"] != HARD_MAXIMUM_ARTIFACT_BYTES
                or entry["expires_at_unix_ns"] <= entry["created_at_unix_ns"]
                or entry["owner_pid"] <= 0
                or not isinstance(entry["owner_process_identity"], str)
                or _PROCESS_IDENTITY.fullmatch(entry["owner_process_identity"]) is None
            ):
                raise ArtifactScratchIntegrityError("artifact scratch ledger is invalid")

    @staticmethod
    def _validate_reservation(reservation: _ScratchReservation) -> None:
        """Reject forged or malformed in-process reservation handles."""
        if (
            not _RESERVATION_ID.fullmatch(reservation.reservation_id)
            or reservation.filename != f"prep_{reservation.reservation_id}.bin"
            or type(reservation.expires_at_unix_ns) is not int
            or reservation.expires_at_unix_ns <= 0
        ):
            raise ArtifactScratchIntegrityError("artifact scratch reservation is invalid")

    def _unlink_regular_optional(self, filename: str) -> None:
        """Durably remove one private regular scratch file when present."""
        if _SCRATCH_FILE.fullmatch(filename) is None:
            raise ArtifactScratchIntegrityError("artifact scratch filename is invalid")
        try:
            details = os.stat(filename, dir_fd=self._files_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.fsync(self._files_fd)
            return
        if (
            not stat_module.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or details.st_mode & 0o077
        ):
            raise ArtifactScratchIntegrityError("artifact scratch file is invalid")
        os.unlink(filename, dir_fd=self._files_fd)
        os.fsync(self._files_fd)

    def _open_directory(self, name: str) -> int:
        """Open and validate a private child directory without following links."""
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=self._root_fd,
            )
        except OSError as exc:
            raise ValueError("artifact scratch layout is unsafe") from exc
        details = os.fstat(descriptor)
        if (
            not stat_module.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o077
        ):
            os.close(descriptor)
            raise ValueError("artifact scratch layout is unsafe")
        return descriptor

    @staticmethod
    def _assert_private_file_descriptor(descriptor: int, *, expected_mode: int) -> None:
        """Require a descriptor to identify one private single-link regular file."""
        details = os.fstat(descriptor)
        if (
            not stat_module.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or details.st_mode & 0o777 != expected_mode
        ):
            raise ArtifactScratchIntegrityError("artifact scratch file is invalid")

    @staticmethod
    def _write_all(descriptor: int, chunk: memoryview) -> None:
        """Write an entire bounded memory view or fail on a short write."""
        remaining = chunk
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short artifact scratch write")
            remaining = remaining[written:]

    @staticmethod
    async def _run_io(function: Any, *args: Any) -> Any:
        """Run blocking filesystem work while preserving cancellation cleanup."""
        return await run_blocking_cancellation_resistant(function, *args)


class ArtifactPreparationService:
    """Prepare untrusted bytes and seal their exact second-pass stream."""

    def __init__(self, manager: ArtifactScratchManager) -> None:
        """Bind preparation to one explicitly configured scratch manager."""
        self._manager = manager
        self._active: dict[object, _ActivePreparation] = {}
        self._pending_cleanup: dict[str, _PendingPreparationCleanup] = {}

    @property
    def pending_cleanup_count(self) -> int:
        """Return failed unhanded cleanups retained for explicit retry."""
        return len(self._pending_cleanup) + self._manager.pending_cleanup_count

    async def prepare(
        self,
        stream: AsyncIterable[bytes],
        *,
        media_type: str,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> PreparedArtifact:
        """Hash and count one complete source before any future provider call."""
        self._validate_client_commitment(
            media_type=media_type,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._manager.limits.total_deadline_seconds
        reservation: _ScratchReservation | None = None
        descriptor: int | None = None
        reader: BinaryIO | None = None
        handoff_ready = False
        try:
            async with asyncio.timeout_at(deadline):
                reservation, descriptor = await self._manager.allocate()
                digest = hashlib.sha256()
                byte_count = 0
                async for source_chunk in stream:
                    if not isinstance(source_chunk, bytes):
                        raise ArtifactInputMismatchError("artifact source must yield bytes")
                    view = memoryview(source_chunk)
                    for offset in range(0, len(view), self._manager.limits.stream_buffer_bytes):
                        chunk = view[offset : offset + self._manager.limits.stream_buffer_bytes]
                        byte_count += len(chunk)
                        if byte_count > self._manager.limits.maximum_source_bytes:
                            raise ArtifactLimitExceededError(
                                "artifact source exceeds maximum bytes"
                            )
                        digest.update(chunk)
                        await self._write_chunk(descriptor, chunk)
                sha256 = f"sha256:{digest.hexdigest()}"
                if expected_sha256 is not None and sha256 != expected_sha256:
                    raise ArtifactInputMismatchError(
                        "artifact source does not match expected digest"
                    )
                if expected_size is not None and byte_count != expected_size:
                    raise ArtifactInputMismatchError("artifact source does not match expected size")
                descriptor_to_seal = descriptor
                descriptor = None
                reader = await self._manager.seal_for_read(reservation, descriptor_to_seal)
            handoff_ready = True
        except TimeoutError:
            raise ArtifactPreparationDeadlineError(
                "artifact preparation deadline exceeded"
            ) from None
        except OSError as exc:
            if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
                raise ArtifactScratchCapacityError(
                    "artifact scratch capacity is unavailable"
                ) from None
            raise ArtifactStoreUnavailableError("artifact preparation failed") from None
        finally:
            if not handoff_ready and reservation is not None:
                await await_cancellation_resistant(
                    self._release_unhanded_preparation(
                        _PendingPreparationCleanup(
                            reservation=reservation,
                            descriptor=descriptor,
                            reader=reader,
                        )
                    )
                )
        assert reservation is not None and reader is not None
        commitment = ArtifactCommitment(
            sha256=sha256,
            byte_count=byte_count,
            media_type=media_type,
        )
        binding = object()
        self._active[binding] = _ActivePreparation(
            reservation=reservation,
            reader=reader,
            commitment=commitment,
            deadline=deadline,
        )
        return PreparedArtifact._from_preparation_service(
            owner=self,
            binding=binding,
        )

    def claim_prepared_commitment(self, binding: object) -> ArtifactCommitment:
        """Claim the commitment for one active binding exactly once."""
        active = self._active.get(binding)
        if active is None or active.handle_issued:
            raise ArtifactScratchIntegrityError("prepared artifact source is unavailable")
        active.handle_issued = True
        return active.commitment

    def validates_committed_source(
        self,
        binding: object,
        commitment: ArtifactCommitment,
        source: CommittedArtifactSource,
    ) -> bool:
        """Confirm one sealed value still maps to its live preparation."""
        active = self._active.get(binding)
        return (
            active is not None
            and active.handle_issued
            and active.commitment is commitment
            and active.source is source
        )

    def register_committed_source(
        self,
        binding: object,
        source: CommittedArtifactSource,
    ) -> None:
        """Bind the exact service-minted source identity once."""
        active = self._active.get(binding)
        if active is None or not active.handle_issued or active.source is not None:
            raise ArtifactScratchIntegrityError("prepared artifact source is unavailable")
        active.source = source

    def open_committed_stream(
        self,
        binding: object,
        commitment: ArtifactCommitment,
    ) -> AsyncIterator[bytes]:
        """Open the single complete stream inseparably bound to a commitment."""

        async def iterate() -> AsyncIterator[bytes]:
            """Verify and yield the single service-bound committed byte stream."""
            active = self._active.get(binding)
            if active is None or active.commitment is not commitment:
                raise ArtifactScratchIntegrityError("prepared artifact source is unavailable")
            if active.stream_claimed:
                raise ArtifactScratchIntegrityError("prepared artifact stream was already claimed")
            active.stream_claimed = True
            try:
                async with asyncio.timeout_at(active.deadline):
                    await self._verify_reader_commitment(active.reader, commitment)
                    digest = hashlib.sha256()
                    byte_count = 0
                    while True:
                        chunk = await self._read_chunk(active.reader)
                        if not chunk:
                            break
                        digest.update(chunk)
                        byte_count += len(chunk)
                        yield chunk
            except TimeoutError:
                raise ArtifactPreparationDeadlineError(
                    "artifact preparation deadline exceeded"
                ) from None
            if (
                f"sha256:{digest.hexdigest()}" != commitment.sha256
                or byte_count != commitment.byte_count
            ):
                raise ArtifactScratchIntegrityError(
                    "prepared artifact bytes changed after commitment"
                )

        return iterate()

    async def release_prepared_artifact(self, binding: object) -> None:
        """Close and remove one active prepared artifact exactly once."""
        active = self._active.get(binding)
        if active is None:
            return
        await self._run_io(active.reader.close)
        await self._manager.release(active.reservation)
        self._active.pop(binding, None)

    async def _release_unhanded_preparation(
        self,
        pending: _PendingPreparationCleanup,
    ) -> bool:
        """Close unhanded ownership or retain it for explicit retry."""
        failed = False
        if pending.descriptor is not None:
            descriptor = pending.descriptor
            pending.descriptor = None
            try:
                await self._close_descriptor(descriptor)
            except Exception:
                if not self._manager._descriptor_is_closed(descriptor):
                    self._manager._retain_uncertain_descriptor(pending.reservation)
                failed = True
        if pending.reader is not None:
            reader = pending.reader
            try:
                await self._run_io(reader.close)
                pending.reader = None
            except Exception:
                failed = True
        if pending.reader is None:
            try:
                await self._manager.release(pending.reservation)
            except Exception:
                failed = True
        reservation_id = pending.reservation.reservation_id
        if failed:
            self._pending_cleanup[reservation_id] = pending
            return False
        self._pending_cleanup.pop(reservation_id, None)
        return True

    async def retry_pending_cleanup(self) -> int:
        """Retry retained failed-preparation cleanup without activating a worker."""
        cleaned = await self._manager.retry_pending_cleanup()
        for pending in tuple(self._pending_cleanup.values()):
            if await await_completion_preserving_cancellation(
                self._release_unhanded_preparation(pending)
            ):
                cleaned += 1
        return cleaned

    @staticmethod
    def _validate_client_commitment(
        *,
        media_type: str,
        expected_sha256: str | None,
        expected_size: int | None,
    ) -> None:
        """Validate optional client commitment claims before reading bytes."""
        try:
            ArtifactCommitment.validate_media_type(media_type)
        except ValueError:
            raise ArtifactInputMismatchError("artifact media type is invalid") from None
        if expected_sha256 is not None:
            try:
                ArtifactCommitment.validate_sha256(expected_sha256)
            except ValueError:
                raise ArtifactInputMismatchError("artifact expected digest is invalid") from None
        if expected_size is not None:
            try:
                ArtifactCommitment.validate_byte_count(expected_size)
            except ValueError:
                raise ArtifactInputMismatchError("artifact expected size is invalid") from None

    async def _verify_reader_commitment(
        self,
        reader: BinaryIO,
        commitment: ArtifactCommitment,
    ) -> None:
        """Verify the anonymous read-only source before any byte can escape."""
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            chunk = await self._read_chunk(reader)
            if not chunk:
                break
            digest.update(chunk)
            byte_count += len(chunk)
        if (
            f"sha256:{digest.hexdigest()}" != commitment.sha256
            or byte_count != commitment.byte_count
        ):
            raise ArtifactScratchIntegrityError(
                "prepared artifact bytes changed after commitment"
            )
        await self._run_io(reader.seek, 0)

    @staticmethod
    async def _write_chunk(descriptor: int, chunk: memoryview) -> None:
        """Write one bounded source chunk through cancellation-safe I/O."""
        await ArtifactScratchManager._run_io(ArtifactScratchManager._write_all, descriptor, chunk)

    async def _read_chunk(self, reader: BinaryIO) -> bytes:
        """Read one configured bounded chunk from a prepared source."""
        return await self._run_io(reader.read, self._manager.limits.stream_buffer_bytes)

    @staticmethod
    async def _close_descriptor(descriptor: int) -> None:
        """Close a raw descriptor exactly once through cancellation-safe I/O."""
        await ArtifactScratchManager._run_io(os.close, descriptor)

    @staticmethod
    async def _run_io(function: Any, *args: Any) -> Any:
        """Reuse the manager's cancellation-safe blocking I/O boundary."""
        return await ArtifactScratchManager._run_io(function, *args)
