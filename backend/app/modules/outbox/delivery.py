"""Canonical claim/invoke/finalize owner with exact phase authority custody."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.hashing import canonical_json_hash
from app.core.observability import annotate_current_span
from app.modules.authorization.api.decisions import AuthorizationDecision, DecisionOutcome
from app.modules.authorization.api.errors import AuthorizationBoundaryError
from app.modules.authorization.api.outbox_dispatch import (
    OUTBOX_DISPATCH_ACTION,
    OUTBOX_DISPATCH_PERMISSION,
    OutboxDispatchAuthorizationPort,
    OutboxDispatchFacts,
    OutboxDispatchPhase,
)
from app.modules.outbox.api import (
    CommittedInvocationObservation,
    DeliveryOptions,
    DeliveryCandidatePage,
    DeliveryPersistenceError,
    DeliveryReceipt,
    DeliveryUnavailable,
    DrainObservation,
    FinalizationCause,
    HandlerOutcome,
    OutboxClaim,
    OutboxEventEnvelope,
)
from app.modules.outbox.delivery_repository import (
    DeliveryRepository,
    claim_from_attempt,
    database_time,
    matches_event,
)
from app.modules.outbox.models import OutboxDeliveryAttempt
from app.modules.outbox.registry import HandlerRegistry


class _CompletedDuringFinalization(DeliveryUnavailable):
    """A concurrent completion requires fresh preparation of its stored digest."""

    def __init__(self, receipt: DeliveryReceipt) -> None:
        """Carry only immutable delivery facts for one fresh authorization."""
        self.receipt = receipt


def _checked_claim(claim: OutboxClaim) -> OutboxClaim:
    """Revalidate even caller-constructed or copied value objects."""
    try:
        return OutboxClaim.model_validate(claim.model_dump())
    except Exception:
        raise DeliveryUnavailable("outbox_delivery_unavailable") from None


def _facts(
    claim: OutboxClaim, phase: OutboxDispatchPhase, digest: str | None = None
) -> OutboxDispatchFacts:
    """Bind every lease scalar and, for finalization, the complete outcome."""
    return OutboxDispatchFacts(**claim.model_dump(), phase=phase, outcome_digest=digest)


def _allow(decision: AuthorizationDecision) -> str:
    """A mismatched action or denied decision cannot authorize any phase write."""
    if (
        type(decision) is not AuthorizationDecision
        or type(decision.decision_id) is not UUID
        or decision.outcome is not DecisionOutcome.ALLOW
        or decision.action_id != OUTBOX_DISPATCH_ACTION
        or decision.permission_id != OUTBOX_DISPATCH_PERMISSION
    ):
        raise DeliveryUnavailable("outbox_delivery_unavailable")
    return str(decision.decision_id)


def _receipt(claim: OutboxClaim, attempt: OutboxDeliveryAttempt) -> DeliveryReceipt:
    """Detach exact completed facts, never regenerate replay timestamps."""
    return DeliveryReceipt(
        claim=claim, outcome_json=attempt.outcome_json, outcome_digest=attempt.outcome_digest
    )


def _outcome(
    claim: OutboxClaim,
    invoked_at: datetime | None,
    cause: FinalizationCause,
    now: datetime,
    options: DeliveryOptions,
) -> dict:
    """Map closed disposition to database-timed outcome with bounded backoff."""
    if type(cause) is not FinalizationCause:
        raise DeliveryUnavailable("outbox_delivery_unavailable")
    expired = now >= claim.claim_expires_at
    if (
        invoked_at is None
        and (cause is not FinalizationCause.EXPIRED or not expired)
        or cause is FinalizationCause.EXPIRED
        and not expired
    ):
        raise DeliveryUnavailable("outbox_delivery_unavailable")
    unknown = invoked_at is not None and (expired or cause is FinalizationCause.UNKNOWN)
    state, code, retry = "dead_letter", "HANDLER_REJECTED", None
    if unknown:
        code = "INVOKE_OUTCOME_UNKNOWN"
    elif cause is FinalizationCause.ACKNOWLEDGE:
        state, code = "acknowledged", None
    elif cause in (FinalizationCause.RETRY, FinalizationCause.EXPIRED):
        if claim.claim_generation >= options.max_attempts:
            code = "ATTEMPTS_EXHAUSTED"
        else:
            state = "retryable"
            code = "RETRY_REQUESTED" if invoked_at is not None else "LEASE_EXPIRED_BEFORE_INVOKE"
            delay = min(
                options.retry_cap_seconds,
                options.retry_base_seconds * 2 ** min(claim.claim_generation - 1, 30),
            )
            retry = now + timedelta(seconds=delay)
    return {
        "delivery_state": state,
        "error_code": code,
        "next_attempt_at": retry.isoformat() if retry else None,
        "finalized_at": None if state == "retryable" else now.isoformat(),
        "receipt_completed_at": now.isoformat(),
        "invocation_unknown": unknown,
        "invoked_at": invoked_at.isoformat() if invoked_at else None,
    }


def _encode(value: dict) -> str:
    """Use the canonical UTF-8 JSON representation shared with outcome hashing."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


