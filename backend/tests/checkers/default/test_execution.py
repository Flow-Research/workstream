"""Behavior proof for the unselected Workstream default checker."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, cast
import zipfile

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveFailureCode,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.default_checker import (
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultPredecessor,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.default_checker import (
    WorkstreamDefaultCheckerUnavailable,
    evaluate_rejected_archive,
    evaluate_verified_archive,
)
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView


RULES_A = "sha256:" + "a" * 64
RULES_B = "sha256:" + "b" * 64


def _archive(files: dict[str, bytes], *, comment: bytes = b"") -> bytes:
    target = BytesIO()
    with zipfile.ZipFile(target, "w") as output:
        output.comment = comment
        for path, content in sorted(files.items()):
            entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            output.writestr(entry, content)
    return target.getvalue()


def _facts(value: bytes):
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    inspection = inspector.inspect(BytesIO(value))
    manifest = build_submission_manifest(inspection)
    commitment = ArtifactCommitment(
        "sha256:" + hashlib.sha256(value).hexdigest(), len(value), "application/zip"
    )
    return inspector, inspection, manifest, commitment


def _input(
    value: bytes,
    *,
    predecessor: WorkstreamDefaultPredecessor | None = None,
    current_predecessor: WorkstreamDefaultPredecessor | None = None,
    current_rules_sha256: str = RULES_A,
    predecessor_rules_sha256: str | None = None,
    summary: str = "Implemented the requested behavior.",
    attestation: str = "I confirm the submitted material is authorized.",
) -> WorkstreamDefaultCheckerInput:
    _, inspection, manifest, commitment = _facts(value)
    return WorkstreamDefaultCheckerInput(
        archive_sha256=commitment.sha256,
        archive_byte_count=commitment.byte_count,
        archive_media_type=commitment.media_type,
        semantic_manifest_sha256=manifest.sha256,
        entries=tuple(
            SubmissionMaterialEntry(
                item.normalized_path,
                item.entry_type.value,
                item.byte_count,
                item.sha256,
                item.executable,
            )
            for item in inspection.entries
        ),
        predecessor=predecessor,
        predecessor_exists=predecessor is not None,
        current_predecessor=current_predecessor,
        current_rules_sha256=current_rules_sha256,
        predecessor_rules_sha256=predecessor_rules_sha256,
        packet=SubmissionPacketView(
            summary=summary, contributor_attestation=attestation
        ),
    )


def _evaluate(value: bytes, request: WorkstreamDefaultCheckerInput, workspace: Path):
    inspector, inspection, _, _ = _facts(value)
    workspace.mkdir(mode=0o700)
    return inspector.project_and_run(
        BytesIO(value),
        workspace,
        expected=inspection,
        callback=lambda tree: evaluate_verified_archive(request, tree),
    )


def test_safe_first_submission_passes_exact_four_defaults(tmp_path: Path) -> None:
    archive = _archive({"src/main.txt": b"verified work"})
    result = _evaluate(archive, _input(archive), tmp_path / "work")

    assert result.eligible is True
    assert [item.status for item in result.checks] == ["passed"] * 4
    assert result.warnings == ()


@pytest.mark.parametrize(
    "failure",
    [
        SubmissionArchiveFailureCode.MALFORMED,
        SubmissionArchiveFailureCode.LIMIT_EXCEEDED,
        SubmissionArchiveFailureCode.UNSAFE_ENTRY,
        SubmissionArchiveFailureCode.COLLISION,
        SubmissionArchiveFailureCode.ENCRYPTED,
    ],
)
def test_contributor_archive_failures_return_one_bounded_finding(
    failure: SubmissionArchiveFailureCode,
) -> None:
    result = evaluate_rejected_archive(
        failure.value,
        packet=SubmissionPacketView(summary="", contributor_attestation=""),
    )

    assert result.eligible is False
    assert result.checks[0].failure_code == failure.value
    assert [item.status for item in result.checks] == [
        "failed",
        "not_run",
        "not_run",
        "not_run",
    ]
    assert [item.code for item in result.warnings] == [
        "submission_summary_missing",
        "submission_attestation_missing",
    ]


@pytest.mark.parametrize(
    "failure",
    [
        SubmissionArchiveFailureCode.INTEGRITY_FAILURE,
        SubmissionArchiveFailureCode.TIMEOUT,
    ],
)
def test_archive_infrastructure_failures_never_become_work_findings(
    failure: SubmissionArchiveFailureCode,
) -> None:
    with pytest.raises(WorkstreamDefaultCheckerUnavailable, match=failure.value):
        evaluate_rejected_archive(
            failure.value,
            packet=SubmissionPacketView(
                summary="summary", contributor_attestation="attestation"
            ),
        )


@pytest.mark.parametrize(
    "secret",
    [
        b"-----BEGIN OPENSSH PRIVATE KEY-----\nencoded",
        b"AKIAIOSFODNN7EXAMPLE",
        b"ghp_" + b"a" * 36,
        b"github_pat_" + b"a" * 82,
        b"glpat-" + b"a" * 20,
        b"AIza" + b"a" * 35,
        b"xoxb-" + b"a" * 20,
        b"sk_live_" + b"a" * 16,
    ],
)
def test_high_confidence_secret_signatures_fail_without_retaining_values(
    secret: bytes, tmp_path: Path
) -> None:
    archive = _archive({"src/config.txt": b"prefix " + secret + b" suffix"})
    result = _evaluate(archive, _input(archive), tmp_path / "work")

    assert result.eligible is False
    assert result.checks[2].failure_code == "high_confidence_secret_detected"
    assert result.checks[2].finding_count == 1
    assert secret.decode() not in result.model_dump_json()


def test_secret_near_misses_and_missing_packet_text_are_warning_only(
    tmp_path: Path,
) -> None:
    archive = _archive(
        {
            "notes.txt": (
                b"BEGIN PUBLIC KEY; AKIA-too-short; ghp_short; "
                b"sk_test_1234567890123456"
            )
        }
    )
    result = _evaluate(
        archive,
        _input(archive, summary=" \n", attestation=""),
        tmp_path / "work",
    )

    assert result.eligible is True
    assert [item.status for item in result.checks] == ["passed"] * 4
    assert [item.code for item in result.warnings] == [
        "submission_summary_missing",
        "submission_attestation_missing",
    ]


def test_exact_and_semantic_replay_fail_until_task_rules_change(tmp_path: Path) -> None:
    first = _archive({"src/main.txt": b"same work"})
    _, _, manifest, commitment = _facts(first)
    predecessor = WorkstreamDefaultPredecessor(
        new_record_id(), 1, commitment.sha256, manifest.sha256
    )

    exact = _evaluate(
        first,
        _input(
            first,
            predecessor=predecessor,
            current_predecessor=predecessor,
            predecessor_rules_sha256=RULES_A,
        ),
        tmp_path / "exact",
    )
    repacked = _archive({"src/main.txt": b"same work"}, comment=b"repacked")
    semantic = _evaluate(
        repacked,
        _input(
            repacked,
            predecessor=predecessor,
            current_predecessor=predecessor,
            predecessor_rules_sha256=RULES_A,
        ),
        tmp_path / "semantic",
    )
    rules_changed = _evaluate(
        first,
        _input(
            first,
            predecessor=predecessor,
            current_predecessor=predecessor,
            current_rules_sha256=RULES_B,
            predecessor_rules_sha256=RULES_A,
        ),
        tmp_path / "rules-changed",
    )
    with pytest.raises(
        WorkstreamDefaultCheckerUnavailable, match="submission_predecessor_stale"
    ):
        _evaluate(
            first,
            _input(
                first,
                predecessor=predecessor,
                current_predecessor=WorkstreamDefaultPredecessor(
                    new_record_id(),
                    2,
                    commitment.sha256,
                    manifest.sha256,
                ),
                current_rules_sha256=RULES_B,
                predecessor_rules_sha256=RULES_A,
            ),
            tmp_path / "rules-changed-stale",
        )

    assert exact.checks[3].failure_code == "submission_archive_unchanged"
    assert semantic.checks[3].failure_code == "submission_manifest_unchanged"
    assert rules_changed.checks[3].status == "passed"
    assert rules_changed.eligible is True


def test_stale_predecessor_and_cross_archive_manifest_are_infrastructure(
    tmp_path: Path,
) -> None:
    archive = _archive({"src/main.txt": b"candidate"})
    _, _, manifest, _ = _facts(archive)
    predecessor = WorkstreamDefaultPredecessor(
        new_record_id(), 1, "sha256:" + "1" * 64, "sha256:" + "2" * 64
    )
    stale = WorkstreamDefaultPredecessor(
        new_record_id(), 2, "sha256:" + "3" * 64, "sha256:" + "4" * 64
    )
    with pytest.raises(
        WorkstreamDefaultCheckerUnavailable, match="submission_predecessor_stale"
    ):
        _evaluate(
            archive,
            _input(
                archive,
                predecessor=predecessor,
                current_predecessor=stale,
                predecessor_rules_sha256=RULES_A,
            ),
            tmp_path / "stale",
        )

    other = _archive({"src/other.txt": b"other"})
    cross = _input(archive)
    assert cross.semantic_manifest_sha256 == manifest.sha256
    with pytest.raises(
        WorkstreamDefaultCheckerUnavailable, match="submission_material_identity_invalid"
    ):
        _evaluate(other, cross, tmp_path / "cross")


def test_detached_manifest_and_callback_bytes_cannot_be_substituted(
    tmp_path: Path,
) -> None:
    archive = _archive({"src/main.txt": b"candidate"})
    request = _input(archive)
    with pytest.raises(
        WorkstreamDefaultCheckerUnavailable,
        match="submission_manifest_identity_invalid",
    ):
        _evaluate(
            archive,
            replace(request, semantic_manifest_sha256="sha256:" + "0" * 64),
            tmp_path / "manifest",
        )

    other = _archive({"src/main.txt": b"substitute"})
    with pytest.raises(
        WorkstreamDefaultCheckerUnavailable,
        match="submission_material_identity_invalid",
    ):
        _evaluate(other, request, tmp_path / "bytes")


def test_predecessor_currentness_rejects_duck_typed_equal_values() -> None:
    class AlwaysEqual:
        def __eq__(self, other: object) -> bool:
            return True

    archive = _archive({"src/main.txt": b"candidate"})
    request = _input(archive)
    foreign = cast(Any, AlwaysEqual())

    with pytest.raises(ValueError, match="default checker input is invalid"):
        replace(request, current_predecessor=foreign)
    with pytest.raises(ValueError, match="default checker input is invalid"):
        replace(
            request,
            predecessor=foreign,
            predecessor_exists=True,
            current_predecessor=foreign,
            predecessor_rules_sha256=RULES_A,
        )
