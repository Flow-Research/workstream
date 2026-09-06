"""PROJECT generated post-submit fixtures, not agent-execution proof."""

from __future__ import annotations

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session as db_session
from app.modules.projects.models import PostSubmitCheckerPolicy, ProjectGuide, ProjectSetupRun
from app.modules.projects.post_submit_policy import (
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
)
from projects.client_fixtures import auth_headers


async def create_generated_post_submit_setup_output(
    *,
    project_id: str,
    guide_id: str,
    source_snapshot: dict,
    sufficiency_report: dict,
    submission_artifact_policy: dict,
    pre_submit_checker_policy: dict,
) -> dict:
    """Persist the generated post-submit setup output used by activation tests."""
    async with db_session.get_session_factory()() as session:
        guide = await session.get(ProjectGuide, guide_id)
        assert guide is not None
        spec = build_project_post_submit_checker_spec(
            project_id=project_id,
            guide_version=guide.version,
            required_checkers=["check_policy_context_present"],
            warning_checkers=[],
            blocking_severities=["critical", "high"],
        )
        compiled = compile_project_post_submit_checker_spec(
            project_id=project_id,
            guide_version=guide.version,
            spec=spec,
        )
        post_submit_policy = PostSubmitCheckerPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide.version,
            source_snapshot_id=source_snapshot["id"],
            source_snapshot_hash=source_snapshot["bundle_hash"],
            effective_policy_id=pre_submit_checker_policy["effective_policy_id"],
            effective_policy_hash=pre_submit_checker_policy["effective_policy_hash"],
            pre_submit_checker_policy_id=pre_submit_checker_policy["id"],
            pre_submit_checker_bundle_hash=pre_submit_checker_policy["compiled_bundle_hash"],
            required_checkers=compiled.required_checkers,
            warning_checkers=compiled.warning_checkers,
            blocking_severities=compiled.blocking_severities,
            policy_hash=compiled.policy_hash,
            policy_body=compiled.policy_body,
            lifecycle_status="compiled",
            created_by="project-manager-subject",
        )
        setup_run = await session.scalar(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.source_snapshot_id == source_snapshot["id"])
            .order_by(ProjectSetupRun.setup_generation.desc())
            .limit(1)
        )
        if setup_run is None:
            setup_run = ProjectSetupRun(
                id=str(uuid4()),
                project_id=project_id,
                guide_id=guide_id,
                guide_version=guide.version,
                source_snapshot_id=source_snapshot["id"],
                source_snapshot_hash=source_snapshot["bundle_hash"],
                setup_generation=source_snapshot["manifest_json"]["generation"],
                status="queued",
                current_step="queued",
                created_by="test-project-manager",
            )
            session.add(setup_run)
            await session.commit()
        setup_run.status = "post_submit_policy_compiled"
        setup_run.current_step = "post_submit_checker_policy_compilation"
        setup_run.output_sufficiency_report_id = sufficiency_report["id"]
        setup_run.output_submission_artifact_policy_id = submission_artifact_policy["id"]
        setup_run.output_post_submit_checker_policy_id = post_submit_policy.id
        setup_run.post_submit_derivation_summary = {
            "status": "compiled",
            "post_submit_checker_policy_id": post_submit_policy.id,
            "required_checkers": post_submit_policy.required_checkers,
            "warning_checkers": post_submit_policy.warning_checkers,
            "blocking_severities": post_submit_policy.blocking_severities,
        }
        session.add(post_submit_policy)
        await session.commit()
        return {
            "id": post_submit_policy.id,
            "required_checkers": post_submit_policy.required_checkers,
            "warning_checkers": post_submit_policy.warning_checkers,
            "blocking_severities": post_submit_policy.blocking_severities,
            "policy_hash": post_submit_policy.policy_hash,
            "policy_body": post_submit_policy.policy_body,
            "lifecycle_status": post_submit_policy.lifecycle_status,
        }


async def approve_post_submit_checker_policy(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
) -> dict:
    """Approve the current compiled project post-submit checker policy by API."""
    response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/approve",
        headers=auth_headers(),
        json={},
    )
    assert response.status_code == 200, response.text
    policy = response.json()["post_submit_checker_policy"]
    assert policy is not None
    return policy
