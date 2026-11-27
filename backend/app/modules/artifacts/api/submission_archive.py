"""Canonical structural ZIP contracts shared by ART and trusted intake."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import unicodedata


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

    def canonical_body(self) -> dict[str, int | float]:
        """Serialize all bounds with the existing invocation-wire field names."""
        return {
            "maximum_entries": self.maximum_entries,
            "maximum_path_bytes": self.maximum_path_bytes,
            "maximum_path_depth": self.maximum_path_depth,
            "maximum_central_directory_bytes": self.maximum_central_directory_bytes,
            "maximum_entry_bytes": self.maximum_entry_bytes,
            "maximum_expanded_bytes": self.maximum_expanded_bytes,
            "maximum_compression_ratio": self.maximum_compression_ratio,
            "maximum_inspection_seconds": float(self.maximum_inspection_seconds),
        }


def normalize_submission_archive_path(
    path: str, *, maximum_path_bytes: int, maximum_path_depth: int,
) -> str:
    """Apply the same path rules to inspected and recovered manifest entries."""
    parts = path.split("/")
    normalized = unicodedata.normalize("NFC", path)
    if (
        not path or "\\" in path or path.startswith("/")
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts)
        or ":" in parts[0] or len(parts) > maximum_path_depth
        or max(len(path.encode("utf-8")), len(normalized.encode("utf-8"))) > maximum_path_bytes
    ):
        raise SubmissionArchiveRejectedError(SubmissionArchiveFailureCode.UNSAFE_ENTRY)
    return normalized


def validate_submission_archive_inventory(entries: tuple[SubmissionArchiveEntry, ...]) -> None:
    """Require one unambiguous path per entry and exact directory ancestry."""
    kinds = {entry.normalized_path: entry.entry_type for entry in entries}
    folded_paths: set[str] = set()
    for entry in entries:
        folded = unicodedata.normalize("NFC", entry.normalized_path).casefold()
        if folded in folded_paths:
            raise SubmissionArchiveRejectedError(SubmissionArchiveFailureCode.COLLISION)
        folded_paths.add(folded)
        parts = entry.normalized_path.split("/")
        for depth in range(1, len(parts)):
            if kinds.get("/".join(parts[:depth])) is not SubmissionArchiveEntryType.DIRECTORY:
                raise SubmissionArchiveRejectedError(SubmissionArchiveFailureCode.COLLISION)
