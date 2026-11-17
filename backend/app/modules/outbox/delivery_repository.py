"""SQL delivery facts and single-statement observations; no authority decisions."""

from __future__ import annotations

from datetime import datetime
import json
from uuid import UUID

from sqlalchemy import and_, cast, func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.outbox.api import (
    CommittedInvocationObservation,
    DeliveryCandidate, DeliveryCandidatePage,
    DrainObservation,
    FinalizedUnknownDelivery, FinalizedUnknownDeliveryPage,
    OutboxClaim,
    OutboxEventEnvelope,
    DeliveryUnavailable,
    ReconciliationChildObservation,
)
from app.core.hashing import canonical_json_hash
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent


async def database_time(session: AsyncSession) -> datetime:
    """Use wall-clock database time even after a transaction waits for a lock."""
    return (await session.execute(select(func.clock_timestamp()))).scalar_one()


def claim_from_attempt(attempt: OutboxDeliveryAttempt) -> OutboxClaim:
    """Detach the exact immutable lease facts from retained custody."""
    return OutboxClaim(
        **{
            name: UUID(attempt.project_id) if name == "project_id" else getattr(attempt, name)
            for name in OutboxClaim.model_fields
        }
    )


def matches_event(event: OutboxEvent, claim: OutboxClaim) -> bool:
    """Require all current event facts, including the lease and generation."""
    return (
        event.delivery_state == "claimed"
        and event.event_id == claim.event_id
        and event.project_id == str(claim.project_id)
        and event.payload_digest == claim.payload_digest
        and event.claim_generation == claim.claim_generation
        and event.claim_owner == claim.claim_owner
        and event.claimed_at == claim.claimed_at
        and event.claim_expires_at == claim.claim_expires_at
    )


