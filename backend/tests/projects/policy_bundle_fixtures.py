"""Compose one coherent PROJECT policy lineage for downstream tests."""

from __future__ import annotations

from httpx import AsyncClient

from projects.guide_fixtures import read_guide_source_snapshot
from projects.post_submit_fixtures import (
    seed_post_submit_policy_for_downstream_tests,
)
from projects.submission_policy_fixtures import (
    approve_submission_artifact_policy,
    create_submission_artifact_policy,
    create_sufficiency_report,
    force_pre_submit_checker_policy_pending,
    load_pre_submit_checker_policy,
)
from committed_guide_fixtures import create_compiled_report_fixture


async def create_approved_policy_bundle(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    *,
    sufficiency_status: str = "passed",
    compile_pre_submit_checker: bool = True,
) -> dict:
    snapshot = await read_guide_source_snapshot(project_id, guide_id)
    report = await create_sufficiency_report(
        client,
        project_id,
        guide_id,
        snapshot["id"],
        status=sufficiency_status,
    )
    verified_report_id = await create_compiled_report_fixture(report["id"], snapshot["id"])
    report = {**report, "id": verified_report_id}
    policy = await create_submission_artifact_policy(client, project_id, guide_id, snapshot["id"])
    effective = await approve_submission_artifact_policy(
        client,
        project_id,
        guide_id,
        policy["id"],
    )
    compiled_pre_submit_checker = await load_pre_submit_checker_policy(effective)
    if compile_pre_submit_checker:
        assert compiled_pre_submit_checker["lifecycle_status"] == "compiled"
        post_submit_checker_policy = await seed_post_submit_policy_for_downstream_tests(
            project_id=project_id, guide_id=guide_id, source_snapshot=snapshot,
            pre_submit_checker_policy=compiled_pre_submit_checker,
        )
    else:
        await force_pre_submit_checker_policy_pending(effective)
        compiled_pre_submit_checker = None
        post_submit_checker_policy = None
    return {
        "source_snapshot": snapshot,
        "sufficiency_report": report,
        "submission_artifact_policy": policy,
        "effective_policy": effective,
        "pre_submit_checker_policy": compiled_pre_submit_checker,
        "post_submit_checker_policy": post_submit_checker_policy,
    }
