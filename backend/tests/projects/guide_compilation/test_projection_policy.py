"""Deterministic transform proofs for compilation-derived product rows."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
)
from app.modules.projects.guide_compilation.projections import (
    _policy_body,
    _policy_digest,
    _report_digest,
    _report_payload,
)
from app.modules.projects.service import PolicySetupBlocked

from .helpers import result


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("guide_blocked", "blocked"),
        ("draft_ready", "passed"),
        ("draft_ready_with_warnings", "passed_with_warnings"),
    ],
)
def test_report_status_mapping_is_closed(status: str, expected: str) -> None:
    """Map every unified outcome to its sole canonical report status."""
    payload = result().model_dump(mode="json") | {"status": status}
    if status == "guide_blocked":
        payload["submission_artifact_policy"] = None
    compiled = ProjectGuideCompilationResult.model_validate(payload)
    report = _report_payload(compiled, str(uuid4()))
    assert report.status == expected
    assert report.summary is None


def test_artifact_policy_transform_preserves_values_and_server_owned_order() -> None:
    """Build the exact v1 policy without repair, truncation, or model input."""
    proposal = SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=123,
        maximum_package_size_bytes=456,
        required_artifacts=("result.json", "report.md"),
        forbidden_artifacts=("*.env", "private_*"),
        required_evidence=("test_report", "coverage_report"),
        attestation_terms=("tests_passed", "source_reviewed"),
    )
    policy = _policy_body(cast(AsyncSession, None), proposal)
    assert policy == {
        "schema_version": "project_submission_artifact_policy.v1",
        "required_artifacts": [
            {
                "key": "required-artifact-001",
                "path": "result.json",
                "hash_required": True,
                "required": True,
                "description": None,
            },
            {
                "key": "required-artifact-002",
                "path": "report.md",
                "hash_required": True,
                "required": True,
                "description": None,
            },
        ],
        "required_evidence": [
            {
                "key": "required-evidence-001",
                "label": "test_report",
                "hash_required": True,
                "required": True,
                "description": None,
            },
            {
                "key": "required-evidence-002",
                "label": "coverage_report",
                "hash_required": True,
                "required": True,
                "description": None,
            },
        ],
        "forbidden_artifacts": [
            {"pattern": "*.env", "reason": "*.env", "worker_facing_fix": None},
            {
                "pattern": "private_*",
                "reason": "private_*",
                "worker_facing_fix": None,
            },
        ],
        "attestation_terms": ["source_reviewed", "tests_passed"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3"],
        "maximum_file_size_bytes": 123,
        "maximum_package_size_bytes": 456,
        "packaging": {
            "package_required": True,
            "allowed_package_formats": ["zip"],
        },
    }


def test_artifact_policy_transform_requires_a_persisted_proposal() -> None:
    """Reject a missing policy component instead of manufacturing defaults."""
    with pytest.raises(ValueError, match="proposal is absent"):
        _policy_body(cast(AsyncSession, None), None)


@pytest.mark.parametrize(
    "proposal",
    [
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_artifacts=("a" * 501,),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            forbidden_artifacts=("x" * 501,),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_artifacts=(" README.md ",),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_artifacts=("cafe\u0301.txt",),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_artifacts=("nested\\result.json",),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_artifacts=("s3://bucket/result.json",),
        ),
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1,
            maximum_package_size_bytes=2,
            required_evidence=("invalid evidence",),
        ),
    ],
)
def test_unprojectable_v1_policy_fails_without_best_effort_repair(
    proposal: SubmissionArtifactPolicyProposal,
) -> None:
    """Reject incompatible persisted-v1 text instead of rewriting it."""
    with pytest.raises((PolicySetupBlocked, ValueError)):
        _policy_body(cast(AsyncSession, None), proposal)


@pytest.mark.parametrize(
    "path",
    ["../private.txt", "/absolute.txt", "nested//result.json"],
)
def test_persisted_v1_noncanonical_path_fails_at_projection(path: str) -> None:
    """Reject a persisted legacy path at the projection-owned boundary."""
    proposal = SubmissionArtifactPolicyProposal.model_construct(
        maximum_file_size_bytes=1,
        maximum_package_size_bytes=2,
        required_artifacts=(path,),
        forbidden_artifacts=(),
        required_evidence=(),
        attestation_terms=(),
    )
    with pytest.raises(PolicySetupBlocked, match="artifact path"):
        _policy_body(cast(AsyncSession, None), proposal)


def test_absent_outputs_have_no_replay_digest() -> None:
    """Fail closed when replay custody points to no canonical product row."""
    assert _report_digest(None) is None
    assert _policy_digest(None) is None
