"""TASK custody required before evaluation reservations and current-result reads."""

from dataclasses import asdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest
from app.modules.checkers.api.output_custody import CheckerOutputSelector, CheckerOutputUnavailable
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest, SubmittedBundleUnavailable
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submitted_bundle import SubmittedBundleReader


def _context_matches(request: PostSubmissionExecutionRequest, context: object) -> bool:
    """Compare selected request lineage with exact retained TASK facts."""
    observed = asdict(context)
    return request.expected_context.model_dump() == {
        "guide_version": observed["guide_version"],
        "source_id": observed["source_id"],
        "source_hash": observed["source_hash"],
        "effective_policy_id": observed["effective_policy_id"],
        "effective_policy_hash": observed["effective_policy_hash"],
        "pre_policy_id": observed["pre_policy_id"],
        "pre_policy_hash": observed["pre_policy_hash"],
        "post_policy_id": observed["post_policy_id"],
        "post_policy_version": observed["post_policy_version"],
        "post_policy_hash": observed["post_policy_hash"],
        "review_policy_id": observed["review_policy_id"],
        "review_generation": observed["review_generation"],
        "review_hash": observed["review_hash"],
        "revision_policy_id": observed["revision_policy_id"],
        "revision_generation": observed["revision_generation"],
        "revision_hash": observed["revision_hash"],
    } and observed["selected_post_policy_hash"] == request.expected_context.post_policy_hash \
      and observed["selected_post_policy_body"] == request.policy.model_dump(mode="json")


class TaskEvaluationGuard:
    """Lock current TASK scope without granting execution or changing product state."""

    def __init__(self, session: AsyncSession):
        self._repository = TaskRepository(session)
        self._submitted = SubmittedBundleReader(session)

    async def lock_model_evidence_scope(self, selector: CheckerOutputSelector) -> None:
        """Retain exact historical owners before private model evidence FK writes."""
        slot = selector.paid_slot
        task = await self._repository.lock_project_task(slot.project_id, selector.task_id)
        if task is None:
            raise CheckerOutputUnavailable("checker_output_task_unavailable")
        assignment = await self._repository.lock_accepted_assignment(
            project_id=slot.project_id, task_id=selector.task_id,
            assignment_id=slot.assignment_id,
        )
        submission = await self._repository.lock_exact_submission_for_task(
            project_id=slot.project_id, task_id=selector.task_id,
            submission_id=slot.submission_id,
        )
        if assignment is None or submission is None or (
            submission.version != slot.submission_version
            or submission.task_assignment_id != str(slot.assignment_id)
            or submission.contributor_id != assignment.contributor_id
        ):
            raise CheckerOutputUnavailable("checker_output_task_unavailable")

    async def lock_evaluation_scope(self, request: PostSubmissionExecutionRequest) -> bool:
        """Return new-generation eligibility after exact Task/Assignment/Submission locks."""
        task = await self._repository.lock_project_task(request.project_id, request.task_id)
        if task is None:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        assignment = await self._repository.lock_accepted_assignment(
            project_id=request.project_id, task_id=request.task_id,
            assignment_id=request.assignment_id,
        )
        latest = await self._repository.get_latest_submission_for_task(
            str(request.task_id), for_update=True, populate_existing=True,
        )
        if assignment is None or latest is None or not (
            latest.id == str(request.submission_id)
            and latest.version == request.submission_version
            and latest.status == "submitted"
            and latest.task_assignment_id == assignment.id
            and latest.contributor_id == assignment.contributor_id
            and task.assigned_to == latest.contributor_id
        ):
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        try:
            facts = await self._submitted.read(SubmittedBundleRequest(
                request.project_id, request.task_id, request.submission_id,
            ))
        except SubmittedBundleUnavailable:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable") from None
        if not (
            facts.assignment_id == request.assignment_id
            and facts.submission_version == request.submission_version
            and facts.contributor_id == UUID(assignment.contributor_id)
            and facts.binding_id == request.binding_id
            and facts.content_id == request.content_id
            and _context_matches(request, facts.context)
        ):
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        if (task.status == "evaluation_pending" and task.active_submission_operation_id is not None
                and latest.attempt_status != "evaluation_pending"):
            # Accepted replacement owns current work until T5 inserts its new attempt.
            return False
        if task.status in {"accepted", "rejected"}:
            return False
        if task.status not in {
            "in_progress", "submitted", "evaluation_pending", "review_pending", "needs_revision",
        } or assignment.status != "active" or assignment.released_at is not None:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        return True

    async def lock_terminal_retry_scope(self, request: PostSubmissionExecutionRequest) -> None:
        """New recovery must target an active and unrouted evaluation-pending task."""
        if not await self.lock_evaluation_scope(request):
            raise CheckerExecutionUnavailable("checker_retry_scope_unavailable")
        task = await self._repository.lock_project_task(request.project_id, request.task_id)
        if task is None or task.status != "evaluation_pending":
            raise CheckerExecutionUnavailable("checker_retry_scope_unavailable")

    async def lock_retry_replay_scope(self, request: PostSubmissionExecutionRequest) -> None:
        """Replay retains exact historical owners even after accepted completion."""
        task = await self._repository.lock_project_task(request.project_id, request.task_id)
        if task is None:
            raise CheckerExecutionUnavailable("checker_retry_replay_unavailable")
        assignment = await self._repository.lock_accepted_assignment(
            project_id=request.project_id, task_id=request.task_id,
            assignment_id=request.assignment_id,
        )
        submission = await self._repository.lock_exact_submission_for_task(
            project_id=request.project_id, task_id=request.task_id,
            submission_id=request.submission_id,
        )
        if assignment is None or submission is None or not (
            submission.version == request.submission_version
            and submission.status == "submitted"
            and submission.task_assignment_id == assignment.id
            and submission.contributor_id == assignment.contributor_id
        ):
            raise CheckerExecutionUnavailable("checker_retry_replay_unavailable")
        try:
            facts = await self._submitted.read(SubmittedBundleRequest(
                request.project_id, request.task_id, request.submission_id,
            ))
        except SubmittedBundleUnavailable:
            raise CheckerExecutionUnavailable("checker_retry_replay_unavailable") from None
        if not (
            facts.assignment_id == request.assignment_id
            and facts.submission_version == request.submission_version
            and facts.contributor_id == UUID(assignment.contributor_id)
            and facts.binding_id == request.binding_id
            and facts.content_id == request.content_id
            and _context_matches(request, facts.context)
        ):
            raise CheckerExecutionUnavailable("checker_retry_replay_unavailable")
