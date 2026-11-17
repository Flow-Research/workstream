"""Compose one coherent PROJECT policy lineage for downstream tests."""

from __future__ import annotations

from httpx import AsyncClient
from tests.checkers.external.support import pre_registry_spec, post_registry_spec

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
    post_submit_registry_spec=post_registry_spec(),
    document_access_factory=None,
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
    policy = await create_unified_submission_policy(
        report["id"],
        snapshot["id"],
        proposal=artifact_proposal,
        post_submit_registry_spec=post_submit_registry_spec,
        document_access_factory=document_access_factory,
    )
    from app.db import session as db_session
    from app.modules.projects.models import ProjectSetupRun
    from sqlalchemy import select
    async with db_session.get_session_factory()() as session:
        setup = (await session.scalars(select(ProjectSetupRun).where(
            ProjectSetupRun.guide_id == guide_id,
        ))).one()
        report = {**report, "id": setup.output_sufficiency_report_id}
    from tests.projects.guide_activation.source_fixtures import _prepare_human_attachments
    choices = await _prepare_human_attachments(
        db_session.get_session_factory(), project_id,
        pre_registry_spec(), post_submit_registry_spec, None, None,
    )
    effective = await approve_submission_artifact_policy(
        client,
        project_id,
        guide_id,
        policy["id"],
        pre_submit_attachments=choices["pre_submit_attachments"],
        post_submit_attachments=choices["post_submit_attachments"],
    )
    compiled_pre_submit_checker = await load_pre_submit_checker_policy(effective)
    assert compiled_pre_submit_checker["lifecycle_status"] == "compiled"
    post_submit_checker_policy = await seed_post_submit_policy_for_downstream_tests(
        project_id=project_id, guide_id=guide_id, source_snapshot=snapshot,
        pre_submit_checker_policy=compiled_pre_submit_checker, sessions=db_session.get_session_factory(),
    )
    if post_submit_registry_spec is not None:
        selected = post_submit_checker_policy["policy_body"]["entries"]
        assert len(selected) == 1
        assert selected[0]["requirement_id"] == "project.post_evidence"
        assert selected[0]["registry"]["entry_digest"] == post_submit_registry_spec.spec_digest
    return {
        "source_snapshot": snapshot,
        "sufficiency_report": report,
        "submission_artifact_policy": policy,
        "effective_policy": effective,
        "pre_submit_checker_policy": compiled_pre_submit_checker,
        "post_submit_checker_policy": post_submit_checker_policy,
    }
