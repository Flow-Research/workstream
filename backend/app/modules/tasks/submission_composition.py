"""TASK-owned immutable Submission command for the hidden composed transaction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import (
    SubmissionArtifactAdmissionPort,
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    TaskSubmissionContextRequest,
)
from app.modules.tasks.models import EvidenceItem, Submission
from app.modules.tasks.repository import TaskRepository


def build_submission(
    *,
    submission_id: str,
    task: Any,
    contributor_id: str,
    version: int,
    summary: str,
    worker_attestation: str,
    supersedes_submission_id: str | None,
    task_assignment_id: str | None = None,
    package_uri: str | None = None,
    package_hash: str | None = None,
    artifact_hash_manifest: list[dict[str, Any]] | None = None,
    evidence_items: Sequence[EvidenceItem] = (),
) -> Submission:
    """Build a Submission with one canonical copy of the task policy locks."""
    return Submission(
        id=submission_id,
        task_id=task.id,
        task_assignment_id=task_assignment_id,
        contributor_id=contributor_id,
        version=version,
        status="submitted",
        summary=summary,
        package_uri=package_uri,
        package_hash=package_hash,
        artifact_hash_manifest=artifact_hash_manifest or [],
        worker_attestation=worker_attestation,
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
        supersedes_submission_id=supersedes_submission_id,
        evidence_items=list(evidence_items),
    )


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
        preliminary = SubmissionCreationPreparationFacts(
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
        submission = build_submission(
            submission_id=str(submission_id), task=task,
            contributor_id=str(request.contributor_id), version=version,
            summary=request.summary, worker_attestation=request.contributor_attestation,
            supersedes_submission_id=(str(context.predecessor.submission_id)
                                      if context.predecessor else None),
        )
        final = SubmissionCreationAuthorityFacts(
            task_id=preliminary.task_id,
            assignment_id=preliminary.assignment_id,
            contributor_id=preliminary.contributor_id,
            admission_id=preliminary.admission_id,
            predecessor_submission_id=preliminary.predecessor_submission_id,
            submission_id=submission_id,
            submission_version=version,
            task_context=context,
        )
        prepared_authorization = await self._authorization.prepare(final)
        try:
            await self._repository.add_submission(submission)
            consumed = await self._admissions.consume(
                SubmissionArtifactAdmissionRequest(
                    admission_id=request.admission_id,
                    submission_id=submission_id,
                    submission_version=version,
                    task_context=context,
                )
            )
            if (
                type(consumed) is not SubmissionArtifactAdmissionResult
                or not isinstance(consumed.binding_id, UUID)
                or not isinstance(consumed.content_id, UUID)
            ):
                raise RuntimeError("artifact admission did not produce exact binding facts")
            submission.submission_bundle_admission_id = str(request.admission_id)
            submission.task_assignment_id = str(request.assignment_id)
            submission.artifact_binding_id = str(consumed.binding_id)
            submission.artifact_content_id = str(consumed.content_id)
            await self._session.flush()
            await self._authorization.consume(prepared_authorization, final)
        finally:
            self._authorization.close(prepared_authorization)
        return SubmissionCreationResult(
            submission_id=submission_id,
            submission_version=version,
            admission_id=request.admission_id,
            artifact_binding_id=consumed.binding_id,
            artifact_content_id=consumed.content_id,
        )
