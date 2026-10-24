"""Exact TASK-owned revision lineage, independent of today's revision clock."""

import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.evaluation_revision import (
    EvaluationRevisionSource,
    EvaluationSubmissionReference,
    TaskEvaluationRevisionContext,
    TaskEvaluationRevisionRequest,
)
from app.modules.tasks.api.post_submit_routing import TaskRoutingSelection
from app.modules.tasks.api.revision import RevisionCandidate
from app.modules.tasks.api.submitted_bundle import SubmittedBundleUnavailable
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.models import Submission, SubmissionDispatch, TaskAssignment, WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.revision.models import TaskRevisionPreparation


def _reference(submission: Submission, project_id: UUID) -> EvaluationSubmissionReference:
    """Project immutable byte ownership without dereferencing another owner's tables."""
    return EvaluationSubmissionReference(
        project_id=project_id,
        task_id=UUID(submission.task_id),
        assignment_id=UUID(submission.task_assignment_id),
        contributor_id=UUID(submission.contributor_id),
        submission_id=UUID(submission.id),
        submission_version=submission.version,
        admission_id=UUID(submission.submission_bundle_admission_id),
        binding_id=UUID(submission.artifact_binding_id),
        content_id=UUID(submission.artifact_content_id),
    )


def _lineage(submission: Submission) -> TaskPolicyLineage:
    """Recover the same complete locked lineage used by submission replay."""
    values = {
        name: getattr(
            submission,
            "contribution_policy_version_id"
            if name == "locked_contribution_policy_version_id"
            else name,
        )
        for name in TaskPolicyLineage.model_fields
    }
    return TaskPolicyLineage.model_validate_json(json.dumps(values, default=str))


