"""Bounded structural inspection of one contributor outer ZIP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import math
from pathlib import PurePosixPath
import stat
import struct
import time
from typing import BinaryIO
import unicodedata
import zipfile
import zlib

from app.modules.artifacts.zip_safety import zip_directory_layout


_READ_BYTES = 1024 * 1024


class SubmissionArchiveFailureCode(StrEnum):
    """Stable, non-sensitive outer-ZIP rejection categories."""

    MALFORMED = "submission_archive_malformed"
    LIMIT_EXCEEDED = "submission_archive_limit_exceeded"
    UNSAFE_ENTRY = "submission_archive_unsafe_entry"
    COLLISION = "submission_archive_collision"
    ENCRYPTED = "submission_archive_encrypted"
    INTEGRITY_FAILURE = "submission_archive_integrity_failure"
    TIMEOUT = "submission_archive_timeout"


class SubmissionArchiveRejectedError(ValueError):
    """Reject an archive without exposing attacker-controlled metadata."""

    def __init__(self, code: SubmissionArchiveFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


class SubmissionArchiveEntryType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True, slots=True)
class SubmissionArchiveEntry:
    """One normalized structural entry; no scratch or ZIP handles escape."""

    normalized_path: str
    entry_type: SubmissionArchiveEntryType
    byte_count: int
    sha256: str | None
    executable: bool | None


@dataclass(frozen=True, slots=True)
class SubmissionArchiveInspectionResult:
    """Non-durable structural facts for the later semantic-manifest chunk."""

    entries: tuple[SubmissionArchiveEntry, ...]
    entry_count: int
    file_count: int
    directory_count: int
    total_expanded_bytes: int


@dataclass(frozen=True, slots=True)
class SubmissionArchiveLimits:
    """Startup-fixed limits for one outer ZIP inspection."""

    maximum_entries: int = 2_000
    maximum_path_bytes: int = 1024
    maximum_path_depth: int = 32
    maximum_central_directory_bytes: int = 8 * 1024 * 1024
    maximum_entry_bytes: int = 128 * 1024 * 1024
    maximum_expanded_bytes: int = 512 * 1024 * 1024
    maximum_compression_ratio: int = 100
    maximum_inspection_seconds: float = 300.0

    def __post_init__(self) -> None:
        integers = (
            self.maximum_entries,
            self.maximum_path_bytes,
            self.maximum_path_depth,
            self.maximum_central_directory_bytes,
            self.maximum_entry_bytes,
            self.maximum_expanded_bytes,
            self.maximum_compression_ratio,
        )
        if any(type(value) is not int or value <= 0 for value in integers):
            raise ValueError("submission archive limits are invalid")
        if self.maximum_entries > 100_000 or self.maximum_path_depth > 256:
            raise ValueError("submission archive inventory limits are invalid")
        if self.maximum_expanded_bytes > 512 * 1024 * 1024:
            raise ValueError("submission archive expansion exceeds 512 MiB")
        if self.maximum_entry_bytes > self.maximum_expanded_bytes:
            raise ValueError("submission archive entry limit exceeds total limit")
        if not isinstance(self.maximum_inspection_seconds, (int, float)) or isinstance(
            self.maximum_inspection_seconds, bool
        ) or not math.isfinite(self.maximum_inspection_seconds) or self.maximum_inspection_seconds <= 0:
            raise ValueError("submission archive deadline is invalid")


class SubmissionArchiveInspector:
    """Fully read one outer ZIP and return only bounded structural facts."""

    def __init__(self, limits: SubmissionArchiveLimits) -> None:
        self._limits = limits

    def inspect(self, reader: BinaryIO) -> SubmissionArchiveInspectionResult:
        started = time.monotonic()
        try:
            reader.seek(0)
            if reader.read(4) not in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x06\x06"}:
                self._reject(SubmissionArchiveFailureCode.MALFORMED)
            layout = zip_directory_layout(reader, allow_zip64=True)
            if (
                layout.entry_count > self._limits.maximum_entries
                or layout.directory_bytes > self._limits.maximum_central_directory_bytes
            ):
                self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
            reader.seek(0)
            with zipfile.ZipFile(reader, allowZip64=True) as archive:
                infos = archive.infolist()
                if len(infos) != layout.entry_count:
                    self._reject(SubmissionArchiveFailureCode.MALFORMED)
                self._validate_record_coverage(
                    archive, infos, directory_offset=layout.directory_offset
                )
                entries = self._read_entries(archive, infos, started=started)
        except SubmissionArchiveRejectedError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
            self._reject(SubmissionArchiveFailureCode.MALFORMED)
        files = sum(entry.entry_type is SubmissionArchiveEntryType.FILE for entry in entries)
        directories = len(entries) - files
        total = sum(entry.byte_count for entry in entries)
        return SubmissionArchiveInspectionResult(
            entries=tuple(sorted(entries, key=lambda entry: entry.normalized_path)),
            entry_count=len(entries),
            file_count=files,
            directory_count=directories,
            total_expanded_bytes=total,
        )

    def _read_entries(
        self, archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], *, started: float
    ) -> list[SubmissionArchiveEntry]:
        results: list[SubmissionArchiveEntry] = []
        paths: dict[str, SubmissionArchiveEntryType] = {}
        source_paths: set[str] = set()
        total = 0
        for info in infos:
            self._check_deadline(started)
            path, entry_type = self._validated_path(info)
            folded = unicodedata.normalize("NFC", path).casefold()
            if folded in source_paths or (
                folded in paths and entry_type is SubmissionArchiveEntryType.FILE
            ):
                self._reject(SubmissionArchiveFailureCode.COLLISION)
            parts = PurePosixPath(path).parts
            for index in range(1, len(parts)):
                ancestor = unicodedata.normalize("NFC", "/".join(parts[:index])).casefold()
                if paths.get(ancestor) is SubmissionArchiveEntryType.FILE:
                    self._reject(SubmissionArchiveFailureCode.COLLISION)
                if ancestor not in paths:
                    implicit_path = "/".join(parts[:index])
                    paths[ancestor] = SubmissionArchiveEntryType.DIRECTORY
                    results.append(
                        SubmissionArchiveEntry(
                            implicit_path,
                            SubmissionArchiveEntryType.DIRECTORY,
                            0,
                            None,
                            None,
                        )
                    )
                    if len(paths) > self._limits.maximum_entries:
                        self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
            if entry_type is SubmissionArchiveEntryType.FILE:
                prefix = folded + "/"
                if any(existing.startswith(prefix) for existing in paths):
                    self._reject(SubmissionArchiveFailureCode.COLLISION)
            paths[folded] = entry_type
            source_paths.add(folded)
            if entry_type is SubmissionArchiveEntryType.DIRECTORY and any(
                entry.normalized_path == path for entry in results
            ):
                continue
            actual, digest = (
                self._read_member(
                    archive,
                    info,
                    started=started,
                    remaining_expanded_bytes=self._limits.maximum_expanded_bytes - total,
                )
                if entry_type is SubmissionArchiveEntryType.FILE
                else (0, None)
            )
            total += actual
            if total > self._limits.maximum_expanded_bytes:
                self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
            results.append(
                SubmissionArchiveEntry(
                    path,
                    entry_type,
                    actual,
                    digest,
                    self._normalized_executable(info) if digest is not None else None,
                )
            )
        return results

    def _validated_path(
        self, info: zipfile.ZipInfo
    ) -> tuple[str, SubmissionArchiveEntryType]:
        raw = info.filename
        if (
            not raw
            or "\\" in raw
            or "\x00" in raw
            or raw.startswith("/")
            or any(ord(character) < 32 or ord(character) == 127 for character in raw)
        ):
            self._reject(SubmissionArchiveFailureCode.UNSAFE_ENTRY)
        is_directory = info.is_dir()
        if is_directory and (info.file_size != 0 or info.compress_size != 0):
            self._reject(SubmissionArchiveFailureCode.UNSAFE_ENTRY)
        path = raw[:-1] if is_directory and raw.endswith("/") else raw
        raw_parts = path.split("/")
        pure = PurePosixPath(path)
        parts = pure.parts
        if (
            not parts
            or any(
                part in {"", ".", ".."} or part.endswith((" ", "."))
                for part in raw_parts
            )
            or ":" in parts[0]
            or len(parts) > self._limits.maximum_path_depth
            or len(path.encode("utf-8")) > self._limits.maximum_path_bytes
        ):
            self._reject(SubmissionArchiveFailureCode.UNSAFE_ENTRY)
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
            self._reject(SubmissionArchiveFailureCode.UNSAFE_ENTRY)
        if (kind == stat.S_IFDIR) != is_directory and kind != 0:
            self._reject(SubmissionArchiveFailureCode.UNSAFE_ENTRY)
        if info.flag_bits & 0x1:
            self._reject(SubmissionArchiveFailureCode.ENCRYPTED)
        return unicodedata.normalize("NFC", path), (
            SubmissionArchiveEntryType.DIRECTORY
            if is_directory
            else SubmissionArchiveEntryType.FILE
        )

    def _read_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        *,
        started: float,
        remaining_expanded_bytes: int,
    ) -> tuple[int, str]:
        maximum_output = min(
            self._limits.maximum_entry_bytes, remaining_expanded_bytes
        )
        if info.file_size > maximum_output:
            self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
        if info.file_size and (
            info.compress_size == 0
            or info.file_size > info.compress_size * self._limits.maximum_compression_ratio
        ):
            self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
        self._validate_compressed_stream(
            archive, info, started=started, maximum_output_bytes=maximum_output
        )
        actual = 0
        digest = hashlib.sha256()
        try:
            with archive.open(info, "r") as member:
                while chunk := member.read(_READ_BYTES):
                    self._check_deadline(started)
                    actual += len(chunk)
                    digest.update(chunk)
                    if actual > maximum_output:
                        self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
        except (EOFError, OSError, RuntimeError, zipfile.BadZipFile):
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        if actual != info.file_size:
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        return actual, f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _normalized_executable(info: zipfile.ZipInfo) -> bool:
        """Collapse valid Unix execute intent without preserving permissions."""
        if info.create_system != 3:
            return False
        mode = info.external_attr >> 16
        return bool(mode & 0o111)

    def _validate_record_coverage(
        self,
        archive: zipfile.ZipFile,
        infos: list[zipfile.ZipInfo],
        *,
        directory_offset: int,
    ) -> None:
        """Prove local records cover every byte before the central directory."""
        expected_offset = 0
        for info in sorted(infos, key=lambda item: item.header_offset):
            if info.header_offset != expected_offset:
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            expected_offset = self._validate_local_record(archive, info)
        if expected_offset != directory_offset:
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)

    def _validate_local_record(self, archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> int:
        """Bind central facts to one exact local record and return its end."""
        source = archive.fp
        if source is None:
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        prior = source.tell()
        try:
            source.seek(info.header_offset)
            header = source.read(30)
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            flags, compression = struct.unpack_from("<HH", header, 6)
            crc, compressed, expanded = struct.unpack_from("<III", header, 14)
            name_bytes, extra_bytes = struct.unpack_from("<HH", header, 26)
            if flags != info.flag_bits or compression != info.compress_type:
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            local_name_bytes = source.read(name_bytes)
            if len(local_name_bytes) != name_bytes:
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            encoding = "utf-8" if flags & 0x800 else "cp437"
            try:
                local_name = local_name_bytes.decode(encoding)
            except UnicodeDecodeError:
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            if local_name != info.orig_filename:
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            source.seek(extra_bytes, 1)
            payload_end = source.tell() + info.compress_size
            if flags & 0x08:
                source.seek(payload_end)
                descriptor = source.read(24)
                offset = 4 if descriptor.startswith(b"PK\x07\x08") else 0
                if len(descriptor) < offset + 12:
                    self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
                descriptor_crc = int.from_bytes(descriptor[offset : offset + 4], "little")
                if info.file_size > 0xFFFFFFFF or info.compress_size > 0xFFFFFFFF:
                    if len(descriptor) < offset + 20:
                        self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
                    descriptor_compressed, descriptor_expanded = struct.unpack_from(
                        "<QQ", descriptor, offset + 4
                    )
                else:
                    descriptor_compressed, descriptor_expanded = struct.unpack_from(
                        "<II", descriptor, offset + 4
                    )
                if (
                    descriptor_crc != info.CRC
                    or descriptor_compressed != info.compress_size
                    or descriptor_expanded != info.file_size
                ):
                    self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
                return payload_end + offset + (
                    20
                    if info.file_size > 0xFFFFFFFF or info.compress_size > 0xFFFFFFFF
                    else 12
                )
            elif (
                crc != info.CRC
                or compressed not in {info.compress_size, 0xFFFFFFFF}
                or expanded not in {info.file_size, 0xFFFFFFFF}
            ):
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            return payload_end
        except (OSError, struct.error):
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        finally:
            source.seek(prior)

    def _validate_compressed_stream(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        *,
        started: float,
        maximum_output_bytes: int,
    ) -> None:
        """Consume the exact compressed range without accepting trailing payload."""
        if info.compress_type == zipfile.ZIP_STORED:
            if info.compress_size != info.file_size:
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
            return
        if info.compress_type != zipfile.ZIP_DEFLATED:
            self._reject(SubmissionArchiveFailureCode.MALFORMED)
        source = archive.fp
        if source is None:
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        prior = source.tell()
        actual = 0
        try:
            source.seek(info.header_offset)
            header = source.read(30)
            name_bytes, extra_bytes = struct.unpack_from("<HH", header, 26)
            source.seek(name_bytes + extra_bytes, 1)
            remaining = info.compress_size
            decompressor = zlib.decompressobj(-15)
            while remaining:
                self._check_deadline(started)
                chunk = source.read(min(_READ_BYTES, remaining))
                if not chunk:
                    self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
                remaining -= len(chunk)
                pending = chunk
                while pending:
                    output = decompressor.decompress(
                        pending,
                        min(_READ_BYTES, maximum_output_bytes - actual + 1),
                    )
                    actual += len(output)
                    if actual > maximum_output_bytes:
                        self._reject(SubmissionArchiveFailureCode.LIMIT_EXCEEDED)
                    pending = decompressor.unconsumed_tail
            actual += len(decompressor.flush())
            if (
                not decompressor.eof
                or decompressor.unused_data
                or decompressor.unconsumed_tail
                or actual != info.file_size
            ):
                self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        except (OSError, struct.error, zlib.error):
            self._reject(SubmissionArchiveFailureCode.INTEGRITY_FAILURE)
        finally:
            source.seek(prior)

    def _check_deadline(self, started: float) -> None:
        if time.monotonic() - started > self._limits.maximum_inspection_seconds:
            self._reject(SubmissionArchiveFailureCode.TIMEOUT)

    @staticmethod
    def _reject(code: SubmissionArchiveFailureCode) -> None:
        raise SubmissionArchiveRejectedError(code)
