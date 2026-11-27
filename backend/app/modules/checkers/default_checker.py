"""Unselected implementation of the one Workstream default checker."""

from __future__ import annotations

import hashlib
import re
from typing import cast

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WORKSTREAM_DEFAULT_SECRET_SIGNATURES,
    WorkstreamDefaultArchiveFailureCode,
    WorkstreamDefaultCheck,
    WorkstreamDefaultCheckId,
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultCheckerResult,
    WorkstreamDefaultFailureCode,
    WorkstreamDefaultWarning,
)
from app.modules.checkers.api.materialization import (
    SubmissionMaterialEntry,
    SubmissionMaterialView,
)
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView


_CONTRIBUTOR_ARCHIVE_FAILURES = frozenset(
    {
        "submission_archive_malformed",
        "submission_archive_limit_exceeded",
        "submission_archive_unsafe_entry",
        "submission_archive_collision",
        "submission_archive_encrypted",
    }
)
_SECRET_SIGNATURES = tuple(
    re.compile(pattern.encode("ascii"), flags)
    for _, pattern, flags in WORKSTREAM_DEFAULT_SECRET_SIGNATURES
)


class WorkstreamDefaultCheckerUnavailable(RuntimeError):
    """Fail closed without attributing an infrastructure defect to the contributor."""


def evaluate_rejected_archive(
    failure: WorkstreamDefaultArchiveFailureCode,
    *,
    packet: SubmissionPacketView,
) -> WorkstreamDefaultCheckerResult:
    """Return one bounded work finding for a contributor-correctable unsafe ZIP."""
    if failure not in _CONTRIBUTOR_ARCHIVE_FAILURES:
        raise WorkstreamDefaultCheckerUnavailable(str(failure))
    return _result(
        checks=(
            _failed("archive_safe", cast(WorkstreamDefaultFailureCode, failure)),
            _not_run("received_identity_exact"),
            _not_run("high_confidence_secrets_absent"),
            _not_run("submission_changed_for_current_rules"),
        ),
        warnings=_warnings(packet),
    )


def evaluate_verified_archive(
    value: WorkstreamDefaultCheckerInput,
    material: SubmissionMaterialView,
) -> WorkstreamDefaultCheckerResult:
    """Evaluate all four defaults during one callback-scoped verified-byte lifetime."""
    try:
        manifest_entries = _validated_entries(value.entries)
        observed_entries = _validated_entries(material.entries)
        if observed_entries != manifest_entries:
            raise WorkstreamDefaultCheckerUnavailable(
                "submission_material_identity_invalid"
            )
        if canonical_json_hash(_manifest_body(manifest_entries)) != (
            value.semantic_manifest_sha256
        ):
            raise WorkstreamDefaultCheckerUnavailable(
                "submission_manifest_identity_invalid"
            )
        secret_file_count = _verify_files_and_count_secrets(material, manifest_entries)
        change_failure = _change_failure(value)
    except WorkstreamDefaultCheckerUnavailable:
        raise
    except Exception as exc:
        raise WorkstreamDefaultCheckerUnavailable(
            "workstream_default_checker_input_unavailable"
        ) from exc
    checks = (
        _passed("archive_safe"),
        _passed("received_identity_exact"),
        (
            _failed(
                "high_confidence_secrets_absent",
                "high_confidence_secret_detected",
                count=secret_file_count,
            )
            if secret_file_count
            else _passed("high_confidence_secrets_absent")
        ),
        (
            _failed("submission_changed_for_current_rules", change_failure)
            if change_failure is not None
            else _passed("submission_changed_for_current_rules")
        ),
    )
    return _result(checks=checks, warnings=_warnings(value.packet))


def _validated_entries(
    values: tuple[object, ...],
) -> tuple[SubmissionMaterialEntry, ...]:
    """Detach and validate the exact canonical entry projection."""
    entries = tuple(
        SubmissionMaterialEntry(
            normalized_path=getattr(item, "normalized_path"),
            entry_type=cast(str, getattr(item, "entry_type")),
            byte_count=getattr(item, "byte_count"),
            sha256=getattr(item, "sha256"),
            executable=getattr(item, "executable"),
        )
        for item in values
    )
    if tuple(sorted(entries, key=lambda item: item.normalized_path)) != entries:
        raise ValueError("default checker entries are not canonical")
    if len({item.normalized_path for item in entries}) != len(entries):
        raise ValueError("default checker entries are duplicated")
    for item in entries:
        if type(item.normalized_path) is not str or not item.normalized_path:
            raise ValueError("default checker entry path is invalid")
        if item.entry_type == "directory":
            if item.byte_count != 0 or item.sha256 is not None or item.executable is not None:
                raise ValueError("default checker directory entry is invalid")
            continue
        if (
            item.entry_type != "file"
            or type(item.byte_count) is not int
            or item.byte_count < 0
            or type(item.executable) is not bool
            or not _is_sha256(item.sha256)
        ):
            raise ValueError("default checker file entry is invalid")
    return entries


