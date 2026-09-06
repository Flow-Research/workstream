"""Controlled diagnostic rows and ports; no persistence or authorization engine."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

from app.modules.authorization.catalogue import ActionId
from app.modules.projects.authorization_reads import authorize_project_diagnostic_read


def make_diagnostic_case() -> SimpleNamespace:
    """Create fresh valid parents and one record before any test mutation."""
    project_id, guide_id, target_id, snapshot_id = (str(uuid4()) for _ in range(4))
    project = SimpleNamespace(id=project_id)
    guide = SimpleNamespace(id=guide_id, project_id=project_id, version="v1")
    target = SimpleNamespace(
        id=target_id,
        project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=f"sha256:{'a' * 64}",
        output_post_submit_checker_policy_id=None,
    )
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=project),
        lock_project_guide=AsyncMock(return_value=guide),
        lock_latest_project_setup_run=AsyncMock(return_value=target),
        lock_guide_sufficiency_reports=AsyncMock(return_value=[target]),
        lock_guide_sufficiency_report=AsyncMock(return_value=target),
        lock_submission_artifact_policies=AsyncMock(return_value=[target]),
        lock_submission_artifact_policy_diagnostic=AsyncMock(return_value=target),
        lock_post_submit_checker_policy=AsyncMock(return_value=None),
    )
    return SimpleNamespace(
        project_id=project_id, guide_id=guide_id, target_id=target_id,
        project=project, guide=guide, target=target, repository=repository,
        authorization=SimpleNamespace(require=AsyncMock()),
    )


def attach_post_submit_policy(case: SimpleNamespace) -> SimpleNamespace:
    """Attach one matching output without validating its business rules."""
    policy = SimpleNamespace(
        id=str(uuid4()), project_id=case.project_id, guide_id=case.guide_id,
        guide_version="v1", source_snapshot_id=case.target.source_snapshot_id,
        source_snapshot_hash=case.target.source_snapshot_hash,
    )
    case.target.output_post_submit_checker_policy_id = policy.id
    case.repository.lock_post_submit_checker_policy.return_value = policy
    return policy


async def read_diagnostic(case: SimpleNamespace, action: ActionId) -> Any:
    """Call real PROJECT composition with the requested immutable selectors."""
    return await authorize_project_diagnostic_read(
        authorization=case.authorization,
        repository=case.repository,
        action_id=action,
        project_id=case.project_id,
        guide_id=case.guide_id,
        target_id=case.target_id,
    )