class OutboxDelivery:
    """Own short root transactions; never hold a session across handler I/O."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        authorization_factory: Callable[[AsyncSession], OutboxDispatchAuthorizationPort],
        registry: HandlerRegistry,
        options: DeliveryOptions,
    ) -> None:
        """Require explicit AUTH composition and bounded handler registration."""
        self._sessions = session_factory
        self._authorization = authorization_factory
        self._registry = registry
        self._options = DeliveryOptions.model_validate(options.model_dump())
        self._running_handlers: set[asyncio.Task] = set()

    @asynccontextmanager
    async def _authority(self, session, **selectors):
        """Conceal AUTH boundary failures without swallowing owner errors."""
        try:
            async with self._authorization(session).prepare_outbox_dispatch(**selectors) as prepared:
                yield prepared
        except AuthorizationBoundaryError:
            raise DeliveryUnavailable("outbox_delivery_unavailable") from None

    def _handler_done(self, task: asyncio.Task) -> None:
        """Retain running calls and consume failures without keeping provider text."""
        self._running_handlers.discard(task)
        if not task.cancelled():
            task.exception()

    async def candidates(self, *, after: UUID | None = None, limit: int = 100) -> DeliveryCandidatePage:
        """Return selectors after closing SQL; a later scan revisits IDs behind the cursor."""
        if (after is not None and type(after) is not UUID) or type(limit) is not int or not 1 <= limit <= 500:
            raise DeliveryUnavailable("outbox_delivery_unavailable")
        async with self._sessions() as session:
            return await DeliveryRepository(session).candidates(self._registry.keys, after=after, limit=limit)

    async def deliver(self, event_id: UUID, project_id: UUID, owner: str) -> DeliveryReceipt | None:
        """Reuse recovery and claim/invoke; duplicate transport cannot bypass custody."""
        recovered = await self.recover(event_id, project_id)
        if recovered is not None:
            return recovered
        claim = await self.claim(event_id, project_id, owner)
        return await self.invoke(claim) if claim is not None else None

    async def claim(self, event_id: UUID, project_id: UUID, owner: str) -> OutboxClaim | None:
        """Commit one eligible exact registered claim, or leave unavailable work alone."""
        async with self._sessions() as session:
            event = await DeliveryRepository(session).event(event_id, project_id)
            now = await database_time(session)
            if (
                event is None
                or self._registry.get(event.event_type, event.event_version) is None
                or event.delivery_state not in ("pending", "retryable")
                or event.next_attempt_at > now
                or event.claim_generation >= self._options.max_attempts
            ):
                return None
            claim = OutboxClaim(
                event_id=event.event_id,
                project_id=project_id,
                payload_digest=event.payload_digest,
                claim_generation=event.claim_generation + 1,
                claim_owner=owner,
                claimed_at=now,
                claim_expires_at=now + timedelta(seconds=self._options.lease_seconds),
            )
        facts = _facts(claim, OutboxDispatchPhase.CLAIM)
        async with self._sessions() as session, session.begin():
            async with self._authority(session,
                facts=facts,
                request_id=uuid4(),
                correlation_id=uuid4(),
            ) as prepared:
                event = await DeliveryRepository(session).event(event_id, project_id, lock=True)
                locked_now = await database_time(session)
                if (
                    event is None
                    or event.delivery_state not in ("pending", "retryable")
                    or event.claim_generation + 1 != claim.claim_generation
                    or event.payload_digest != claim.payload_digest
                    or event.next_attempt_at > locked_now
                    or claim.claim_expires_at <= locked_now
                ):
                    return None
                decision_id = _allow(await prepared.consume(_facts(claim, OutboxDispatchPhase.CLAIM)))
                if await database_time(session) >= claim.claim_expires_at:
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                event.delivery_state = "claimed"
                event.attempt_count = event.claim_generation = claim.claim_generation
                event.claim_owner, event.claimed_at = claim.claim_owner, claim.claimed_at
                event.claim_expires_at, event.last_attempt_at = (
                    claim.claim_expires_at,
                    claim.claimed_at,
                )
                event.next_attempt_at = None
                session.add(
                    OutboxDeliveryAttempt(
                        **{**claim.model_dump(), "project_id": str(project_id)},
                        stage="claimed", claim_decision_event_id=decision_id,
                    )
                )
                await session.flush()
        return claim

    async def _begin_invocation(self, claim: OutboxClaim) -> OutboxEventEnvelope | None:
        """Commit the one invocation marker before handing anything to a handler."""
        claim = _checked_claim(claim)
        facts = _facts(claim, OutboxDispatchPhase.INVOKE)
        async with self._sessions() as session, session.begin():
            async with self._authority(session,
                facts=facts,
                request_id=uuid4(),
                correlation_id=uuid4(),
            ) as prepared:
                repo = DeliveryRepository(session)
                event = await repo.event(claim.event_id, claim.project_id, lock=True)
                attempt = await repo.attempt(claim, lock=True)
                now = await database_time(session)
                if (
                    event is None
                    or attempt is None
                    or not matches_event(event, claim)
                    or claim_from_attempt(attempt) != claim
                    or attempt.stage != "claimed"
                    or now >= claim.claim_expires_at
                    or self._registry.get(event.event_type, event.event_version) is None
                ):
                    return None
                if canonical_json_hash(event.payload) != claim.payload_digest:
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                decision_id = _allow(await prepared.consume(_facts(claim, OutboxDispatchPhase.INVOKE)))
                now = await database_time(session)
                if now >= claim.claim_expires_at:
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                attempt.stage, attempt.invoked_at = "invoked", now
                attempt.invoke_decision_event_id = decision_id
                envelope = OutboxEventEnvelope(
                    claim=claim,
                    payload_json=_encode(event.payload),
                    **{
                        name: getattr(event, name)
                        for name in (
                            "event_type",
                            "event_version",
                            "aggregate_type",
                            "aggregate_id",
                            "correlation_id",
                            "causation_event_id",
                            "idempotency_key",
                            "occurred_at",
                        )
                    },
                )
                await session.flush()
        return envelope

    async def invoke(self, claim: OutboxClaim) -> DeliveryReceipt | None:
        """Run once without locks; failures are unknown, never an implicit safe retry."""
        envelope = await self._begin_invocation(claim)
        if envelope is None:
            return None
        annotate_current_span(outbox_correlation_id=envelope.correlation_id)
        handler = self._registry.get(envelope.event_type, envelope.event_version)
        cause = FinalizationCause.UNKNOWN
        task = None
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._options.handler_timeout_seconds
            task = asyncio.create_task(handler(envelope))
            self._running_handlers.add(task)
            task.add_done_callback(self._handler_done)
            done, _ = await asyncio.wait((task,), timeout=self._options.handler_timeout_seconds)
            if done and loop.time() < deadline and not task.cancelled():
                result = task.result()
                if type(result) is HandlerOutcome:
                    cause = FinalizationCause(result.value)
        except Exception:
            # Do not retain or log provider payloads. Cancellation deliberately leaves
            # committed invoked custody for expiration recovery.
            pass
        finally:
            if task is not None and not task.done():
                task.cancel()
        return await self.finalize(claim, cause)

    async def finalize(self, claim: OutboxClaim, cause: FinalizationCause) -> DeliveryReceipt:
        """Authorize the exact outcome; response loss replays original delivery facts."""
        claim = _checked_claim(claim)
        async with self._sessions() as session:
            attempt = await DeliveryRepository(session).attempt(claim)
            if attempt is None or claim_from_attempt(attempt) != claim:
                raise DeliveryUnavailable("outbox_delivery_unavailable")
            now = await database_time(session)
            if attempt.stage == "completed":
                now = datetime.fromisoformat(
                    json.loads(attempt.outcome_json)["receipt_completed_at"]
                )
            value = _outcome(claim, attempt.invoked_at, cause, now, self._options)
            proposed = DeliveryReceipt(
                claim=claim, outcome_json=_encode(value), outcome_digest=canonical_json_hash(value)
            )
        try:
            return await self._finalize(proposed, cause)
        except _CompletedDuringFinalization as completed:
            stored = json.loads(completed.receipt.outcome_json)
            expected = _outcome(
                claim,
                attempt.invoked_at,
                cause,
                datetime.fromisoformat(stored["receipt_completed_at"]),
                self._options,
            )
            if _encode(expected) != completed.receipt.outcome_json:
                raise DeliveryUnavailable("outbox_delivery_unavailable") from None
            # The prior transaction consumed no authority. Re-prepare once with
            # the immutable winner's exact digest, never change the current event.
            return await self._finalize(completed.receipt, cause)

    async def _finalize(
        self, receipt: DeliveryReceipt, cause: FinalizationCause
    ) -> DeliveryReceipt:
        """Compare prepared facts under the event/custody locks before consumption."""
        claim = _checked_claim(receipt.claim)
        facts = _facts(claim, OutboxDispatchPhase.FINALIZE, receipt.outcome_digest)
        async with self._sessions() as session, session.begin():
            async with self._authority(session,
                facts=facts,
                request_id=uuid4(),
                correlation_id=uuid4(),
            ) as prepared:
                repo = DeliveryRepository(session)
                event = await repo.event(claim.event_id, claim.project_id, lock=True)
                attempt = await repo.attempt(claim, lock=True)
                now = await database_time(session)
                if event is None or attempt is None or claim_from_attempt(attempt) != claim:
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                if attempt.stage == "completed":
                    if _receipt(claim, attempt) != receipt:
                        raise _CompletedDuringFinalization(_receipt(claim, attempt))
                    _allow(
                        await prepared.consume(
                            _facts(claim, OutboxDispatchPhase.FINALIZE, receipt.outcome_digest)
                        )
                    )
                    return _receipt(claim, attempt)
                if event.claim_generation != claim.claim_generation or not matches_event(
                    event, claim
                ):
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                value = json.loads(receipt.outcome_json)
                completed = datetime.fromisoformat(value["receipt_completed_at"])
                expected = _outcome(claim, attempt.invoked_at, cause, completed, self._options)
                if (
                    completed > now
                    or _encode(expected) != receipt.outcome_json
                    or canonical_json_hash(expected) != receipt.outcome_digest
                    or (completed < claim.claim_expires_at <= now)
                ):
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                decision_id = _allow(
                    await prepared.consume(
                        _facts(claim, OutboxDispatchPhase.FINALIZE, receipt.outcome_digest)
                    )
                )
                if completed < claim.claim_expires_at <= await database_time(session):
                    raise DeliveryUnavailable("outbox_delivery_unavailable")
                attempt.finalize_decision_event_id = decision_id
                attempt.stage, attempt.outcome_json, attempt.outcome_digest = (
                    "completed",
                    receipt.outcome_json,
                    receipt.outcome_digest,
                )
                event.delivery_state, event.last_error_code = (
                    value["delivery_state"],
                    value["error_code"],
                )
                event.next_attempt_at = (
                    datetime.fromisoformat(value["next_attempt_at"])
                    if value["next_attempt_at"]
                    else None
                )
                event.finalized_at = (
                    datetime.fromisoformat(value["finalized_at"]) if value["finalized_at"] else None
                )
                event.claim_owner = event.claimed_at = event.claim_expires_at = None
                await session.flush()
        return receipt

    async def recover(self, event_id: UUID, project_id: UUID) -> DeliveryReceipt | None:
        """Expired uninvoked work retries; expired invocation remains unknown."""
        async with self._sessions() as session:
            event = await DeliveryRepository(session).event(event_id, project_id)
            now = await database_time(session)
            if event is None or event.delivery_state != "claimed" or event.claim_expires_at > now:
                return None
            claim = OutboxClaim(
                **{
                    name: UUID(event.project_id) if name == "project_id" else getattr(event, name)
                    for name in OutboxClaim.model_fields
                }
            )
        return await self.finalize(claim, FinalizationCause.EXPIRED)

    async def observe_invocation(self, envelope: OutboxEventEnvelope) -> CommittedInvocationObservation | None:
        """Use the same independent committed reader supplied to feature handlers."""
        return await CommittedInvocationReader(self._sessions).observe_invocation(envelope)

    async def drain(self, project_id: UUID) -> DrainObservation:
        """Observe one exact project without row locks or fabricated empty results."""
        try:
            async with self._sessions() as session:
                return await DeliveryRepository(session).drain(project_id, self._registry.keys)
        except SQLAlchemyError:
            raise DeliveryPersistenceError("outbox_observation_failed") from None


class CommittedInvocationReader:
    """Independent observation without constructing a second delivery engine."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sessions = session_factory

    async def observe_invocation(self, envelope: OutboxEventEnvelope) -> CommittedInvocationObservation | None:
        """Independent committed snapshot, no feature authority or reservation."""
        try:
            async with self._sessions() as session:
                return await DeliveryRepository(session).observe(envelope)
        except SQLAlchemyError:
            raise DeliveryPersistenceError("outbox_observation_failed") from None
