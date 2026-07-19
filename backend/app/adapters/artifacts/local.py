"""Private local implementation of the immutable ArtifactStore v2 port."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator
from uuid import uuid4

from app.core.cancellation import (
    await_cancellation_resistant,
    run_blocking_cancellation_resistant,
)
from app.core.file_locks import acquire_exclusive_file_lock
from app.interfaces.artifacts import (
    ARTIFACT_STORE_CAPABILITY_KEY,
    ArtifactByteRange,
    ArtifactConfigurationError,
    ArtifactInputMismatchError,
    ArtifactIntegrityError,
    ArtifactLimitExceededError,
    ArtifactObjectHead,
    ArtifactObjectMissingError,
    ArtifactOperationConflictError,
    ArtifactPutObservation,
    ArtifactPutResult,
    ArtifactRangeInvalidError,
    ArtifactStoreError,
    ArtifactStoreNamespaceClaim,
    ArtifactStoreNamespaceIdentity,
    ArtifactStoreUnavailableError,
    artifact_provider_object_ref,
    artifact_store_namespace_material,
    parse_artifact_provider_object_ref,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.core.hashing import canonical_json_hash
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource


_IDENTITY = ExternalServiceAdapterIdentity(ARTIFACT_STORE_CAPABILITY_KEY, "local")
_LAYOUT_MARKER = ".workstream-artifact-store-v2"
_LAYOUT_MARKER_TEMPORARY = ".workstream-artifact-store-v2.initializing"
_LAYOUT_MARKER_BYTES = b"workstream-artifact-store-v2\n"
_LAYOUT_ENTRY_NAMES = frozenset(
    {_LAYOUT_MARKER, _LAYOUT_MARKER_TEMPORARY, "locks", "objects", "tmp"}
)
_DIGEST_PREFIX_NAME = re.compile(r"^[0-9a-f]{2}$")
_DIGEST_OBJECT_NAME = re.compile(r"^[0-9a-f]{62}$")
_TEMPORARY_NAME = re.compile(r"^\.put\.[0-9a-f]{32}\.tmp$")
_LOCK_NAME = re.compile(r"^[0-9a-f]{64}\.lock$")


class LocalStorageBootstrap:
    """Composition-only namespace lifecycle for one pinned local store."""

    def __init__(self, adapter: LocalStorageAdapter) -> None:
        """Own one unopened-layout adapter created by the composition root."""
        if type(adapter) is not LocalStorageAdapter:
            raise ValueError("local artifact bootstrap adapter is invalid")
        self._adapter = adapter

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the canonical artifact-store/local adapter identity."""
        return self._adapter.identity

    @property
    def namespace_identity(self) -> ArtifactStoreNamespaceIdentity:
        """Return the namespace identity of the pinned local root."""
        return self._adapter._namespace_identity

    def initialize_after_namespace_claim(
        self,
        claim: ArtifactStoreNamespaceClaim,
    ) -> LocalStorageAdapter:
        """Return the byte store only after exact namespace admission."""
        return self._adapter._initialize_after_namespace_claim(claim)

    def close(self) -> None:
        """Release the pinned local store resources."""
        self._adapter.close()


