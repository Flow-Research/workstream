"""Pure canonical source and output custody shared by projections and finalization."""

from app.core.hashing import canonical_json_hash
from app.modules.projects.models import GuideSufficiencyReport, SubmissionArtifactPolicy


def source_state(guide, snapshot, setup) -> dict:
    """Build the complete source-state digest payload."""
    return {
        "celery_task_id": setup.celery_task_id,
        "documents_ready_at": (
            setup.documents_ready_at.isoformat()
            if setup.documents_ready_at is not None
            else None
        ),
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
