"""Caller-owned request reservation and exact current-result reads; no execution."""

import json
from uuid import UUID

from sqlalchemy import select, text, func
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    CheckerRequestConflict,
    CheckerRetryDelivery,
    CheckerRetrySourceUnavailable,
    CompletedEvaluation,
    EvaluationReservation,
    EvaluationProgress,
    ReservedEvaluation,
    EvaluationCompletion,
    EvaluationTaskGuard, POST_SUBMISSION_ATTEMPT_LIMIT,
    VerifiedMaterialFacts,
    VerifiedEvaluationCompletion,
)
from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    validate_execution_request,
)
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitExpiredLease, PostSubmitRequestDeliveryFacts,
)
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmitCurrentResultReference,
)
from app.modules.checkers.execution_repository import (
    ExecutionRepository,
    require_transaction,
    request_text,
    reservation,
    stored_result,
    stored_request,
)
from app.modules.outbox.api import (
    DeliveryOptions,
    OutboxAppendInput, OutboxAppendPort, OutboxIdempotencyConflict, OutboxInputError, OutboxPersistenceError,
)
from app.modules.checkers.execution_results import evaluation_completion_event
from app.modules.checkers.models import CheckerRun, CheckerSubmissionFence, CheckerRetryReceipt


POST_SUBMISSION_RETRY_OPTIONS = DeliveryOptions(max_attempts=POST_SUBMISSION_ATTEMPT_LIMIT)


