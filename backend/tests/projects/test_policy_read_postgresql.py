"""Persisted approval and public policy reads retain exact selected checker custody."""
from __future__ import annotations

from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session as db_session
from app.modules.checkers.api.external_policy import validate_stored_external_pre_policy
from app.modules.projects.models import PreSubmitCheckerPolicy, SubmissionArtifactPolicy
from projects.client_fixtures import (
    auth_headers,
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import (
    complete_guide_payload, create_guide, create_project, read_guide_source_snapshot,
)
from projects.policy_bundle_fixtures import create_approved_policy_bundle
from projects.submission_policy_fixtures import approve_submission_artifact_policy, create_sufficiency_report
from tests.projects.guide_activation.read_fixtures import activate_approved_guide


async def test_submission_artifact_policy_approval_persists_effective_policy_hash(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    report = await create_sufficiency_report(project_client, project["id"], guide["id"], snapshot["id"])
    from projects.unified_policy_fixtures import create_unified_submission_policy
    policy = await create_unified_submission_policy(report["id"], snapshot["id"])

    effective = await approve_submission_artifact_policy(
        project_client,
        project["id"],
        guide["id"],
        policy["id"],
    )

    assert policy["lifecycle_status"] == "draft"
    assert policy["policy_hash"].startswith("sha256:")
    assert effective["source_snapshot_id"] == snapshot["id"]
    assert effective["source_snapshot_hash"] == snapshot["bundle_hash"]
    assert effective["submission_artifact_policy_hash"] == policy["policy_hash"]
    assert effective["effective_policy_hash"].startswith("sha256:")
    assert effective["effective_policy"]["artifact_hash_algorithm"] == "sha256"

    async with db_session.get_session_factory()() as session:
        persisted_policy = await session.get(SubmissionArtifactPolicy, policy["id"])
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective["id"]
            )
        )

    assert persisted_policy is not None
    assert persisted_policy.lifecycle_status == "approved"
    assert persisted_policy.approved_by_role == "project_manager"
    assert persisted_policy.approved_by_actor == persisted_policy.approved_by_actor_profile_id
    assert persisted_policy.approved_by_actor != policy["created_by"]
    assert persisted_policy.approved_at is not None
    assert persisted_policy.derivation_source == "unified_compilation"
    assert len(persisted_policy.source_material_refs) == len(snapshot["items"])
    assert all(
        ref.startswith("guide-document:") and "#sha256:" in ref
        for ref in persisted_policy.source_material_refs
    )
    assert pre_submit_checker_policy.lifecycle_status == "compiled"
    assert pre_submit_checker_policy.effective_policy_hash == effective["effective_policy_hash"]
    assert pre_submit_checker_policy.compiler_version == "external_checker_policy.v1"
    locked_pre_policy = validate_stored_external_pre_policy(
        pre_submit_checker_policy.compiled_bundle
    )
    assert locked_pre_policy.policy_sha256 == pre_submit_checker_policy.compiled_bundle_hash
    assert [(e.requirement_id, e.stage, e.registry.capability_id, e.registry.capability_version, e.registry.image_digest, e.configuration) for e in locked_pre_policy.entries] == [("project.archive_rules", "pre_submit", "acme.safe_archive", "v1.2.3", "sha256:" + "a" * 64, {})]


async def test_active_guide_retrieval_returns_exact_policy_bundle(project_client: AsyncClient) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(project_client, project["id"], guide["id"])

    activation = await activate_approved_guide(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )
    active = await project_client.get(
        f"/api/v1/projects/{project['id']}/active-guide",
        headers=auth_headers(),
    )
    effective_read = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/"
        "effective-submission-artifact-policy",
        headers=auth_headers(),
    )
    checker_read = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/pre-submit-checker-policy",
        headers=auth_headers(),
    )

    assert active.status_code == 200, active.text
    assert effective_read.status_code == 200, effective_read.text
    assert checker_read.status_code == 200, checker_read.text
    assert set(effective_read.json()) == {
        "id",
        "project_id",
        "guide_id",
        "guide_version",
        "source_snapshot_id",
        "source_snapshot_hash",
        "submission_artifact_policy_id",
        "submission_artifact_policy_hash",
        "lifecycle_status",
        "merge_algorithm_version",
        "effective_policy",
        "effective_policy_hash",
        "created_by",
        "created_at",
        "supersedes_effective_policy_id",
        "superseded_at",
    }
    assert set(checker_read.json()) == {
        "id",
        "project_id",
        "guide_id",
        "guide_version",
        "source_snapshot_id",
        "source_snapshot_hash",
        "effective_policy_id",
        "effective_policy_hash",
        "lifecycle_status",
        "compiler_version",
        "compiled_bundle_hash",
        "checker_names",
        "created_by",
        "created_at",
        "supersedes_pre_submit_checker_policy_id",
        "superseded_at",
    }
    assert set(active.json()) == {
        "guide",
        "guide_source_snapshot",
        "guide_sufficiency_report",
        "submission_artifact_policy",
        "effective_submission_artifact_policy",
        "pre_submit_checker_policy",
        "post_submit_checker_policy",
        "review_policy",
        "revision_policy",
    }
    assert effective_read.json()["id"] == bundle["effective_policy"]["id"]
    assert checker_read.json()["effective_policy_id"] == bundle["effective_policy"]["id"]
    assert "compiled_bundle" not in checker_read.json()
    assert "checker_configs" not in checker_read.json()
    assert active.json()["guide"]["status"] == "active"
    assert active.json()["guide"]["version"] == "v1"
    assert active.json()["guide"]["approved_by"] == guide["created_by"]
    assert active.json()["guide"]["effective_at"] is not None
    assert activation["guide"]["approved_by"] == guide["created_by"]
    assert datetime.fromisoformat(activation["guide"]["effective_at"]) == datetime.fromisoformat(active.json()["guide"]["effective_at"])
    assert active.json()["post_submit_checker_policy"]["required_checkers"] == ["acme.safe_archive"]
    assert (
        active.json()["guide_source_snapshot"]["bundle_hash"]
        == (bundle["source_snapshot"]["bundle_hash"])
    )
    assert active.json()["guide_sufficiency_report"]["status"] == "passed"
    assert active.json()["submission_artifact_policy"]["lifecycle_status"] == "approved"
    assert (
        active.json()["effective_submission_artifact_policy"]["effective_policy_hash"]
        == (bundle["effective_policy"]["effective_policy_hash"])
    )
    assert active.json()["pre_submit_checker_policy"]["lifecycle_status"] == "compiled"
    assert (
        active.json()["pre_submit_checker_policy"]["effective_policy_id"]
        == (bundle["effective_policy"]["id"])
    )
    assert (
        active.json()["pre_submit_checker_policy"]["compiled_bundle_hash"]
        == (bundle["pre_submit_checker_policy"]["compiled_bundle_hash"])
    )
    assert "compiled_bundle" not in active.json()["pre_submit_checker_policy"]
    assert "payment_policy" not in active.json()
    assert "review_policy" in active.json()
    assert (
        active.json()["pre_submit_checker_policy"]["checker_names"]
        == (bundle["pre_submit_checker_policy"]["checker_names"])
    )
    assert (
        active.json()["pre_submit_checker_policy"]["checker_configs"]
        == (bundle["pre_submit_checker_policy"]["checker_configs"])
    )
    assert active.json()["revision_policy"]["max_revision_rounds"] == 7
    assert "auto_reject_after_limit" not in active.json()["revision_policy"]