def _envelope(event: OutboxEvent, attempt: OutboxDeliveryAttempt) -> OutboxEventEnvelope:
    """Detach an exact retained envelope from immutable event and attempt custody."""
    return OutboxEventEnvelope(
        claim=claim_from_attempt(attempt),
        event_type=event.event_type,
        event_version=event.event_version,
        aggregate_type=event.aggregate_type,
        aggregate_id=UUID(str(event.aggregate_id)),
        correlation_id=event.correlation_id,
        causation_event_id=(
            UUID(str(event.causation_event_id))
            if event.causation_event_id is not None
            else None
        ),
        idempotency_key=event.idempotency_key,
        occurred_at=event.occurred_at,
        payload_json=json.dumps(
            event.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
    )


def _child(event: OutboxEvent) -> ReconciliationChildObservation:
    """Project closed child delivery state without provider or outcome detail."""
    if event.delivery_state in {"pending", "retryable"}:
        state = "pending"
    elif event.delivery_state == "claimed":
        state = "active"
    elif event.delivery_state == "acknowledged":
        state = "acknowledged"
    elif (
        event.delivery_state == "dead_letter"
        and event.last_error_code == "INVOKE_OUTCOME_UNKNOWN"
    ):
        state = "unknown"
    else:
        state = "held"
    return ReconciliationChildObservation(
        event_id=UUID(str(event.event_id)),
        payload_digest=event.payload_digest,
        payload_json=json.dumps(
            event.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        occurred_at=event.occurred_at,
        state=state,
    )


class DeliveryRepository:
    """A participant in the orchestrator's transaction, never its committer."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind one owner session."""
        self.session = session

    async def candidates(self, registered, *, after: UUID | None, limit: int) -> DeliveryCandidatePage:
        """One nonlocking statement includes due supported work and all expired claims."""
        e = OutboxEvent
        now = func.statement_timestamp()
        query = select(e.event_id, e.project_id, e.event_type).where(or_(
            and_(e.delivery_state.in_(("pending", "retryable")), e.next_attempt_at <= now,
                 tuple_(e.event_type, e.event_version).in_(sorted(registered))),
            and_(e.delivery_state == "claimed", e.claim_expires_at <= now),
        ))
        if after is not None:
            query = query.where(e.event_id > after)
        rows = (await self.session.execute(query.order_by(e.event_id).limit(limit + 1))).all()
        items = tuple(DeliveryCandidate(event_id=UUID(str(row.event_id)), project_id=UUID(row.project_id), event_type=row.event_type)
                      for row in rows[:limit])
        return DeliveryCandidatePage(items=items, next_after=items[-1].event_id if len(rows) > limit else None)

    async def event(
        self, event_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> OutboxEvent | None:
        """Conceal foreign events; refresh identity-map values after any lock wait."""
        query = (
            select(OutboxEvent)
            .where(
                OutboxEvent.event_id == event_id,
                OutboxEvent.project_id == str(project_id),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def attempt(
        self, claim: OutboxClaim, *, lock: bool = False
    ) -> OutboxDeliveryAttempt | None:
        """Read or lock custody only after its event when locking."""
        query = (
            select(OutboxDeliveryAttempt)
            .where(
                OutboxDeliveryAttempt.event_id == claim.event_id,
                OutboxDeliveryAttempt.claim_generation == claim.claim_generation,
                OutboxDeliveryAttempt.project_id == str(claim.project_id),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    @staticmethod
    def _unknown_predicate(event_types):
        e, a = OutboxEvent, OutboxDeliveryAttempt
        supported = (
            or_(*(and_(e.event_type == name, e.event_version == version)
                  for name, version in event_types))
            if event_types
            else literal(False)
        )
        return and_(
            supported,
            e.delivery_state == "dead_letter",
            e.last_error_code == "INVOKE_OUTCOME_UNKNOWN",
            e.finalized_at.is_not(None),
            a.event_id == e.event_id,
            a.claim_generation == e.claim_generation,
            a.project_id == e.project_id,
            a.payload_digest == e.payload_digest,
            a.stage == "completed",
            func.jsonb_extract_path_text(
                cast(a.outcome_json, JSONB), "invocation_unknown"
            ) == "true",
            func.jsonb_extract_path_text(
                cast(a.outcome_json, JSONB), "delivery_state"
            ) == "dead_letter",
            func.jsonb_extract_path_text(
                cast(a.outcome_json, JSONB), "error_code"
            ) == "INVOKE_OUTCOME_UNKNOWN",
        )

    async def _children(self, originals, child_event_type, *, lock):
        """Return at most one exact child per original, rejecting corrupt multiplicity."""
        if not originals:
            return {}
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == child_event_type,
                OutboxEvent.event_version == 1,
                OutboxEvent.causation_event_id.in_(originals),
            )
            .order_by(OutboxEvent.causation_event_id, OutboxEvent.event_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        values = {}
        for event in (await self.session.scalars(statement)).all():
            key = UUID(str(event.causation_event_id))
            if key in values or event.project_id != originals[key]:
                raise DeliveryUnavailable("outbox_delivery_reconciliation_unavailable")
            values[key] = _child(event)
        return values

    async def list_finalized_unknown(
        self,
        *,
        project_id: UUID,
        event_types: tuple[tuple[str, int], ...],
        child_event_type: str,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> FinalizedUnknownDeliveryPage:
        """List exact terminal UNKNOWN custody without returning payloads publicly."""
        if (
            type(project_id) is not UUID
            or type(event_types) is not tuple
            or not event_types
            or type(child_event_type) is not str
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DeliveryUnavailable("outbox_delivery_reconciliation_unavailable")
        e, a = OutboxEvent, OutboxDeliveryAttempt
        statement = (
            select(e, a)
            .join(
                a,
                and_(a.event_id == e.event_id, a.claim_generation == e.claim_generation),
            )
            .where(
                e.project_id == str(project_id),
                self._unknown_predicate(event_types),
            )
        )
        if after is not None:
            statement = statement.where(
                tuple_(e.finalized_at, e.event_id) > tuple_(after[0], after[1])
            )
        rows = (
            await self.session.execute(
                statement.order_by(e.finalized_at, e.event_id).limit(limit + 1)
            )
        ).all()
        selected = rows[:limit]
        children = await self._children(
            {UUID(str(row[0].event_id)): row[0].project_id for row in selected},
            child_event_type,
            lock=False,
        )
        items = tuple(
            FinalizedUnknownDelivery(
                envelope=_envelope(event, attempt),
                finalized_at=event.finalized_at,
                error_code="INVOKE_OUTCOME_UNKNOWN",
                child=children.get(UUID(str(event.event_id))),
            )
            for event, attempt in selected
        )
        return FinalizedUnknownDeliveryPage(items=items, has_more=len(rows) > limit)

    async def read_finalized_unknown(
        self,
        *,
        project_id: UUID,
        event_id: UUID,
        event_types: tuple[tuple[str, int], ...],
        child_event_type: str,
        lock: bool,
    ) -> FinalizedUnknownDelivery | None:
        """Qualify project before optionally locking exact original custody and child."""
        if (
            type(project_id) is not UUID
            or type(event_id) is not UUID
            or type(event_types) is not tuple
            or not event_types
            or type(child_event_type) is not str
            or type(lock) is not bool
        ):
            raise DeliveryUnavailable("outbox_delivery_reconciliation_unavailable")
        e, a = OutboxEvent, OutboxDeliveryAttempt
        statement = (
            select(e, a)
            .join(
                a,
                and_(a.event_id == e.event_id, a.claim_generation == e.claim_generation),
            )
            .where(
                e.event_id == event_id,
                e.project_id == str(project_id),
                self._unknown_predicate(event_types),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update(of=(e, a))
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        event, attempt = row
        children = await self._children(
            {UUID(str(event.event_id)): event.project_id}, child_event_type, lock=lock
        )
        return FinalizedUnknownDelivery(
            envelope=_envelope(event, attempt),
            finalized_at=event.finalized_at,
            error_code="INVOKE_OUTCOME_UNKNOWN",
            child=children.get(UUID(str(event.event_id))),
        )

    async def fence_reconciliation(
        self,
        *,
        original: OutboxEventEnvelope,
        child: OutboxEventEnvelope,
        event_types: tuple[tuple[str, int], ...],
        child_event_type: str,
    ) -> CommittedInvocationObservation | None:
        """Hold original terminal custody and the linked live child through commit."""
        if not self.session.in_transaction() or self.session.in_nested_transaction():
            raise DeliveryUnavailable("outbox reconciliation requires a root transaction")
        try:
            original = OutboxEventEnvelope.model_validate(original)
            child = OutboxEventEnvelope.model_validate(child)
        except (TypeError, ValueError):
            return None
        retained = await self.read_finalized_unknown(
            project_id=original.claim.project_id,
            event_id=original.claim.event_id,
            event_types=event_types,
            child_event_type=child_event_type,
            lock=True,
        )
        if (
            retained is None
            or retained.envelope != original
            or retained.child is None
            or retained.child.event_id != child.claim.event_id
            or child.event_type != child_event_type
            or child.event_version != 1
            or child.claim.project_id != original.claim.project_id
            or child.aggregate_type != "outbox_delivery"
            or child.aggregate_id != original.claim.event_id
            or child.causation_event_id != original.claim.event_id
        ):
            return None
        return await self.fence_invocation(child)

    async def observe(self, envelope: OutboxEventEnvelope) -> CommittedInvocationObservation | None:
        """Compare the entire immutable envelope in one nonlocking SQL snapshot."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope.model_dump())
            payload = json.loads(envelope.payload_json)
            if (
                type(payload) is not dict
                or json.dumps(payload, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False) != envelope.payload_json
                or canonical_json_hash(payload) != envelope.claim.payload_digest
            ):
                return None
        except (AttributeError, TypeError, ValueError):
            return None
        claim = envelope.claim
        e, a = OutboxEvent, OutboxDeliveryAttempt
        query = (
            select(func.statement_timestamp())
            .select_from(e)
            .join(
                a,
                and_(a.event_id == e.event_id, a.claim_generation == e.claim_generation),
            )
            .where(
                e.event_id == claim.event_id,
                e.project_id == str(claim.project_id),
                e.payload_digest == claim.payload_digest,
                e.event_type == envelope.event_type,
                e.event_version == envelope.event_version,
                e.aggregate_type == envelope.aggregate_type,
                e.aggregate_id == envelope.aggregate_id,
                e.correlation_id == envelope.correlation_id,
                e.causation_event_id.is_not_distinct_from(envelope.causation_event_id),
                e.idempotency_key == envelope.idempotency_key,
                e.occurred_at == envelope.occurred_at,
                e.payload == payload,
                e.delivery_state == "claimed",
                a.stage == "invoked",
                a.outcome_json.is_(None),
                e.claim_generation == claim.claim_generation,
                e.claim_owner == claim.claim_owner,
                e.claimed_at == claim.claimed_at,
                e.claim_expires_at == claim.claim_expires_at,
                a.project_id == e.project_id,
                a.payload_digest == e.payload_digest,
                a.claim_owner == e.claim_owner,
                a.claimed_at == e.claimed_at,
                a.claim_expires_at == e.claim_expires_at,
                e.claim_expires_at > func.statement_timestamp(),
            )
        )
        observed = (await self.session.execute(query)).scalar_one_or_none()
        return (
            None
            if observed is None
            else CommittedInvocationObservation(claim=claim, observed_at=observed)
        )

    async def fence_invocation(self, envelope: OutboxEventEnvelope) -> CommittedInvocationObservation | None:
        """Freeze current custody in the effect transaction, after feature AUTH locks.

        This does not prove a claim was committed: the caller must first use the
        independent observer. The lease must be live after all lock waits; row
        locks freeze generation/state through commit, not the passage of time.
        """
        if not self.session.in_transaction() or self.session.in_nested_transaction():
            raise DeliveryUnavailable("outbox fence requires a root transaction")
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope.model_dump())
        except (AttributeError, TypeError, ValueError):
            return None
        claim = envelope.claim
        with self.session.no_autoflush:
            if await self.event(claim.event_id, claim.project_id, lock=True) is None:
                return None
            if await self.attempt(claim, lock=True) is None:
                return None
            return await self.observe(envelope)

    async def drain(self, project_id: UUID, keys: tuple[tuple[str, int], ...]) -> DrainObservation:
        """One statement, disjoint state counts and explicitly overlapping facts."""
        e, a = OutboxEvent, OutboxDeliveryAttempt
        supported = (
            or_(*(and_(e.event_type == t, e.event_version == v) for t, v in keys))
            if keys
            else literal(False)
        )
        count = lambda predicate: func.count().filter(predicate)  # noqa: E731
        row = (
            (
                await self.session.execute(
                    select(
                        func.statement_timestamp().label("observed_at"),
                        count(e.delivery_state == "pending").label("pending"),
                        count(e.delivery_state == "claimed").label("claimed"),
                        count(e.delivery_state == "retryable").label("retryable"),
                        count(a.stage == "invoked").label("invoked"),
                        count(
                            and_(
                                a.stage == "completed",
                                func.jsonb_extract_path_text(
                                    cast(a.outcome_json, JSONB),
                                    "invocation_unknown",
                                )
                                == "true",
                            )
                        ).label("unresolved"),
                        count(
                            and_(
                                e.delivery_state.in_(("pending", "claimed", "retryable")),
                                ~supported,
                            )
                        ).label("unsupported"),
                        count(e.delivery_state == "dead_letter").label("dead_letter"),
                        count(and_(e.claim_generation > 0, a.event_id.is_(None))).label(
                            "missing_custody"
                        ),
                    )
                    .select_from(e)
                    .outerjoin(
                        a,
                        and_(
                            a.event_id == e.event_id,
                            a.claim_generation == e.claim_generation,
                        ),
                    )
                    .where(e.project_id == str(project_id))
                )
            )
            .mappings()
            .one()
        )
        if row["missing_custody"]:
            from app.modules.outbox.api import DeliveryPersistenceError

            raise DeliveryPersistenceError("outbox_observation_failed")
        return DrainObservation(
            project_id=project_id, **{k: v for k, v in row.items() if k != "missing_custody"}
        )
