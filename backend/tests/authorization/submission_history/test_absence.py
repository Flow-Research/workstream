"""Removed authority and alternate execution cannot re-enter the v0.1 surface."""

from pathlib import Path

from app.main import create_app
from app.schemas.auth import AuthVerificationResult


def test_removed_mutation_and_worker_surface():
    root = Path(__file__).resolve().parents[3] / "app"
    forbidden = (
        "get_registered_actor", "LegacyAuthorizationCompatibilityContext", "ActorContext",
        "normalize_legacy_roles", "dev_auth_roles", "require_any_role", "legacy_actor(",
        "refresh_legacy_identity", "upsert_legacy_identity", "pre_review_gate_system_actor",
        "enqueue_pre_review_gate", "app.workers.checkers", "finalize_submission_if_unlocked",
        "resolve_run_reference", "CheckerHistoryReference",
    )
    for path in root.rglob("*.py"):
        source = path.read_text()
        assert not any(symbol in source for symbol in forbidden), path
    for relative in ("core/permissions.py", "modules/tasks/authorization.py", "modules/checkers/service.py",
                     "modules/checkers/gate_queue.py", "modules/checkers/pre_review_gate.py", "workers/checkers.py"):
        assert not (root / relative).exists()
    paths = create_app().openapi()["paths"]
    assert "/api/v1/submissions/{submission_id}/finalize" not in paths
    assert "post" not in paths["/api/v1/submissions/{submission_id}/checker-runs"]
    assert "/api/v1/checker-runs/{checker_run_id}" not in paths
    assert "/api/v1/projects/{project_id}/checker-runs/{checker_run_id}" not in paths
    assert set(AuthVerificationResult.model_fields) == {"token"}


SUBMISSION_FIELDS = set("id task_id version status summary submitted_at locked_at supersedes_submission_id evidence_items".split())
MANAGER_SUBMISSION_FIELDS = SUBMISSION_FIELDS | set("""contributor_id task_assignment_id contribution_policy_version_id locked_guide_version
    locked_post_submit_checker_policy_id locked_post_submit_checker_policy_version locked_post_submit_checker_policy_hash
    locked_review_policy_id locked_review_policy_generation locked_review_policy_hash
    locked_revision_policy_id locked_revision_policy_generation locked_revision_policy_hash
    locked_guide_source_snapshot_id locked_guide_source_snapshot_hash
    locked_effective_project_submission_artifact_policy_id locked_effective_project_submission_artifact_policy_hash
    locked_pre_submit_checker_policy_id locked_pre_submit_checker_bundle_hash""".split())
RUN_FIELDS = set("id task_id submission_id submission_version status attempt_number supersedes_checker_run_id is_current_for_submission created_at completed_at results".split())
MANAGER_RUN_FIELDS = RUN_FIELDS | set("""routing_recommendation outcome_source trigger_source locked_guide_version
    locked_post_submit_checker_policy_id locked_post_submit_checker_policy_version locked_post_submit_checker_policy_hash
    locked_review_policy_id locked_review_policy_generation locked_review_policy_hash
    locked_revision_policy_id locked_revision_policy_generation locked_revision_policy_hash""".split())
RESULT_FIELDS = set("id checker_name status severity worker_message worker_suggested_fix".split())
MANAGER_RESULT_FIELDS = RESULT_FIELDS | {"message", "blocks_review"}
EVIDENCE_FIELDS = {"id", "type", "label", "size_bytes"}


def test_fixed_public_history_schemas():
    schemas = create_app().openapi()["components"]["schemas"]
    for name, expected in (
        ("ContributorSubmissionHistory", SUBMISSION_FIELDS), ("ManagementSubmissionHistory", MANAGER_SUBMISSION_FIELDS),
        ("ContributorCheckerHistory", RUN_FIELDS), ("ManagementCheckerHistory", MANAGER_RUN_FIELDS),
        ("ContributorCheckerResult", RESULT_FIELDS), ("ManagementCheckerResult", MANAGER_RESULT_FIELDS),
        ("SubmissionEvidenceDescriptor", EVIDENCE_FIELDS),
    ):
        assert schemas[name]["additionalProperties"] is False
        assert set(schemas[name]["properties"]) == expected
