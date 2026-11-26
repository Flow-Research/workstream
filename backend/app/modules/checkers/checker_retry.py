"""Exact automatic and Operator retry custody for terminal checker failures."""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    CheckerRequestConflict,
    CheckerRetryAuditPort,
    CheckerRetryAuthorizationPort,
    CheckerRetryCommand,
    CheckerRetryDelivery,
    CheckerRetryDiscoveryAuthorizationPort,
    CheckerRetryAuthorityDenied,
    CheckerRetryDiscoverySource,
    CheckerRetryEventExpectation,
    CheckerRetryOperationUnavailable,
    CheckerRetryPreparation,
    CheckerRetryResult,
    CheckerRetrySource,
    CheckerRetrySourceUnavailable,
    CheckerRetrySourceItem,
    CheckerRetrySourcePage,
    CheckerRetrySourcePosition,
    CheckerRetrySourceQuery,
    CheckerRetrySuccessor,
    EvaluationTaskGuard,
    POST_SUBMISSION_RETRY_OPTIONS, REQUEST_EVENT,
)
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest
from app.modules.checkers.api.selected_post_submit import make_selected_post_submit_request
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.execution_repository import (
    require_transaction,
    stored_request,
    stored_result,
)
from app.modules.checkers.models import (
    CheckerRetryReceipt,
    CheckerRun,
    CheckerSubmissionFence,
)
from app.modules.model_usage.api import ModelRecoverySourcePort
from app.modules.outbox.api import (
    OutboxAppendInput,
    OutboxAppendPort,
    OutboxAppendResult,
    OutboxIdempotencyConflict,
    OutboxInputError,
    OutboxPersistenceError,
)


def require_finalized_infrastructure_source(
    run: CheckerRun,
) -> tuple[PostSubmissionExecutionRequest, CheckerRetrySource]:
    """Require a real terminal result/finalization before any new Operator effect."""
    if (
        run.status != "infrastructure_failed"
        or run.finalize_evidence_id is None
        or run.result_json is None
        or run.result_digest is None
        or run.completion_event_id is not None
        or run.failure_code is None
    ):
        raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
    try:
        request = stored_request(run)
        result = stored_result(run)
    except CheckerExecutionUnavailable as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_evidence_unavailable") from exc
    if result.outcome != "infrastructure_failed":
        raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
    if (
        result.infrastructure_failure_code != run.failure_code
        or request.evaluation_generation != run.evaluation_generation
    ):
        raise CheckerRetryOperationUnavailable("checker_retry_evidence_unavailable")
    try:
        source = CheckerRetrySource(
            project_id=request.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_id=request.submission_id,
            submission_version=request.submission_version,
            source_run_id=UUID(run.id),
            source_request_id=request.evaluation_request_id,
            source_request_digest=request.request_sha256,
            source_result_id=UUID(run.result_id),
            source_result_digest=run.result_digest,
            source_finalize_evidence_id=UUID(run.finalize_evidence_id),
            source_generation=run.evaluation_generation,
            failure_code=run.failure_code,
        )
    except (TypeError, ValueError) as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_evidence_unavailable") from exc
    return request, source


def _source_from_receipt(receipt: CheckerRetryReceipt) -> CheckerRetrySource:
    try:
        return CheckerRetrySource(
            project_id=UUID(receipt.project_id),
            task_id=UUID(receipt.task_id),
            assignment_id=UUID(receipt.assignment_id),
            submission_id=UUID(receipt.submission_id),
            submission_version=receipt.submission_version,
            source_run_id=UUID(receipt.source_run_id),
            source_request_id=UUID(receipt.source_request_id),
            source_request_digest=receipt.source_request_digest,
            source_result_id=UUID(receipt.source_result_id),
            source_result_digest=receipt.source_result_digest,
            source_finalize_evidence_id=UUID(receipt.source_finalize_evidence_id),
            source_generation=receipt.source_generation,
            failure_code=receipt.failure_code,
        )
    except (TypeError, ValueError) as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_replay_unavailable") from exc


def _successor_from_receipt(receipt: CheckerRetryReceipt) -> CheckerRetrySuccessor:
    try:
        return CheckerRetrySuccessor(
            request_id=UUID(receipt.successor_request_id),
            request_digest=receipt.successor_request_digest,
            run_id=UUID(receipt.successor_run_id),
            result_id=UUID(receipt.successor_result_id),
            generation=receipt.successor_generation,
            event_id=receipt.event_id,
            audit_event_id=UUID(receipt.audit_event_id),
        )
    except (TypeError, ValueError) as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_replay_unavailable") from exc


