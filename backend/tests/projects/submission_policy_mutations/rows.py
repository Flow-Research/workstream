"""Passive, fresh submission-policy rows; no persistence or authorization rules."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.projects import submission_policy_mutation_service as module
from projects.submission_policy_fixtures import project_submission_artifact_policy_body

PROJECT, GUIDE, SNAPSHOT, SETUP, REPORT, ACTOR, LINK, GRANT, KEY, POLICY, OPERATION = (
    UUID(int=value) for value in range(1, 12)
)
NOW = datetime(2026, 1, 1, tzinfo=UTC)
SNAPSHOT_HASH = "sha256:" + "a" * 64
REQUEST_HASH = "sha256:" + "b" * 64


def lineage():
    return module._ManualPolicyLineage(
        guide_version="v1",
        snapshot_id=SNAPSHOT,
        snapshot_hash=SNAPSHOT_HASH,
        setup_run_id=SETUP,
        setup_generation=4,
        report_id=REPORT,
        report_status="passed",
        acknowledgement_digest=None,
        source_material_refs=("guide-source:item",),
    )


def predecessor():
    body = project_submission_artifact_policy_body()
    body.update(
        schema_version="project_submission_artifact_policy.v1",
        allowed_storage_schemes=["local", "r2", "s3"],
        packaging={"package_required": False, "allowed_package_formats": []},
    )
    return SimpleNamespace(
        id=str(POLICY),
        project_id=str(PROJECT),
        guide_id=str(GUIDE),
        source_snapshot_id=str(SNAPSHOT),
        lifecycle_status="draft",
        derivation_source="manual_admin_derivation",
        policy_version="manual-v1",
        policy_body=body,
        policy_hash=canonical_json_hash(body),
        change_summary="initial",
    )


def replay_facts():
    resource = module.ProjectSubmissionArtifactPolicyMutationResourceContext(
        resource_type="project_submission_artifact_policy_mutation",
        resource_id=POLICY,
        operation_id=OPERATION,
        request_digest=REQUEST_HASH,
        scope_project_id=PROJECT,
        guide_id=GUIDE,
        guide_version="v1",
        source_snapshot_id=SNAPSHOT,
        source_snapshot_hash=SNAPSHOT_HASH,
        target_kind="create",
        execution_kind="human",
        policy_id=POLICY,
        policy_version="manual-v1",
        policy_generation=4,
        setup_generation=4,
        sufficiency_report_id=REPORT,
        sufficiency_status="passed",
    )
    return module.SubmissionPolicyReplayFacts(
        actor_profile_id=str(ACTOR),
        identity_link_id=str(LINK),
        action_id=module.ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE.value,
        idempotency_key=KEY,
        request_digest=REQUEST_HASH,
        resource_context=resource,
        operation_id=OPERATION,
        project_id=str(PROJECT),
        guide_id=str(GUIDE),
        source_snapshot_id=str(SNAPSHOT),
        policy_id=str(POLICY),
        setup_generation=4,
    )


def warning_report():
    return SimpleNamespace(
        id=str(REPORT),
        status="passed_with_warnings",
        warnings_acknowledged_by_actor_profile_id=str(ACTOR),
        warnings_acknowledged_via_identity_link_id=str(LINK),
        warnings_acknowledged_by_admin_role_grant_id=GRANT,
        warning_acknowledgement_scope_type="project",
        warning_acknowledgement_scope_project_id=str(PROJECT),
        warning_acknowledgement_action_id="project.guide_sufficiency.warnings.acknowledge",
        warning_acknowledgement_decision_event_id=str(UUID(int=20)),
        warnings_acknowledged_at=NOW,
    )


def unacknowledged_report(status="passed"):
    return SimpleNamespace(
        id=str(REPORT),
        status=status,
        project_setup_run_id=str(SETUP),
        setup_generation=4,
        agent_material_sha256="sha256:" + "c" * 64,
        agent_material_byte_count=128,
        source_snapshot_hash=SNAPSHOT_HASH,
        warnings_acknowledged_by_actor_profile_id=None,
        warnings_acknowledged_via_identity_link_id=None,
        warnings_acknowledged_by_admin_role_grant_id=None,
        warning_acknowledgement_scope_type=None,
        warning_acknowledgement_scope_project_id=None,
        warning_acknowledgement_action_id=None,
        warning_acknowledgement_decision_event_id=None,
        warnings_acknowledged_at=None,
    )
