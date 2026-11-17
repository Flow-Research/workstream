"""Recover historical acceptance context without renewing contributor eligibility."""
import json
from uuid import UUID
from sqlalchemy import func, select, text

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api import (
    SubmissionCreationUnavailable, SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences, TaskPolicyLineage, TaskSubmissionContextFacts,
)
from app.modules.tasks.models import Submission, TaskAssignment
from app.modules.tasks.submission_attempts import COVERAGE_RETURN_REASON


async def accepted_submission_context(session, task, request, *, operation_id,
                                      snapshot_sha256, eligible_status, remediation_id):
    """Read immutable accepted lineage under TASK custody; deadlines were decided at T4."""
    invalid = SubmissionCreationUnavailable("accepted submission custody differs")
    snapshot = await session.scalar(text("SELECT public.submission_intake_task_snapshot(t) "
        "FROM public.workstream_tasks t WHERE id=:id"), {"id": task.id})
    assignment = await session.get(TaskAssignment, str(request.assignment_id))
    if (task.status != "evaluation_pending" or task.active_submission_operation_id != str(operation_id)
            or canonical_json_hash(snapshot) != snapshot_sha256 or assignment is None
            or assignment.task_id != task.id or assignment.contributor_id != str(request.contributor_id)
            or task.assigned_to != str(request.contributor_id)):
        raise invalid
    predecessor = None
    if request.predecessor_submission_id:
        previous = await session.get(Submission, str(request.predecessor_submission_id))
        if (previous is None or previous.task_id != task.id
                or previous.task_assignment_id != assignment.id or previous.contributor_id != assignment.contributor_id):
            raise invalid
        count = await session.scalar(select(func.count(Submission.id)).where(
            Submission.task_assignment_id == assignment.id, Submission.version <= previous.version,
            Submission.status_reason.is_distinct_from(COVERAGE_RETURN_REASON)))
        predecessor = SubmissionPredecessorFacts(UUID(previous.id), previous.version, count)
    policy = TaskPolicyLineage.model_validate_json(json.dumps({
        name: str(value) if isinstance(value, UUID) else value
        for name in TaskPolicyLineage.model_fields for value in (getattr(task, name),)
    }))
    refs = TaskLockedProjectContextReferences(
        project_id=UUID(task.project_id), locked_contribution_policy_version_id=policy.locked_contribution_policy_version_id,
        guide_version=policy.locked_guide_version, source_snapshot_id=policy.locked_guide_source_snapshot_id,
        source_snapshot_hash=policy.locked_guide_source_snapshot_hash,
        effective_policy_id=policy.locked_effective_project_submission_artifact_policy_id,
        effective_policy_hash=policy.locked_effective_project_submission_artifact_policy_hash,
        pre_submit_policy_id=policy.locked_pre_submit_checker_policy_id,
        pre_submit_policy_bundle_hash=policy.locked_pre_submit_checker_bundle_hash,
    )
    return TaskSubmissionContextFacts(
        task_id=request.task_id, assignment_id=request.assignment_id, contributor_id=request.contributor_id,
        status=eligible_status, kind="checker_remediation" if predecessor else "initial", predecessor=predecessor,
        submitter_contribution_policy_version_id=assignment.submitter_contribution_policy_version_id,
        locked_project_context=refs, locked_policy=policy, acceptance_criteria=task.acceptance_criteria,
        checker_remediation_manifest_id=remediation_id,
    )
