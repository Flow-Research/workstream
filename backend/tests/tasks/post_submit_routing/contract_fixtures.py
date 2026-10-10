"""Side-effect-free routing contract inputs shared by owner-boundary tests."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.identifiers import new_record_id
from app.modules.tasks.api.transition_audit import TaskPolicyLineage

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


def _lineage(*, contribution_policy_version_id: UUID) -> TaskPolicyLineage:
    return TaskPolicyLineage(
        locked_guide_version="guide-v1",
        locked_guide_source_snapshot_id=new_record_id(),
        locked_guide_source_snapshot_hash=SHA_A,
        locked_effective_project_submission_artifact_policy_id=new_record_id(),
        locked_effective_project_submission_artifact_policy_hash=SHA_A,
        locked_pre_submit_checker_policy_id=new_record_id(),
        locked_pre_submit_checker_bundle_hash=SHA_A,
        locked_post_submit_checker_policy_id=new_record_id(),
        locked_post_submit_checker_policy_version="post-v1",
        locked_post_submit_checker_policy_hash=SHA_A,
        locked_review_policy_id=new_record_id(),
        locked_review_policy_generation=1,
        locked_review_policy_hash=SHA_A,
        locked_revision_policy_id=new_record_id(),
        locked_revision_policy_generation=1,
        locked_revision_policy_hash=SHA_A,
        locked_contribution_policy_version_id=contribution_policy_version_id,
    )


def _source_values(**changes: object) -> dict[str, object]:
    contribution_policy_version_id = new_record_id()
    values: dict[str, object] = {
        "id": new_record_id(),
        "created_at": datetime(2026, 1, 2, tzinfo=UTC),
        "project_id": new_record_id(),
        "task_id": new_record_id(),
        "submission_id": new_record_id(),
        "submission_version": 1,
        "assignment_id": new_record_id(),
        "contributor_id": new_record_id(),
        "contribution_policy_version_id": contribution_policy_version_id,
        "checker_run_id": new_record_id(),
        "evaluation_request_id": new_record_id(),
        "request_digest": SHA_A,
        "evaluation_generation": 1,
        "result_id": new_record_id(),
        "result_digest": SHA_B,
        "completion_event_id": new_record_id(),
        "creation_decision_id": new_record_id(),
        "binding_decision_id": new_record_id(),
        "input_materialization_evidence_id": new_record_id(),
        "execute_evidence_id": new_record_id(),
        "finalize_evidence_id": new_record_id(),
        "human_review_required": True,
        "replica_id": new_record_id(),
        "content_sha256": SHA_A,
        "byte_count": 0,
        "semantic_manifest_sha256": SHA_B,
        "predecessor_submission_id": None,
        "predecessor_submission_version": None,
        "admission_id": new_record_id(),
        "binding_id": new_record_id(),
        "content_id": new_record_id(),
        "locked_policy": _lineage(contribution_policy_version_id=contribution_policy_version_id),
        "routing_recommendation": "allow_review",
    }
    values.update(changes)
    return values