class EvaluationCoordinator:
    """Own exact request reservation and current-result reads in caller transactions."""

    def __init__(self, session: AsyncSession, *, tasks: EvaluationTaskGuard, events: OutboxAppendPort):
        """Use the supplied session without taking ownership of its commit."""
        self._session, self._tasks, self._events = session, tasks, events

    async def reserve_current_evaluation(
        self, request: PostSubmissionExecutionRequest
    ) -> EvaluationReservation:
        """Serialize initial creation, exact replay and the next current generation."""
        request = validate_execution_request(request)
        with self._session.no_autoflush:
            can_create = await self._lock_task_scope(request)
            if not can_create:
                replay = await self._replay(request)
                if replay is None:
                    raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
                return reservation(replay)
        return await self._reserve_after_task_lock(request)

    async def schedule_automatic_retry(self, run: CheckerRun) -> None:
        """Reserve a delayed successor only from exact known terminal custody."""
        from app.modules.checkers.checker_retry import require_finalized_infrastructure_source, retry_successor_request

        if run.evaluation_generation >= POST_SUBMISSION_RETRY_OPTIONS.max_attempts:
            return
        previous, source = require_finalized_infrastructure_source(run)
        await self._tasks.lock_terminal_retry_scope(previous)
        await self._reserve_after_task_lock(
            retry_successor_request(previous), terminal_source_id=source.source_run_id, automatic_retry=True,
        )

    async def require_expired_unknown_lease(self, request: PostSubmissionExecutionRequest) -> PostSubmitExpiredLease:
        """Require exact still-current invocation custody with no retained result."""
        await self._tasks.lock_terminal_retry_scope(request)
        repo = ExecutionRepository(self._session)
        run = await repo.lock_current(request)
        if (run.status != "running" or run.worker_lease_id is None or run.worker_lease_expires_at is None
                or run.worker_lease_live_until is None or run.worker_lease_live_until > await repo.now()
                or run.result_json is not None):
            raise CheckerRetrySourceUnavailable("checker_abandonment_source_unavailable")
        return PostSubmitExpiredLease(lease_id=UUID(run.worker_lease_id), lease_generation=run.worker_lease_generation,
                                      expires_at=run.worker_lease_expires_at)

    async def reserve_abandoned_evaluation(
        self, request: PostSubmissionExecutionRequest, lease: PostSubmitExpiredLease, cause: UUID,
    ) -> EvaluationReservation:
        """Atomically displace the same exact expired worker without terminalizing it."""
        from app.modules.checkers.checker_retry import retry_successor_request

        if await self.require_expired_unknown_lease(request) != lease:
            raise CheckerRetrySourceUnavailable("checker_abandonment_source_unavailable")
        run = await ExecutionRepository(self._session).lock_current(request)
        return await self._reserve_after_task_lock(
            retry_successor_request(request), terminal_source_id=UUID(run.id), abandonment_event_id=cause,
        )

    async def _reserve_after_task_lock(
        self, request: PostSubmissionExecutionRequest, *, terminal_source_id: UUID | None = None,
        automatic_retry: bool = False, abandonment_event_id: UUID | None = None,
    ) -> EvaluationReservation:
        """Use the existing CHECKERS locks after the caller has retained TASK custody."""
        require_transaction(self._session)
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
        if terminal_source_id is not None and (prior is None or prior.id != str(terminal_source_id)):
            raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
        if terminal_source_id is not None and abandonment_event_id is None:
            if (
                prior.status != "infrastructure_failed"
                or prior.finalize_evidence_id is None
                or prior.result_json is None or prior.result_digest is None
                or prior.completion_event_id is not None
                or stored_result(prior).outcome != "infrastructure_failed"
            ):
                raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
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
            locked_post_submit_checker_policy_version=(
                context.post_policy_version
            ),
            locked_post_submit_checker_policy_hash=context.post_policy_hash,
            selected_post_submit_policy_sha256=request.policy.policy_sha256,
            selected_post_submit_policy_body=request.policy.model_dump(mode="json"),
            locked_review_policy_id=str(context.review_policy_id),
            locked_review_policy_generation=context.review_generation,
            locked_review_policy_hash=context.review_hash,
            locked_revision_policy_id=str(context.revision_policy_id),
            locked_revision_policy_generation=context.revision_generation,
            locked_revision_policy_hash=context.revision_hash,
        )
        if automatic_retry or abandonment_event_id is not None:
            from app.modules.checkers.checker_retry import abandoned_retry_event, automatic_retry_event

            if terminal_source_id is None or prior is None:
                raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
            event = (abandoned_retry_event(prior, run, abandonment_event_id) if abandonment_event_id is not None
                     else automatic_retry_event(prior, run))
            appended = await self._events.append(event)
            run.retry_delivery_event_id = appended.event_id
            run.retry_abandonment_event_id = abandonment_event_id
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

    async def read_current_progress(
        self, *, project_id: UUID, task_id: UUID, submission_id: UUID,
        original_request_id: UUID,
    ) -> EvaluationProgress:
        """Read the exact Submission fence; never follow the task's newest attempt."""
        original = await self.read_reserved_evaluation(
            project_id=project_id, task_id=task_id, submission_id=submission_id,
            request_id=original_request_id,
        )
        unavailable = "checker_progress_unavailable"
        if original.reservation.evaluation_generation != 1:
            raise CheckerExecutionUnavailable(unavailable)
        run = await self._session.scalar(select(CheckerRun).join(
            CheckerSubmissionFence, CheckerSubmissionFence.current_run_id == CheckerRun.id,
        ).where(
            CheckerSubmissionFence.submission_id == str(submission_id),
            CheckerRun.submission_id == str(submission_id),
            CheckerRun.project_id == str(project_id), CheckerRun.task_id == str(task_id),
            CheckerRun.phase == "post_submission",
        ).with_for_update(read=True, of=(CheckerSubmissionFence, CheckerRun))
          .execution_options(populate_existing=True))
        if run is None:
            raise CheckerExecutionUnavailable(unavailable)
        current = await self.read_reserved_evaluation(
            project_id=project_id, task_id=task_id, submission_id=submission_id,
            request_id=UUID(run.evaluation_request_id),
        )
        if (current.request.assignment_id != original.request.assignment_id
                or current.request.submission_version != original.request.submission_version):
            raise CheckerExecutionUnavailable(unavailable)
        retry_event_id = run.retry_delivery_event_id
        delivery_event = None
        previous_failure_code = None
        if current.reservation.attempt_id == original.reservation.attempt_id:
            if run.supersedes_checker_run_id is not None or retry_event_id is not None:
                raise CheckerExecutionUnavailable(unavailable)
        else:
            if retry_event_id is None:
                receipt = await self._session.scalar(select(CheckerRetryReceipt).where(
                    CheckerRetryReceipt.successor_run_id == run.id,
                    CheckerRetryReceipt.project_id == str(project_id),
                    CheckerRetryReceipt.task_id == str(task_id),
                    CheckerRetryReceipt.submission_id == str(submission_id),
                    CheckerRetryReceipt.source_run_id == run.supersedes_checker_run_id,
                    CheckerRetryReceipt.successor_generation == run.evaluation_generation,
                ))
                if receipt is None:
                    raise CheckerExecutionUnavailable(unavailable)
                retry_event_id = receipt.event_id
                retained = await self.read_retry_delivery(
                    project_id=project_id, submission_id=submission_id, event_id=retry_event_id,
                )
            else:
                retained, previous_failure_code = await self._read_service_retry(run)
            if retained is None or retained.request != current.request or run.evaluation_generation <= 1:
                raise CheckerExecutionUnavailable(unavailable)
            expected = retained.expected_event
            delivery_event = OutboxAppendInput(
                **expected.model_dump(exclude={"payload_json", "payload_digest"}),
                project_id=project_id, payload=json.loads(expected.payload_json),
            )
        failure_code = None
        terminal = run.status in {"completed", "infrastructure_failed"}
        if terminal:
            result = stored_result(run)
            if (result.outcome != run.status or run.finalize_evidence_id is None
                    or (run.status == "completed") != (run.completion_event_id is not None)
                    or run.failure_code != result.infrastructure_failure_code):
                raise CheckerExecutionUnavailable(unavailable)
            failure_code = result.infrastructure_failure_code
            if run.status == "completed":
                if run.execute_evidence_id is None:
                    raise CheckerExecutionUnavailable(unavailable)
                delivery_event = evaluation_completion_event(
                    current.request, result, attempt_id=UUID(run.id),
                    execute_evidence_id=UUID(run.execute_evidence_id),
                    finalize_evidence_id=UUID(run.finalize_evidence_id),
                    routing_recommendation=run.routing_recommendation,
                )
        elif run.completion_event_id is not None:
            raise CheckerExecutionUnavailable(unavailable)
        now = await self._session.scalar(select(func.clock_timestamp()))
        live = (run.status == "running" and run.worker_lease_id is not None
                and run.worker_lease_generation > 0 and run.worker_lease_live_until is not None
                and run.worker_lease_live_until > now)
        return EvaluationProgress(
            current=current, status=run.status, live_worker_lease=live, failure_code=failure_code,
            previous_failure_code=previous_failure_code,
            retry_event_id=retry_event_id, completion_event_id=run.completion_event_id,
            delivery_event_json=delivery_event.model_dump_json() if delivery_event is not None else None,
        )

    async def read_retry_delivery(
        self, *, project_id: UUID, submission_id: UUID, event_id: UUID,
    ) -> CheckerRetryDelivery | None:
        """Expose exact CHECKERS retry receipt facts without a private TASK import."""
        from app.modules.checkers.checker_retry import read_retry_delivery
        require_transaction(self._session)
        automatic = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.retry_delivery_event_id == event_id,
            CheckerRun.project_id == str(project_id),
            CheckerRun.submission_id == str(submission_id),
        ))
        if automatic is not None:
            retained, _ = await self._read_service_retry(automatic)
            return retained
        return await read_retry_delivery(
            self._session, self, project_id=project_id,
            submission_id=submission_id, event_id=event_id,
        )

    async def _read_service_retry(self, successor: CheckerRun):
        """Verify the exact service-triggered event and its retained cause."""
        from app.modules.checkers.checker_retry import abandoned_retry_event, automatic_retry_event, retry_event_expectation

        unavailable = "checker_automatic_retry_delivery_unavailable"
        if successor.supersedes_checker_run_id is None or successor.retry_delivery_event_id is None:
            raise CheckerExecutionUnavailable(unavailable)
        source = await self._session.get(CheckerRun, successor.supersedes_checker_run_id, populate_existing=True)
        if source is None:
            raise CheckerExecutionUnavailable(unavailable)
        abandonment = successor.retry_abandonment_event_id
        expected = (abandoned_retry_event(source, successor, abandonment) if abandonment is not None
                    else automatic_retry_event(source, successor))
        try:
            await self._events.require_existing(successor.retry_delivery_event_id, expected)
        except (OutboxIdempotencyConflict, OutboxInputError, OutboxPersistenceError) as exc:
            raise CheckerExecutionUnavailable(unavailable) from exc
        return CheckerRetryDelivery(
            request=stored_request(successor), expected_event=retry_event_expectation(expected),
        ), stored_result(source).infrastructure_failure_code if abandonment is None else None

    async def _lock_task_scope(self, request: PostSubmissionExecutionRequest) -> bool:
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

    async def _replay(self, request: PostSubmissionExecutionRequest) -> CheckerRun | None:
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
        self, request: PostSubmissionExecutionRequest
    ) -> CompletedEvaluation:
        """Return only a locked completed result matching the entire current request."""
        request = validate_execution_request(request)
        with self._session.no_autoflush:
            await self._lock_task_scope(request)
            run = await ExecutionRepository(self._session).lock_current(request)
        if run.status != "completed":
            raise CheckerExecutionUnavailable("checker_current_result_unavailable")
        result = stored_result(run)
        reference = SelectedPostSubmitCurrentResultReference(
            **result.model_dump(
                include=set(SelectedPostSubmitCurrentResultReference.model_fields) - {"schema_version"}
            )
        )
        reference.validate_result(result)
        result.validate_request(request)
        # Terminal custody already recomputed this routing under the locked policy.
        return CompletedEvaluation(
            reference=reference, routing_recommendation=run.routing_recommendation, result=result
        )

    async def classify_uncertain_delivery(
        self, request: PostSubmissionExecutionRequest,
    ) -> PostSubmitRequestDeliveryFacts:
        """Classify one original UNKNOWN request from exact current CHECKERS custody."""
        request = validate_execution_request(request)
        with self._session.no_autoflush:
            await self._lock_task_scope(request)
            try:
                run = await ExecutionRepository(self._session).lock_current(request)
            except CheckerExecutionUnavailable:
                run = await self._closed_automatic_retry_source(request)
        if run.status == "queued":
            retry_safe = (
                run.worker_lease_generation == 0
                and run.worker_lease_id is None
                and run.worker_lease_expires_at is None
                and run.started_at is None
                and run.execute_evidence_id is None
                and run.finalize_evidence_id is None
                and run.result_json is None
                and run.result_digest is None
                and run.input_materialization_evidence_id is None
                and run.material_custody is None
                and run.completion_event_id is None
                and run.completed_at is None
                and run.failure_code is None
                and run.outcome_source == "none"
                and run.routing_recommendation == "not_evaluated"
                and run.passed_count == run.warning_count == run.failed_count
                == run.blocking_count == 0
            )
            return PostSubmitRequestDeliveryFacts(
                request=request,
                checker_run_id=UUID(str(run.id)),
                classification="retry_safe" if retry_safe else "unresolved",
            )
        if run.status == "infrastructure_failed":
            from app.modules.checkers.checker_retry import (
                require_finalized_infrastructure_source,
            )

            retained, _ = require_finalized_infrastructure_source(run)
            if retained != request:
                raise CheckerExecutionUnavailable(
                    "checker_uncertain_delivery_source_unavailable"
                )
            return PostSubmitRequestDeliveryFacts(
                request=request,
                checker_run_id=UUID(str(run.id)),
                classification="committed",
                terminal_outcome="infrastructure_failed",
            )
        if run.status == "completed":
            result = stored_result(run)
            reference = SelectedPostSubmitCurrentResultReference(
                **result.model_dump(
                    include=set(SelectedPostSubmitCurrentResultReference.model_fields)
                    - {"schema_version"}
                )
            )
            try:
                completion_event_id = UUID(str(run.completion_event_id))
                completion = EvaluationCompletion(
                    project_id=request.project_id,
                    task_id=request.task_id,
                    submission_id=request.submission_id,
                    reference=reference,
                    routing_recommendation=run.routing_recommendation,
                    output_binding_ids=(),
                    execute_evidence_id=UUID(run.execute_evidence_id),
                    finalize_evidence_id=UUID(run.finalize_evidence_id),
                )
            except (TypeError, ValueError) as exc:
                raise CheckerExecutionUnavailable(
                    "checker_uncertain_delivery_source_unavailable"
                ) from exc
            await self.require_current_completion(completion_event_id, completion)
            return PostSubmitRequestDeliveryFacts(
                request=request,
                checker_run_id=UUID(str(run.id)),
                classification="committed",
                terminal_outcome="completed",
                completion_event_id=completion_event_id,
            )
        return PostSubmitRequestDeliveryFacts(
            request=request,
            checker_run_id=UUID(str(run.id)),
            classification="unresolved",
        )

    async def _closed_automatic_retry_source(self, request: PostSubmissionExecutionRequest) -> CheckerRun:
        """Resolve a lost delivery ACK after the source and successor committed together."""
        unavailable = "checker_uncertain_delivery_source_unavailable"
        source = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.project_id == str(request.project_id), CheckerRun.task_id == str(request.task_id),
            CheckerRun.submission_id == str(request.submission_id),
            CheckerRun.evaluation_request_id == str(request.evaluation_request_id),
        ))
        if source is None or source.status != "infrastructure_failed" or stored_request(source) != request:
            raise CheckerExecutionUnavailable(unavailable)
        successor = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.submission_id == source.submission_id,
            CheckerRun.evaluation_generation == source.evaluation_generation + 1,
            CheckerRun.supersedes_checker_run_id == source.id,
            CheckerRun.retry_delivery_event_id.is_not(None),
            CheckerRun.retry_abandonment_event_id.is_(None),
        ))
        if successor is None:
            raise CheckerExecutionUnavailable(unavailable)
        await self._read_service_retry(successor)
        return source

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
