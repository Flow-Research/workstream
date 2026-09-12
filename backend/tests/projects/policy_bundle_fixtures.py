"""Compose one coherent PROJECT policy lineage for downstream tests."""

from __future__ import annotations

from httpx import AsyncClient

from projects.guide_fixtures import read_guide_source_snapshot
from projects.post_submit_fixtures import (
    seed_post_submit_policy_for_downstream_tests,
)
from projects.submission_policy_fixtures import (
    approve_submission_artifact_policy,
    create_sufficiency_report,
    load_pre_submit_checker_policy,
)
from projects.unified_policy_fixtures import create_unified_submission_policy


async def create_approved_policy_bundle(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    *,
    sufficiency_status: str = "passed",
    artifact_proposal=None,
    request_headers=None,
    post_submit_required_checkers=None,
    post_submit_warning_checkers=None,
    post_submit_blocking_severities=None,
) -> dict:
    snapshot = await read_guide_source_snapshot(project_id, guide_id)
    report = await create_sufficiency_report(
        client,
        project_id,
        guide_id,
        snapshot["id"],
        status=sufficiency_status,
        request_headers=request_headers,
    )
    policy = await create_unified_submission_policy(report["id"], snapshot["id"], proposal=artifact_proposal)
    from app.db import session as db_session
    from app.modules.projects.models import ProjectSetupRun
    from sqlalchemy import select
    async with db_session.get_session_factory()() as session:
        setup = (await session.scalars(select(ProjectSetupRun).where(
            ProjectSetupRun.guide_id == guide_id,
        ))).one()
        report = {**report, "id": setup.output_sufficiency_report_id}
    effective = await approve_submission_artifact_policy(
        client,
        project_id,
        guide_id,
        policy["id"],
    )
    compiled_pre_submit_checker = await load_pre_submit_checker_policy(effective)
    assert compiled_pre_submit_checker["lifecycle_status"] == "compiled"
    post_submit_checker_policy = await seed_post_submit_policy_for_downstream_tests(
        project_id=project_id, guide_id=guide_id, source_snapshot=snapshot,
        pre_submit_checker_policy=compiled_pre_submit_checker,
        required_checkers=post_submit_required_checkers,
        warning_checkers=post_submit_warning_checkers,
        blocking_severities=post_submit_blocking_severities,
    )
    return {
        "source_snapshot": snapshot,
        "sufficiency_report": report,
        "submission_artifact_policy": policy,
        "effective_policy": effective,
        "pre_submit_checker_policy": compiled_pre_submit_checker,
        "post_submit_checker_policy": post_submit_checker_policy,
    }
