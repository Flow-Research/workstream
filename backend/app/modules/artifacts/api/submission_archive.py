"""Canonical structural ZIP contracts shared by ART and trusted intake."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


# Compressed intake ceiling; expanded content has its own inspection limit.
MAXIMUM_SUBMISSION_ZIP_BYTES = 500 * 1024 * 1024


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
        if (
            not isinstance(self.maximum_inspection_seconds, (int, float))
            or isinstance(self.maximum_inspection_seconds, bool)
            or not math.isfinite(self.maximum_inspection_seconds)
            or self.maximum_inspection_seconds <= 0
        ):
            raise ValueError("submission archive deadline is invalid")


def validate_submission_manifest(
    body: object, *, sha256: str, limits: SubmissionArchiveLimits,
) -> SubmissionArchiveInspectionResult:
    """Validate reported canonical metadata without claiming observation of bytes.

    Reuse ART's manifest semantics and the invocation's stricter resource limits.
    Source integrity still requires a trusted loader receipt.
    """
    from app.modules.artifacts.submission_manifest import SubmissionManifest
    from app.modules.artifacts.submission_archive import normalize_submission_archive_path

    manifest = SubmissionManifest.from_dict(body, sha256=sha256)
    if (manifest.entry_count > limits.maximum_entries
            or manifest.total_expanded_bytes > limits.maximum_expanded_bytes):
        raise ValueError("submission manifest exceeds execution limits")
    for entry in manifest.entries:
        if entry.byte_count > limits.maximum_entry_bytes:
            raise ValueError("submission manifest exceeds execution limits")
        normalize_submission_archive_path(
            entry.normalized_path, maximum_path_bytes=limits.maximum_path_bytes,
            maximum_path_depth=limits.maximum_path_depth,
        )
    return SubmissionArchiveInspectionResult(
        entries=manifest.entries, entry_count=manifest.entry_count,
        file_count=manifest.file_count, directory_count=manifest.directory_count,
        total_expanded_bytes=manifest.total_expanded_bytes,
    )
