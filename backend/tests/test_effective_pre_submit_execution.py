"""Focused proof for canonical effective pre-submit execution and evidence custody."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.tasks.pre_submit_context import (
    PreSubmitLockedContextInvalid,
    load_locked_pre_submit_context,
)
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict,
    PreSubmitEvidenceContext,
    PreSubmitPassCapability,
    PersistedPreSubmitEvidence,
    pre_submit_failure_audit_payload,
    semantic_manifest_identity,
)
from app.modules.checkers.compiler import (
    PreSubmitCheckerCompilerError,
    compile_effective_project_submission_artifact_policy,
)
from app.modules.checkers.pre_submit_execution import (
    PreSubmissionEntryResult,
    PreSubmissionExecutionResult,
    PreSubmissionExecutionCustody,
    PreSubmissionResultDefinition,
    PreSubmissionResultPolicyTrace,
    PreSubmissionResultStatus,
)


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _context() -> PreSubmitEvidenceContext:
    return PreSubmitEvidenceContext(
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        assignment_id=uuid4(),
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        prepared_generation_id=uuid4(),
        archive_sha256=_sha("1"),
        archive_byte_count=1024,
        semantic_manifest_id=uuid4(),
        semantic_manifest_sha256=_sha("2"),
        guide_id=uuid4(),
        guide_version="1",
        locked_guide_sha256=_sha("3"),
        effective_policy_id=uuid4(),
        locked_artifact_policy_sha256=_sha("4"),
        pre_submit_policy_id=uuid4(),
        locked_checker_policy_sha256=_sha("5"),
        catalogue_id="workstream.pre_submission_checkers",
        catalogue_version="v0.1",
        catalogue_manifest_sha256=_sha("6"),
        storage_scheme="s3",
    )


def test_evidence_operation_identity_binds_every_custody_fact() -> None:
    context = _context()
    identity = context.operation_identity(effective_plan_sha256=_sha("7"))

    assert identity == context.operation_identity(effective_plan_sha256=_sha("7"))
    assert identity != replace(
        context, prepared_generation_id=uuid4()
    ).operation_identity(effective_plan_sha256=_sha("7"))
    assert identity != context.operation_identity(effective_plan_sha256=_sha("8"))


def test_semantic_manifest_identity_is_server_deterministic() -> None:
    assert semantic_manifest_identity(_sha("a")) == semantic_manifest_identity(_sha("a"))
    assert semantic_manifest_identity(_sha("a")) != semantic_manifest_identity(_sha("b"))


def test_pass_capability_is_generation_bound_and_single_use() -> None:
    evidence_set_id = uuid4()
    generation_id = uuid4()
    capability = PreSubmitPassCapability(
        evidence_set_id=evidence_set_id,
        prepared_generation_id=generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=_sha("7"),
        archive_sha256=_sha("1"),
        semantic_manifest_sha256=_sha("2"),
        storage_scheme="s3",
    )

    assert capability.consume(
        prepared_generation_id=generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=_sha("7"),
        archive_sha256=_sha("1"),
        semantic_manifest_sha256=_sha("2"),
        storage_scheme="s3",
    ) == evidence_set_id
    with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_pass_capability_invalid"):
        capability.consume(
            prepared_generation_id=generation_id,
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )


def test_compiler_projects_policy_artifact_path_not_contributor_label() -> None:
    effective_policy = {
        "workstream_default_policy": {
            "required_packet_fields": [],
            "forbidden_artifacts": [{"pattern": ".env"}],
            "attestation_terms": ["rights_confirmed"],
        },
        "project_policy": {},
        "required_packet_fields": [],
        "required_artifacts": [
            {"key": "answer", "path": "outputs/final.md", "required": True}
        ],
        "required_evidence": [],
        "forbidden_artifacts": [{"pattern": ".env"}],
        "attestation_terms": ["rights_confirmed"],
        "manifest_required": False,
        "artifact_hash_required": False,
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": None,
        "maximum_package_size_bytes": None,
        "packaging": {"package_required": False},
    }

    compiled = compile_effective_project_submission_artifact_policy(
        effective_policy, _sha("9")
    )
    required = next(
        rule for rule in compiled.compiled_bundle["rules"] if rule["primitive"] == "require_file"
    )

    assert required["config"] == {"artifact_paths": ["outputs/final.md"]}


@pytest.mark.parametrize("path", [None, "", "../answer.md", "/answer.md", "a\\b"])
def test_compiler_rejects_unmappable_artifact_paths(path: object) -> None:
    policy = {
        "workstream_default_policy": {},
        "project_policy": {},
        "required_packet_fields": [],
        "required_artifacts": [{"key": "answer", "path": path, "required": True}],
        "required_evidence": [],
        "forbidden_artifacts": [],
        "attestation_terms": [],
        "manifest_required": False,
        "artifact_hash_required": False,
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": None,
        "maximum_package_size_bytes": None,
        "packaging": {"package_required": False},
    }

    with pytest.raises(PreSubmitCheckerCompilerError, match="path is invalid"):
        compile_effective_project_submission_artifact_policy(policy, _sha("9"))


def test_compiler_rejects_duplicate_policy_keys_and_projected_paths() -> None:
    base = {
        "workstream_default_policy": {},
        "project_policy": {},
        "required_packet_fields": [],
        "required_evidence": [],
        "forbidden_artifacts": [],
        "attestation_terms": [],
        "manifest_required": False,
        "artifact_hash_required": False,
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": None,
        "maximum_package_size_bytes": None,
        "packaging": {"package_required": False},
    }
    duplicate_keys = {
        **base,
        "required_artifacts": [
            {"key": "answer", "path": "a.md"},
            {"key": "answer", "path": "b.md"},
        ],
    }
    duplicate_paths = {
        **base,
        "required_artifacts": [
            {"key": "answer", "path": "a.md"},
            {"key": "report", "path": "a.md"},
        ],
    }

    with pytest.raises(PreSubmitCheckerCompilerError, match="keys are invalid"):
        compile_effective_project_submission_artifact_policy(duplicate_keys, _sha("9"))
    with pytest.raises(PreSubmitCheckerCompilerError, match="paths are ambiguous"):
        compile_effective_project_submission_artifact_policy(duplicate_paths, _sha("9"))


@pytest.mark.asyncio
async def test_locked_context_revalidates_identity_assignment_and_policy_lineage() -> None:
    actor_id = uuid4()
    identity_link_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    assignment_id = uuid4()
    guide_id = uuid4()
    effective_policy_id = uuid4()
    checker_policy_id = uuid4()
    source_snapshot_id = uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(
            side_effect=[
                SimpleNamespace(id=str(actor_id), status="active"),
                SimpleNamespace(
                    id=str(identity_link_id), actor_profile_id=str(actor_id), status="active"
                ),
                SimpleNamespace(
                    id=str(task_id),
                    project_id=str(project_id),
                    assigned_to=str(actor_id),
                    status="in_progress",
                    locked_guide_version="1",
                    locked_guide_source_snapshot_id=str(source_snapshot_id),
                    locked_guide_source_snapshot_hash=_sha("1"),
                    locked_effective_project_submission_artifact_policy_id=str(
                        effective_policy_id
                    ),
                    locked_effective_project_submission_artifact_policy_hash=_sha("2"),
                    locked_pre_submit_checker_policy_id=str(checker_policy_id),
                    locked_pre_submit_checker_bundle_hash=_sha("3"),
                ),
                SimpleNamespace(
                    id=str(assignment_id),
                    task_id=str(task_id),
                    contributor_id=str(actor_id),
                    status="active",
                ),
                None,
                SimpleNamespace(
                    id=str(guide_id), project_id=str(project_id), version="1"
                ),
                SimpleNamespace(
                    id=str(effective_policy_id), effective_policy_hash=_sha("2")
                ),
                SimpleNamespace(
                    id=str(checker_policy_id), compiled_bundle_hash=_sha("3")
                ),
            ]
        )
    )

    result = await load_locked_pre_submit_context(
        session,
        actor_profile_id=actor_id,
        identity_link_id=identity_link_id,
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=None,
    )

    assert result.project_id == project_id
    assert result.effective_policy_id == effective_policy_id
    assert result.pre_submit_policy_id == checker_policy_id
    assert session.scalar.await_count == 8


@pytest.mark.asyncio
async def test_locked_context_rejects_revoked_identity_before_policy_reads() -> None:
    actor_id = uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(
            side_effect=[
                SimpleNamespace(id=str(actor_id), status="active"),
                SimpleNamespace(actor_profile_id=str(actor_id), status="revoked"),
                None,
                None,
            ]
        )
    )

    with pytest.raises(PreSubmitLockedContextInvalid, match="pre_submit_locked_context_invalid"):
        await load_locked_pre_submit_context(
            session,
            actor_profile_id=actor_id,
            identity_link_id=uuid4(),
            task_id=uuid4(),
            assignment_id=uuid4(),
            predecessor_submission_id=None,
        )

    assert session.scalar.await_count == 4


def test_failure_audit_projection_is_bounded_and_path_free() -> None:
    actor_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    generation_id = uuid4()
    evidence = PersistedPreSubmitEvidence(uuid4(), _sha("1"), False)
    execution = PreSubmissionExecutionResult(
        plan_sha256=_sha("2"),
        custody=PreSubmissionExecutionCustody(
            prepared_generation_id=generation_id,
            archive_sha256=_sha("5"),
            archive_byte_count=1,
            semantic_manifest_sha256=_sha("6"),
            storage_scheme="s3",
        ),
        eligible=False,
        entries=(
            PreSubmissionEntryResult(
                schema_version="pre_submission_checker_result.v1",
                definition=PreSubmissionResultDefinition(
                    dispatch_authority="workstream.pre_submission_checker_catalogue",
                    definition_id="policy.file.require",
                    definition_version="v1",
                    public_name="check_required_files",
                    source="locked_effective_project_submission_artifact_policy",
                ),
                policy_trace=PreSubmissionResultPolicyTrace(
                    effective_plan_sha256=_sha("2"),
                    rule_instance_id=_sha("3"),
                    locked_policy_sha256=_sha("4"),
                ),
                phase="project_policy",
                order=10,
                classification="mandatory_accountability",
                severity="blocking",
                status=PreSubmissionResultStatus.FAILED,
                failure_code="pre_submission_checker_failed",
                message_code="required_file_missing",
                metadata=(("finding_count", 1),),
            ),
        ),
    )

    payload = pre_submit_failure_audit_payload(
        actor_profile_id=actor_id,
        project_id=project_id,
        task_id=task_id,
        prepared_generation_id=generation_id,
        evidence=evidence,
        execution=execution,
        catalogue_id="workstream.pre_submission_checkers",
        catalogue_version="v0.1",
    )

    assert payload["event_type"] == "pre_submission_check_failed"
    assert payload["failed_count"] == 1
    serialized = repr(payload)
    assert "required_file_missing" not in serialized
    assert "finding_count" not in serialized
    assert "/" not in serialized
