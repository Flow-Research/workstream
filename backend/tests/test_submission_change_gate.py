from __future__ import annotations

from io import BytesIO
from uuid import uuid4
import zipfile

import pytest

from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    SubmissionChangeFailureCode,
    SubmissionChangeOutcome,
    SubmissionChangeRejectedError,
    build_submission_manifest,
    evaluate_submission_change,
)


def _manifest(content: bytes):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("work.txt", content)
    inspection = SubmissionArchiveInspector(SubmissionArchiveLimits()).inspect(
        BytesIO(output.getvalue())
    )
    return build_submission_manifest(inspection)


def _commitment(digit: str = "a", byte_count: int = 100) -> ArtifactCommitment:
    return ArtifactCommitment(f"sha256:{digit * 64}", byte_count, "application/zip")


def _predecessor(
    *, archive: str = "b", manifest: str = "c", version: int = 1
) -> SubmissionCanonicalPredecessor:
    return SubmissionCanonicalPredecessor(
        uuid4(), version, f"sha256:{archive * 64}", f"sha256:{manifest * 64}"
    )


def _rejects(code: SubmissionChangeFailureCode, **kwargs: object) -> None:
    with pytest.raises(SubmissionChangeRejectedError) as caught:
        evaluate_submission_change(**kwargs)  # type: ignore[arg-type]
    assert caught.value.code is code
    assert str(caught.value) == code.value


def test_first_submission_and_changed_success_bind_exact_selector() -> None:
    manifest = _manifest(b"candidate")
    first = evaluate_submission_change(
        commitment=_commitment(),
        manifest=manifest,
        predecessor=None,
        predecessor_exists=False,
    )
    predecessor = _predecessor()
    changed = evaluate_submission_change(
        commitment=_commitment(),
        manifest=manifest,
        predecessor=predecessor,
        predecessor_exists=True,
        current_predecessor=predecessor,
    )

    assert first.outcome is SubmissionChangeOutcome.FIRST_SUBMISSION
    assert first.predecessor is None
    assert changed.outcome is SubmissionChangeOutcome.CHANGED
    assert changed.predecessor is predecessor
    assert changed.archive_sha256 == _commitment().sha256


def test_existing_submission_without_canonical_identity_fails_closed() -> None:
    _rejects(
        SubmissionChangeFailureCode.CANONICAL_PREDECESSOR_UNAVAILABLE,
        commitment=_commitment(),
        manifest=_manifest(b"candidate"),
        predecessor=None,
        predecessor_exists=True,
    )


def test_predecessor_facts_cannot_claim_a_first_submission() -> None:
    with pytest.raises(ValueError, match="existence is inconsistent"):
        evaluate_submission_change(
            commitment=_commitment(),
            manifest=_manifest(b"candidate"),
            predecessor=_predecessor(),
            predecessor_exists=False,
        )


def test_exact_archive_and_semantically_unchanged_reject_distinctly() -> None:
    manifest = _manifest(b"candidate")
    exact_predecessor = _predecessor(archive="a")
    _rejects(
        SubmissionChangeFailureCode.ARCHIVE_UNCHANGED,
        commitment=_commitment(),
        manifest=manifest,
        predecessor=exact_predecessor,
        predecessor_exists=True,
        current_predecessor=exact_predecessor,
    )
    semantic_predecessor = SubmissionCanonicalPredecessor(
        uuid4(), 1, f"sha256:{'b' * 64}", manifest.sha256
    )
    _rejects(
        SubmissionChangeFailureCode.MANIFEST_UNCHANGED,
        commitment=_commitment(),
        manifest=manifest,
        predecessor=semantic_predecessor,
        predecessor_exists=True,
        current_predecessor=semantic_predecessor,
    )


def test_predecessor_advancement_rejects_stale_selector_before_comparison() -> None:
    _rejects(
        SubmissionChangeFailureCode.PREDECESSOR_STALE,
        commitment=_commitment(),
        manifest=_manifest(b"candidate"),
        predecessor=_predecessor(version=1),
        predecessor_exists=True,
        current_predecessor=_predecessor(version=2),
    )


def test_non_first_comparison_requires_locked_current_predecessor() -> None:
    _rejects(
        SubmissionChangeFailureCode.PREDECESSOR_STALE,
        commitment=_commitment(),
        manifest=_manifest(b"candidate"),
        predecessor=_predecessor(),
        predecessor_exists=True,
        current_predecessor=None,
    )
