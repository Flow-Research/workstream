"""Canonical semantic identity and unchanged-work gate for submission ZIPs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.hashing import validate_sha256
from app.modules.artifacts.api.submission_manifest import SubmissionManifest
from app.modules.artifacts.sources import ArtifactCommitment


def semantic_manifest_identity(semantic_manifest_sha256: str) -> UUID:
    """Derive one provider-neutral identity from the canonical manifest digest."""
    validate_sha256(semantic_manifest_sha256)
    return uuid5(
        NAMESPACE_URL,
        f"workstream:submission-semantic-manifest:v1:{semantic_manifest_sha256}",
    )


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
    UNCHANGED = "unchanged"


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
        validate_sha256(self.archive_sha256)
        validate_sha256(self.semantic_manifest_sha256)


@dataclass(frozen=True, slots=True)
class SubmissionChangeGateResult:
    """One successful comparison bound to its nullable predecessor selector."""

    archive_sha256: str
    archive_byte_count: int
    manifest: SubmissionManifest
    outcome: SubmissionChangeOutcome
    predecessor: SubmissionCanonicalPredecessor | None


def evaluate_submission_change(
    *,
    commitment: ArtifactCommitment,
    manifest: SubmissionManifest,
    predecessor: SubmissionCanonicalPredecessor | None,
    predecessor_exists: bool,
    current_predecessor: SubmissionCanonicalPredecessor | None = None,
) -> SubmissionChangeGateResult:
    """Compare server-owned identities without performing any durable effect."""
    result = bind_submission_change(
        commitment=commitment,
        manifest=manifest,
        predecessor=predecessor,
        predecessor_exists=predecessor_exists,
        current_predecessor=current_predecessor,
    )
    if result.outcome is SubmissionChangeOutcome.UNCHANGED:
        assert predecessor is not None
        code = (
            SubmissionChangeFailureCode.ARCHIVE_UNCHANGED
            if commitment.sha256 == predecessor.archive_sha256
            else SubmissionChangeFailureCode.MANIFEST_UNCHANGED
        )
        raise SubmissionChangeRejectedError(code)
    return result


def bind_submission_change(
    *,
    commitment: ArtifactCommitment,
    manifest: SubmissionManifest,
    predecessor: SubmissionCanonicalPredecessor | None,
    predecessor_exists: bool,
    current_predecessor: SubmissionCanonicalPredecessor | None = None,
) -> SubmissionChangeGateResult:
    """Bind exact predecessor and byte facts without deciding the default check."""
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
    unchanged = (
        commitment.sha256 == predecessor.archive_sha256
        or manifest.sha256 == predecessor.semantic_manifest_sha256
    )
    return SubmissionChangeGateResult(
        commitment.sha256,
        commitment.byte_count,
        manifest,
        (
            SubmissionChangeOutcome.UNCHANGED
            if unchanged
            else SubmissionChangeOutcome.CHANGED
        ),
        predecessor,
    )
