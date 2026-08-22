"""Pure value construction for unified guide-compilation projections."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, cast
import unicodedata
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import GuideSufficiencyMaterialResult
from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
)
from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    GuideSufficiencyProjectionFacts,
    ProjectGuideProjectionIdentity,
)
from app.modules.projects.models import (
    GuideSufficiencyReport,
    SubmissionArtifactPolicy,
)
from app.modules.projects.schemas import (
    GuideSufficiencyFindingInput,
    GuideSufficiencyReportCreate,
    SubmissionArtifactPolicyInput,
)
from app.modules.projects.service import ProjectService

from .models import ProjectGuideComponentProjectionOperation

PROJECTOR_NAME = "ProjectGuideCompilationProjection"
PROJECTOR_VERSION = "v1"
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


@dataclass(frozen=True, slots=True)
class ProjectionSeed:
    """Immutable compilation lineage prepared before authorization."""

    attempt_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    request_operation_id: UUID
    provider_idempotency_key: UUID
    compilation_id: UUID
    result_hash: str
    component_hash: str
    sufficiency_component_hash: str
    result_schema_version: str
    compilation_agent_name: str
    compilation_agent_version: str
    result: ProjectGuideCompilationResult
    report_payload: GuideSufficiencyReportCreate | None = None
    policy_body: dict | None = None


@dataclass(frozen=True, slots=True)
class LockedProjection:
    """Verified material and source state locked for one transaction."""

    material: GuideSufficiencyMaterialResult
    material_sha256: str
    material_byte_count: int
    celery_task_id: UUID
    source_state_digest: str


def report_payload(
    result: ProjectGuideCompilationResult, source_snapshot_id: str
) -> GuideSufficiencyReportCreate:
    """Map one validated compilation result to a canonical report payload."""
    status = {
        "guide_blocked": "blocked",
        "draft_ready": "passed",
        "draft_ready_with_warnings": "passed_with_warnings",
    }[result.status]
    return GuideSufficiencyReportCreate(
        source_snapshot_id=source_snapshot_id,
        status=cast(Literal["passed", "blocked", "passed_with_warnings"], status),
        findings=[
            GuideSufficiencyFindingInput(
                severity=item.severity,
                code=item.code,
                message=item.message,
                location=None,
            )
            for item in result.findings
        ],
        summary=None,
    )


def policy_body(
    session: AsyncSession, proposal: SubmissionArtifactPolicyProposal | None
) -> dict:
    """Map a bounded proposal to the canonical platform policy body."""
    if proposal is None:
        raise ValueError("artifact policy proposal is absent")
    for value in proposal.required_artifacts:
        if value != value.strip() or value != unicodedata.normalize("NFC", value):
            raise ValueError("artifact policy path is not canonical")
    for value in (*proposal.required_evidence, *proposal.attestation_terms):
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("artifact policy identifier is not canonical")
    policy = SubmissionArtifactPolicyInput(
        required_artifacts=[
            {
                "key": f"required-artifact-{index:03d}",
                "path": value,
                "hash_required": True,
                "required": True,
                "description": None,
            }
            for index, value in enumerate(proposal.required_artifacts, 1)
        ],
        required_evidence=[
            {
                "key": f"required-evidence-{index:03d}",
                "label": value,
                "hash_required": True,
                "required": True,
                "description": None,
            }
            for index, value in enumerate(proposal.required_evidence, 1)
        ],
        forbidden_artifacts=[
            {"pattern": value, "reason": value, "worker_facing_fix": None}
            for value in proposal.forbidden_artifacts
        ],
        attestation_terms=list(proposal.attestation_terms),
        manifest_required=True,
        artifact_hash_required=True,
        artifact_hash_algorithm="sha256",
        allowed_storage_schemes=["local", "s3"],
        maximum_file_size_bytes=proposal.maximum_file_size_bytes,
        maximum_package_size_bytes=proposal.maximum_package_size_bytes,
        packaging={"package_required": True, "allowed_package_formats": ["zip"]},
    )
    return ProjectService(session).canonical_agent_submission_policy_body(
        policy.model_dump(mode="json")
    )


def source_state(guide, snapshot, setup) -> dict:
    """Build the complete source-state digest payload."""
    return {
        "celery_task_id": setup.celery_task_id,
        "continuation_started_at": (
            setup.continuation_started_at.isoformat()
            if setup.continuation_started_at is not None
            else None
        ),
        "continuation_verification_job_id": setup.continuation_verification_job_id,
        "current_step": setup.current_step,
        "error_artifact_incident_id": setup.error_artifact_incident_id,
        "error_code": setup.error_code,
        "error_summary": setup.error_summary,
        "finished_at": setup.finished_at.isoformat() if setup.finished_at else None,
        "guide_id": guide.id,
        "guide_status": guide.status,
        "guide_version": guide.version,
        "output_post_submit_checker_policy_id": setup.output_post_submit_checker_policy_id,
        "output_submission_artifact_policy_id": (
            setup.output_submission_artifact_policy_id
        ),
        "output_sufficiency_report_id": setup.output_sufficiency_report_id,
        "post_submit_derivation_summary": setup.post_submit_derivation_summary,
        "setup_generation": setup.setup_generation,
        "setup_run_id": setup.id,
        "source_snapshot_hash": snapshot.bundle_hash,
        "source_snapshot_id": snapshot.id,
        "started_at": setup.started_at.isoformat() if setup.started_at else None,
        "status": setup.status,
    }


def report_output(
    seed: ProjectionSeed,
    locked: LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    payload: GuideSufficiencyReportCreate,
) -> dict:
    """Build the exact sufficiency output digest payload."""
    return {
        "id": str(identity.output_id),
        "project_id": str(seed.project_id),
        "guide_id": str(seed.guide_id),
        "guide_version": seed.guide_version,
        "source_snapshot_id": str(seed.source_snapshot_id),
        "source_snapshot_hash": seed.source_snapshot_hash,
        "status": payload.status,
        "findings": [item.model_dump(mode="json") for item in payload.findings],
        "summary": None,
        "agent_name": PROJECTOR_NAME,
        "agent_version": PROJECTOR_VERSION,
        "project_setup_run_id": str(seed.setup_run_id),
        "setup_generation": seed.setup_generation,
        "agent_material_sha256": locked.material_sha256,
        "agent_material_byte_count": locked.material_byte_count,
        "created_by": str(identity.actor_profile_id),
    }


def policy_output(
    seed: ProjectionSeed,
    locked: LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    body: dict,
) -> dict:
    """Build the exact draft-policy output digest payload."""
    policy_hash = canonical_json_hash(body)
    return {
        "id": str(identity.output_id),
        "project_id": str(seed.project_id),
        "guide_id": str(seed.guide_id),
        "guide_version": seed.guide_version,
        "source_snapshot_id": str(seed.source_snapshot_id),
        "source_snapshot_hash": seed.source_snapshot_hash,
        "policy_version": (
            f"unified-{seed.source_snapshot_hash.removeprefix('sha256:')[:16]}"
            f"-g{seed.setup_generation}"
        ),
        "lifecycle_status": "draft",
        "policy_body": body,
        "policy_hash": policy_hash,
        "derivation_source": "unified_compilation",
        "source_material_refs": [
            "artifact-content:"
            f"{item.content_id}#extraction-usage:{item.extraction_usage_id}"
            for item in locked.material.provenance
        ],
        "derivation_agent_name": PROJECTOR_NAME,
        "derivation_agent_version": PROJECTOR_VERSION,
        "created_by": str(identity.actor_profile_id),
        "change_summary": "Projected from unified project guide compilation.",
    }


def sufficiency_facts(
    seed: ProjectionSeed,
    locked: LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    output_digest: str,
) -> GuideSufficiencyProjectionFacts:
    """Build the closed AUTH facts for sufficiency projection."""
    return GuideSufficiencyProjectionFacts(
        project_id=seed.project_id,
        attempt_id=seed.attempt_id,
        request_operation_id=seed.request_operation_id,
        provider_idempotency_key=seed.provider_idempotency_key,
        compilation_id=seed.compilation_id,
        guide_id=seed.guide_id,
        guide_version=seed.guide_version,
        source_snapshot_id=seed.source_snapshot_id,
        source_snapshot_hash=seed.source_snapshot_hash,
        setup_run_id=seed.setup_run_id,
        setup_generation=seed.setup_generation,
        celery_task_id=locked.celery_task_id,
        source_state_digest=locked.source_state_digest,
        result_hash=seed.result_hash,
        component_hash=seed.component_hash,
        result_schema_version=seed.result_schema_version,
        compilation_agent_name=seed.compilation_agent_name,
        compilation_agent_version=seed.compilation_agent_version,
        material_sha256=locked.material_sha256,
        material_byte_count=locked.material_byte_count,
        report_id=identity.output_id,
        report_content_digest=output_digest,
    )


def policy_facts(
    seed: ProjectionSeed,
    locked: LockedProjection,
    identity: ProjectGuideProjectionIdentity,
    prior: ProjectGuideComponentProjectionOperation,
    output_digest: str,
) -> ArtifactPolicyProjectionFacts:
    """Build the closed AUTH facts for artifact-policy projection."""
    return ArtifactPolicyProjectionFacts(
        project_id=seed.project_id,
        attempt_id=seed.attempt_id,
        request_operation_id=seed.request_operation_id,
        provider_idempotency_key=seed.provider_idempotency_key,
        compilation_id=seed.compilation_id,
        guide_id=seed.guide_id,
        guide_version=seed.guide_version,
        source_snapshot_id=seed.source_snapshot_id,
        source_snapshot_hash=seed.source_snapshot_hash,
        setup_run_id=seed.setup_run_id,
        setup_generation=seed.setup_generation,
        celery_task_id=locked.celery_task_id,
        source_state_digest=locked.source_state_digest,
        result_hash=seed.result_hash,
        component_hash=seed.component_hash,
        result_schema_version=seed.result_schema_version,
        compilation_agent_name=seed.compilation_agent_name,
        compilation_agent_version=seed.compilation_agent_version,
        prior_operation_id=prior.operation_id,
        sufficiency_report_id=UUID(cast(str, prior.report_id)),
        sufficiency_report_digest=prior.output_digest,
        policy_id=identity.output_id,
        policy_content_digest=output_digest,
    )


def report_digest(report: GuideSufficiencyReport | None) -> str | None:
    """Recompute the canonical report output digest."""
    if report is None:
        return None
    return canonical_json_hash(
        {
            "domain": "workstream.project_guide_sufficiency_projection.output.v1",
            "facts": {
                "id": report.id,
                "project_id": report.project_id,
                "guide_id": report.guide_id,
                "guide_version": report.guide_version,
                "source_snapshot_id": report.source_snapshot_id,
                "source_snapshot_hash": report.source_snapshot_hash,
                "status": report.status,
                "findings": report.findings,
                "summary": report.summary,
                "agent_name": report.agent_name,
                "agent_version": report.agent_version,
                "project_setup_run_id": report.project_setup_run_id,
                "setup_generation": report.setup_generation,
                "agent_material_sha256": report.agent_material_sha256,
                "agent_material_byte_count": report.agent_material_byte_count,
                "created_by": report.created_by,
            },
        }
    )


def policy_digest(policy: SubmissionArtifactPolicy | None) -> str | None:
    """Recompute the canonical policy output digest."""
    if policy is None:
        return None
    return canonical_json_hash(
        {
            "domain": (
                "workstream.project_submission_artifact_policy_projection.output.v1"
            ),
            "facts": {
                "id": policy.id,
                "project_id": policy.project_id,
                "guide_id": policy.guide_id,
                "guide_version": policy.guide_version,
                "source_snapshot_id": policy.source_snapshot_id,
                "source_snapshot_hash": policy.source_snapshot_hash,
                "policy_version": policy.policy_version,
                "lifecycle_status": policy.lifecycle_status,
                "policy_body": policy.policy_body,
                "policy_hash": policy.policy_hash,
                "derivation_source": policy.derivation_source,
                "source_material_refs": policy.source_material_refs,
                "derivation_agent_name": policy.derivation_agent_name,
                "derivation_agent_version": policy.derivation_agent_version,
                "created_by": policy.created_by,
                "change_summary": policy.change_summary,
            },
        }
    )