class LocalStorageAdapter:
    """Filesystem-backed immutable byte provider for development and tests."""

    def __init__(
        self,
        *,
        root: Path,
        buffer_bytes: int = 1024 * 1024,
        lock_timeout_seconds: float = 1800.0,
    ) -> None:
        """Pin one pre-provisioned private root without mutating its layout."""
        if type(buffer_bytes) is not int or not 1 <= buffer_bytes <= 1024 * 1024:
            raise ValueError("artifact buffer must be between 1 byte and 1 MiB")
        if (
            isinstance(lock_timeout_seconds, bool)
            or not isinstance(lock_timeout_seconds, (int, float))
            or not math.isfinite(lock_timeout_seconds)
            or lock_timeout_seconds <= 0
        ):
            raise ValueError("artifact lock timeout is invalid")

        self._buffer_bytes = buffer_bytes
        self._lock_timeout_seconds = float(lock_timeout_seconds)
        self._root_fd = -1
        self._sha256_fd = -1
        self._tmp_fd = -1
        self._locks_fd = -1
        self._configured_root = os.path.abspath(os.fspath(root)) if isinstance(root, Path) else ""
        self._root_device = -1
        self._root_inode = -1
        self._initialized = False
        try:
            self._open_root(root)
        except (ArtifactStoreError, ValueError):
            self.close()
            raise
        except OSError:
            self.close()
            raise ArtifactConfigurationError("local artifact storage is unavailable") from None

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the canonical artifact-store/local adapter identity."""
        return _IDENTITY

    @property
    def _namespace_identity(self) -> ArtifactStoreNamespaceIdentity:
        """Return the canonical identity of the pinned local namespace."""
        root_identity = canonical_json_hash(
            {
                "private_root": self._configured_root,
                "device": self._root_device,
                "inode": self._root_inode,
            }
        )
        return ArtifactStoreNamespaceIdentity(
            provider_profile="local-v2",
            descriptor_items=(
                ("private_prefix", "objects/sha256"),
                ("private_root_identity", root_identity),
            ),
        )

    def _initialize_after_namespace_claim(
        self,
        claim: ArtifactStoreNamespaceClaim,
    ) -> LocalStorageAdapter:
        """Create or validate layout through the same root accepted by PostgreSQL."""
        try:
            if (
                type(claim) is not ArtifactStoreNamespaceClaim
                or claim.adapter_identity != self.identity
                or claim.namespace_identity != self._namespace_identity
                or claim.namespace_fingerprint != self._expected_namespace_fingerprint()
            ):
                raise ArtifactConfigurationError(
                    "artifact namespace claim does not match provider"
                )
            if self._initialized:
                raise ArtifactConfigurationError(
                    "local artifact storage is already initialized"
                )
            self._assert_pinned_root_is_current()
            self._initialize_layout()
            self._initialized = True
            return self
        except (ArtifactStoreError, ValueError):
            self.close()
            raise
        except OSError:
            self.close()
            raise ArtifactConfigurationError("local artifact storage is unavailable") from None

    def _expected_namespace_fingerprint(self) -> str:
        """Return the shared canonical fingerprint for this pinned local namespace."""
        _, fingerprint = artifact_store_namespace_material(
            backend="local",
            adapter_identity=self.identity,
            namespace_identity=self._namespace_identity,
        )
        return fingerprint

    def close(self) -> None:
        """Release pinned private directory descriptors."""
        for attribute in ("_locks_fd", "_tmp_fd", "_sha256_fd", "_root_fd"):
            descriptor = getattr(self, attribute, -1)
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                setattr(self, attribute, -1)
        self._initialized = False

    def __del__(self) -> None:
        """Best-effort descriptor cleanup."""
        self.close()

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        """Publish sealed bytes exclusively or verify an exact immutable replay."""
        self._require_initialized()
        if type(source) is not CommittedArtifactSource:
            raise ArtifactInputMismatchError("artifact source is not sealed")
        commitment = source.commitment
        if commitment.byte_count > HARD_MAXIMUM_ARTIFACT_BYTES:
            raise ArtifactLimitExceededError("artifact source exceeds provider limit")

        provider_object_ref = artifact_provider_object_ref(commitment)
        lock: tuple[Any, int] | None = None
        descriptor: int | None = None
        temporary_name: str | None = None
        try:
            lock = await self._acquire_lock_async(commitment.sha256[7:])
            try:
                await self._run_io(self._head_object, provider_object_ref)
            except FileNotFoundError:
                pass
            else:
                await self._run_io(
                    self._verify_exact_under_lock,
                    provider_object_ref,
                    commitment,
                )
                return ArtifactPutResult(provider_object_ref, replayed=True)

            descriptor, temporary_name = await self._create_temporary_async()
            digest = hashlib.sha256()
            byte_count = 0
            async for source_chunk in source.stream():
                if not isinstance(source_chunk, bytes):
                    raise ArtifactInputMismatchError("artifact source must yield bytes")
                view = memoryview(source_chunk)
                for offset in range(0, len(view), self._buffer_bytes):
                    chunk = view[offset : offset + self._buffer_bytes]
                    byte_count += len(chunk)
                    if byte_count > commitment.byte_count:
                        raise ArtifactInputMismatchError(
                            "artifact source exceeds committed byte count"
                        )
                    digest.update(chunk)
                    await self._run_io(self._write_all, descriptor, chunk)

            observed_sha256 = f"sha256:{digest.hexdigest()}"
            if (
                byte_count != commitment.byte_count
                or observed_sha256 != commitment.sha256
            ):
                raise ArtifactInputMismatchError("artifact source violates commitment")

            await self._run_io(self._seal_temporary, descriptor)
            published = await self._run_io(
                self._publish_exclusive,
                temporary_name,
                provider_object_ref,
            )
            temporary_name = None
            if not published:
                await self._run_io(
                    self._verify_exact_under_lock,
                    provider_object_ref,
                    commitment,
                )
                return ArtifactPutResult(provider_object_ref, replayed=True)
            return ArtifactPutResult(provider_object_ref, replayed=False)
        except asyncio.CancelledError as cancellation:
            await await_cancellation_resistant(
                asyncio.to_thread(self._cleanup_resources, descriptor, temporary_name, lock)
            )
            descriptor = None
            temporary_name = None
            lock = None
            raise cancellation
        except ArtifactStoreError:
            raise
        except OSError:
            raise ArtifactStoreUnavailableError("local artifact operation failed") from None
        finally:
            if descriptor is not None or temporary_name is not None or lock is not None:
                await self._run_io(
                    self._cleanup_resources,
                    descriptor,
                    temporary_name,
                    lock,
                )

    async def observe_put_result(
        self,
        commitment: ArtifactCommitment,
    ) -> ArtifactPutObservation:
        """Read and validate the complete deterministic object when it exists."""
        self._require_initialized()
        if type(commitment) is not ArtifactCommitment:
            raise ArtifactOperationConflictError("artifact commitment is invalid")
        provider_object_ref = artifact_provider_object_ref(commitment)
        observed = await self.head(provider_object_ref)
        if not observed.exists:
            return ArtifactPutObservation(provider_object_ref, committed=False)
        await self._verify_exact(provider_object_ref, commitment)
        return ArtifactPutObservation(provider_object_ref, committed=True)

    def open(
        self,
        provider_object_ref: str,
        byte_range: ArtifactByteRange | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream a full object or range through bounded off-loop reads."""
        self._require_initialized()
        parse_artifact_provider_object_ref(provider_object_ref)
        if byte_range is not None and type(byte_range) is not ArtifactByteRange:
            raise ArtifactOperationConflictError("artifact byte range is invalid")
        selected_range = byte_range or ArtifactByteRange()

        async def iterate() -> AsyncIterator[bytes]:
            """Yield bounded chunks while retaining one validated descriptor."""
            descriptor: int | None = None
            try:
                try:
                    descriptor, byte_count = await self._open_object_async(
                        provider_object_ref
                    )
                except FileNotFoundError:
                    raise ArtifactObjectMissingError("artifact object is missing") from None
                if selected_range.offset > byte_count:
                    raise ArtifactRangeInvalidError("artifact range starts past object end")
                remaining = byte_count - selected_range.offset
                if selected_range.length is not None:
                    remaining = min(remaining, selected_range.length)
                position = selected_range.offset
                while remaining:
                    chunk = await self._run_io(
                        os.pread,
                        descriptor,
                        min(self._buffer_bytes, remaining),
                        position,
                    )
                    if not chunk:
                        raise ArtifactIntegrityError("artifact object was truncated")
                    if len(chunk) > self._buffer_bytes or len(chunk) > remaining:
                        raise ArtifactIntegrityError("artifact read exceeded its bound")
                    position += len(chunk)
                    remaining -= len(chunk)
                    yield chunk
            except asyncio.CancelledError as cancellation:
                if descriptor is not None:
                    await await_cancellation_resistant(asyncio.to_thread(os.close, descriptor))
                    descriptor = None
                raise cancellation
            except ArtifactStoreError:
                raise
            except OSError:
                raise ArtifactStoreUnavailableError("local artifact read failed") from None
            finally:
                if descriptor is not None:
                    await self._run_io(os.close, descriptor)

        return iterate()

    async def head(self, provider_object_ref: str) -> ArtifactObjectHead:
        """Return an existing or missing observation without exposing paths."""
        self._require_initialized()
        parse_artifact_provider_object_ref(provider_object_ref)
        try:
            try:
                byte_count = await self._run_io(
                    self._head_object_with_recovery,
                    provider_object_ref,
                )
            except FileNotFoundError:
                return ArtifactObjectHead(provider_object_ref, exists=False)
            return ArtifactObjectHead(
                provider_object_ref,
                exists=True,
                byte_count=byte_count,
            )
        except ArtifactStoreError:
            raise
        except OSError:
            raise ArtifactStoreUnavailableError("local artifact head failed") from None

    async def _verify_exact(
        self,
        provider_object_ref: str,
        commitment: ArtifactCommitment,
    ) -> None:
        """Independently hash and count one complete existing object."""
        digest = hashlib.sha256()
        byte_count = 0
        async for chunk in self.open(provider_object_ref):
            digest.update(chunk)
            byte_count += len(chunk)
        if (
            byte_count != commitment.byte_count
            or f"sha256:{digest.hexdigest()}" != commitment.sha256
        ):
            raise ArtifactIntegrityError("artifact object violates commitment")

    async def _run_io(self, function: Any, *args: Any) -> Any:
        """Complete blocking filesystem work before preserving cancellation."""
        return await run_blocking_cancellation_resistant(function, *args)

    async def _acquire_lock_async(self, digest_hex: str) -> tuple[Any, int]:
        """Acquire a cross-process digest lock without leaking it on cancellation."""
        task = asyncio.create_task(asyncio.to_thread(self._acquire_lock, digest_hex))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError as cancellation:
            try:
                lock = await await_cancellation_resistant(task)
            except Exception:
                raise cancellation from None
            await await_cancellation_resistant(asyncio.to_thread(self._release_lock, lock))
            raise cancellation

    async def _create_temporary_async(self) -> tuple[int, str]:
        """Create a temporary file without losing ownership on cancellation."""
        task = asyncio.create_task(asyncio.to_thread(self._create_temporary))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError as cancellation:
            try:
                descriptor, temporary_name = await await_cancellation_resistant(task)
            except Exception:
                raise cancellation from None
            await await_cancellation_resistant(
                asyncio.to_thread(
                    self._cleanup_resources,
                    descriptor,
                    temporary_name,
                    None,
                )
            )
            raise cancellation

    async def _open_object_async(self, provider_object_ref: str) -> tuple[int, int]:
        """Open an object without losing descriptor ownership on cancellation."""
        task = asyncio.create_task(
            asyncio.to_thread(self._open_object_with_recovery, provider_object_ref)
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError as cancellation:
            try:
                descriptor, _ = await await_cancellation_resistant(task)
            except Exception:
                raise cancellation from None
            await await_cancellation_resistant(asyncio.to_thread(os.close, descriptor))
            raise cancellation

    def _open_root(self, configured_root: Path) -> None:
        """Open and pin one existing owner-private root without mutation."""
        if not isinstance(configured_root, Path):
            raise ValueError("artifact root must be a path")
        if configured_root.is_symlink():
            raise ArtifactConfigurationError("local artifact root is unsafe")
        self._root_fd = os.open(
            configured_root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        self._assert_private_directory(self._root_fd)
        details = os.fstat(self._root_fd)
        self._root_device = details.st_dev
        self._root_inode = details.st_ino

    def _assert_pinned_root_is_current(self) -> None:
        """Reject same-path replacement before any layout mutation."""
        try:
            current = os.lstat(self._configured_root)
        except OSError:
            raise ArtifactConfigurationError("local artifact root changed after validation") from None
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_uid != os.geteuid()
            or stat.S_IMODE(current.st_mode) != 0o700
            or current.st_dev != self._root_device
            or current.st_ino != self._root_inode
        ):
            raise ArtifactConfigurationError("local artifact root changed after validation")

    def _initialize_layout(self) -> None:
        """Initialize only an empty or already-valid v2 layout on the pinned root."""
        fcntl.flock(self._root_fd, fcntl.LOCK_EX)
        try:
            entries = set(os.listdir(self._root_fd))
            if not entries.issubset(_LAYOUT_ENTRY_NAMES):
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            if _LAYOUT_MARKER_TEMPORARY in entries:
                self._recover_layout_marker(entries)
                entries = set(os.listdir(self._root_fd))
            if _LAYOUT_MARKER in entries:
                self._validate_existing_layout(entries)
            else:
                if entries:
                    raise ArtifactConfigurationError("local artifact layout is incompatible")
                self._publish_layout_marker()

            self._validate_marker()

            objects_fd = self._ensure_directory(self._root_fd, "objects")
            try:
                self._sha256_fd = self._ensure_directory(objects_fd, "sha256")
            finally:
                os.close(objects_fd)
            self._tmp_fd = self._ensure_directory(self._root_fd, "tmp")
            self._locks_fd = self._ensure_directory(self._root_fd, "locks")
        finally:
            fcntl.flock(self._root_fd, fcntl.LOCK_UN)

    def _publish_layout_marker(self) -> None:
        """Durably publish the marker from one private temporary file."""
        marker = os.open(
            _LAYOUT_MARKER_TEMPORARY,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=self._root_fd,
        )
        try:
            self._write_all(marker, memoryview(_LAYOUT_MARKER_BYTES))
            os.fsync(marker)
        finally:
            os.close(marker)
        os.link(
            _LAYOUT_MARKER_TEMPORARY,
            _LAYOUT_MARKER,
            src_dir_fd=self._root_fd,
            dst_dir_fd=self._root_fd,
            follow_symlinks=False,
        )
        os.fsync(self._root_fd)
        os.unlink(_LAYOUT_MARKER_TEMPORARY, dir_fd=self._root_fd)
        os.fsync(self._root_fd)

    def _recover_layout_marker(self, entries: set[str]) -> None:
        """Complete or remove one exact durable marker publication remnant."""
        temporary_details = self._validate_marker(
            _LAYOUT_MARKER_TEMPORARY,
            recoverable=True,
        )
        if _LAYOUT_MARKER in entries:
            marker_details = self._validate_marker(_LAYOUT_MARKER, recoverable=True)
            if (
                temporary_details.st_dev != marker_details.st_dev
                or temporary_details.st_ino != marker_details.st_ino
                or temporary_details.st_nlink != 2
                or marker_details.st_nlink != 2
            ):
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            os.unlink(_LAYOUT_MARKER_TEMPORARY, dir_fd=self._root_fd)
        else:
            if (
                entries != {_LAYOUT_MARKER_TEMPORARY}
                or temporary_details.st_nlink != 1
            ):
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            os.link(
                _LAYOUT_MARKER_TEMPORARY,
                _LAYOUT_MARKER,
                src_dir_fd=self._root_fd,
                dst_dir_fd=self._root_fd,
                follow_symlinks=False,
            )
            os.fsync(self._root_fd)
            os.unlink(_LAYOUT_MARKER_TEMPORARY, dir_fd=self._root_fd)
        os.fsync(self._root_fd)

    def _validate_existing_layout(self, root_entries: set[str]) -> None:
        """Validate the complete existing v2 grammar before any mutation."""
        self._validate_marker()
        temporary_links: set[tuple[int, int]] = set()
        if "tmp" in root_entries:
            temporary_fd = self._open_existing_directory(self._root_fd, "tmp")
            try:
                temporary_links = self._validate_temporary_entries(temporary_fd)
            finally:
                os.close(temporary_fd)
        object_links: set[tuple[int, int]] = set()
        if "objects" in root_entries:
            objects_fd = self._open_existing_directory(self._root_fd, "objects")
            try:
                object_links = self._validate_object_entries(objects_fd)
            finally:
                os.close(objects_fd)
        if object_links != temporary_links:
            raise ArtifactIntegrityError("local artifact recovery links are inconsistent")
        if "locks" in root_entries:
            locks_fd = self._open_existing_directory(self._root_fd, "locks")
            try:
                self._validate_lock_entries(locks_fd)
            finally:
                os.close(locks_fd)

    def _validate_object_entries(self, objects_fd: int) -> set[tuple[int, int]]:
        """Require only canonical immutable objects and recoverable hard links."""
        object_entries = set(os.listdir(objects_fd))
        if not object_entries.issubset({"sha256"}):
            raise ArtifactConfigurationError("local artifact layout is incompatible")
        if "sha256" not in object_entries:
            return set()
        sha256_fd = self._open_existing_directory(objects_fd, "sha256")
        recovery_links: set[tuple[int, int]] = set()
        try:
            for prefix in os.listdir(sha256_fd):
                if _DIGEST_PREFIX_NAME.fullmatch(prefix) is None:
                    raise ArtifactConfigurationError("local artifact layout is incompatible")
                prefix_fd = self._open_existing_directory(sha256_fd, prefix)
                try:
                    for name in os.listdir(prefix_fd):
                        if _DIGEST_OBJECT_NAME.fullmatch(name) is None:
                            raise ArtifactConfigurationError(
                                "local artifact layout is incompatible"
                            )
                        details = self._stat_layout_file(
                            prefix_fd,
                            name,
                            recoverable=True,
                        )
                        if details is None:
                            continue
                        if stat.S_IMODE(details.st_mode) != 0o400:
                            raise ArtifactIntegrityError("local artifact object is mutable")
                        if details.st_nlink == 2:
                            recovery_links.add((details.st_dev, details.st_ino))
                finally:
                    os.close(prefix_fd)
        finally:
            os.close(sha256_fd)
        return recovery_links

    def _validate_temporary_entries(self, temporary_fd: int) -> set[tuple[int, int]]:
        """Require only bounded private put temporaries and recovery links."""
        recovery_links: set[tuple[int, int]] = set()
        for name in os.listdir(temporary_fd):
            if _TEMPORARY_NAME.fullmatch(name) is None:
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            details = self._stat_layout_file(temporary_fd, name, recoverable=True)
            if details is None:
                continue
            mode = stat.S_IMODE(details.st_mode)
            if mode not in {0o400, 0o600} or (details.st_nlink == 2 and mode != 0o400):
                raise ArtifactIntegrityError("local artifact temporary is unsafe")
            if details.st_nlink == 1:
                raise ArtifactConfigurationError(
                    "local artifact startup requires orphan temporary cleanup"
                )
            recovery_links.add((details.st_dev, details.st_ino))
        return recovery_links

    def _validate_lock_entries(self, locks_fd: int) -> None:
        """Require only canonical private digest-lock files."""
        for name in os.listdir(locks_fd):
            if _LOCK_NAME.fullmatch(name) is None:
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            details = self._stat_layout_file(locks_fd, name, recoverable=False)
            if details is not None and stat.S_IMODE(details.st_mode) != 0o600:
                raise ArtifactIntegrityError("local artifact lock is unsafe")

    def _require_initialized(self) -> None:
        """Reject provider operations before PostgreSQL namespace admission."""
        if not self._initialized:
            raise ArtifactConfigurationError("artifact store namespace is not initialized")

    def _validate_marker(
        self,
        name: str = _LAYOUT_MARKER,
        *,
        recoverable: bool = False,
    ) -> os.stat_result:
        """Require the exact private v2 layout marker."""
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=self._root_fd,
        )
        try:
            details = (
                self._assert_recoverable_object(descriptor)
                if recoverable
                else self._assert_private_regular(descriptor)
            )
            if stat.S_IMODE(details.st_mode) != 0o600:
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            content = os.read(descriptor, len(_LAYOUT_MARKER_BYTES) + 1)
            if content != _LAYOUT_MARKER_BYTES:
                raise ArtifactConfigurationError("local artifact layout is incompatible")
            return details
        finally:
            os.close(descriptor)

    def _ensure_directory(self, parent_fd: int, name: str) -> int:
        """Create or open one fixed private no-follow directory."""
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        return self._open_existing_directory(parent_fd, name)

    def _open_existing_directory(self, parent_fd: int, name: str) -> int:
        """Open and validate one existing private directory without leaking it."""
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            self._assert_private_directory(descriptor)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _stat_layout_file(
        self,
        parent_fd: int,
        name: str,
        *,
        recoverable: bool,
    ) -> os.stat_result | None:
        """Open one raced layout file safely and return its validated metadata."""
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None
        try:
            if recoverable:
                return self._assert_recoverable_object(descriptor)
            return self._assert_private_regular(descriptor)
        finally:
            os.close(descriptor)

    def _open_prefix(self, prefix: str, *, create: bool) -> int:
        """Open one digest-prefix directory without following links."""
        if create:
            try:
                os.mkdir(prefix, 0o700, dir_fd=self._sha256_fd)
            except FileExistsError:
                pass
        try:
            descriptor = os.open(
                prefix,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=self._sha256_fd,
            )
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise ArtifactIntegrityError("local artifact prefix is unsafe") from None
            raise
        self._assert_private_directory(descriptor)
        if create:
            os.fsync(self._sha256_fd)
        return descriptor

    def _create_temporary(self) -> tuple[int, str]:
        """Create one unpublished private temporary object."""
        name = f".put.{uuid4().hex}.tmp"
        descriptor = os.open(
            name,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=self._tmp_fd,
        )
        self._assert_private_regular(descriptor)
        return descriptor, name

    @staticmethod
    def _seal_temporary(descriptor: int) -> None:
        """Make one complete temporary object read-only and durable."""
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)

    def _publish_exclusive(self, temporary_name: str, provider_object_ref: str) -> bool:
        """Hard-link one complete object without ever replacing existing bytes."""
        prefix, filename = parse_artifact_provider_object_ref(provider_object_ref)
        prefix_fd = self._open_prefix(prefix, create=True)
        try:
            try:
                os.link(
                    temporary_name,
                    filename,
                    src_dir_fd=self._tmp_fd,
                    dst_dir_fd=prefix_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                os.unlink(temporary_name, dir_fd=self._tmp_fd)
                os.fsync(self._tmp_fd)
                return False
            os.fsync(prefix_fd)
            os.unlink(temporary_name, dir_fd=self._tmp_fd)
            os.fsync(self._tmp_fd)
            return True
        finally:
            os.close(prefix_fd)

    def _head_object(self, provider_object_ref: str) -> int:
        """Return an exact size after validating one private regular object."""
        descriptor, byte_count = self._open_object(provider_object_ref)
        os.close(descriptor)
        return byte_count

    def _head_object_with_recovery(self, provider_object_ref: str) -> int:
        """Recover an interrupted publication under its digest lock before head."""
        prefix, filename = parse_artifact_provider_object_ref(provider_object_ref)
        with self._locked_file(prefix + filename):
            return self._head_object(provider_object_ref)

    def _open_object_with_recovery(self, provider_object_ref: str) -> tuple[int, int]:
        """Recover an interrupted publication under its digest lock before open."""
        prefix, filename = parse_artifact_provider_object_ref(provider_object_ref)
        with self._locked_file(prefix + filename):
            return self._open_object(provider_object_ref)

    def _open_object(self, provider_object_ref: str) -> tuple[int, int]:
        """Open one immutable no-follow object and return its exact size."""
        prefix, filename = parse_artifact_provider_object_ref(provider_object_ref)
        prefix_fd = self._open_prefix(prefix, create=False)
        descriptor = -1
        try:
            try:
                descriptor = os.open(
                    filename,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=prefix_fd,
                )
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ArtifactIntegrityError("local artifact object is unsafe") from None
                raise
            details = self._assert_recoverable_object(descriptor)
            if details.st_nlink == 2:
                self._recover_interrupted_publication(descriptor, details, prefix_fd)
                details = self._assert_private_regular(descriptor)
            if stat.S_IMODE(details.st_mode) != 0o400:
                raise ArtifactIntegrityError("local artifact object is mutable")
            return descriptor, details.st_size
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            raise
        finally:
            os.close(prefix_fd)

    def _recover_interrupted_publication(
        self,
        descriptor: int,
        object_stat: os.stat_result,
        prefix_fd: int,
    ) -> None:
        """Remove the one sealed temp hard link left by a crashed publisher."""
        matches: list[str] = []
        for name in os.listdir(self._tmp_fd):
            if _TEMPORARY_NAME.fullmatch(name) is None:
                continue
            try:
                candidate = os.stat(name, dir_fd=self._tmp_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if candidate.st_dev == object_stat.st_dev and candidate.st_ino == object_stat.st_ino:
                if (
                    not stat.S_ISREG(candidate.st_mode)
                    or candidate.st_mode & 0o077
                    or stat.S_IMODE(candidate.st_mode) != 0o400
                    or candidate.st_nlink != 2
                ):
                    raise ArtifactIntegrityError("local artifact recovery link is unsafe")
                matches.append(name)
        if len(matches) != 1:
            raise ArtifactIntegrityError("local artifact publication is ambiguous")
        os.unlink(matches[0], dir_fd=self._tmp_fd)
        os.fsync(self._tmp_fd)
        os.fsync(prefix_fd)
        if os.fstat(descriptor).st_nlink != 1:
            raise ArtifactIntegrityError("local artifact publication recovery failed")

    def _verify_exact_under_lock(
        self,
        provider_object_ref: str,
        commitment: ArtifactCommitment,
    ) -> None:
        """Hash one object while the caller owns its digest lock."""
        descriptor, byte_count = self._open_object(provider_object_ref)
        digest = hashlib.sha256()
        observed_bytes = 0
        try:
            while observed_bytes < byte_count:
                chunk = os.read(descriptor, min(self._buffer_bytes, byte_count - observed_bytes))
                if not chunk:
                    raise ArtifactIntegrityError("artifact object was truncated")
                observed_bytes += len(chunk)
                digest.update(chunk)
        finally:
            os.close(descriptor)
        if (
            observed_bytes != commitment.byte_count
            or f"sha256:{digest.hexdigest()}" != commitment.sha256
        ):
            raise ArtifactIntegrityError("artifact object violates commitment")

    @contextmanager
    def _locked_file(self, digest_hex: str) -> Iterator[int]:
        """Own one bounded cross-process lock for a canonical digest."""
        descriptor = os.open(
            f"{digest_hex}.lock",
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=self._locks_fd,
        )
        try:
            self._assert_private_regular(descriptor)
            try:
                acquire_exclusive_file_lock(
                    descriptor,
                    timeout_seconds=self._lock_timeout_seconds,
                )
            except TimeoutError:
                raise ArtifactStoreUnavailableError(
                    "local artifact lock deadline exceeded"
                ) from None
            yield descriptor
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _acquire_lock(self, digest_hex: str) -> tuple[Any, int]:
        """Acquire one validated digest lock."""
        if re.fullmatch(r"[0-9a-f]{64}", digest_hex) is None:
            raise ArtifactOperationConflictError("artifact commitment is invalid")
        manager = self._locked_file(digest_hex)
        descriptor = manager.__enter__()
        return manager, descriptor

    @staticmethod
    def _release_lock(lock: tuple[Any, int]) -> None:
        """Release one owned digest lock."""
        manager, _ = lock
        manager.__exit__(None, None, None)

    def _cleanup_resources(
        self,
        descriptor: int | None,
        temporary_name: str | None,
        lock: tuple[Any, int] | None,
    ) -> None:
        """Release all private put resources after failure or cancellation."""
        try:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary_name is not None and _TEMPORARY_NAME.fullmatch(temporary_name):
                try:
                    os.unlink(temporary_name, dir_fd=self._tmp_fd)
                    os.fsync(self._tmp_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
        finally:
            if lock is not None:
                try:
                    self._release_lock(lock)
                except OSError:
                    pass

    @staticmethod
    def _write_all(descriptor: int, chunk: memoryview) -> None:
        """Write one already-bounded view completely."""
        remaining = chunk
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError(errno.EIO, "short artifact write")
            remaining = remaining[written:]

    @staticmethod
    def _assert_private_directory(descriptor: int) -> os.stat_result:
        """Require one owner-private directory descriptor."""
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) != 0o700
        ):
            raise ArtifactConfigurationError("local artifact directory is unsafe")
        return details

    @staticmethod
    def _assert_private_regular(descriptor: int) -> os.stat_result:
        """Require one owner-private, single-link regular file."""
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o077
            or details.st_nlink != 1
        ):
            raise ArtifactIntegrityError("local artifact object is unsafe")
        return details

    @staticmethod
    def _assert_recoverable_object(descriptor: int) -> os.stat_result:
        """Allow only the one extra link produced by interrupted publication."""
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o077
            or details.st_nlink not in {1, 2}
        ):
            raise ArtifactIntegrityError("local artifact object is unsafe")
        return details
