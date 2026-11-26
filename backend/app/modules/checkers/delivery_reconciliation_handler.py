"""Execute one immutable uncertain-delivery reconciliation child."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryChildPayload,
    PostSubmitDeliveryOperationUnavailable,
    PostSubmitDeliveryRetryable,
    PostSubmitDeliverySourceUnavailable,
)
from app.modules.checkers.api.execution import (
    COMPLETION_EVENT,
    REQUEST_EVENT,
    CheckerExecutionUnavailable,
    EvaluationCoordinationPort,
)
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest
from app.modules.checkers.delivery_reconciliation import (
    PostSubmitDeliveryOutcomePort,
    PostSubmitDeliveryRequestReadPort,
    RECONCILIATION_EVENT,
    SUPPORTED_DELIVERIES,
)
from app.modules.outbox.api import (
    CommittedInvocationObservation,
    CommittedInvocationPort,
    DeliveryUnavailable,
    FinalizedUnknownDeliveryPort,
    HandlerOutcome,
    InvocationFencePort,
    OutboxClaim,
    OutboxEventEnvelope,
)


def _matches_child(
    child: OutboxEventEnvelope,
    payload: PostSubmitDeliveryChildPayload,
) -> bool:
    return (
        child.event_type == RECONCILIATION_EVENT
        and child.event_version == 1
        and child.aggregate_type == "outbox_delivery"
        and child.aggregate_id == payload.original_event_id
        and child.causation_event_id == payload.original_event_id
    )


class PostSubmitDeliveryCauseAuthorizationPort(Protocol):
    """Validate the retained human Operator decision as cause, not authority."""

    async def validate_cause(
        self,
        payload: PostSubmitDeliveryChildPayload,
        original: OutboxEventEnvelope,
    ) -> None: ...


def _matches_original(
    original: OutboxEventEnvelope,
    payload: PostSubmitDeliveryChildPayload,
) -> bool:
    return (
        original.claim.event_id == payload.original_event_id
        and original.claim.claim_generation == payload.original_claim_generation
        and original.claim.payload_digest == payload.original_payload_digest
        and original.event_type == payload.original_event_type
        and original.event_version == payload.original_event_version
    )


class ReconciliationInvocationCustody(CommittedInvocationPort, InvocationFencePort):
    """Map original owner calls to the sole live child plus terminal original fence."""

    def __init__(
        self,
        *,
        child: OutboxEventEnvelope,
        original: OutboxEventEnvelope,
        observer: CommittedInvocationPort,
        deliveries: FinalizedUnknownDeliveryPort,
    ) -> None:
        self._child, self._original = child, original
        self._observer, self._deliveries = observer, deliveries

    async def observe_invocation(
        self, envelope: OutboxEventEnvelope,
    ) -> CommittedInvocationObservation | None:
        if envelope != self._original:
            return None
        observed = await self._observer.observe_invocation(self._child)
        if observed is None or observed.claim != self._child.claim:
            return None
        return CommittedInvocationObservation(
            claim=self._original.claim,
            observed_at=observed.observed_at,
        )

    async def fence_invocation(
        self, envelope: OutboxEventEnvelope,
    ) -> CommittedInvocationObservation | None:
        if envelope != self._original:
            return None
        observed = await self._deliveries.fence_reconciliation(
            original=self._original,
            child=self._child,
            event_types=SUPPORTED_DELIVERIES,
            child_event_type=RECONCILIATION_EVENT,
        )
        if observed is None or observed.claim != self._child.claim:
            return None
        return CommittedInvocationObservation(
            claim=self._original.claim,
            observed_at=observed.observed_at,
        )


class PostSubmitDeliveryReconciliationHandler:
    """Reclassify under owner locks, then verify or execute without blind retry."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        observer: CommittedInvocationPort,
        deliveries: Callable[[AsyncSession], FinalizedUnknownDeliveryPort],
        evaluations: Callable[[AsyncSession], EvaluationCoordinationPort],
        requests: Callable[
            [AsyncSession, EvaluationCoordinationPort],
            PostSubmitDeliveryRequestReadPort,
        ],
        authorization: Callable[
            [AsyncSession], PostSubmitDeliveryCauseAuthorizationPort
        ],
        outcomes: Callable[
            [
                AsyncSession,
                ReconciliationInvocationCustody,
                Callable[[], Awaitable[OutboxClaim]],
            ],
            PostSubmitDeliveryOutcomePort,
        ],
        executor: Callable[
            [
                OutboxEventEnvelope,
                OutboxEventEnvelope,
                PostSubmitDeliveryChildPayload,
                PostSubmissionExecutionRequest,
            ],
            object,
        ],
    ) -> None:
        self._sessions, self._observer = sessions, observer
        self._deliveries, self._evaluations, self._requests = (
            deliveries, evaluations, requests
        )
        self._authorization, self._outcomes, self._executor = (
            authorization,
            outcomes,
            executor,
        )

    async def __call__(self, child: OutboxEventEnvelope) -> HandlerOutcome:
        try:
            child = OutboxEventEnvelope.model_validate(child)
            payload = PostSubmitDeliveryChildPayload.model_validate_json(
                child.payload_json
            )
        except (TypeError, ValueError, ValidationError):
            return HandlerOutcome.REJECT
        if not _matches_child(child, payload):
            return HandlerOutcome.REJECT
        observed = await self._observer.observe_invocation(child)
        if observed is None or observed.claim != child.claim:
            return HandlerOutcome.REJECT

        try:
            async with self._sessions() as session, session.begin():
                classified = await self._classify_child(session, child, payload)
        except (
            PostSubmitDeliverySourceUnavailable,
            PostSubmitDeliveryOperationUnavailable,
            CheckerExecutionUnavailable,
            DeliveryUnavailable,
        ):
            return HandlerOutcome.REJECT
        if isinstance(classified, HandlerOutcome):
            return classified
        original, request = classified

        # Existing owner operations open their own effect transactions. Their
        # recovery-bound authority repeats currentness, Operator cause, original
        # terminal custody and live child custody before every effect commit.
        if original.event_type == REQUEST_EVENT:
            result = await self._executor(
                child, original, payload, request
            ).evaluate_post_submission(request)
            result.validate_request(request)
            return HandlerOutcome.ACKNOWLEDGE
        try:
            async with self._sessions() as session, session.begin():
                deliveries = self._deliveries(session)
                custody = ReconciliationInvocationCustody(
                    child=child,
                    original=original,
                    observer=self._observer,
                    deliveries=deliveries,
                )
                cause = self._authorization(session)

                async def reconciliation_claim() -> OutboxClaim:
                    await cause.validate_cause(payload, original)
                    return child.claim

                outcomes = self._outcomes(session, custody, reconciliation_claim)
                generation = await outcomes.observe_delivery_generation(original)
                await outcomes.apply(original, current_generation=generation)
            return HandlerOutcome.ACKNOWLEDGE
        except PostSubmitDeliveryRetryable:
            return HandlerOutcome.RETRY
        except (PostSubmitDeliverySourceUnavailable, CheckerExecutionUnavailable):
            return HandlerOutcome.REJECT

    async def _classify_child(
        self,
        session: AsyncSession,
        child: OutboxEventEnvelope,
        payload: PostSubmitDeliveryChildPayload,
    ) -> HandlerOutcome | tuple[
        OutboxEventEnvelope, PostSubmissionExecutionRequest | None
    ]:
        """Return a terminal outcome or the exact source for one safe retry."""
        deliveries = self._deliveries(session)
        retained = await deliveries.read_finalized_unknown(
            project_id=child.claim.project_id,
            event_id=payload.original_event_id,
            event_types=SUPPORTED_DELIVERIES,
            child_event_type=RECONCILIATION_EVENT,
            lock=False,
        )
        if (
            retained is None
            or retained.child is None
            or retained.child.event_id != child.claim.event_id
            or not _matches_original(retained.envelope, payload)
        ):
            return HandlerOutcome.REJECT
        original = retained.envelope
        custody = ReconciliationInvocationCustody(
            child=child,
            original=original,
            observer=self._observer,
            deliveries=deliveries,
        )
        cause = self._authorization(session)

        async def validate_cause() -> None:
            await cause.validate_cause(payload, original)

        if original.event_type == REQUEST_EVENT:
            evaluations = self._evaluations(session)
            request = await self._requests(session, evaluations).read(original)
            if payload.abandonment is not None:
                if await evaluations.require_expired_unknown_lease(request) != payload.abandonment:
                    return HandlerOutcome.REJECT
                await validate_cause()
                if await custody.fence_invocation(original) is None:
                    return HandlerOutcome.REJECT
                await evaluations.reserve_abandoned_evaluation(request, payload.abandonment, child.claim.event_id)
                return HandlerOutcome.ACKNOWLEDGE
            facts = await evaluations.classify_uncertain_delivery(request)
            if facts.classification == "committed":
                await validate_cause()
                if await custody.fence_invocation(original) is None:
                    return HandlerOutcome.REJECT
                return HandlerOutcome.ACKNOWLEDGE
            if facts.classification != "retry_safe":
                return HandlerOutcome.REJECT
            return original, request
        if original.event_type == COMPLETION_EVENT:
            outcomes = self._outcomes(session, custody, validate_cause)
            generation = await outcomes.observe_delivery_generation(original)
            classification = await outcomes.classify_uncertain_delivery(
                original, current_generation=generation
            )
            if classification == "committed":
                await outcomes.verify_retained_delivery(
                    original, current_generation=generation
                )
                return HandlerOutcome.ACKNOWLEDGE
            if classification == "retry_safe":
                return original, None
        return HandlerOutcome.REJECT
