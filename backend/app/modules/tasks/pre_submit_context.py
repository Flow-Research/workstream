"""Locked database context assembly for pre-submit evidence persistence."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.checkers.catalogue import PreSubmissionCheckerCatalogue
from app.modules.checkers.effective_plan import (
    EffectivePreSubmissionExecutionPlan,
    EffectivePreSubmissionPlanLineage,
    compile_effective_pre_submission_execution_plan,
)
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    PreSubmitCheckerPolicy,
    ProjectGuide,
)
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask


class PreSubmitLockedContextInvalid(RuntimeError):
    """Fail closed when preparation no longer matches task-owned state."""


@dataclass(frozen=True, slots=True)
class LockedPreSubmitContext:
    """Exact locked rows revalidated immediately before evidence persistence."""

    actor_profile_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    locked_guide_sha256: str
    effective_policy_id: UUID
    effective_policy_sha256: str
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str
    effective_policy: dict[str, object]
    compiled_pre_submit_bundle: dict[str, object]


async def load_locked_pre_submit_context(
    session: AsyncSession,
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
    task_id: UUID,
    assignment_id: UUID,
    predecessor_submission_id: UUID | None,
    include_actor_identity_locks: bool = True,
) -> LockedPreSubmitContext:
    """Lock and revalidate task, assignment, predecessor, guide, and policy lineage."""
    actor_profile = identity_link = None
    if include_actor_identity_locks:
        actor_profile = await session.scalar(
            select(ActorProfile).where(ActorProfile.id == str(actor_profile_id)).with_for_update()
        )
        identity_link = await session.scalar(
            select(ActorIdentityLink)
            .where(ActorIdentityLink.id == str(identity_link_id))
            .with_for_update()
        )
    task = await session.scalar(
        select(WorkstreamTask).where(WorkstreamTask.id == str(task_id)).with_for_update()
    )
    assignment = await session.scalar(
        select(TaskAssignment).where(TaskAssignment.id == str(assignment_id)).with_for_update()
    )
    if (
        (
            include_actor_identity_locks
            and (
                actor_profile is None
                or actor_profile.status != "active"
                or identity_link is None
                or identity_link.actor_profile_id != str(actor_profile_id)
                or identity_link.status != "active"
            )
        )
        or task is None
        or assignment is None
        or assignment.task_id != str(task_id)
        or assignment.contributor_id != str(actor_profile_id)
        or assignment.status != "active"
        or task.assigned_to != str(actor_profile_id)
        or task.status not in {"in_progress", "needs_revision"}
        or task.locked_guide_version is None
        or task.locked_guide_source_snapshot_id is None
        or task.locked_guide_source_snapshot_hash is None
        or task.locked_effective_project_submission_artifact_policy_id is None
        or task.locked_effective_project_submission_artifact_policy_hash is None
        or task.locked_pre_submit_checker_policy_id is None
        or task.locked_pre_submit_checker_bundle_hash is None
    ):
        raise PreSubmitLockedContextInvalid("pre_submit_locked_context_invalid")
    latest_submission = await session.scalar(
        select(Submission)
        .where(Submission.task_id == str(task_id))
        .order_by(Submission.version.desc())
        .limit(1)
        .with_for_update()
    )
    latest_submission_id = latest_submission.id if latest_submission is not None else None
    if latest_submission_id != (
        str(predecessor_submission_id) if predecessor_submission_id is not None else None
    ):
        raise PreSubmitLockedContextInvalid("pre_submit_predecessor_changed")
    guide = await session.scalar(
        select(ProjectGuide)
        .where(
            ProjectGuide.project_id == task.project_id,
            ProjectGuide.version == task.locked_guide_version,
        )
        .with_for_update()
    )
    effective_policy = await session.scalar(
        select(EffectiveProjectSubmissionArtifactPolicy)
        .where(
            EffectiveProjectSubmissionArtifactPolicy.id
            == task.locked_effective_project_submission_artifact_policy_id,
            EffectiveProjectSubmissionArtifactPolicy.project_id == task.project_id,
            EffectiveProjectSubmissionArtifactPolicy.guide_version == task.locked_guide_version,
            EffectiveProjectSubmissionArtifactPolicy.effective_policy_hash
            == task.locked_effective_project_submission_artifact_policy_hash,
        )
        .with_for_update()
    )
    checker_policy = await session.scalar(
        select(PreSubmitCheckerPolicy)
        .where(
            PreSubmitCheckerPolicy.id == task.locked_pre_submit_checker_policy_id,
            PreSubmitCheckerPolicy.project_id == task.project_id,
            PreSubmitCheckerPolicy.guide_version == task.locked_guide_version,
            PreSubmitCheckerPolicy.effective_policy_id
            == task.locked_effective_project_submission_artifact_policy_id,
            PreSubmitCheckerPolicy.effective_policy_hash
            == task.locked_effective_project_submission_artifact_policy_hash,
            PreSubmitCheckerPolicy.compiled_bundle_hash
            == task.locked_pre_submit_checker_bundle_hash,
            PreSubmitCheckerPolicy.lifecycle_status == "compiled",
        )
        .with_for_update()
    )
    if guide is None or effective_policy is None or checker_policy is None:
        raise PreSubmitLockedContextInvalid("pre_submit_locked_context_changed")
    guide_sha256 = canonical_json_hash(
        {
            "domain": "workstream.locked_task_guide.v1",
            "project_id": task.project_id,
            "guide_id": guide.id,
            "guide_version": guide.version,
            "source_snapshot_id": task.locked_guide_source_snapshot_id,
            "source_snapshot_sha256": task.locked_guide_source_snapshot_hash,
        }
    )
    return LockedPreSubmitContext(
        actor_profile_id=actor_profile_id,
        project_id=UUID(task.project_id),
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=predecessor_submission_id,
        predecessor_submission_version=(
            latest_submission.version if latest_submission is not None else None
        ),
        guide_id=UUID(guide.id),
        guide_version=guide.version,
        source_snapshot_id=UUID(task.locked_guide_source_snapshot_id),
        source_snapshot_sha256=task.locked_guide_source_snapshot_hash,
        locked_guide_sha256=guide_sha256,
        effective_policy_id=UUID(effective_policy.id),
        effective_policy_sha256=effective_policy.effective_policy_hash,
        pre_submit_policy_id=UUID(checker_policy.id),
        pre_submit_policy_sha256=checker_policy.compiled_bundle_hash,
        effective_policy=dict(effective_policy.effective_policy),
        compiled_pre_submit_bundle=dict(checker_policy.compiled_bundle),
    )


def compile_locked_pre_submit_plan(
    context: LockedPreSubmitContext,
    catalogue: PreSubmissionCheckerCatalogue,
) -> EffectivePreSubmissionExecutionPlan:
    """Compile one exact plan from TASK-locked policy rows and the fixed catalogue."""
    guide_version_text = context.guide_version
    if guide_version_text.startswith("v"):
        guide_version_text = guide_version_text[1:]
    try:
        guide_version = int(guide_version_text)
    except ValueError as exc:
        raise PreSubmitLockedContextInvalid("pre_submit_guide_version_invalid") from exc
    return compile_effective_pre_submission_execution_plan(
        lineage=EffectivePreSubmissionPlanLineage(
            project_id=context.project_id,
            guide_id=context.guide_id,
            guide_version=guide_version,
            source_snapshot_id=context.source_snapshot_id,
            source_snapshot_hash=context.source_snapshot_sha256,
            effective_policy_id=context.effective_policy_id,
            effective_policy_hash=context.effective_policy_sha256,
            pre_submit_policy_id=context.pre_submit_policy_id,
            pre_submit_policy_bundle_hash=context.pre_submit_policy_sha256,
        ),
        effective_policy=context.effective_policy,
        compiled_bundle=context.compiled_pre_submit_bundle,
        catalogue=catalogue,
    )


async def load_canonical_submission_version(
    session: AsyncSession, *, submission_id: UUID
) -> int | None:
    """Project TASK-owned immutable Submission version without leaking its model."""
    return await session.scalar(
        select(Submission.version).where(Submission.id == str(submission_id))
    )
