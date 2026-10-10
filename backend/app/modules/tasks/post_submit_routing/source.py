"""Prepare exact semantic routing source facts without publishing or authorizing."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import EvaluationCompletion, EvaluationCoordinationPort
from app.modules.projects.api import (
    ProjectLockedPolicyContextPort, ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitSourceProposal, TaskRoutingSourcePreparation,
)
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.post_submit_routing.requests import (
    TaskRoutingRequests, TaskRoutingRequestUnavailable, require_routing_transaction,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.models import Submission, SubmissionDispatch
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.service import TaskService


class TaskRoutingSourcePreparer:
    """Retain caller locks and stage only the existing routing request identity."""

    def __init__(
        self, session: AsyncSession, *, evaluations: EvaluationCoordinationPort,
        projects: ProjectLockedPolicyContextPort,
    ) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._requests = TaskRoutingRequests(session, evaluations)
        self._projects = projects

    async def prepare(
        self, event_id: UUID, completion: EvaluationCompletion,
    ) -> TaskRoutingSourcePreparation:
        """Resolve TASK then PROJECTS before retaining CHECKERS currentness custody."""
        await require_routing_transaction(self._session)
        completion = EvaluationCompletion.model_validate_json(completion.model_dump_json())
        with self._session.no_autoflush:
            return await self._prepare(event_id, completion)

    async def _prepare(self, event_id, completion):
        task = await self._tasks.lock_project_task(completion.project_id, completion.task_id)
        if task is None or task.status not in {"evaluation_pending", "review_pending", "accepted"}:
            raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        retained = await self._session.scalar(
            select(TaskPostSubmitRoutingManifest).where(
                TaskPostSubmitRoutingManifest.project_id == str(completion.project_id),
                TaskPostSubmitRoutingManifest.task_id == str(completion.task_id),
                TaskPostSubmitRoutingManifest.submission_id == str(completion.submission_id),
                TaskPostSubmitRoutingManifest.completion_event_id == event_id,
            )
        )
        if (task.status != "evaluation_pending") != (retained is not None):
            raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        # Read selectors without taking a Submission lock ahead of Assignment.
        submission = await self._tasks.get_latest_submission_for_task(str(completion.task_id))
        if submission is None or submission.id != str(completion.submission_id):
            raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        assignment = await self._tasks.lock_accepted_assignment(
            project_id=completion.project_id, task_id=completion.task_id,
            assignment_id=UUID(submission.task_assignment_id),
        )
        submission = await self._tasks.get_latest_submission_for_task(
            str(completion.task_id), for_update=True, populate_existing=True,
        )
        if (
            assignment is None
            or submission is None
            or not (
                submission.id == str(completion.submission_id)
                and submission.task_assignment_id == assignment.id
                and assignment.status == ("completed" if task.status == "accepted" else "active")
                and assignment.released_at is None
                and assignment.accepted_at is not None
                and submission.contributor_id == assignment.contributor_id == task.assigned_to
                and submission.contribution_policy_version_id
                == assignment.submitter_contribution_policy_version_id
                == task.locked_contribution_policy_version_id
            )
        ):
            raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        try:
            context = await self._projects.lock_locked_policy_context(ProjectLockedPolicyContextRequest(
                project_id=completion.project_id, guide_version=submission.locked_guide_version,
                source_snapshot_id=UUID(submission.locked_guide_source_snapshot_id),
                source_snapshot_hash=submission.locked_guide_source_snapshot_hash,
                effective_policy_id=UUID(submission.locked_effective_project_submission_artifact_policy_id),
                effective_policy_hash=submission.locked_effective_project_submission_artifact_policy_hash,
                pre_submit_policy_id=UUID(submission.locked_pre_submit_checker_policy_id),
                pre_submit_policy_bundle_hash=submission.locked_pre_submit_checker_bundle_hash,
            ))
            stamps = TaskService._policy_stamps(context)
            if any(getattr(task, key) != value for key, value in stamps.items()):
                raise ValueError("task policy differs")
            fields = {}
            for key in TaskPolicyLineage.model_fields:
                value = getattr(submission, key, None)
                if key == "locked_contribution_policy_version_id":
                    value = submission.contribution_policy_version_id
                if key.endswith("_id"):
                    value = UUID(str(value))
                fields[key] = value
            lineage = TaskPolicyLineage(**fields)
            for key in TaskPolicyLineage.model_fields:
                value = getattr(task, key)
                if key.endswith("_id"):
                    value = UUID(str(value))
                if value != getattr(lineage, key):
                    raise ValueError("submission policy differs")
            human_review_required = json.loads(context.review_policy.value)["human_review_required"]
        except (ProjectLockedPolicyContextUnavailable, ValueError, TypeError, KeyError) as exc:
            raise TaskRoutingRequestUnavailable("routing_source_unavailable") from exc
        request, verified = await self._requests._stage(event_id, completion)
        material = verified.material
        if not (
            material.admission_id == UUID(submission.submission_bundle_admission_id)
            and material.binding_id == UUID(submission.artifact_binding_id)
            and material.content_id == UUID(submission.artifact_content_id)
        ):
            raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        dispatch = await self._session.scalar(
            select(SubmissionDispatch).where(
                SubmissionDispatch.project_id == str(completion.project_id),
                SubmissionDispatch.task_id == str(completion.task_id),
                SubmissionDispatch.submission_id == submission.id,
                SubmissionDispatch.submission_version == submission.version,
                SubmissionDispatch.admission_id == submission.submission_bundle_admission_id,
                SubmissionDispatch.artifact_binding_id == submission.artifact_binding_id,
                SubmissionDispatch.artifact_content_id == submission.artifact_content_id,
            )
        )
        if dispatch is None:
            raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        predecessor = None
        if submission.supersedes_submission_id:
            predecessor = await self._session.scalar(select(Submission).where(
                Submission.id == submission.supersedes_submission_id,
                Submission.task_id == submission.task_id,
            ))
            if predecessor is None or predecessor.task_id != submission.task_id:
                raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        source = TaskPostSubmitSourceProposal(
            id=request.routing_manifest_id,
            project_id=completion.project_id,
            task_id=completion.task_id,
            submission_id=completion.submission_id,
            submission_version=verified.submission_version,
            assignment_id=UUID(assignment.id),
            contributor_id=UUID(submission.contributor_id),
            contribution_policy_version_id=submission.contribution_policy_version_id,
            checker_run_id=request.checker_run_id,
            evaluation_request_id=request.evaluation_request_id,
            request_digest=request.evaluation_request_digest,
            evaluation_generation=request.evaluation_generation,
            result_id=request.result_id,
            result_digest=request.result_digest,
            completion_event_id=event_id,
            creation_decision_id=UUID(dispatch.creation_decision_id),
            binding_decision_id=UUID(dispatch.binding_decision_id),
            input_materialization_evidence_id=verified.input_materialization_evidence_id,
            execute_evidence_id=verified.completion.execute_evidence_id,
            finalize_evidence_id=verified.completion.finalize_evidence_id,
            human_review_required=human_review_required,
            predecessor_submission_id=UUID(predecessor.id) if predecessor else None,
            predecessor_submission_version=predecessor.version if predecessor else None,
            locked_policy=lineage,
            routing_recommendation="allow_review",
            **material.model_dump(exclude={"submission_id", "submission_version"}),
        )
        if retained is not None:
            expected_status = "review_pending" if source.human_review_required else "accepted"
            if task.status != expected_status or retained.authority_context.get(
                "source"
            ) != source.model_dump(mode="json"):
                raise TaskRoutingRequestUnavailable("routing_source_unavailable")
        return TaskRoutingSourcePreparation(request=request, source=source)
