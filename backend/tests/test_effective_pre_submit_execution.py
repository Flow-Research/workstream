"""Focused proof for canonical effective pre-submit execution and evidence custody."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.tasks.pre_submit_context import (
    PreSubmitLockedContextInvalid,
    load_locked_pre_submit_context,
)
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitExecutionCustody,
    PreSubmitExecutionResult,
    PreSubmitEvidenceConflict,
    PreSubmitEvidenceContext,
    PreSubmitEvidenceService,
    PersistedPreSubmitEvidence,
    pre_submit_failure_audit_payload,
    semantic_manifest_identity,
    validate_predecessor_lineage,
)
from app.modules.tasks.api import (
    SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
)
from app.modules.checkers.api import (
    PreSubmissionExecutionEntryFacts,
    PreSubmissionExecutionFacts,
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
    PreSubmissionInfrastructureUnavailable,
    validate_pre_submission_execution_result,
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
        source_snapshot_id=uuid4(),
        source_snapshot_sha256=_sha("8"),
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
    assert identity != replace(context, prepared_generation_id=uuid4()).operation_identity(
        effective_plan_sha256=_sha("7")
    )
    assert identity != context.operation_identity(effective_plan_sha256=_sha("8"))


def test_post_byte_relock_rejects_advanced_predecessor_version() -> None:
    predecessor_id = uuid4()
    task_context = TaskSubmissionContextFacts(
        task_id=uuid4(),
        assignment_id=uuid4(),
        contributor_id=uuid4(),
        status="needs_revision",
        kind="revision",
        predecessor=SubmissionPredecessorFacts(
            submission_id=predecessor_id,
            version=2,
        ),
        locked_project_context=TaskLockedProjectContextReferences(
            project_id=uuid4(),
            guide_version="1",
            source_snapshot_id=uuid4(),
            source_snapshot_hash=_sha("1"),
            effective_policy_id=uuid4(),
            effective_policy_hash=_sha("2"),
            pre_submit_policy_id=uuid4(),
            pre_submit_policy_bundle_hash=_sha("3"),
        ),
    )

    with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_locked_context_changed"):
        validate_predecessor_lineage(
            task_context,
            predecessor_submission_id=predecessor_id,
            predecessor_submission_version=1,
        )


def test_semantic_manifest_identity_is_server_deterministic() -> None:
    assert semantic_manifest_identity(_sha("a")) == semantic_manifest_identity(_sha("a"))
    assert semantic_manifest_identity(_sha("a")) != semantic_manifest_identity(_sha("b"))


def test_pass_capability_is_generation_bound_and_single_use() -> None:
    evidence_set_id = uuid4()
    generation_id = uuid4()
    capability = PreSubmitEvidenceService(
        SimpleNamespace(),
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
    )._mint_pass_capability(
        evidence_set_id=evidence_set_id,
        prepared_generation_id=generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=_sha("7"),
        archive_sha256=_sha("1"),
        semantic_manifest_sha256=_sha("2"),
        storage_scheme="s3",
    )

    with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_pass_capability_invalid"):
        capability.consume(
            prepared_generation_id=uuid4(),
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )

    assert (
        capability.consume(
            prepared_generation_id=generation_id,
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )
        == evidence_set_id
    )
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
        "required_artifacts": [{"key": "answer", "path": "outputs/final.md", "required": True}],
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

    compiled = compile_effective_project_submission_artifact_policy(effective_policy, _sha("9"))
    required = next(
        rule for rule in compiled.compiled_bundle["rules"] if rule["primitive"] == "require_file"
    )

    assert required["config"] == {"artifact_paths": ["outputs/final.md"]}


@pytest.mark.parametrize("path", [None, "", "../answer.md", "/answer.md", "a\\b"])
def test_compiler_rejects_unmappable_artifact_paths(path: object) -> None:
    policy = {
        "workstream_default_policy": {
            "required_packet_fields": ["summary", "worker_attestation"],
            "forbidden_artifacts": [{"pattern": ".env"}],
            "attestation_terms": ["rights_confirmed"],
        },
        "project_policy": {},
        "required_packet_fields": ["summary", "worker_attestation"],
        "required_artifacts": [{"key": "answer", "path": path, "required": True}],
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

    with pytest.raises(PreSubmitCheckerCompilerError, match="path is invalid"):
        compile_effective_project_submission_artifact_policy(policy, _sha("9"))


@pytest.mark.parametrize("key", [".", ".."])
def test_compiler_rejects_noncanonical_evidence_keys(key: str) -> None:
    policy = {
        "workstream_default_policy": {},
        "project_policy": {},
        "required_packet_fields": [],
        "required_artifacts": [],
        "required_evidence": [{"key": key, "required": True}],
        "forbidden_artifacts": [],
        "attestation_terms": [],
        "manifest_required": False,
        "artifact_hash_required": False,
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": None,
        "maximum_package_size_bytes": None,
        "packaging": {"package_required": False},
    }

    with pytest.raises(PreSubmitCheckerCompilerError, match="key is unmappable"):
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
                    locked_effective_project_submission_artifact_policy_id=str(effective_policy_id),
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
                SimpleNamespace(id=str(guide_id), project_id=str(project_id), version="1"),
                SimpleNamespace(
                    id=str(effective_policy_id),
                    effective_policy_hash=_sha("2"),
                    effective_policy={},
                ),
                SimpleNamespace(
                    id=str(checker_policy_id),
                    compiled_bundle_hash=_sha("3"),
                    compiled_bundle={},
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
    assert result.guide_version == "1"
    assert result.source_snapshot_id == source_snapshot_id
    assert result.source_snapshot_sha256 == _sha("1")
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
    execution = PreSubmitExecutionResult(
        custody=PreSubmitExecutionCustody(
            prepared_generation_id=generation_id,
            archive_sha256=_sha("5"),
            archive_byte_count=1,
            semantic_manifest_sha256=_sha("6"),
            storage_scheme="s3",
        ),
        checker_facts=PreSubmissionExecutionFacts(
            plan_sha256=_sha("2"),
            eligible=False,
            entries=(
                PreSubmissionExecutionEntryFacts(
                    dispatch_authority="workstream.pre_submission_checker_catalogue",
                    definition_id="policy.file.require",
                    definition_version="v1",
                    public_name="check_required_files",
                    policy_source="locked_effective_project_submission_artifact_policy",
                    effective_plan_sha256=_sha("2"),
                    rule_instance_id=_sha("3"),
                    locked_policy_sha256=_sha("4"),
                    phase="project_policy",
                    order=10,
                    classification="mandatory_accountability",
                    severity="blocking",
                    checker_execution_status="failed",
                    failure_code="pre_submission_checker_failed",
                    message_code="required_file_missing",
                    metadata=(("finding_count", 1),),
                ),
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
    assert payload["result_outcomes"] == [
        {
            "definition_id": "policy.file.require",
            "definition_version": "v1",
            "status": "failed",
            "message_code": "required_file_missing",
        }
    ]
    assert "finding_count" not in serialized
    assert "/" not in serialized


def test_result_validation_rejects_failure_code_on_non_failed_result() -> None:
    from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
    from app.modules.checkers.effective_plan import (
        EffectivePreSubmissionPlanLineage,
        compile_effective_pre_submission_execution_plan,
    )

    effective_policy = {
        "workstream_default_policy": {
            "required_packet_fields": ["summary", "worker_attestation"],
            "forbidden_artifacts": [{"pattern": ".env"}],
            "attestation_terms": ["rights_confirmed"],
        },
        "project_policy": {},
        "required_packet_fields": ["summary", "worker_attestation"],
        "required_artifacts": [],
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
    policy_hash = canonical_json_hash(effective_policy)
    compiled = compile_effective_project_submission_artifact_policy(effective_policy, policy_hash)
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version=1,
        source_snapshot_id=uuid4(),
        source_snapshot_hash=_sha("a"),
        effective_policy_id=uuid4(),
        effective_policy_hash=policy_hash,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )
    plan = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=effective_policy,
        compiled_bundle=compiled.compiled_bundle,
        catalogue=build_pre_submission_checker_catalogue(),
    )
    forged = PreSubmissionExecutionResult(
        plan_sha256=plan.plan_sha256,
        custody=PreSubmissionExecutionCustody(
            prepared_generation_id=uuid4(),
            archive_sha256=_sha("b"),
            archive_byte_count=1,
            semantic_manifest_sha256=_sha("c"),
            storage_scheme="s3",
        ),
        eligible=True,
        entries=tuple(
            PreSubmissionEntryResult(
                schema_version=entry.result_schema,
                definition=PreSubmissionResultDefinition(
                    dispatch_authority="workstream.pre_submission_checker_catalogue",
                    definition_id=entry.definition_id,
                    definition_version=entry.definition_version,
                    public_name=entry.public_name,
                    source=entry.policy_trace_source,
                ),
                policy_trace=PreSubmissionResultPolicyTrace(
                    effective_plan_sha256=plan.plan_sha256,
                    rule_instance_id=entry.rule_instance_id,
                    locked_policy_sha256=lineage.effective_policy_hash,
                ),
                phase=entry.phase,
                order=entry.order,
                classification=entry.classification,
                severity="warning" if entry.classification == "advisory" else "blocking",
                status=PreSubmissionResultStatus.PASSED,
                failure_code="forged" if index == 0 else None,
                message_code="passed",
            )
            for index, entry in enumerate(plan.entries)
        ),
    )

    with pytest.raises(
        PreSubmissionInfrastructureUnavailable,
        match="pre_submission_result_context_invalid",
    ):
        validate_pre_submission_execution_result(plan, forged)

    class _ForgedStatus:
        value = "failed"

    forged_entry = replace(
        forged.entries[0],
        status=_ForgedStatus(),  # type: ignore[arg-type]
        failure_code=None,
    )
    forged_status = replace(
        forged,
        eligible=True,
        entries=(forged_entry, *forged.entries[1:]),
    )

    with pytest.raises(
        PreSubmissionInfrastructureUnavailable,
        match="pre_submission_result_context_invalid",
    ):
        validate_pre_submission_execution_result(plan, forged_status)

    with pytest.raises(
        PreSubmissionInfrastructureUnavailable,
        match="pre_submission_result_context_invalid",
    ):
        validate_pre_submission_execution_result(plan, replace(forged, eligible=1))  # type: ignore[arg-type]

    for metadata in (
        (("finding_count",),),
        ((["finding_count"], 1),),
        (("unknown_count", 1),),
        (("finding_count", 1), ("finding_count", 2)),
        (("finding_count", "1"),),
        (("finding_count", -1),),
    ):
        malformed_entry = replace(
            forged.entries[0],
            failure_code=None,
            metadata=metadata,  # type: ignore[arg-type]
        )
        malformed = replace(
            forged,
            entries=(malformed_entry, *forged.entries[1:]),
        )
        with pytest.raises(
            PreSubmissionInfrastructureUnavailable,
            match="pre_submission_result_context_invalid",
        ):
            validate_pre_submission_execution_result(plan, malformed)
