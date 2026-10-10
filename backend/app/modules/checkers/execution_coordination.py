"""Caller-owned request reservation and exact current-result reads; no execution."""

import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerRequestConflict,
    CheckerExecutionUnavailable,
    CompletedEvaluation,
    EvaluationReservation,
    ReservedEvaluation,
    EvaluationCompletion,
    EvaluationTaskGuard,
    VerifiedMaterialFacts,
    VerifiedEvaluationCompletion,
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
    stored_request,
)
from app.modules.checkers.execution_results import classify_result
from app.modules.checkers.models import CheckerRun, CheckerSubmissionFence


class EvaluationCoordinator:
    """Own exact request reservation and current-result reads in caller transactions."""

    def __init__(self, session: AsyncSession, *, tasks: EvaluationTaskGuard):
        """Use the supplied session without taking ownership of its commit."""
        self._session = session
        self._tasks = tasks

    async def reserve_current_evaluation(
        self, request: PostSubmissionEvaluationRequest
    ) -> EvaluationReservation:
        """Serialize initial creation, exact replay and the next current generation."""
        request = PostSubmissionEvaluationRequest.model_validate(request)
        with self._session.no_autoflush:
            can_create = await self._lock_task_scope(request)
            if not can_create:
                replay = await self._replay(request)
                if replay is None:
                    raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
                return reservation(replay)
        # Every new generation takes TASK custody before this key, fence and run.
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "checkers:submission:" + str(request.submission_id)},
        )
        replay = await self._replay(request)
        if replay is not None:
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

    async def read_reserved_evaluation(
        self, *, project_id: UUID, task_id: UUID, submission_id: UUID, request_id: UUID,
    ) -> ReservedEvaluation:
        """Read all owner selectors together; missing custody is never repaired."""
        require_transaction(self._session)
        run = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.project_id == str(project_id),
            CheckerRun.task_id == str(task_id),
            CheckerRun.submission_id == str(submission_id),
            CheckerRun.evaluation_request_id == str(request_id),
            CheckerRun.phase == "post_submission",
        ).execution_options(populate_existing=True))
        if run is None:
            raise CheckerExecutionUnavailable("checker_reservation_unavailable")
        request = stored_request(run)
        if (
            request.project_id != project_id or request.task_id != task_id
            or request.submission_id != submission_id
            or request.evaluation_request_id != request_id
            or request.request_sha256 != run.request_digest
        ):
            raise CheckerExecutionUnavailable("checker_reservation_unavailable")
        return ReservedEvaluation(request=request, reservation=reservation(run))

    async def _lock_task_scope(self, request: PostSubmissionEvaluationRequest) -> bool:
        """Retain root-transaction TASK custody before any coordination fence lock."""
        require_transaction(self._session)
        connection = await self._session.connection()
        if connection.in_nested_transaction():
            raise CheckerExecutionUnavailable("checker_caller_transaction_required")
        # PostgreSQL detects raw savepoints that SQLAlchemy cannot observe.
        try:
            await self._session.execute(text("SELECT pg_catalog.pg_export_snapshot()"))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != "25001":
                raise
            raise CheckerExecutionUnavailable("checker_caller_transaction_required") from exc
        can_create = await self._tasks.lock_evaluation_scope(request)
        if type(can_create) is not bool:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        return can_create

    async def _replay(self, request: PostSubmissionEvaluationRequest) -> CheckerRun | None:
        """Read an exact stored envelope; never repair or restore its current fence."""
        replay = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.evaluation_request_id == str(request.evaluation_request_id),
            CheckerRun.phase == "post_submission",
        ).execution_options(populate_existing=True))
        if replay is not None and (
            replay.request_json != request_text(request)
            or replay.request_digest != request.request_sha256
        ):
            raise CheckerRequestConflict("checker_request_conflict")
        return replay

    async def read_current_result(
        self, request: PostSubmissionEvaluationRequest
    ) -> CompletedEvaluation:
        """Return only a locked completed result matching the entire current request."""
        request = PostSubmissionEvaluationRequest.model_validate(request)
        with self._session.no_autoflush:
            await self._lock_task_scope(request)
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

    async def require_current_completion(
        self, event_id: UUID, completion: EvaluationCompletion
    ) -> VerifiedEvaluationCompletion:
        """Verify caller completion against retained current custody without granting authority."""
        require_transaction(self._session)
        completion = EvaluationCompletion.model_validate(completion)
        if not isinstance(event_id, UUID):
            raise CheckerExecutionUnavailable("checker_current_completion_unavailable")
        ref = completion.reference
        # Qualify every untrusted owner selector before acquiring any CHECKERS lock.
        run = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.id == str(ref.attempt_id),
            CheckerRun.project_id == str(completion.project_id),
            CheckerRun.task_id == str(completion.task_id),
            CheckerRun.submission_id == str(completion.submission_id),
            CheckerRun.evaluation_request_id == str(ref.request_id),
            CheckerRun.request_digest == ref.request_digest,
            CheckerRun.evaluation_generation == ref.evaluation_generation,
            CheckerRun.result_id == str(ref.result_id),
            CheckerRun.result_digest == ref.result_digest,
            CheckerRun.completion_event_id == event_id,
        ).execution_options(populate_existing=True))
        if run is None:
            raise CheckerExecutionUnavailable("checker_current_completion_unavailable")
        request = stored_request(run)
        completed = await self.read_current_result(request)
        # read_current_result refreshes and locks this same run after its fence.
        if (
            completed.reference != ref
            or completed.routing_recommendation != completion.routing_recommendation
            or run.completion_event_id != event_id
            or run.execute_evidence_id != str(completion.execute_evidence_id)
            or run.finalize_evidence_id != str(completion.finalize_evidence_id)
            or completion.execute_evidence_id == completion.finalize_evidence_id
            or run.material_custody is None
            or run.input_materialization_evidence_id is None
        ):
            raise CheckerExecutionUnavailable("checker_current_completion_unavailable")
        material = VerifiedMaterialFacts.model_validate_json(
            json.dumps(run.material_custody)
        )
        if (
            material.submission_id != request.submission_id
            or material.submission_version != request.submission_version
            or material.binding_id != request.binding_id
            or material.content_id != request.content_id
            or material.content_sha256 != request.content_sha256
            or material.byte_count != request.byte_count
        ):
            raise CheckerExecutionUnavailable("checker_current_completion_unavailable")
        return VerifiedEvaluationCompletion(
            completion=completion,
            result=completed.result,
            submission_version=run.submission_version,
            material=material,
            input_materialization_evidence_id=UUID(run.input_materialization_evidence_id),
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
