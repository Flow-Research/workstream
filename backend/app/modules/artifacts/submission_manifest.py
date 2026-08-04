"""Canonical semantic identity and unchanged-work gate for submission ZIPs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveEntry,
    SubmissionArchiveEntryType,
    SubmissionArchiveInspectionResult,
)


SUBMISSION_MANIFEST_SCHEMA_VERSION = "workstream.submission_bundle_manifest.v1"


class SubmissionChangeFailureCode(StrEnum):
    """Stable side-effect-free semantic change-gate failures."""

    ARCHIVE_UNCHANGED = "submission_archive_unchanged"
    MANIFEST_UNCHANGED = "submission_manifest_unchanged"
    CANONICAL_PREDECESSOR_UNAVAILABLE = "submission_canonical_predecessor_unavailable"
    PREDECESSOR_STALE = "submission_predecessor_stale"


class SubmissionChangeRejectedError(ValueError):
    """Reject an unchanged or unprovable successor without leaking content."""

    def __init__(self, code: SubmissionChangeFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


class SubmissionChangeOutcome(StrEnum):
    """Successful process-local change-gate outcomes."""

    FIRST_SUBMISSION = "first_submission"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class SubmissionCanonicalPredecessor:
    """ART-owned immutable identities for one immediate Submission predecessor."""

    submission_id: UUID
    submission_version: int
    archive_sha256: str
    semantic_manifest_sha256: str

    def __post_init__(self) -> None:
        if type(self.submission_id) is not UUID:
            raise ValueError("submission predecessor id is invalid")
        if type(self.submission_version) is not int or self.submission_version <= 0:
            raise ValueError("submission predecessor version is invalid")
        ArtifactCommitment.validate_sha256(self.archive_sha256)
        ArtifactCommitment.validate_sha256(self.semantic_manifest_sha256)


@dataclass(frozen=True, slots=True)
class SubmissionManifest:
    """Closed canonical semantic manifest derived from inspected bytes."""

    sha256: str
    entries: tuple[SubmissionArchiveEntry, ...]
    entry_count: int
    file_count: int
    directory_count: int
    total_expanded_bytes: int

    def __post_init__(self) -> None:
        """Reject mutable, incomplete, or self-inconsistent manifest facts."""
        if type(self.entries) is not tuple or tuple(
            sorted(self.entries, key=lambda entry: entry.normalized_path)
        ) != self.entries:
            raise ValueError("submission manifest entries are not canonical")
        for entry in self.entries:
            if type(entry) is not SubmissionArchiveEntry:
                raise ValueError("submission manifest entry is invalid")
            if entry.entry_type is SubmissionArchiveEntryType.DIRECTORY:
                if entry.byte_count != 0 or entry.sha256 is not None or entry.executable is not None:
                    raise ValueError("submission directory identity is invalid")
            elif (
                entry.entry_type is not SubmissionArchiveEntryType.FILE
                or entry.byte_count < 0
                or type(entry.executable) is not bool
                or entry.sha256 is None
            ):
                raise ValueError("submission file identity is incomplete")
            else:
                ArtifactCommitment.validate_sha256(entry.sha256)
        files = sum(
            entry.entry_type is SubmissionArchiveEntryType.FILE for entry in self.entries
        )
        if (
            self.entry_count != len(self.entries)
            or self.file_count != files
            or self.directory_count != len(self.entries) - files
            or self.total_expanded_bytes
            != sum(entry.byte_count for entry in self.entries)
        ):
            raise ValueError("submission manifest aggregates are inconsistent")
        ArtifactCommitment.validate_sha256(self.sha256)
        if canonical_json_hash(self.as_dict()) != self.sha256:
            raise ValueError("submission manifest digest is inconsistent")

    @property
    def schema_version(self) -> str:
        """Return the fixed closed-schema version."""
        return SUBMISSION_MANIFEST_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible closed manifest body."""
        return _manifest_body(self.entries)


@dataclass(frozen=True, slots=True)
class SubmissionChangeGateResult:
    """One successful comparison bound to its nullable predecessor selector."""

    archive_sha256: str
    archive_byte_count: int
    manifest: SubmissionManifest
    outcome: SubmissionChangeOutcome
    predecessor: SubmissionCanonicalPredecessor | None


def build_submission_manifest(
    inspection: SubmissionArchiveInspectionResult,
) -> SubmissionManifest:
    """Build the sole canonical JSON identity from a validated archive read."""
    entries = tuple(sorted(inspection.entries, key=lambda entry: entry.normalized_path))
    for entry in entries:
        if entry.entry_type is SubmissionArchiveEntryType.FILE and (
            entry.sha256 is None or entry.executable is None
        ):
            raise ValueError("submission file identity is incomplete")
    body = _manifest_body(entries)
    return SubmissionManifest(
        sha256=canonical_json_hash(body),
        entries=entries,
        entry_count=inspection.entry_count,
        file_count=inspection.file_count,
        directory_count=inspection.directory_count,
        total_expanded_bytes=inspection.total_expanded_bytes,
    )


def _manifest_body(entries: tuple[SubmissionArchiveEntry, ...]) -> dict[str, Any]:
    """Project immutable entries into the one closed canonical JSON shape."""
    body_entries: list[dict[str, object]] = []
    for entry in entries:
        if entry.entry_type is SubmissionArchiveEntryType.DIRECTORY:
            body_entries.append(
                {"normalized_path": entry.normalized_path, "entry_type": "directory"}
            )
            continue
        body_entries.append(
            {
                "normalized_path": entry.normalized_path,
                "entry_type": "file",
                "sha256": entry.sha256,
                "byte_count": entry.byte_count,
                "executable": entry.executable,
            }
        )
    return {
        "schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION,
        "entries": body_entries,
    }


def evaluate_submission_change(
    *,
    commitment: ArtifactCommitment,
    manifest: SubmissionManifest,
    predecessor: SubmissionCanonicalPredecessor | None,
    predecessor_exists: bool,
    current_predecessor: SubmissionCanonicalPredecessor | None = None,
) -> SubmissionChangeGateResult:
    """Compare server-owned identities without performing any durable effect."""
    if predecessor is not None and not predecessor_exists:
        raise ValueError("submission predecessor existence is inconsistent")
    if predecessor is None:
        if predecessor_exists:
            raise SubmissionChangeRejectedError(
                SubmissionChangeFailureCode.CANONICAL_PREDECESSOR_UNAVAILABLE
            )
        return SubmissionChangeGateResult(
            commitment.sha256,
            commitment.byte_count,
            manifest,
            SubmissionChangeOutcome.FIRST_SUBMISSION,
            None,
        )
    if current_predecessor is None or current_predecessor != predecessor:
        raise SubmissionChangeRejectedError(SubmissionChangeFailureCode.PREDECESSOR_STALE)
    if commitment.sha256 == predecessor.archive_sha256:
        raise SubmissionChangeRejectedError(SubmissionChangeFailureCode.ARCHIVE_UNCHANGED)
    if manifest.sha256 == predecessor.semantic_manifest_sha256:
        raise SubmissionChangeRejectedError(SubmissionChangeFailureCode.MANIFEST_UNCHANGED)
    return SubmissionChangeGateResult(
        commitment.sha256,
        commitment.byte_count,
        manifest,
        SubmissionChangeOutcome.CHANGED,
        predecessor,
    )
