"""TASK-owned immutable Submission command for the hidden composed transaction."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import (
    SubmissionArtifactAdmissionPort,
    SubmissionArtifactAdmissionRequest,
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    TaskSubmissionContextRequest,
)
from app.modules.tasks.models import Submission
from app.modules.tasks.repository import TaskRepository


class TaskSubmissionCreationService:
    """Sequence TASK and ART owner operations inside a caller-owned transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: SubmissionCreationAuthorizationPort,
        admissions: SubmissionArtifactAdmissionPort,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._admissions = admissions
        self._repository = TaskRepository(session)

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        """Create one Submission without opening or committing a transaction."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise RuntimeError("submission creation requires one root transaction")
        preliminary = SubmissionCreationAuthorityFacts(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            contributor_id=request.contributor_id,
            admission_id=request.admission_id,
            predecessor_submission_id=request.predecessor_submission_id,
        )
        await self._authorization.authorize(preliminary)
        context = await self._repository.lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                contributor_id=request.contributor_id,
                predecessor_submission_id=request.predecessor_submission_id,
            )
        )
        task = await self._repository.get_task(str(request.task_id))
        if task is None:
            raise RuntimeError("locked task disappeared")
        version = 1 if context.predecessor is None else context.predecessor.version + 1
        submission_id = uuid4()
        consumed = await self._admissions.consume(
            SubmissionArtifactAdmissionRequest(
                admission_id=request.admission_id,
                submission_id=submission_id,
                submission_version=version,
                task_context=context,
            )
        )
        submission = Submission(
            id=str(submission_id),
            task_id=str(request.task_id),
            task_assignment_id=str(request.assignment_id),
            contributor_id=str(request.contributor_id),
            version=version,
            status="submitted",
            summary=request.summary,
            package_uri=None,
            package_hash=None,
            artifact_hash_manifest=[],
            worker_attestation=request.contributor_attestation,
            submission_bundle_admission_id=str(request.admission_id),
            artifact_binding_id=str(consumed.binding_id),
            artifact_content_id=str(consumed.content_id),
            locked_guide_version=task.locked_guide_version,
            locked_post_submit_checker_policy_id=task.locked_post_submit_checker_policy_id,
            locked_post_submit_checker_policy_version=task.locked_post_submit_checker_policy_version,
            locked_post_submit_checker_policy_hash=task.locked_post_submit_checker_policy_hash,
            locked_post_submit_checker_policy_body=task.locked_post_submit_checker_policy_body,
            locked_review_policy_id=task.locked_review_policy_id,
            locked_review_policy_generation=task.locked_review_policy_generation,
            locked_review_policy_hash=task.locked_review_policy_hash,
            locked_revision_policy_id=task.locked_revision_policy_id,
            locked_revision_policy_generation=task.locked_revision_policy_generation,
            locked_revision_policy_hash=task.locked_revision_policy_hash,
            locked_payment_policy_version=task.locked_payment_policy_version,
            locked_guide_source_snapshot_id=task.locked_guide_source_snapshot_id,
            locked_guide_source_snapshot_hash=task.locked_guide_source_snapshot_hash,
            locked_effective_project_submission_artifact_policy_id=(
                task.locked_effective_project_submission_artifact_policy_id
            ),
            locked_effective_project_submission_artifact_policy_hash=(
                task.locked_effective_project_submission_artifact_policy_hash
            ),
            locked_pre_submit_checker_policy_id=task.locked_pre_submit_checker_policy_id,
            locked_pre_submit_checker_bundle_hash=task.locked_pre_submit_checker_bundle_hash,
            supersedes_submission_id=(
                str(context.predecessor.submission_id) if context.predecessor else None
            ),
        )
        await self._repository.add_submission(submission)
        final = SubmissionCreationAuthorityFacts(
            **{name: getattr(preliminary, name) for name in (
                "task_id", "assignment_id", "contributor_id", "admission_id",
                "predecessor_submission_id",
            )},
            submission_id=submission_id,
            submission_version=version,
        )
        await self._authorization.consume(final)
        return SubmissionCreationResult(
            submission_id=submission_id,
            submission_version=version,
            admission_id=request.admission_id,
            artifact_binding_id=consumed.binding_id,
            artifact_content_id=consumed.content_id,
        )