def retry_successor_request(previous: PostSubmissionExecutionRequest) -> PostSubmissionExecutionRequest:
    """Retain every locked request fact apart from identity and generation."""
    return make_selected_post_submit_request(
        **previous.model_dump(exclude={"evaluation_request_id", "evaluation_generation", "request_sha256"}),
        evaluation_request_id=new_record_id(), evaluation_generation=previous.evaluation_generation + 1,
    )


def abandoned_retry_event(prior: CheckerRun, successor: CheckerRun, cause: UUID) -> OutboxAppendInput:
    """Record an explicit abandonment child without asserting a checker result."""
    if prior.status != "running" or prior.worker_lease_id is None:
        raise CheckerRetrySourceUnavailable("checker_abandonment_source_unavailable")
    return OutboxAppendInput(
        event_type=REQUEST_EVENT, event_version=1, aggregate_type="submission",
        aggregate_id=UUID(successor.submission_id), project_id=UUID(successor.project_id),
        correlation_id=prior.id, causation_event_id=cause,
        idempotency_key="checker-abandonment-retry:" + prior.id,
        payload={
            "project_id": successor.project_id, "task_id": successor.task_id,
            "submission_id": successor.submission_id, "submission_version": successor.submission_version,
            "request_id": successor.evaluation_request_id, "request_digest": successor.request_digest,
            "evaluation_generation": successor.evaluation_generation, "attempt_id": successor.id,
            "result_id": successor.result_id, "source_run_id": prior.id,
            "source_worker_lease_id": prior.worker_lease_id,
            "source_worker_lease_generation": prior.worker_lease_generation,
        },
    )


def automatic_retry_event(prior: CheckerRun, successor: CheckerRun) -> OutboxAppendInput:
    """Use the committed fixed-service finalization as the automatic retry cause."""
    _, source = require_finalized_infrastructure_source(prior)
    if prior.completed_at is None or source.source_generation >= POST_SUBMISSION_RETRY_OPTIONS.max_attempts:
        raise CheckerRetrySourceUnavailable("checker_automatic_retry_source_unavailable")
    return OutboxAppendInput(
        event_type=REQUEST_EVENT, event_version=1, aggregate_type="submission",
        aggregate_id=source.submission_id, project_id=source.project_id,
        correlation_id=str(source.source_run_id),
        idempotency_key="checker-auto-retry:" + str(source.source_run_id),
        not_before_at=prior.completed_at + timedelta(seconds=POST_SUBMISSION_RETRY_OPTIONS.retry_delay_seconds(
            source.source_generation,
        )),
        payload={
            "project_id": str(source.project_id), "task_id": str(source.task_id),
            "submission_id": str(source.submission_id), "submission_version": source.submission_version,
            "request_id": successor.evaluation_request_id, "request_digest": successor.request_digest,
            "evaluation_generation": successor.evaluation_generation, "attempt_id": successor.id,
            "result_id": successor.result_id, "source_run_id": str(source.source_run_id),
            "source_result_digest": source.source_result_digest,
            "source_finalize_evidence_id": str(source.source_finalize_evidence_id),
        },
    )


def retry_event_expectation(expected: OutboxAppendInput) -> CheckerRetryEventExpectation:
    """Express the exact immutable event expected by TASK and progress readers."""
    return CheckerRetryEventExpectation(
        event_type=expected.event_type, event_version=expected.event_version,
        aggregate_type=expected.aggregate_type, aggregate_id=expected.aggregate_id,
        correlation_id=expected.correlation_id, causation_event_id=expected.causation_event_id,
        idempotency_key=expected.idempotency_key, not_before_at=expected.not_before_at,
        payload_json=json.dumps(expected.payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False),
        payload_digest=canonical_json_hash(expected.payload),
    )


def retry_request_event(
    source: CheckerRetrySource,
    *,
    receipt_id: UUID,
    request_id: UUID,
    request_digest: str,
    run_id: UUID,
    result_id: UUID,
) -> OutboxAppendInput:
    """One v1 request event schema for creation and later exact delivery."""
    return OutboxAppendInput(
        event_type="PostSubmissionEvaluationRequested",
        event_version=1,
        aggregate_type="submission",
        aggregate_id=source.submission_id,
        project_id=source.project_id,
        correlation_id=str(source.source_run_id),
        idempotency_key="checker-retry:" + str(source.source_run_id),
        payload={
            "project_id": str(source.project_id),
            "task_id": str(source.task_id),
            "submission_id": str(source.submission_id),
            "submission_version": source.submission_version,
            "request_id": str(request_id),
            "request_digest": request_digest,
            "evaluation_generation": source.source_generation + 1,
            "attempt_id": str(run_id),
            "result_id": str(result_id),
            "source_run_id": str(source.source_run_id),
            "source_result_digest": source.source_result_digest,
            "retry_receipt_id": str(receipt_id),
        },
    )