class TaskEvaluationRevisionReader:
    """Read exact immutable sources; the materialization caller owns current authority."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the caller's short transaction without acquiring later owner locks."""
        self._session = session

    async def read(
        self,
        request: TaskEvaluationRevisionRequest,
    ) -> TaskEvaluationRevisionContext:
        """Resolve the consumed preparation, never a replacement head or live deadline."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        try:
            request = TaskEvaluationRevisionRequest.model_validate(request)
            return await self._read(request)
        except (ValueError, TypeError, AttributeError, KeyError):
            raise SubmittedBundleUnavailable("submitted_revision_unavailable") from None

    async def _read(
        self,
        request: TaskEvaluationRevisionRequest,
    ) -> TaskEvaluationRevisionContext:
        """Resolve the immutable creation receipt before its optional historical source."""
        row = (
            await self._session.execute(
                select(Submission, SubmissionDispatch)
                .join(WorkstreamTask, WorkstreamTask.id == Submission.task_id)
                .join(
                    TaskAssignment,
                    (TaskAssignment.id == Submission.task_assignment_id)
                    & (TaskAssignment.task_id == Submission.task_id)
                    & (TaskAssignment.project_id == WorkstreamTask.project_id)
                    & (TaskAssignment.contributor_id == Submission.contributor_id),
                )
                .join(SubmissionDispatch, SubmissionDispatch.submission_id == Submission.id)
                .where(
                    WorkstreamTask.project_id == str(request.project_id),
                    Submission.task_id == str(request.task_id),
                    Submission.task_assignment_id == str(request.assignment_id),
                    Submission.id == str(request.submission_id),
                    Submission.version == request.submission_version,
                    Submission.status == "submitted",
                    Submission.submission_bundle_admission_id == str(request.admission_id),
                )
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        submission, dispatch = row
        current = _reference(submission, request.project_id)
        if (
            dispatch.project_id,
            dispatch.task_id,
            dispatch.assignment_id,
            dispatch.contributor_id,
            dispatch.submission_version,
            dispatch.admission_id,
            dispatch.artifact_binding_id,
            dispatch.artifact_content_id,
        ) != (
            str(current.project_id),
            str(current.task_id),
            str(current.assignment_id),
            str(current.contributor_id),
            current.submission_version,
            str(current.admission_id),
            str(current.binding_id),
            str(current.content_id),
        ):
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        if dispatch.creation_kind == "initial":
            prior_count = await self._session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.task_assignment_id == submission.task_assignment_id,
                    Submission.version < submission.version,
                )
            )
            if (
                dispatch.creation_status != "in_progress"
                or submission.supersedes_submission_id
                or dispatch.checker_remediation_manifest_id is not None
                or request.preparation_id is not None
                or prior_count != 0
            ):
                raise SubmittedBundleUnavailable("submitted_revision_unavailable")
            return TaskEvaluationRevisionContext(
                kind="initial",
                current=current,
                predecessor=None,
                source=None,
            )
        if (
            dispatch.creation_kind != "checker_remediation"
            or dispatch.creation_status != "needs_revision"
            or request.preparation_id is None
            or submission.supersedes_submission_id is None
        ):
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        prior = await self._session.scalar(
            select(Submission)
            .where(
                Submission.id == submission.supersedes_submission_id,
                Submission.task_id == submission.task_id,
                Submission.task_assignment_id == submission.task_assignment_id,
                Submission.contributor_id == submission.contributor_id,
                Submission.version == submission.version - 1,
                Submission.status == "submitted",
                Submission.attempt_status == "needs_revision",
            )
            .execution_options(populate_existing=True)
        )
        preparation = await self._session.scalar(
            select(TaskRevisionPreparation)
            .where(
                TaskRevisionPreparation.id == request.preparation_id,
                TaskRevisionPreparation.preparation_sha256 == request.preparation_sha256,
                TaskRevisionPreparation.project_id == str(request.project_id),
                TaskRevisionPreparation.task_id == submission.task_id,
                TaskRevisionPreparation.assignment_id == submission.task_assignment_id,
                TaskRevisionPreparation.contributor_id == submission.contributor_id,
                TaskRevisionPreparation.submission_id == submission.supersedes_submission_id,
                TaskRevisionPreparation.source_submission_version == submission.version - 1,
                TaskRevisionPreparation.routing_manifest_id
                == dispatch.checker_remediation_manifest_id,
            )
            .execution_options(populate_existing=True)
        )
        if prior is None or preparation is None:
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        manifest = await self._session.scalar(
            select(TaskPostSubmitRoutingManifest)
            .where(
                TaskPostSubmitRoutingManifest.id == preparation.routing_manifest_id,
                TaskPostSubmitRoutingManifest.project_id == str(request.project_id),
                TaskPostSubmitRoutingManifest.task_id == submission.task_id,
                TaskPostSubmitRoutingManifest.assignment_id == submission.task_assignment_id,
                TaskPostSubmitRoutingManifest.contributor_id == submission.contributor_id,
                TaskPostSubmitRoutingManifest.submission_id == prior.id,
                TaskPostSubmitRoutingManifest.submission_version == prior.version,
                TaskPostSubmitRoutingManifest.routing_recommendation == "needs_revision",
            )
            .execution_options(populate_existing=True)
        )
        if manifest is None:
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        candidate = RevisionCandidate.model_validate_json(
            json.dumps(preparation.packet["candidate"])
        )
        if (
            canonical_json_hash(preparation.packet) != preparation.preparation_sha256
            or preparation.outcome not in {"kept", "rebased"}
            or preparation.blocked_reason is not None
            or preparation.next_revision_round > preparation.max_revision_rounds
            or candidate.target is None
            or candidate.target_post_policy_json is None
            or candidate.prior.lineage != _lineage(prior)
            or candidate.target.lineage != _lineage(submission)
            or json.loads(candidate.target_post_policy_json)
            != submission.selected_post_submit_policy_body
        ):
            raise SubmittedBundleUnavailable("submitted_revision_unavailable")
        source = TaskRoutingSelection(
            project_id=request.project_id,
            task_id=request.task_id,
            submission_id=UUID(prior.id),
            submission_version=prior.version,
            checker_run_id=UUID(manifest.checker_run_id),
            evaluation_request_id=manifest.evaluation_request_id,
            evaluation_request_digest=manifest.request_digest,
            evaluation_generation=manifest.evaluation_generation,
            result_id=manifest.result_id,
            result_digest=manifest.result_digest,
            completion_event_id=manifest.completion_event_id,
            routing_recommendation="needs_revision",
        )
        return TaskEvaluationRevisionContext(
            kind="checker_remediation",
            current=current,
            predecessor=_reference(prior, request.project_id),
            source=EvaluationRevisionSource(
                preparation_id=preparation.id,
                preparation_sha256=preparation.preparation_sha256,
                routing_manifest_id=manifest.id,
                revision_round=preparation.next_revision_round,
                evaluation=source,
            ),
        )
