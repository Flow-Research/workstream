"""Operation-owned local ZIPs; the existing local adapter owns all path safety."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
import re
import secrets
import stat
from typing import Any, Iterator
from uuid import UUID

from app.core.file_locks import acquire_exclusive_file_lock
from app.interfaces.artifacts import (
    ArtifactIntegrityError, ArtifactOperationConflictError,
    ArtifactPreconditionFailedError, ArtifactStoreUnavailableError,
    ArtifactInputMismatchError, ArtifactLimitExceededError,
)
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource, SubmissionSourceCompletion, SubmissionSourceLocation,
    SubmissionSourcePart, SubmissionSourceUpload, SubmissionSourceUploadIntent,
)

_METADATA_LIMIT = 256 * 1024
_TEMP = re.compile(r"^\.(?:upload|seal|aborted)\.[0-9a-f]{32}\.tmp$")
_FILES = frozenset({"upload.json", "seal.json", "aborted.json", "bundle.zip"})


class LocalSubmissionSource:
    """Private synchronous primitives, called off-loop with cancellation drained."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def location(self, value: SubmissionSourceLocation) -> SubmissionSourceLocation:
        self.store._require_initialized()
        value = SubmissionSourceLocation.model_validate(value)
        if (value.provider_profile != "local-v2"
                or value.namespace_fingerprint != self.store._expected_namespace_fingerprint()):
            raise ArtifactOperationConflictError("submission source namespace mismatch")
        return value

    @staticmethod
    def deadline(intent: SubmissionSourceUploadIntent) -> float:
        remaining = (intent.upload_deadline_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise ArtifactStoreUnavailableError("submission upload deadline expired")
        return remaining

    @contextmanager
    def locked(self, location: SubmissionSourceLocation, intent: SubmissionSourceUploadIntent | None = None, *, create: bool = False) -> Iterator[int]:
        location = self.location(location)
        key = hashlib.sha256(location.object_ref.encode()).hexdigest()
        lock_fd = os.open(key + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                          0o600, dir_fd=self.store._locks_fd)
        directories = []
        try:
            self.store._assert_private_regular(lock_fd)
            timeout = self.store._lock_timeout_seconds
            if intent is not None:
                timeout = min(timeout, self.deadline(intent))
            acquire_exclusive_file_lock(lock_fd, timeout_seconds=timeout)
            if intent is not None:
                self.deadline(intent)
            parent = self.store._root_fd
            for name in ("objects", "submission-source", "v1", str(location.operation_id)):
                method = self.store._ensure_directory if create else self.store._open_existing_directory
                child = method(parent, name)
                directories.append(child)
                if create:
                    os.fsync(parent)
                parent = child
            yield parent
        except TimeoutError:
            raise ArtifactStoreUnavailableError("submission source lock deadline expired") from None
        finally:
            for descriptor in reversed(directories):
                os.close(descriptor)
            os.close(lock_fd)

    def read(self, directory: int, name: str) -> bytes:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            info = self.store._assert_private_regular(descriptor)
            if info.st_size > _METADATA_LIMIT:
                raise ArtifactIntegrityError("submission source metadata exceeds bound")
            raw = os.read(descriptor, _METADATA_LIMIT + 1)
            if len(raw) != info.st_size:
                raise ArtifactIntegrityError("submission source metadata changed")
            return raw
        except (ValueError, UnicodeError):
            raise ArtifactIntegrityError("submission source metadata is invalid") from None
        finally:
            os.close(descriptor)

    def publish(self, directory: int, name: str, value: dict[str, Any]) -> None:
        # Every caller holds the same operation lock. Only metadata is renamed;
        # the raw ZIP remains at its original key and inode from begin onward.
        try:
            os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ArtifactPreconditionFailedError("submission source metadata already exists")
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        if len(raw) > _METADATA_LIMIT:
            raise ArtifactIntegrityError("submission source metadata exceeds bound")
        temporary = f".{name[:-5]}.{secrets.token_hex(16)}.tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            self.store._write_all(descriptor, memoryview(raw))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.rename(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)

    def upload(self, directory: int, supplied: SubmissionSourceUpload) -> SubmissionSourceUpload:
        stored = SubmissionSourceUpload.model_validate_json(self.read(directory, "upload.json"))
        if stored != supplied:
            raise ArtifactOperationConflictError("submission upload identity mismatch")
        return stored

    @staticmethod
    def exists(directory: int, name: str) -> bool:
        try:
            os.stat(name, dir_fd=directory, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def begin(self, intent: SubmissionSourceUploadIntent) -> SubmissionSourceUpload:
        intent = SubmissionSourceUploadIntent.model_validate(intent)
        with self.locked(intent.location, intent, create=True) as directory:
            if self.exists(directory, "upload.json") or self.exists(directory, "aborted.json"):
                raise ArtifactPreconditionFailedError("submission source already initiated")
            # An opaque provider token is not a Workstream surrogate record ID.
            upload = SubmissionSourceUpload(intent=intent, provider_upload_id=secrets.token_hex(16))
            self.publish(directory, "upload.json", upload.model_dump(mode="json"))
            descriptor = os.open("bundle.zip", os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(directory)
            return upload

    def part(self, upload: SubmissionSourceUpload, number: int, data: bytes) -> SubmissionSourcePart:
        upload = SubmissionSourceUpload.model_validate(upload)
        if type(number) is not int or not 1 <= number <= 100 or type(data) is not bytes or not data:
            raise ArtifactInputMismatchError("submission source part is invalid")
        intent = upload.intent
        offset = (number - 1) * intent.part_bytes
        limit = intent.declared_raw_bytes or intent.maximum_raw_bytes
        if len(data) > intent.part_bytes or offset + len(data) > limit:
            raise ArtifactLimitExceededError("submission source part exceeds bound")
        with self.locked(intent.location, intent) as directory:
            self.upload(directory, upload)
            if self.exists(directory, "seal.json") or self.exists(directory, "aborted.json"):
                raise ArtifactPreconditionFailedError("submission source no longer writable")
            descriptor = os.open("bundle.zip", os.O_WRONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                info = self.store._assert_private_regular(descriptor)
                if info.st_size != offset or stat.S_IMODE(info.st_mode) != 0o600:
                    raise ArtifactPreconditionFailedError("submission source part is not next")
                os.lseek(descriptor, offset, os.SEEK_SET)
                self.store._write_all(descriptor, memoryview(data))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.deadline(intent)
            return SubmissionSourcePart(number=number, byte_count=len(data),
                                        provider_etag=hashlib.sha256(data).hexdigest())

    def verify(self, descriptor: int, completion: SubmissionSourceCompletion) -> os.stat_result:
        info = self.store._assert_private_regular(descriptor)
        if info.st_size != completion.raw_byte_count:
            raise ArtifactIntegrityError("submission source size mismatch")
        raw_hash = hashlib.sha256()
        position = 0
        for part in completion.parts:
            part_hash = hashlib.sha256()
            remaining = part.byte_count
            while remaining:
                chunk = os.pread(descriptor, min(self.store._buffer_bytes, remaining), position)
                if not chunk:
                    raise ArtifactIntegrityError("submission source was truncated")
                raw_hash.update(chunk)
                part_hash.update(chunk)
                position += len(chunk)
                remaining -= len(chunk)
            if part_hash.hexdigest() != part.provider_etag:
                raise ArtifactIntegrityError("submission source part mismatch")
        if "sha256:" + raw_hash.hexdigest() != completion.raw_sha256:
            raise ArtifactIntegrityError("submission source digest mismatch")
        return info

    @staticmethod
    def source(completion: SubmissionSourceCompletion, info: os.stat_result) -> SealedSubmissionSource:
        return SealedSubmissionSource(
            location=completion.upload.intent.location,
            provider_generation=f"{completion.upload.provider_upload_id}:{info.st_dev}:{info.st_ino}",
            raw_sha256=completion.raw_sha256, raw_byte_count=completion.raw_byte_count,
            sealed_upload_fence=completion.upload.intent.upload_fence,
        )

    def complete(self, completion: SubmissionSourceCompletion) -> SealedSubmissionSource:
        completion = SubmissionSourceCompletion.model_validate(completion)
        upload = completion.upload
        with self.locked(upload.intent.location, upload.intent) as directory:
            self.upload(directory, upload)
            if self.exists(directory, "aborted.json") or self.exists(directory, "seal.json"):
                raise ArtifactPreconditionFailedError("submission source completion already decided")
            descriptor = os.open("bundle.zip", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                info = self.verify(descriptor, completion)
                if stat.S_IMODE(info.st_mode) != 0o600:
                    raise ArtifactIntegrityError("submission source seal state is invalid")
                self.deadline(upload.intent)
                self.publish(directory, "seal.json", {
                    "completion": completion.model_dump(mode="json"),
                    "source": self.source(completion, info).model_dump(mode="json"),
                })
                os.fchmod(descriptor, 0o400)
                os.fsync(descriptor)
                return self.source(completion, info)
            finally:
                os.close(descriptor)

    def observe(self, completion: SubmissionSourceCompletion) -> SealedSubmissionSource | None:
        completion = SubmissionSourceCompletion.model_validate(completion)
        try:
            with self.locked(completion.upload.intent.location) as directory:
                self.upload(directory, completion.upload)
                if self.exists(directory, "aborted.json") or not self.exists(directory, "seal.json"):
                    return None
                stored, sealed = self.seal(directory)
                if stored != completion:
                    raise ArtifactOperationConflictError("submission source completion mismatch")
                descriptor = os.open("bundle.zip", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    info = self.verify(descriptor, completion)
                    if stat.S_IMODE(info.st_mode) != 0o400:
                        return None
                    if self.source(completion, info) != sealed:
                        raise ArtifactIntegrityError("submission source generation mismatch")
                    return sealed
                finally:
                    os.close(descriptor)
        except FileNotFoundError:
            return None

    def discover(self, intent: SubmissionSourceUploadIntent) -> tuple[SubmissionSourceUpload, ...]:
        intent = SubmissionSourceUploadIntent.model_validate(intent)
        try:
            with self.locked(intent.location) as directory:
                upload = SubmissionSourceUpload.model_validate_json(self.read(directory, "upload.json"))
                if upload.intent != intent:
                    raise ArtifactOperationConflictError("submission upload intent mismatch")
                if self.exists(directory, "aborted.json"):
                    return ()
                if self.exists(directory, "seal.json"):
                    completion, sealed = self.seal(directory)
                    descriptor = os.open("bundle.zip", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        info = self.store._assert_private_regular(descriptor)
                        if completion.upload != upload or self.source(completion, info) != sealed:
                            raise ArtifactIntegrityError("submission source generation mismatch")
                        if stat.S_IMODE(info.st_mode) == 0o400:
                            return ()
                    finally:
                        os.close(descriptor)
                return (upload,)
        except FileNotFoundError:
            return ()

    def abort(self, upload: SubmissionSourceUpload) -> None:
        upload = SubmissionSourceUpload.model_validate(upload)
        try:
            with self.locked(upload.intent.location) as directory:
                self.upload(directory, upload)
                if self.exists(directory, "seal.json"):
                    info = os.stat("bundle.zip", dir_fd=directory, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o400:
                        return  # A late abort never invalidates completed retained bytes.
                if not self.exists(directory, "aborted.json"):
                    self.publish(directory, "aborted.json", {"provider_upload_id": upload.provider_upload_id})
        except FileNotFoundError:
            return

    def seal(self, directory: int) -> tuple[SubmissionSourceCompletion, SealedSubmissionSource]:
        value = json.loads(self.read(directory, "seal.json"))
        if not isinstance(value, dict) or set(value) != {"completion", "source"}:
            raise ArtifactIntegrityError("submission source seal is invalid")
        return (
            SubmissionSourceCompletion.model_validate_json(json.dumps(value["completion"])),
            SealedSubmissionSource.model_validate_json(json.dumps(value["source"])),
        )

    def chunk(self, source: SealedSubmissionSource, position: int, maximum_chunk_bytes: int) -> bytes:
        source = SealedSubmissionSource.model_validate(source)
        with self.locked(source.location) as directory:
            completion, sealed = self.seal(directory)
            self.upload(directory, completion.upload)
            if self.exists(directory, "aborted.json"):
                raise ArtifactIntegrityError("submission source was aborted")
            descriptor = os.open("bundle.zip", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                info = self.store._assert_private_regular(descriptor)
                if (sealed != source or self.source(completion, info) != source or info.st_size != source.raw_byte_count
                        or stat.S_IMODE(info.st_mode) != 0o400):
                    raise ArtifactIntegrityError("submission source generation mismatch")
                return os.pread(descriptor, min(self.store._buffer_bytes, maximum_chunk_bytes, source.raw_byte_count - position), position)
            finally:
                os.close(descriptor)

    def validate_layout(self, objects_fd: int) -> None:
        """Check path grammar and inode safety without racing multi-file state."""
        source_fd = self.store._open_existing_directory(objects_fd, "submission-source")
        try:
            entries = set(os.listdir(source_fd))
            if not entries.issubset({"v1"}):
                raise ArtifactIntegrityError("submission source layout is invalid")
            if "v1" not in entries:
                return
            version_fd = self.store._open_existing_directory(source_fd, "v1")
            try:
                for name in os.listdir(version_fd):
                    try:
                        operation = UUID(name)
                    except ValueError:
                        raise ArtifactIntegrityError("submission source operation path is invalid") from None
                    if operation.version != 7 or str(operation) != name:
                        raise ArtifactIntegrityError("submission source operation path is invalid")
                    directory = self.store._open_existing_directory(version_fd, name)
                    try:
                        files = os.listdir(directory)
                        if len(files) > 16:
                            raise ArtifactIntegrityError("submission source metadata exceeds bound")
                        for filename in files:
                            if filename not in _FILES and _TEMP.fullmatch(filename) is None:
                                raise ArtifactIntegrityError("submission source file path is invalid")
                            details = self.store._stat_layout_file(directory, filename, recoverable=False)
                            if details is None:  # Metadata publication may remove a temporary.
                                continue
                            if (stat.S_IMODE(details.st_mode) not in {0o400, 0o600}
                                    or (filename != "bundle.zip" and details.st_size > _METADATA_LIMIT)):
                                raise ArtifactIntegrityError("submission source file is unsafe")
                    finally:
                        os.close(directory)
            finally:
                os.close(version_fd)
        finally:
            os.close(source_fd)