async def _append_retry_event(
    events: OutboxAppendPort,
    source: CheckerRetrySource,
    *,
    receipt_id: UUID,
    request_id: UUID,
    request_digest: str,
    run_id: UUID,
    result_id: UUID,
) -> OutboxAppendResult:
    """Normalize exact OUTBOX contract failures into retry-owner unavailability."""
    try:
        return await events.append(
            retry_request_event(
                source,
                receipt_id=receipt_id,
                request_id=request_id,
                request_digest=request_digest,
                run_id=run_id,
                result_id=result_id,
            )
        )
    except (
        OutboxIdempotencyConflict,
        OutboxInputError,
        OutboxPersistenceError,
    ) as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_outbox_unavailable") from exc


class CheckerRetryService:
    """Compose existing TASK, AUTH, CHECKERS, OUTBOX and AUDIT owner operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        actor_profile_id: UUID,
        tasks: EvaluationTaskGuard,
        evaluations: EvaluationCoordinator,
        authorization: CheckerRetryAuthorizationPort,
        discovery: CheckerRetryDiscoveryAuthorizationPort,
        events: OutboxAppendPort,
        audit: CheckerRetryAuditPort,
        model_recovery: ModelRecoverySourcePort,
    ) -> None:
        self._session, self._actor_profile_id = session, actor_profile_id
        self._tasks, self._evaluations = tasks, evaluations
        self._authorization, self._discovery = authorization, discovery
        self._events, self._audit = events, audit
        self._model_recovery = model_recovery

    async def discover(self, query: CheckerRetrySourceQuery) -> CheckerRetrySourcePage:
        """List only retained finalized infrastructure failures under fresh authority."""
        query = CheckerRetrySourceQuery.model_validate(query)
        after = await self._discovery.authorize_and_decode(query)
        statement = (
            select(
                CheckerRun.project_id.label("project_id"),
                CheckerRun.task_id.label("task_id"),
                CheckerRun.submission_id.label("submission_id"),
                CheckerRun.submission_version.label("submission_version"),
                CheckerRun.id.label("source_run_id"),
                CheckerRun.evaluation_request_id.label("source_request_id"),
                CheckerRun.request_digest.label("source_request_digest"),
                CheckerRun.result_id.label("source_result_id"),
                CheckerRun.result_digest.label("source_result_digest"),
                CheckerRun.finalize_evidence_id.label("source_finalize_evidence_id"),
                CheckerRun.evaluation_generation.label("source_generation"),
                CheckerRun.failure_code.label("failure_code"),
                CheckerRun.created_at.label("created_at"),
                CheckerRun.completed_at.label("completed_at"),
                CheckerRetryReceipt.id.label("retry_receipt_id"),
                CheckerRetryReceipt.successor_request_id.label("successor_request_id"),
                CheckerRetryReceipt.successor_request_digest.label("successor_request_digest"),
                CheckerRetryReceipt.successor_run_id.label("successor_run_id"),
                CheckerRetryReceipt.successor_result_id.label("successor_result_id"),
                CheckerRetryReceipt.successor_generation.label("successor_generation"),
                CheckerRetryReceipt.event_id.label("successor_event_id"),
                CheckerRetryReceipt.audit_event_id.label("successor_audit_event_id"),
                CheckerSubmissionFence.current_run_id.label("current_run_id"),
            )
            .outerjoin(
                CheckerRetryReceipt,
                CheckerRetryReceipt.source_run_id == CheckerRun.id,
            )
            .outerjoin(
                CheckerSubmissionFence,
                CheckerSubmissionFence.submission_id == CheckerRun.submission_id,
            )
            .where(
                CheckerRun.project_id == str(query.project_id),
                CheckerRun.phase == "post_submission",
                CheckerRun.status == "infrastructure_failed",
                CheckerRun.finalize_evidence_id.is_not(None),
                CheckerRun.result_json.is_not(None),
                CheckerRun.result_digest.is_not(None),
                CheckerRun.completion_event_id.is_(None),
                CheckerRun.failure_code.is_not(None),
                CheckerRun.completed_at.is_not(None),
            )
        )
        if after is not None:
            statement = statement.where(
                tuple_(CheckerRun.created_at, CheckerRun.id)
                > tuple_(after.created_at, str(after.source_run_id))
            )
        rows = (
            (
                await self._session.execute(
                    statement.order_by(CheckerRun.created_at, CheckerRun.id).limit(query.limit + 1)
                )
            )
            .mappings()
            .all()
        )
        recovery_candidates = await self._model_recovery.recovery_candidates(
            tuple(UUID(row.source_run_id) for row in rows[: query.limit]),
        )
        items = []
        for row in rows[: query.limit]:
            source = CheckerRetryDiscoverySource(
                project_id=UUID(row.project_id),
                task_id=UUID(row.task_id),
                submission_id=UUID(row.submission_id),
                submission_version=row.submission_version,
                source_run_id=UUID(row.source_run_id),
                source_request_id=UUID(row.source_request_id),
                source_request_digest=row.source_request_digest,
                source_result_id=UUID(row.source_result_id),
                source_result_digest=row.source_result_digest,
                source_finalize_evidence_id=UUID(row.source_finalize_evidence_id),
                source_generation=row.source_generation,
                failure_code=row.failure_code,
            )
            state: Literal["eligible", "retried", "not_current"]
            if row.retry_receipt_id is not None:
                state, receipt_id, successor = (
                    "retried",
                    UUID(row.retry_receipt_id),
                    CheckerRetrySuccessor(
                        request_id=UUID(row.successor_request_id),
                        request_digest=row.successor_request_digest,
                        run_id=UUID(row.successor_run_id),
                        result_id=UUID(row.successor_result_id),
                        generation=row.successor_generation,
                        event_id=row.successor_event_id,
                        audit_event_id=UUID(row.successor_audit_event_id),
                    ),
                )
            else:
                state = "eligible" if row.current_run_id == row.source_run_id else "not_current"
                receipt_id, successor = None, None
            items.append(
                CheckerRetrySourceItem(
                    source=source,
                    recovery_state=state,
                    created_at=row.created_at,
                    completed_at=row.completed_at,
                    retry_receipt_id=receipt_id,
                    successor=successor,
                    model_recovery_candidates=recovery_candidates.get(UUID(row.source_run_id), ()),
                )
            )
        next_cursor = None
        if len(rows) > query.limit:
            last = items[-1]
            next_cursor = self._discovery.encode(
                query,
                CheckerRetrySourcePosition(
                    created_at=last.created_at,
                    source_run_id=last.source.source_run_id,
                ),
            )
        return CheckerRetrySourcePage(
            project_id=query.project_id,
            items=tuple(items),
            next_cursor=next_cursor,
        )

    async def retry(self, command: CheckerRetryCommand) -> CheckerRetryResult:
        """Return one new authorized successor or the exact retained replay."""
        require_transaction(self._session)
        command = CheckerRetryCommand.model_validate(command)
        # Detached selectors only: no CHECKERS lock, AUTH custody or decision yet.
        existing = await self._session.scalar(
            select(CheckerRetryReceipt)
            .where(
                CheckerRetryReceipt.actor_profile_id == str(self._actor_profile_id),
                CheckerRetryReceipt.request_key == str(command.request_key),
            )
            .execution_options(populate_existing=True)
        )
        if existing is not None and existing.project_id != str(command.project_id):
            raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
        if existing is not None:
            try:
                source_id = UUID(existing.source_run_id)
            except (TypeError, ValueError) as exc:
                raise CheckerRetryOperationUnavailable("checker_retry_replay_unavailable") from exc
        else:
            source_id = command.source_run_id
        source_run = await self._session.scalar(
            select(CheckerRun)
            .where(
                CheckerRun.id == str(source_id),
                CheckerRun.project_id == str(command.project_id),
                CheckerRun.phase == "post_submission",
            )
            .execution_options(populate_existing=True)
        )
        if source_run is None:
            raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
        try:
            source_request = stored_request(source_run)
        except CheckerExecutionUnavailable as exc:
            raise CheckerRetryOperationUnavailable("checker_retry_evidence_unavailable") from exc
        # Both branches first hold the same historical TASK owner rows. A
        # contender that saw no detached receipt must reread it after this
        # lock: the first transaction may have committed while it waited.
        try:
            await self._tasks.lock_retry_replay_scope(source_request)
        except CheckerExecutionUnavailable as exc:
            unavailable = (
                CheckerRetryOperationUnavailable
                if existing is not None
                else CheckerRetrySourceUnavailable
            )
            raise unavailable("checker_retry_scope_unavailable") from exc
        existing = await self._session.scalar(
            select(CheckerRetryReceipt)
            .where(
                CheckerRetryReceipt.actor_profile_id == str(self._actor_profile_id),
                CheckerRetryReceipt.request_key == str(command.request_key),
            )
            .execution_options(populate_existing=True)
        )
        if existing is not None and (
            existing.source_run_id != str(command.source_run_id)
            or existing.reason != command.reason
        ):
            raise CheckerRequestConflict("checker_retry_request_conflict")
        if existing is None:
            try:
                await self._tasks.lock_terminal_retry_scope(source_request)
            except CheckerExecutionUnavailable as exc:
                raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable") from exc
        source_run = await self._session.scalar(
            select(CheckerRun)
            .where(
                CheckerRun.id == str(source_id),
                CheckerRun.project_id == str(command.project_id),
                CheckerRun.phase == "post_submission",
            )
            .execution_options(populate_existing=True)
        )
        if source_run is None:
            raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
        locked_request, source = require_finalized_infrastructure_source(source_run)
        if locked_request != source_request:
            raise CheckerRetrySourceUnavailable("checker_retry_source_unavailable")
        if existing is not None:
            return await self._replay(command, existing, source)
        preparation = CheckerRetryPreparation(
            actor_profile_id=self._actor_profile_id,
            request_key=command.request_key,
            reason=command.reason,
            source=source,
        )
        handle = await self._authorization.prepare(preparation)
        try:
            next_request = retry_successor_request(source_request)
            try:
                reserved = await self._evaluations._reserve_after_task_lock(
                    next_request,
                    terminal_source_id=source.source_run_id,
                )
            except CheckerRetrySourceUnavailable:
                raise
            except CheckerExecutionUnavailable as exc:
                raise CheckerRetryOperationUnavailable(
                    "checker_retry_reservation_unavailable"
                ) from exc
            if (
                reserved.request_id != next_request.evaluation_request_id
                or reserved.request_digest != next_request.request_sha256
                or reserved.evaluation_generation != source.source_generation + 1
            ):
                raise CheckerRetryOperationUnavailable("checker_retry_reservation_unavailable")
            receipt_id = new_record_id()
            event = await _append_retry_event(
                self._events,
                source,
                receipt_id=receipt_id,
                request_id=reserved.request_id,
                request_digest=reserved.request_digest,
                run_id=reserved.attempt_id,
                result_id=reserved.result_id,
            )
            successor = CheckerRetrySuccessor(
                request_id=reserved.request_id,
                request_digest=reserved.request_digest,
                run_id=reserved.attempt_id,
                result_id=reserved.result_id,
                generation=reserved.evaluation_generation,
                event_id=event.event_id,
                audit_event_id=new_record_id(),
            )
            authority = await self._authorization.consume(handle, preparation, successor)
            await self._audit.record(preparation, successor, authority)
            receipt = CheckerRetryReceipt(
                id=str(receipt_id),
                actor_profile_id=str(self._actor_profile_id),
                identity_link_id=str(authority.identity_link_id),
                request_key=str(command.request_key),
                reason=command.reason,
                project_id=str(source.project_id),
                task_id=str(source.task_id),
                assignment_id=str(source.assignment_id),
                submission_id=str(source.submission_id),
                submission_version=source.submission_version,
                source_run_id=str(source.source_run_id),
                source_request_id=str(source.source_request_id),
                source_request_digest=source.source_request_digest,
                source_result_id=str(source.source_result_id),
                source_result_digest=source.source_result_digest,
                source_finalize_evidence_id=str(source.source_finalize_evidence_id),
                source_generation=source.source_generation,
                failure_code=source.failure_code,
                successor_run_id=str(successor.run_id),
                successor_request_id=str(successor.request_id),
                successor_request_digest=successor.request_digest,
                successor_result_id=str(successor.result_id),
                successor_generation=successor.generation,
                event_id=successor.event_id,
                audit_event_id=str(successor.audit_event_id),
                authorization_decision_id=str(authority.decision_id),
                resource_digest=authority.resource_digest,
                resource_json=authority.resource_json,
            )
            self._session.add(receipt)
            await self._session.flush()
            return CheckerRetryResult(
                receipt_id=receipt_id,
                source=source,
                successor=successor,
                authorization_decision_id=authority.decision_id,
            )
        finally:
            self._authorization.close(handle)

    async def restage_denial(self, error: CheckerRetryAuthorityDenied) -> bool:
        """Delegate exact denied mutation evidence to its issuing AUTH adapter."""
        return await self._authorization.restage_denial(error)

    async def restage_discovery_denial(self, error: Exception) -> bool:
        """Delegate exact denied read evidence to its issuing AUTH adapter."""
        return await self._discovery.restage_denial(error)

    async def _replay(
        self,
        command: CheckerRetryCommand,
        detached: CheckerRetryReceipt,
        source: CheckerRetrySource,
    ) -> CheckerRetryResult:
        preparation = CheckerRetryPreparation(
            actor_profile_id=self._actor_profile_id,
            request_key=command.request_key,
            reason=command.reason,
            source=source,
        )
        handle = await self._authorization.prepare(preparation)
        try:
            receipt = await self._session.scalar(
                select(CheckerRetryReceipt)
                .where(
                    CheckerRetryReceipt.id == detached.id,
                    CheckerRetryReceipt.actor_profile_id == str(self._actor_profile_id),
                    CheckerRetryReceipt.request_key == str(command.request_key),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                receipt is None
                or _source_from_receipt(receipt) != source
                or receipt.reason != command.reason
            ):
                raise CheckerRetryOperationUnavailable("checker_retry_replay_unavailable")
            successor = _successor_from_receipt(receipt)
            delivery = await read_retry_delivery(
                self._session,
                self._evaluations,
                project_id=source.project_id,
                submission_id=source.submission_id,
                event_id=successor.event_id,
            )
            # The reader already binds the retained run/result/generation to this receipt.
            if delivery is None or delivery.request.evaluation_request_id != successor.request_id:
                raise CheckerRetryOperationUnavailable("checker_retry_replay_unavailable")
            try:
                identity_link_id = UUID(receipt.identity_link_id)
                decision_id = UUID(receipt.authorization_decision_id)
                receipt_id = UUID(receipt.id)
            except (TypeError, ValueError) as exc:
                raise CheckerRetryOperationUnavailable("checker_retry_replay_unavailable") from exc
            await self._authorization.validate_replay(
                handle,
                preparation,
                successor,
                identity_link_id,
                decision_id,
            )
            return CheckerRetryResult(
                receipt_id=receipt_id,
                source=source,
                successor=successor,
                authorization_decision_id=decision_id,
            )
        finally:
            self._authorization.close(handle)


async def read_retry_delivery(
    session: AsyncSession,
    evaluations: EvaluationCoordinator,
    *,
    project_id: UUID,
    submission_id: UUID,
    event_id: UUID,
) -> CheckerRetryDelivery | None:
    """Expose only a committed exact receipt through CHECKERS's existing port."""
    receipt = await session.scalar(
        select(CheckerRetryReceipt)
        .where(
            CheckerRetryReceipt.project_id == str(project_id),
            CheckerRetryReceipt.submission_id == str(submission_id),
            CheckerRetryReceipt.event_id == event_id,
        )
        .execution_options(populate_existing=True)
    )
    if receipt is None:
        return None
    source, successor = _source_from_receipt(receipt), _successor_from_receipt(receipt)
    try:
        stored = await evaluations.read_reserved_evaluation(
            project_id=source.project_id,
            task_id=source.task_id,
            submission_id=source.submission_id,
            request_id=successor.request_id,
        )
    except CheckerExecutionUnavailable as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_delivery_unavailable") from exc
    if (
        stored.reservation.request_digest != successor.request_digest
        or stored.reservation.attempt_id != successor.run_id
        or stored.reservation.result_id != successor.result_id
        or stored.reservation.evaluation_generation != successor.generation
        or stored.request.assignment_id != source.assignment_id
        or stored.request.submission_version != source.submission_version
    ):
        raise CheckerRetryOperationUnavailable("checker_retry_delivery_unavailable")
    try:
        receipt_id = UUID(receipt.id)
    except (TypeError, ValueError) as exc:
        raise CheckerRetryOperationUnavailable("checker_retry_delivery_unavailable") from exc
    expected = retry_request_event(
        source,
        receipt_id=receipt_id,
        request_id=successor.request_id,
        request_digest=successor.request_digest,
        run_id=successor.run_id,
        result_id=successor.result_id,
    )
    return CheckerRetryDelivery(
        request=stored.request,
        expected_event=retry_event_expectation(expected),
    )
