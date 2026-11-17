"""Operator inspection and one-shot reconciliation for exact post-submit UNKNOWN delivery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryAuthorizationPort,
    PostSubmitDeliveryAuthorityDenied,
    PostSubmitDeliveryChildPayload,
    PostSubmitDeliveryCommand,
    PostSubmitDeliveryConflict,
    PostSubmitDeliveryOperationUnavailable,
    PostSubmitDeliveryPage,
    PostSubmitDeliveryPosition,
    PostSubmitDeliveryPreparation,
    PostSubmitDeliveryQuery,
    PostSubmitDeliveryReadAuthority,
    PostSubmitDeliveryResult,
    PostSubmitDeliverySource,
    PostSubmitDeliverySuccessor,
    PostSubmitDeliveryUnavailable,
    PostSubmitDeliverySourceUnavailable,
    POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT,
    POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS,
    post_submit_delivery_request_digest,
    post_submit_reconciliation_event_json,
)
from app.modules.checkers.api.execution import (
    COMPLETION_EVENT,
    REQUEST_EVENT,
    CheckerExecutionUnavailable,
    EvaluationCoordinationPort,
    EvaluationCompletion,
)
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest
from app.modules.outbox.api import (
    OutboxAppendInput,
    DeliveryUnavailable,
    FinalizedUnknownDelivery,
    FinalizedUnknownDeliveryPort,
    OutboxAppendPort,
    OutboxIdempotencyConflict,
    OutboxInputError,
    OutboxPersistenceError,
    OutboxEventEnvelope,
)


RECONCILIATION_EVENT = POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT
SUPPORTED_DELIVERIES = POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS


class PostSubmitDeliveryRequestReadPort(Protocol):
    """Read one retained request without staging or repairing owner rows."""

    async def read(
        self, envelope: OutboxEventEnvelope
    ) -> PostSubmissionExecutionRequest: ...


class PostSubmitDeliveryOutcomePort(Protocol):
    """TASK routing operation plus nonmutating reconciliation checks."""

    async def observe_delivery_generation(
        self, envelope: OutboxEventEnvelope,
    ) -> int | None: ...

    async def classify_uncertain_delivery(
        self, envelope: OutboxEventEnvelope, *, current_generation: int | None,
    ) -> Literal["committed", "retry_safe", "unresolved"]: ...

    async def verify_retained_delivery(
        self, envelope: OutboxEventEnvelope, *, current_generation: int | None,
    ) -> None: ...

    async def apply(
        self, envelope: OutboxEventEnvelope, *, current_generation: int | None,
    ) -> object: ...


def _public_source(
    delivery: FinalizedUnknownDelivery,
    classified: tuple[Literal["committed", "retry_safe", "unresolved"], UUID, UUID, int],
) -> PostSubmitDeliverySource:
    """Project only the fixed public delivery vocabulary."""
    classification, request_id, run_id, generation = classified
    child = delivery.child
    if child is not None and child.state in {"unknown", "held"}:
        classification = "unresolved"
    envelope = delivery.envelope
    return PostSubmitDeliverySource(
        project_id=envelope.claim.project_id,
        event_id=envelope.claim.event_id,
        event_type=envelope.event_type,
        event_version=envelope.event_version,
        aggregate_id=envelope.aggregate_id,
        evaluation_request_id=request_id,
        checker_run_id=run_id,
        evaluation_generation=generation,
        claim_generation=envelope.claim.claim_generation,
        payload_digest=envelope.claim.payload_digest,
        finalized_at=delivery.finalized_at,
        error_code=delivery.error_code,
        classification=classification,
        reconciliation_event_id=child.event_id if child is not None else None,
        reconciliation_state=(
            "held" if child is not None and child.state == "unknown"
            else child.state if child is not None else None
        ),
    )


async def classify_post_submit_delivery(
    delivery: FinalizedUnknownDelivery,
    *,
    evaluations: EvaluationCoordinationPort,
    requests: PostSubmitDeliveryRequestReadPort,
    outcomes: PostSubmitDeliveryOutcomePort,
) -> tuple[Literal["committed", "retry_safe", "unresolved"], UUID, UUID, int]:
    """Classify through exact source owners; caller chooses the transaction."""
    if delivery.child is not None and delivery.child.state in {"unknown", "held"}:
        held = await _post_submit_delivery_identity(delivery, evaluations, requests)
        return ("unresolved", *held)
    envelope = delivery.envelope
    try:
        if delivery.child is not None:
            payload = PostSubmitDeliveryChildPayload.model_validate_json(
                delivery.child.payload_json
            )
            return (
                payload.classification,
                payload.evaluation_request_id,
                payload.checker_run_id,
                payload.evaluation_generation,
            )
        if envelope.event_type == REQUEST_EVENT:
            request = await requests.read(envelope)
            facts = await evaluations.classify_uncertain_delivery(request)
            return (
                facts.classification,
                facts.request.evaluation_request_id,
                facts.checker_run_id,
                facts.request.evaluation_generation,
            )
        if envelope.event_type == COMPLETION_EVENT:
            generation = await outcomes.observe_delivery_generation(envelope)
            classification = await outcomes.classify_uncertain_delivery(
                envelope, current_generation=generation,
            )
            completion = EvaluationCompletion.model_validate_json(envelope.payload_json)
            return (
                classification,
                completion.reference.request_id,
                completion.reference.attempt_id,
                completion.reference.evaluation_generation,
            )
    except (
        CheckerExecutionUnavailable,
        PostSubmitDeliverySourceUnavailable,
        DeliveryUnavailable,
    ):
        identity = await _post_submit_delivery_identity(
            delivery, evaluations, requests
        )
        return ("unresolved", *identity)
    identity = await _post_submit_delivery_identity(delivery, evaluations, requests)
    return ("unresolved", *identity)


async def _post_submit_delivery_identity(
    delivery: FinalizedUnknownDelivery,
    evaluations: EvaluationCoordinationPort,
    requests: PostSubmitDeliveryRequestReadPort,
) -> tuple[UUID, UUID, int]:
    """Decode only the exact public source identity from the retained envelope."""
    envelope = delivery.envelope
    try:
        if envelope.event_type == REQUEST_EVENT:
            request = await requests.read(envelope)
            facts = await evaluations.classify_uncertain_delivery(request)
            return (
                facts.request.evaluation_request_id,
                facts.checker_run_id,
                facts.request.evaluation_generation,
            )
        completion = EvaluationCompletion.model_validate_json(envelope.payload_json)
        return (
            completion.reference.request_id,
            completion.reference.attempt_id,
            completion.reference.evaluation_generation,
        )
    except (TypeError, ValueError, PostSubmitDeliverySourceUnavailable) as exc:
        raise PostSubmitDeliveryOperationUnavailable(
            "post_submit_delivery_identity_unavailable"
        ) from exc


class PostSubmitDeliveryService:
    """Extend existing owners; OUTBOX remains receipt and delivery custody."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        actor_profile_id: UUID,
        deliveries: FinalizedUnknownDeliveryPort,
        events: OutboxAppendPort,
        evaluations: EvaluationCoordinationPort,
        requests: PostSubmitDeliveryRequestReadPort,
        outcomes: PostSubmitDeliveryOutcomePort,
        read_authority: PostSubmitDeliveryReadAuthority,
        authorization: PostSubmitDeliveryAuthorizationPort,
        detached_classify: Callable[
            [FinalizedUnknownDelivery],
            Awaitable[tuple[Literal["committed", "retry_safe", "unresolved"], UUID, UUID, int]],
        ],
    ) -> None:
        self._session = session
        self._actor_profile_id = actor_profile_id
        self._deliveries, self._events = deliveries, events
        self._evaluations, self._requests, self._outcomes = evaluations, requests, outcomes
        self._read_authority, self._authorization = read_authority, authorization
        self._detached_classify = detached_classify

    async def discover(self, query: PostSubmitDeliveryQuery) -> PostSubmitDeliveryPage:
        """Authorize one page and classify in detached source-owner custody."""
        query = PostSubmitDeliveryQuery.model_validate(query)
        after = await self._read_authority.authorize_and_decode(query)
        try:
            page = await self._deliveries.list_finalized_unknown(
                project_id=query.project_id,
                event_types=SUPPORTED_DELIVERIES,
                child_event_type=RECONCILIATION_EVENT,
                after=(after.finalized_at, after.event_id) if after else None,
                limit=query.limit,
            )
        except DeliveryUnavailable as exc:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_read_unavailable"
            ) from exc
        projected = []
        for delivery in page.items:
            classified = await self._detached_classify(delivery)
            projected.append(_public_source(delivery, classified))
        items = tuple(projected)
        next_cursor = None
        if page.has_more and items:
            last = items[-1]
            next_cursor = self._read_authority.encode(
                query,
                PostSubmitDeliveryPosition(
                    finalized_at=last.finalized_at,
                    event_id=last.event_id,
                ),
            )
        return PostSubmitDeliveryPage(
            project_id=query.project_id,
            items=items,
            next_cursor=next_cursor,
        )

    async def reconcile(
        self, command: PostSubmitDeliveryCommand,
    ) -> PostSubmitDeliveryResult:
        """Append or exactly replay the sole authorized child for one original."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_transaction_required"
            )
        command = PostSubmitDeliveryCommand.model_validate(command)
        delivery = await self._read_delivery(command, lock=False)
        if delivery is None:
            raise PostSubmitDeliveryUnavailable("post_submit_delivery_unavailable")
        await self._session.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "post-submit-delivery:" + str(command.event_id)},
        )
        delivery = await self._read_delivery(command, lock=False)
        if delivery is None:
            raise PostSubmitDeliveryUnavailable("post_submit_delivery_unavailable")
        classified = await self._classify(delivery)
        classification = classified[0]
        if delivery.child is not None:
            return await self._replay(command, delivery, classified)
        if classification == "unresolved":
            raise PostSubmitDeliveryUnavailable("post_submit_delivery_unresolved")
        source = _public_source(delivery, classified)
        preparation = PostSubmitDeliveryPreparation(command=command, source=source)
        handle = await self._authorization.prepare(preparation)
        try:
            authority = await self._authorization.consume(handle, preparation)
            locked = await self._read_delivery(command, lock=True)
            if locked is None or locked.envelope != delivery.envelope:
                raise PostSubmitDeliveryUnavailable("post_submit_delivery_unavailable")
            if locked.child is not None:
                raise PostSubmitDeliveryConflict(
                    "post_submit_delivery_request_conflict"
                )
            payload = PostSubmitDeliveryChildPayload(
                original_event_id=source.event_id,
                original_claim_generation=source.claim_generation,
                original_payload_digest=source.payload_digest,
                original_event_type=source.event_type,
                original_event_version=source.event_version,
                evaluation_request_id=source.evaluation_request_id,
                checker_run_id=source.checker_run_id,
                evaluation_generation=source.evaluation_generation,
                classification=classification,
                reconciliation_request_id=command.request_key,
                request_digest=post_submit_delivery_request_digest(preparation),
                authorization_decision_id=authority.decision_id,
                authorization_resource_digest=authority.resource_digest,
                authorization_resource_json=authority.resource_json,
                operator_actor_profile_id=authority.actor_profile_id,
                operator_identity_link_id=authority.identity_link_id,
            )
            try:
                appended = await self._events.append(
                    OutboxAppendInput.model_validate_json(post_submit_reconciliation_event_json(source.project_id, payload))
                )
            except OutboxIdempotencyConflict as exc:
                raise PostSubmitDeliveryConflict(
                    "post_submit_delivery_request_conflict"
                ) from exc
            except (OutboxInputError, OutboxPersistenceError) as exc:
                raise PostSubmitDeliveryOperationUnavailable(
                    "post_submit_delivery_append_unavailable"
                ) from exc
            successor = PostSubmitDeliverySuccessor(
                event_id=appended.event_id,
                payload_digest=appended.payload_digest,
                occurred_at=appended.occurred_at,
                classification=classification,
            )
            return PostSubmitDeliveryResult(
                source=source.model_copy(
                    update={
                        "reconciliation_event_id": successor.event_id,
                        "reconciliation_state": "pending",
                    }
                ),
                successor=successor,
                authorization_decision_id=authority.decision_id,
            )
        finally:
            self._authorization.close(handle)

    async def _read_delivery(self, command, *, lock):
        """Translate OUTBOX storage failures at CHECKERS's public owner seam."""
        try:
            return await self._deliveries.read_finalized_unknown(
                project_id=command.project_id,
                event_id=command.event_id,
                event_types=SUPPORTED_DELIVERIES,
                child_event_type=RECONCILIATION_EVENT,
                lock=lock,
            )
        except DeliveryUnavailable as exc:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_read_unavailable"
            ) from exc

    async def _replay(
        self,
        command: PostSubmitDeliveryCommand,
        delivery: FinalizedUnknownDelivery,
        current_classification: tuple[
            Literal["committed", "retry_safe", "unresolved"], UUID, UUID, int
        ],
    ) -> PostSubmitDeliveryResult:
        """Revalidate fresh authority without another decision or child."""
        child = delivery.child
        if child is None:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_replay_unavailable"
            )
        try:
            payload = PostSubmitDeliveryChildPayload.model_validate_json(
                child.payload_json
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_replay_unavailable"
            ) from exc
        envelope = delivery.envelope
        if (
            payload.original_event_id != envelope.claim.event_id
            or payload.original_claim_generation != envelope.claim.claim_generation
            or payload.original_payload_digest != envelope.claim.payload_digest
            or payload.original_event_type != envelope.event_type
            or payload.original_event_version != envelope.event_version
        ):
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_replay_unavailable"
            )
        scheduled_source = _public_source(
            delivery.model_copy(update={"child": None}),
            (
                payload.classification,
                payload.evaluation_request_id,
                payload.checker_run_id,
                payload.evaluation_generation,
            ),
        )
        preparation = PostSubmitDeliveryPreparation(
            command=command,
            source=scheduled_source,
        )
        handle = await self._authorization.prepare(preparation)
        try:
            await self._authorization.authorize_replay(handle, preparation)
            if payload.request_digest != post_submit_delivery_request_digest(preparation):
                raise PostSubmitDeliveryConflict(
                    "post_submit_delivery_request_conflict"
                )
            await self._authorization.validate_replay(
                handle,
                preparation,
                payload.operator_identity_link_id,
                payload.authorization_decision_id,
            )
        finally:
            self._authorization.close(handle)
        return PostSubmitDeliveryResult(
            source=_public_source(delivery, current_classification),
            successor=PostSubmitDeliverySuccessor(
                event_id=child.event_id,
                payload_digest=child.payload_digest,
                occurred_at=child.occurred_at,
                classification=payload.classification,
            ),
            authorization_decision_id=payload.authorization_decision_id,
        )

    async def _classify(
        self, delivery: FinalizedUnknownDelivery,
    ) -> tuple[
        Literal["committed", "retry_safe", "unresolved"], UUID, UUID, int
    ]:
        """Delegate current source facts to the exact CHECKERS or TASK owner."""
        return await classify_post_submit_delivery(
            delivery,
            evaluations=self._evaluations,
            requests=self._requests,
            outcomes=self._outcomes,
        )

    async def _delivery_identity(
        self, delivery: FinalizedUnknownDelivery,
    ) -> tuple[UUID, UUID, int]:
        """Decode only the exact public source identity from the retained envelope."""
        return await _post_submit_delivery_identity(
            delivery, self._evaluations, self._requests
        )

    async def restage_denial(self, error: PostSubmitDeliveryAuthorityDenied) -> bool:
        return await self._authorization.restage_denial(error)

    async def restage_read_denial(self, error: Exception) -> bool:
        return await self._read_authority.restage_denial(error)