def _manifest_body(entries: tuple[SubmissionMaterialEntry, ...]) -> dict[str, object]:
    """Recompute the canonical ART semantic-manifest body from detached facts."""
    body_entries: list[dict[str, object]] = []
    for entry in entries:
        if entry.entry_type == "directory":
            body_entries.append(
                {"normalized_path": entry.normalized_path, "entry_type": "directory"}
            )
        else:
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
        "schema_version": "workstream.submission_bundle_manifest.v1",
        "entries": body_entries,
    }


def _change_failure(
    value: WorkstreamDefaultCheckerInput,
) -> WorkstreamDefaultFailureCode | None:
    """Apply unchanged-work refusal only when the canonical task rules are unchanged."""
    predecessor = value.predecessor
    if predecessor is None:
        if value.predecessor_exists or value.current_predecessor is not None:
            raise WorkstreamDefaultCheckerUnavailable(
                "submission_canonical_predecessor_unavailable"
            )
        return None
    if not value.predecessor_exists:
        raise WorkstreamDefaultCheckerUnavailable(
            "submission_canonical_predecessor_unavailable"
        )
    if value.current_predecessor != predecessor:
        raise WorkstreamDefaultCheckerUnavailable("submission_predecessor_stale")
    if value.predecessor_rules_sha256 != value.current_rules_sha256:
        return None
    if value.archive_sha256 == predecessor.archive_sha256:
        return "submission_archive_unchanged"
    if value.semantic_manifest_sha256 == predecessor.semantic_manifest_sha256:
        return "submission_manifest_unchanged"
    return None


def _verify_files_and_count_secrets(
    material: SubmissionMaterialView,
    entries: tuple[SubmissionMaterialEntry, ...],
) -> int:
    """Verify every file again and count matches without retaining matched bytes."""
    affected = 0
    for entry in entries:
        if entry.entry_type != "file":
            continue
        content = material.read_file(
            entry.normalized_path, maximum_bytes=entry.byte_count
        )
        if (
            len(content) != entry.byte_count
            or f"sha256:{hashlib.sha256(content).hexdigest()}" != entry.sha256
        ):
            raise WorkstreamDefaultCheckerUnavailable(
                "submission_material_identity_invalid"
            )
        if any(pattern.search(content) is not None for pattern in _SECRET_SIGNATURES):
            affected += 1
    return affected


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _warnings(packet: SubmissionPacketView) -> tuple[WorkstreamDefaultWarning, ...]:
    """Return stable warning-only absence signals in canonical order."""
    if packet.summary is None or packet.contributor_attestation is None:
        return ()
    values = []
    if not packet.summary.strip():
        values.append(WorkstreamDefaultWarning(code="submission_summary_missing"))
    if not packet.contributor_attestation.strip():
        values.append(WorkstreamDefaultWarning(code="submission_attestation_missing"))
    return tuple(values)


def _passed(check_id: WorkstreamDefaultCheckId) -> WorkstreamDefaultCheck:
    return WorkstreamDefaultCheck(
        check_id=check_id, status="passed", failure_code=None, finding_count=0
    )


def _not_run(check_id: WorkstreamDefaultCheckId) -> WorkstreamDefaultCheck:
    return WorkstreamDefaultCheck(
        check_id=check_id, status="not_run", failure_code=None, finding_count=0
    )


def _failed(
    check_id: WorkstreamDefaultCheckId,
    failure_code: WorkstreamDefaultFailureCode,
    *,
    count: int = 1,
) -> WorkstreamDefaultCheck:
    return WorkstreamDefaultCheck(
        check_id=check_id,
        status="failed",
        failure_code=failure_code,
        finding_count=count,
    )


def _result(
    *,
    checks: tuple[WorkstreamDefaultCheck, ...],
    warnings: tuple[WorkstreamDefaultWarning, ...],
) -> WorkstreamDefaultCheckerResult:
    return WorkstreamDefaultCheckerResult(
        behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        eligible=all(item.status == "passed" for item in checks),
        checks=checks,
        warnings=warnings,
    )


__all__ = (
    "WorkstreamDefaultCheckerUnavailable",
    "evaluate_rejected_archive",
    "evaluate_verified_archive",
)
