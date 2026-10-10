"""One async post-submit execution path over reserved CHECKERS custody."""

import asyncio
import json
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
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
    PostSubmitCurrentResultReference,
)
from app.modules.checkers.api.post_submit_catalogue import canonical_post_submit_bytes
from app.modules.checkers.execution_repository import (
    ExecutionRepository,
    reservation,
    stored_result,
)
from app.modules.checkers.execution_results import classify_result
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.checkers.post_submit_implementations import (
    bounded_structural_result,
    detached_checker_context,
)
from app.modules.checkers.runner import UnknownChecker, CheckerRegistry
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterializationPort, PostSubmissionMaterializationFailure,
)
from app.modules.outbox.api import OutboxAppendPort
from app.modules.outbox.api import OutboxAppendInput

LEASE_SECONDS = 300
EXECUTION_TIMEOUT_SECONDS = 240


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


class _StructuralConsumer:
    """Run registered structural checks while ART owns the verified private view."""

    def __init__(self, registry, lease):
        """Bind the installed registry and reserved attempt identities."""
        self._registry, self._lease = registry, lease

    async def evaluate(self, request, material):
        # ART retains the verified private view for this callback. These registered
        # rules inspect structural facts whose exact archive manifest ART verified.
        """Validate installed definitions and convert bounded outcomes to closed results."""
        del material
        identity = dict(
            request_id=request.evaluation_request_id,
            request_digest=request.request_sha256,
            attempt_id=self._lease.reservation.attempt_id,
            result_id=self._lease.reservation.result_id,
            evaluation_generation=request.evaluation_generation,
        )
        try:
            for entry in request.policy.entries:
                if self._registry.resolve(
                    entry.checker_id
                ).definition != request.catalogue.definition(
                    entry.checker_id, entry.definition_version
                ):
                    raise ValueError("post-submit installed catalogue mismatch")
            limits = request.catalogue.definitions[0].resources
            async with asyncio.timeout(limits.phase_deadline_ms / 1000):
                outcomes = await self._registry.run(
                    detached_checker_context(request), request.policy.entries
                )
            members = tuple(
                bounded_structural_result(
                    request.catalogue.definition(entry.checker_id, entry.definition_version),
                    outcome,
                )
                for entry, outcome in zip(request.policy.entries, outcomes, strict=True)
            )
            result = make_post_submit_result(
                **identity, outcome="completed", member_results=members
            )
            result.validate_request(request)
            return result
        except TimeoutError:
            code = "deadline_exceeded"
        except UnknownChecker:
            code = "implementation_unavailable"
        except ValueError:
            code = "invalid_output"
        return make_post_submit_result(
            **identity,
            outcome="infrastructure_failed",
            member_results=(),
            infrastructure_failure_code=code,
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
        registry: CheckerRegistry,
        outbox: Callable[[AsyncSession], OutboxAppendPort],
    ):
        """Receive explicit session, authority, materialization and publication ports."""
        self._sessions = sessions
        self._execute_authority, self._finalize_authority = execute_authority, finalize_authority
        self._materialization, self._registry, self._outbox = materialization, registry, outbox

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
                lease = ExecutionLease(
                    reservation=reservation(run),
                    lease_id=new_record_id(),
                    lease_generation=run.worker_lease_generation + 1,
                    expires_at=now + timedelta(seconds=LEASE_SECONDS),
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
        self, request: PostSubmissionEvaluationRequest
    ) -> PostSubmissionEvaluationResult:
        """Evaluate outside custody transactions, then separately authorize finalization."""
        request = PostSubmissionEvaluationRequest.model_validate(request)
        lease, replay = await self._claim(request)
        if replay is not None:
            return await self.finalize(replay)
        material = None
        input_materialization_evidence_id = None
        try:
            async with asyncio.timeout(EXECUTION_TIMEOUT_SECONDS):
                materialized = await self._materialization.materialize(
                    ExecuteFacts(request=request, lease=lease), _StructuralConsumer(self._registry, lease)
                )
            material = VerifiedMaterialFacts(
                **{
                    k: v
                    for k, v in asdict(materialized).items()
                    if k not in {"evaluation", "input_materialization_evidence_id"}
                }
            )
            input_materialization_evidence_id = materialized.input_materialization_evidence_id
            result = materialized.evaluation
        except (TimeoutError, PostSubmissionMaterializationFailure) as error:
            result = make_post_submit_result(
                request_id=request.evaluation_request_id,
                request_digest=request.request_sha256,
                attempt_id=lease.reservation.attempt_id,
                result_id=lease.reservation.result_id,
                evaluation_generation=request.evaluation_generation,
                outcome="infrastructure_failed",
                member_results=(),
                infrastructure_failure_code=(
                    "deadline_exceeded" if isinstance(error, TimeoutError) else "material_unavailable"
                ),
            )
        return await self.finalize(
            FinalizeFacts(
                request=request,
                lease=lease,
                result=result,
                material=material,
                input_materialization_evidence_id=input_materialization_evidence_id,
                output_binding_ids=(),
            )
        )

    async def finalize(self, facts: FinalizeFacts) -> PostSubmissionEvaluationResult:
        """Fresh phase-specific PREP and one atomic terminal/member/outbox commit."""
        facts = FinalizeFacts.model_validate(facts)
        request, result = facts.request, facts.result
        classification = classify_result(request, result)
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
                    **facts.model_dump(), execute_evidence_id=UUID(run.execute_evidence_id),
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
                    ):
                        raise CheckerExecutionUnavailable("checker_finalization_replay_conflict")
                    await prepared.validate_replay(authority_facts, UUID(run.finalize_evidence_id))
                    return stored_result(run)
                run = await repo.require_lease(request, facts.lease)
                evidence_id = _evidence(await prepared.consume(authority_facts), FinalizeEvidence, authority_facts)
                completed_at = await repo.now()
                await repo.write_members(run, result)
                if result.outcome == "completed":
                    reference = PostSubmitCurrentResultReference(
                        **result.model_dump(
                            include=set(PostSubmitCurrentResultReference.model_fields)
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
                run.result_json = canonical_post_submit_bytes(
                    result, exclude={"result_digest"}
                ).decode("utf-8")
                run.result_digest = result.result_digest
                run.material_custody = (
                    facts.material.model_dump(mode="json") if facts.material else None
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
