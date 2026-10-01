"""Caller-owned request reservation and exact current-result reads; no execution."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerRequestConflict,
    CheckerExecutionUnavailable,
    CompletedEvaluation,
    EvaluationReservation,
)
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmitCurrentResultReference,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSelector,
    CheckerOutputUnavailable,
)
from app.modules.checkers.execution_repository import (
    ExecutionRepository,
    require_transaction,
    request_text,
    reservation,
    stored_result,
)
from app.modules.checkers.execution_results import classify_result
from app.modules.checkers.models import CheckerRun, CheckerSubmissionFence


class EvaluationCoordinator:
    """Own exact request reservation and current-result reads in caller transactions."""

    def __init__(self, session: AsyncSession):
        """Use the supplied session without taking ownership of its commit."""
        self._session = session

    async def reserve_current_evaluation(
        self, request: PostSubmissionEvaluationRequest
    ) -> EvaluationReservation:
        """Serialize initial creation, exact replay and the next current generation."""
        request = PostSubmissionEvaluationRequest.model_validate(request)
        require_transaction(self._session)
        # Serialize initial creation without taking a foreign TASK row lock. Every
        # later coordinator locks this key before its existing fence and run.
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "checkers:submission:" + str(request.submission_id)},
        )
        replay = await self._session.scalar(
            select(CheckerRun).where(
                CheckerRun.evaluation_request_id == str(request.evaluation_request_id),
                CheckerRun.phase == "post_submission",
            )
        )
        if replay is not None:
            if (
                replay.request_json != request_text(request)
                or replay.request_digest != request.request_sha256
            ):
                raise CheckerRequestConflict("checker_request_conflict")
            return reservation(replay)
        fence = await self._session.scalar(
            select(CheckerSubmissionFence)
            .where(
                CheckerSubmissionFence.submission_id == str(request.submission_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        prior = None
        if fence is not None:
            prior = await self._session.scalar(
                select(CheckerRun)
                .where(
                    CheckerRun.id == fence.current_run_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        expected = 1 if prior is None else prior.evaluation_generation + 1
        if request.evaluation_generation != expected:
            raise CheckerRequestConflict("checker_generation_conflict")
        context = request.expected_context
        run = CheckerRun(
            id=str(new_record_id()),
            project_id=str(request.project_id),
            task_id=str(request.task_id),
            submission_id=str(request.submission_id),
            submission_version=request.submission_version,
            evaluation_request_id=str(request.evaluation_request_id),
            phase="post_submission",
            evaluation_generation=request.evaluation_generation,
            request_json=request_text(request),
            request_digest=request.request_sha256,
            result_id=str(new_record_id()),
            trigger_source="coordinated_evaluation",
            status="queued",
            outcome_source="none",
            routing_recommendation="not_evaluated",
            worker_lease_generation=0,
            supersedes_checker_run_id=prior.id if prior else None,
            locked_guide_version=context.guide_version,
            locked_post_submit_checker_policy_id=str(context.post_policy_id),
            locked_post_submit_checker_policy_version=context.post_policy_version,
            locked_post_submit_checker_policy_hash=context.post_policy_hash,
            locked_review_policy_id=str(context.review_policy_id),
            locked_review_policy_generation=context.review_generation,
            locked_review_policy_hash=context.review_hash,
            locked_revision_policy_id=str(context.revision_policy_id),
            locked_revision_policy_generation=context.revision_generation,
            locked_revision_policy_hash=context.revision_hash,
        )
        self._session.add(run)
        try:
            await self._session.flush()
            if fence is None:
                self._session.add(
                    CheckerSubmissionFence(submission_id=run.submission_id, current_run_id=run.id)
                )
            else:
                fence.current_run_id = run.id
            await self._session.flush()
        except IntegrityError:
            # The caller owns rollback, including a cross-submission request-key collision.
            raise CheckerRequestConflict("checker_request_conflict") from None
        return reservation(run)

    async def read_current_result(
        self, request: PostSubmissionEvaluationRequest
    ) -> CompletedEvaluation:
        """Return only a locked completed result matching the entire current request."""
        request = PostSubmissionEvaluationRequest.model_validate(request)
        run = await ExecutionRepository(self._session).lock_current(request)
        if run.status != "completed":
            raise CheckerExecutionUnavailable("checker_current_result_unavailable")
        result = stored_result(run)
        reference = PostSubmitCurrentResultReference(
            **result.model_dump(
                include=set(PostSubmitCurrentResultReference.model_fields) - {"schema_version"}
            )
        )
        reference.validate_result(result)
        classification = classify_result(request, result)
        return CompletedEvaluation(
            reference=reference, routing_recommendation=classification.routing, result=result
        )


class CurrentExecution:
    """Expose only CHECKERS' current committed lease verification to materialization."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def require_current_execution(self, facts):
        """Keep the caller's AUTH-first transaction and exact fence/run lock order."""
        from app.modules.checkers.api.execution import ExecuteFacts, execution_authority_digest

        if type(facts) is not ExecuteFacts:
            raise CheckerExecutionUnavailable("checker_current_execution_unavailable")
        execution_authority_digest(facts)
        await ExecutionRepository(self._session).require_lease(facts.request, facts.lease)


class CheckerOutputReservations:
    """Current structural handlers have exactly zero output slots."""

    def __init__(self, session: AsyncSession):
        """Resolve output custody within the supplied CHECKERS session."""
        self._session = session

    async def resolve(self, selector: CheckerOutputSelector) -> CheckerOutputReservation:
        """Require exact current lease custody and return the supported zero-output contract."""
        from app.modules.checkers.api.execution import CheckerExecutionUnavailable

        try:
            repo = ExecutionRepository(self._session)
            run = await repo.lock_current(selector.evaluation)
            if (
                run.status != "running"
                or run.id != str(selector.checker_run_id)
                or run.worker_lease_id != str(selector.worker_lease_id)
                or run.worker_lease_generation != selector.worker_lease_generation
                or run.worker_lease_expires_at <= await repo.now()
            ):
                raise CheckerOutputUnavailable("checker_output_reservation_unavailable")
            return CheckerOutputReservation(
                evaluation=selector.evaluation,
                checker_run_id=UUID(run.id),
                worker_lease_id=UUID(run.worker_lease_id),
                worker_lease_generation=run.worker_lease_generation,
                slots=(),
            )
        except CheckerExecutionUnavailable:
            raise CheckerOutputUnavailable("checker_output_reservation_unavailable") from None
