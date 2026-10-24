"""One async post-submit execution path over reserved CHECKERS custody."""

import asyncio
import json
import math
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID
from collections.abc import Callable
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    COMPLETION_EVENT,
    ExecutionAuthorityPort,
    FinalizationAuthorityPort,
    CheckerExecutionUnavailable,
    EvaluationCompletion,
    ExecuteEvidence,
    ExecuteFacts,
    ExecutionLease,
    FinalizeEvidence,
    FinalizeFacts,
    FinalizeAuthorityFacts,
    execution_authority_digest,
    PreparedExecution,
    PreparedFinalization,
    VerifiedMaterialFacts,
)
from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
    validate_execution_request,
)
from app.modules.checkers.api.external import PostSubmitExternalCheckerIdentity
from app.modules.checkers.api.evaluation_context import PostSubmitInputContextCustody
from app.modules.checkers.api.external_policy import (
    SELECTED_POST_FINALIZATION_MARGIN_MS,
    selected_post_submit_execution_budget_ms,
)
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmitCurrentResultReference,
    SelectedPostSubmissionEvaluationRequest,
    SelectedPostSubmitInfrastructureUnavailable,
    make_selected_post_submit_result,
)
from app.modules.checkers.selected_post_submit_execution import (
    SelectedPostSubmitProcessor,
)
from app.interfaces.external_checker_execution import ExternalCheckerExecutionAdapter
from app.modules.checkers.api.canonical_values import canonical_checker_bytes
from app.modules.checkers.execution_repository import (
    ExecutionRepository,
    reservation,
    stored_result,
)
from app.modules.checkers.execution_results import classify_result
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterializationPort,
    PostSubmissionMaterializationFailure,
)
from app.modules.outbox.api import OutboxAppendPort
from app.modules.checkers.api.execution import ReviewModePort
from app.modules.outbox.api import OutboxAppendInput

def _lease(run):
    """Recover the exact persisted lease, including its database expiry."""
    return ExecutionLease(
        reservation=reservation(run),
        lease_id=UUID(run.worker_lease_id),
        lease_generation=run.worker_lease_generation,
        expires_at=run.worker_lease_expires_at,
    )


def _evidence(value, expected_type, facts):
    """Reject a wrong-phase receipt or a digest not bound to these facts."""
    if type(value) is not expected_type or value.facts_digest != execution_authority_digest(facts):
        raise CheckerExecutionUnavailable("checker_action_evidence_unavailable")
    return value.evidence_id


class _SelectedExternalConsumer:
    """Run the selected POST policy through the existing ART callback lifetime."""

    def __init__(
        self,
        execution: ExternalCheckerExecutionAdapter,
        lease: ExecutionLease,
    ) -> None:
        self._execution = execution
        self._lease = lease

    async def evaluate(self, request, material):
        request = SelectedPostSubmissionEvaluationRequest.model_validate(request)
        reservation = self._lease.reservation
        identity = PostSubmitExternalCheckerIdentity(
            project_id=request.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_id=request.submission_id,
            submission_version=request.submission_version,
            evaluation_request_id=request.evaluation_request_id,
            evaluation_request_digest=request.request_sha256,
            evaluation_generation=request.evaluation_generation,
            attempt_id=reservation.attempt_id,
            result_id=reservation.result_id,
            lease_id=self._lease.lease_id,
            lease_generation=self._lease.lease_generation,
            lease_expires_at=self._lease.expires_at,
        )
        values = dict(
            request_id=request.evaluation_request_id,
            request_digest=request.request_sha256,
            attempt_id=reservation.attempt_id,
            evaluation_generation=request.evaluation_generation,
            result_id=reservation.result_id,
        )
        try:
            execution = await SelectedPostSubmitProcessor(
                policy=request.policy,
                identity=identity,
                execution=self._execution,
            ).evaluate(request, material)
            return make_selected_post_submit_result(
                **values,
                outcome="completed",
                execution=execution,
                infrastructure_failure_code=None,
            )
        except SelectedPostSubmitInfrastructureUnavailable as exc:
            return make_selected_post_submit_result(
                **values,
                outcome="infrastructure_failed",
                execution=None,
                infrastructure_failure_code=exc.code,
            )


