"""Canonical manifest facts and validation shared with trusted intake."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.hashing import canonical_json_hash, validate_sha256
from app.modules.artifacts.api.submission_admission import SubmissionBundleFile
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveEntry, SubmissionArchiveEntryType,
    SubmissionArchiveInspectionResult, SubmissionArchiveLimits,
    normalize_submission_archive_path, validate_submission_archive_inventory,
)

SUBMISSION_MANIFEST_SCHEMA_VERSION = "workstream.submission_bundle_manifest.v1"


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
                validate_sha256(entry.sha256)
        validate_submission_archive_inventory(self.entries)
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
        validate_sha256(self.sha256)
        if canonical_json_hash(self.as_dict()) != self.sha256:
            raise ValueError("submission manifest digest is inconsistent")

    def file_facts(self) -> tuple[SubmissionBundleFile, ...]:
        """Project every verified file for both capacity preflight and consumption."""
        return tuple(SubmissionBundleFile(
            normalized_path=item.normalized_path, sha256=item.sha256, byte_count=item.byte_count,
        ) for item in self.entries if item.entry_type is SubmissionArchiveEntryType.FILE)

    @property
    def schema_version(self) -> str:
        """Return the fixed closed-schema version."""
        return SUBMISSION_MANIFEST_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible closed manifest body."""
        return _manifest_body(self.entries)

    @classmethod
    def from_dict(cls, body: object, *, sha256: str) -> SubmissionManifest:
        """Recover the sole canonical manifest, checking closed stored metadata."""
        if (
            type(body) is not dict
            or set(body) != {"schema_version", "entries"}
            or body["schema_version"] != SUBMISSION_MANIFEST_SCHEMA_VERSION
            or type(body["entries"]) is not list
            or len(body["entries"]) > 100_000
        ):
            raise ValueError("submission manifest body is invalid")
        entries = []
        paths = set()
        for value in body["entries"]:
            if type(value) is not dict:
                raise ValueError("submission manifest entry is invalid")
            kind = value.get("entry_type")
            fields = {"normalized_path", "entry_type"}
            if kind == "file":
                fields |= {"sha256", "byte_count", "executable"}
            elif kind != "directory":
                raise ValueError("submission manifest entry is invalid")
            path = value.get("normalized_path")
            if set(value) != fields or type(path) is not str or not path or path in paths:
                raise ValueError("submission manifest entry is invalid")
            if normalize_submission_archive_path(
                path, maximum_path_bytes=4096, maximum_path_depth=256,
            ) != path:
                raise ValueError("submission manifest path is not normalized")
            paths.add(path)
            size = value["byte_count"] if kind == "file" else 0
            if type(size) is not int or not 0 <= size <= 512 * 1024 * 1024:
                raise ValueError("submission manifest file size is invalid")
            entries.append(SubmissionArchiveEntry(
                normalized_path=path, entry_type=SubmissionArchiveEntryType(kind),
                byte_count=size, sha256=value.get("sha256"), executable=value.get("executable"),
            ))
        files = sum(entry.entry_type is SubmissionArchiveEntryType.FILE for entry in entries)
        expanded = sum(entry.byte_count for entry in entries)
        if expanded > 512 * 1024 * 1024:
            raise ValueError("submission manifest expansion is invalid")
        return cls(
            sha256=sha256, entries=tuple(entries), entry_count=len(entries),
            file_count=files, directory_count=len(entries) - files,
            total_expanded_bytes=expanded,
        )


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


def validate_submission_manifest(
    body: object, *, sha256: str, limits: SubmissionArchiveLimits,
) -> SubmissionArchiveInspectionResult:
    """Validate reported canonical metadata without claiming observation of bytes.

    Reuse ART's manifest semantics and the invocation's stricter resource limits.
    Source integrity still requires a trusted loader receipt.
    """

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
