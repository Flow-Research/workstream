"""Focused proof for the dependency-safe CHECKER pre-submit API."""

from uuid import uuid4

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api import (
    EffectivePreSubmissionExecutionPlan,
    EffectivePreSubmissionPlanLineage,
)
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
from app.modules.checkers.compiler import compile_effective_project_submission_artifact_policy
from app.modules.checkers.pre_submit_execution import (
    PreSubmissionEntryResult,
    PreSubmissionExecutionCustody,
    PreSubmissionExecutionResult,
    PreSubmissionResultDefinition,
    PreSubmissionResultPolicyTrace,
    PreSubmissionResultStatus,
)


def _effective_policy() -> dict[str, object]:
    defaults = {
        "required_packet_fields": ["summary", "worker_attestation"],
        "forbidden_artifacts": [{"pattern": ".env"}, {"pattern": ".git/**"}],
        "attestation_terms": ["rights_confirmed"],
    }
    return {
        "workstream_default_policy": defaults,
        "project_policy": {},
        "required_packet_fields": defaults["required_packet_fields"],
        "required_artifacts": [{"key": "task.toml", "path": "task.toml", "required": True}],
        "required_evidence": [{"key": "results", "required": True}],
        "forbidden_artifacts": defaults["forbidden_artifacts"],
        "attestation_terms": defaults["attestation_terms"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": True, "allowed_package_formats": ["zip"]},
    }


def test_public_planning_port_compiles_the_canonical_plan() -> None:
    """The public port delegates to the sole deterministic CHECKER compiler."""
    policy = _effective_policy()
    policy_hash = canonical_json_hash(policy)
    compiled = compile_effective_project_submission_artifact_policy(policy, policy_hash)
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version=1,
        source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "1" * 64,
        effective_policy_id=uuid4(),
        effective_policy_hash=policy_hash,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )

    plan = build_pre_submission_checker_catalogue().compile_effective_plan(
        lineage=lineage,
        effective_policy=policy,
        compiled_bundle=compiled.compiled_bundle,
    )

    assert type(plan) is EffectivePreSubmissionExecutionPlan
    assert plan.lineage is lineage
    assert plan.plan_sha256 == canonical_json_hash(plan.as_dict())


def test_public_execution_facts_exclude_artifact_custody() -> None:
    """The CHECKER result projection cannot leak ART-owned custody fields."""
    execution = PreSubmissionExecutionResult(
        plan_sha256="sha256:" + "1" * 64,
        custody=PreSubmissionExecutionCustody(
            prepared_generation_id=uuid4(),
            archive_sha256="sha256:" + "2" * 64,
            archive_byte_count=7,
            semantic_manifest_sha256="sha256:" + "3" * 64,
            storage_scheme="s3",
        ),
        eligible=True,
        entries=(
            PreSubmissionEntryResult(
                schema_version="pre_submission_checker_result.v1",
                definition=PreSubmissionResultDefinition(
                    dispatch_authority="workstream.pre_submission_checker_catalogue",
                    definition_id="submission_archive.outer_zip_valid",
                    definition_version="v0.1",
                    public_name="Outer ZIP validation",
                    source="platform_default",
                ),
                policy_trace=PreSubmissionResultPolicyTrace(
                    effective_plan_sha256="sha256:" + "1" * 64,
                    rule_instance_id=None,
                    locked_policy_sha256="sha256:" + "4" * 64,
                ),
                phase="custody",
                order=10,
                classification="mandatory_security",
                severity="blocking",
                status=PreSubmissionResultStatus.PASSED,
                failure_code=None,
                message_code="passed",
            ),
        ),
    )

    facts = execution.bounded_facts()

    assert facts.plan_sha256 == execution.plan_sha256
    assert facts.eligible is True
    assert facts.entries[0].status == "passed"
    assert not hasattr(facts, "custody")
    assert not hasattr(facts, "storage_scheme")
