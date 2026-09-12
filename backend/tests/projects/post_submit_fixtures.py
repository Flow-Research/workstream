"""PROJECT generated post-submit fixtures, not agent-execution proof."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


from app.db import session as db_session
from app.modules.projects.models import PostSubmitCheckerPolicy, ProjectGuide
from app.modules.projects.post_submit_policy import (
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
)


async def seed_post_submit_policy_for_downstream_tests(
    *,
    project_id: str,
    guide_id: str,
    source_snapshot: dict,
    pre_submit_checker_policy: dict,
    required_checkers: list[str] | None = None,
    warning_checkers: list[str] | None = None,
    blocking_severities: list[str] | None = None,
    approved_by_actor: str = "project-manager-subject",
) -> dict:
    """Seed the post-submit policy prerequisite without claiming setup execution."""
    async with db_session.get_session_factory()() as session:
        guide = await session.get(ProjectGuide, guide_id)
        assert guide is not None
        spec = build_project_post_submit_checker_spec(
            project_id=project_id,
            guide_version=guide.version,
            required_checkers=[] if required_checkers is None else required_checkers,
            warning_checkers=[] if warning_checkers is None else warning_checkers,
            blocking_severities=blocking_severities,
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
            blocking_severities=list(compiled.blocking_severities),
            policy_hash=compiled.policy_hash,
            policy_body=compiled.policy_body,
            lifecycle_status="approved",
            approved_by_role="project_manager",
            approved_by_actor=approved_by_actor,
            approved_at=datetime.now(UTC),
            created_by=approved_by_actor,
        )
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
