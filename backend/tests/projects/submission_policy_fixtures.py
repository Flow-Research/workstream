"""PROJECT sufficiency and submission-policy test prerequisites."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session as db_session
from app.modules.projects.models import GuideSufficiencyReport, PreSubmitCheckerPolicy
from projects.client_fixtures import auth_headers
from committed_guide_fixtures import create_compiled_report_fixture


def project_submission_artifact_policy_body(
    *,
    artifact_path: str = "outputs/answer.md",
    manifest_required: bool = True,
    artifact_hash_required: bool = True,
    rule_hash_required: bool = True,
    packaging: dict | None = None,
) -> dict:
    return {
        "required_artifacts": [
            {
                "key": "answer",
                "path": artifact_path,
                "hash_required": rule_hash_required,
                "required": True,
                "description": "Final answer artifact.",
            }
        ],
        "required_evidence": [
            {
                "key": "reasoning_trace",
                "label": "Reasoning trace",
                "hash_required": rule_hash_required,
                "required": True,
                "description": "Evidence that supports the answer.",
            }
        ],
        "forbidden_artifacts": [
            {
                "pattern": "*.tmp",
                "reason": "Temporary files are not reviewable.",
                "worker_facing_fix": "Remove temporary files before submission.",
            }
        ],
        "attestation_terms": ["project_specific_originality"],
        "manifest_required": manifest_required,
        "artifact_hash_required": artifact_hash_required,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": packaging if packaging is not None else {"package_required": False},
    }


async def create_sufficiency_report(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    snapshot_id: str,
    *,
    status: str = "passed",
    request_headers=None,
) -> dict:
    findings = []
    if status == "blocked":
        findings = [
            {
                "severity": "blocking_gap",
                "code": "missing_rubric",
                "message": "The guide needs a rubric.",
            }
        ]
    if status == "passed_with_warnings":
        findings = [
            {
                "severity": "warning",
                "code": "thin_examples",
                "message": "Examples are thin but usable.",
            }
        ]
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        headers=request_headers if request_headers is not None else auth_headers(),
        json={
            "source_snapshot_id": snapshot_id,
            "status": status,
            "findings": findings,
            "summary": "Guide reviewed.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_submission_artifact_policy(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    snapshot_id: str,
    *,
    policy_body: dict | None = None,
    policy_version: str = "v1",
) -> dict:
    async with db_session.get_session_factory()() as session:
        authoritative = await session.scalar(
            select(GuideSufficiencyReport).where(
                GuideSufficiencyReport.source_snapshot_id == snapshot_id,
                GuideSufficiencyReport.project_setup_run_id.is_not(None),
            )
        )
        diagnostic = await session.scalar(
            select(GuideSufficiencyReport).where(
                GuideSufficiencyReport.source_snapshot_id == snapshot_id,
                GuideSufficiencyReport.project_setup_run_id.is_(None),
            )
        )
    if authoritative is None and diagnostic is not None:
        await create_compiled_report_fixture(diagnostic.id, snapshot_id)
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot_id,
            "policy_version": policy_version,
            "policy_body": policy_body or project_submission_artifact_policy_body(),
            "change_summary": "Initial artifact intake policy.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def approve_submission_artifact_policy(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    policy_id: str | None,
) -> dict:
    from projects.guide_fixtures import read_guide_source_snapshot
    from projects.unified_policy_fixtures import (
        approve_unified_submission_policy, create_unified_submission_policy,
    )

    if policy_id is None:
        snapshot = await read_guide_source_snapshot(project_id, guide_id)
        report = await create_sufficiency_report(client, project_id, guide_id, snapshot["id"])
        policy = await create_unified_submission_policy(report["id"], snapshot["id"])
        policy_id = policy["id"]
    return await approve_unified_submission_policy(project_id, guide_id, policy_id)


async def load_pre_submit_checker_policy(effective_policy: dict) -> dict:
    """Load the compiled project pre-submit checker policy for an effective policy."""
    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy["id"]
            )
        )
        assert pre_submit_checker_policy is not None
        return {
            "id": pre_submit_checker_policy.id,
            "effective_policy_id": pre_submit_checker_policy.effective_policy_id,
            "effective_policy_hash": pre_submit_checker_policy.effective_policy_hash,
            "lifecycle_status": pre_submit_checker_policy.lifecycle_status,
            "compiler_version": pre_submit_checker_policy.compiler_version,
            "compiled_bundle": pre_submit_checker_policy.compiled_bundle,
            "compiled_bundle_hash": pre_submit_checker_policy.compiled_bundle_hash,
            "checker_names": pre_submit_checker_policy.checker_names,
            "checker_configs": pre_submit_checker_policy.checker_configs,
        }