class PostSubmissionExecutor:
    """Own short execution transactions; all materialization happens outside them."""

    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        execute_authority: Callable[[AsyncSession], ExecutionAuthorityPort],
        finalize_authority: Callable[[AsyncSession], FinalizationAuthorityPort],
        materialization: PostSubmissionMaterializationPort,
        selected_execution: ExternalCheckerExecutionAdapter | None = None,
        outbox: Callable[[AsyncSession], OutboxAppendPort],
        review_modes: Callable[[AsyncSession], ReviewModePort],
    ):
        """Receive explicit session, authority, materialization and publication ports."""
        self._sessions = sessions
        self._review_modes = review_modes
        self._execute_authority, self._finalize_authority = execute_authority, finalize_authority
        self._materialization, self._outbox = materialization, outbox
        self._selected_execution = selected_execution

    @staticmethod
    def _execution_budget_seconds(request: PostSubmissionExecutionRequest) -> int:
        return math.ceil(selected_post_submit_execution_budget_ms(request.policy) / 1000)

    def _consumer(self, request, lease):
        if self._selected_execution is None:
            raise CheckerExecutionUnavailable("checker_external_execution_unavailable")
        return _SelectedExternalConsumer(self._selected_execution, lease)

    async def _claim(self, request):
        """Authorize replay or acquire the next database-timed lease atomically."""
        async with self._sessions() as session, session.begin():
            authority = self._execute_authority(session)
            await authority.preflight(request)
            async with authority.prepare_execution(request) as prepared:
                if not isinstance(prepared, PreparedExecution):
                    raise CheckerExecutionUnavailable("checker_execution_authority_unavailable")
                repo = ExecutionRepository(session)
                run = await repo.lock_current(request)
                if run.status in {"completed", "infrastructure_failed"}:
                    facts = ExecuteFacts(request=request, lease=_lease(run))
                    await prepared.validate_replay(facts, UUID(run.execute_evidence_id))
                    return None, FinalizeFacts(
                        request=request,
                        lease=facts.lease,
                        result=stored_result(run),
                        material=VerifiedMaterialFacts.model_validate_json(
                            json.dumps(run.material_custody)
                        )
                        if run.material_custody is not None
                        else None,
                        input_context_custody=PostSubmitInputContextCustody.model_validate_json(
                            json.dumps(run.input_context_custody)
                        ) if run.input_context_custody is not None else None,
                        input_materialization_evidence_id=(
                            UUID(run.input_materialization_evidence_id)
                            if run.input_materialization_evidence_id
                            else None
                        ),
                        output_binding_ids=(),
                    )
                now = await repo.now()
                if run.status == "running" and run.worker_lease_expires_at > now:
                    raise CheckerExecutionUnavailable("checker_execution_lease_unavailable")
                execution_seconds = self._execution_budget_seconds(request)
                lease_seconds = execution_seconds + math.ceil(
                    SELECTED_POST_FINALIZATION_MARGIN_MS / 1000
                )
                lease = ExecutionLease(
                    reservation=reservation(run),
                    lease_id=new_record_id(),
                    lease_generation=run.worker_lease_generation + 1,
                    expires_at=now + timedelta(seconds=lease_seconds),
                )
                facts = ExecuteFacts(request=request, lease=lease)
                evidence_id = _evidence(await prepared.consume(facts), ExecuteEvidence, facts)
                run.worker_lease_id = str(lease.lease_id)
                run.worker_lease_generation = lease.lease_generation
                run.worker_lease_expires_at = lease.expires_at
                run.started_at = run.started_at or now
                run.status = "running"
                run.execute_evidence_id = str(evidence_id)
                await session.flush()
                return lease, None

    async def evaluate_post_submission(
        self, request: PostSubmissionExecutionRequest
    ) -> PostSubmissionExecutionResult:
        """Evaluate outside custody transactions, then separately authorize finalization."""
        request = validate_execution_request(request)
        lease, replay = await self._claim(request)
        if replay is not None:
            return await self.finalize(replay)
        material = None
        input_materialization_evidence_id = None
        input_context_custody = None
        try:
            async with asyncio.timeout(self._execution_budget_seconds(request)):
                materialized = await self._materialization.materialize(
                    ExecuteFacts(request=request, lease=lease),
                    self._consumer(request, lease),
                )
            material = VerifiedMaterialFacts(
                **{
                    k: v
                    for k, v in asdict(materialized).items()
                    if k not in {"evaluation", "input_materialization_evidence_id", "input_context_custody"}
                }
            )
            input_materialization_evidence_id = materialized.input_materialization_evidence_id
            input_context_custody = materialized.input_context_custody
            result = materialized.evaluation
        except (TimeoutError, PostSubmissionMaterializationFailure) as error:
            values = dict(
                request_id=request.evaluation_request_id,
                request_digest=request.request_sha256,
                attempt_id=lease.reservation.attempt_id,
                result_id=lease.reservation.result_id,
                evaluation_generation=request.evaluation_generation,
                outcome="infrastructure_failed",
                infrastructure_failure_code=(
                    "deadline_exceeded"
                    if isinstance(error, TimeoutError)
                    else "material_unavailable"
                ),
            )
            result = make_selected_post_submit_result(
                **values,
                execution=None,
            )
        return await self.finalize(
            FinalizeFacts(
                request=request,
                lease=lease,
                result=result,
                material=material,
                input_materialization_evidence_id=input_materialization_evidence_id,
                input_context_custody=input_context_custody,
                output_binding_ids=(),
            )
        )

    async def finalize(self, facts: FinalizeFacts) -> PostSubmissionExecutionResult:
        """Fresh phase-specific PREP and one atomic terminal/member/outbox commit."""
        facts = FinalizeFacts.model_validate(facts)
        request, result = facts.request, facts.result
        result.validate_request(request)
        if (result.attempt_id, result.result_id) != (
            facts.lease.reservation.attempt_id,
            facts.lease.reservation.result_id,
        ):
            raise CheckerExecutionUnavailable("checker_final_result_unavailable")
        if result.outcome == "completed" and facts.material is None:
            raise CheckerExecutionUnavailable("checker_material_custody_unavailable")
        if facts.material is not None and (
            facts.material.submission_id,
            facts.material.submission_version,
            facts.material.binding_id,
            facts.material.content_id,
            facts.material.content_sha256,
            facts.material.byte_count,
        ) != (
            request.submission_id,
            request.submission_version,
            request.binding_id,
            request.content_id,
            request.content_sha256,
            request.byte_count,
        ):
            raise CheckerExecutionUnavailable("checker_material_custody_unavailable")
        async with self._sessions() as session, session.begin():
            human = await self._review_modes(session).observe_review_mode(
                request.project_id, request.expected_context.review_policy_id,
            )
            if type(human) is not bool:
                raise CheckerExecutionUnavailable("checker_review_mode_unavailable")
            classification = classify_result(request, result, human_review_required=human)
            authority = self._finalize_authority(session)
            await authority.preflight(request)
            async with authority.prepare_finalization(request) as prepared:
                if not isinstance(prepared, PreparedFinalization):
                    raise CheckerExecutionUnavailable("checker_finalization_authority_unavailable")
                repo = ExecutionRepository(session)
                run = await repo.lock_current(request)
                if run.execute_evidence_id is None:
                    raise CheckerExecutionUnavailable("checker_execution_evidence_unavailable")
                authority_facts = FinalizeAuthorityFacts(
                    **facts.model_dump(),
                    execute_evidence_id=UUID(run.execute_evidence_id),
                )
                if run.status in {"completed", "infrastructure_failed"}:
                    if (
                        stored_result(run) != result
                        or _lease(run) != facts.lease
                        or run.input_materialization_evidence_id
                        != (
                            str(facts.input_materialization_evidence_id)
                            if facts.input_materialization_evidence_id
                            else None
                        )
                        or run.material_custody
                        != (facts.material.model_dump(mode="json") if facts.material else None)
                        or run.input_context_custody != (
                            facts.input_context_custody.model_dump(mode="json")
                            if facts.input_context_custody else None
                        )
                    ):
                        raise CheckerExecutionUnavailable("checker_finalization_replay_conflict")
                    await prepared.validate_replay(authority_facts, UUID(run.finalize_evidence_id))
                    return stored_result(run)
                run = await repo.require_lease(request, facts.lease)
                evidence_id = _evidence(
                    await prepared.consume(authority_facts), FinalizeEvidence, authority_facts
                )
                completed_at = await repo.now()
                await repo.write_members(run, result)
                if result.outcome == "completed":
                    reference = SelectedPostSubmitCurrentResultReference(
                        **result.model_dump(
                            include=set(SelectedPostSubmitCurrentResultReference.model_fields)
                            - {"schema_version"}
                        )
                    )
                    reference.validate_result(result)
                    event = EvaluationCompletion(
                        project_id=request.project_id,
                        task_id=request.task_id,
                        submission_id=request.submission_id,
                        reference=reference,
                        routing_recommendation=classification.routing,
                        output_binding_ids=(),
                        execute_evidence_id=UUID(run.execute_evidence_id),
                        finalize_evidence_id=evidence_id,
                    )
                    appended = await self._outbox(session).append(
                        OutboxAppendInput(
                            event_type=COMPLETION_EVENT,
                            event_version=1,
                            aggregate_type="checker_run",
                            aggregate_id=UUID(run.id),
                            project_id=request.project_id,
                            correlation_id=str(request.evaluation_request_id),
                            idempotency_key="checker-completed:" + run.id,
                            payload=event.model_dump(mode="json"),
                        )
                    )
                    run.completion_event_id = appended.event_id
                run.result_json = canonical_checker_bytes(
                    result, exclude={"result_digest"}
                ).decode("utf-8")
                run.result_digest = result.result_digest
                run.material_custody = (
                    facts.material.model_dump(mode="json") if facts.material else None
                )
                run.input_context_custody = (
                    facts.input_context_custody.model_dump(mode="json")
                    if facts.input_context_custody else None
                )
                run.input_materialization_evidence_id = (
                    str(facts.input_materialization_evidence_id)
                    if facts.input_materialization_evidence_id
                    else None
                )
                run.finalize_evidence_id = str(evidence_id)
                run.routing_recommendation = classification.routing
                run.passed_count, run.warning_count = classification.passed, classification.warning
                run.failed_count, run.blocking_count = (
                    classification.failed,
                    classification.blocking,
                )
                run.completed_at = completed_at
                run.failure_code = result.infrastructure_failure_code
                run.outcome_source = "auto_checker"
                run.status = result.outcome
                await session.flush()
                return result
