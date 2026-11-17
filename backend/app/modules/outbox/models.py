"""SQLAlchemy persistence for the feature-neutral shared outbox."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    """Immutable event envelope plus separately mutable delivery metadata."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "not_before_at is null or (isfinite(not_before_at) and "
            "(next_attempt_at is null or next_attempt_at >= not_before_at) and "
            "(claimed_at is null or claimed_at >= not_before_at))",
            name="not_before_delivery",
        ),
        CheckConstraint("(get_byte(uuid_send(event_id), 6) >> 4) = 7 and (get_byte(uuid_send(event_id), 8) & 192) = 128", name="event_id_uuid7"),
        CheckConstraint(
            "event_type ~ '^[A-Za-z][A-Za-z0-9._:-]{0,127}$'",
            name="event_type",
        ),
        CheckConstraint("event_version between 1 and 32767", name="event_version"),
        CheckConstraint("producer = 'workstream'", name="producer"),
        CheckConstraint(
            "aggregate_type ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="aggregate_type",
        ),
        CheckConstraint(
            "project_id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="project_id",
        ),
        CheckConstraint(
            "correlation_id ~ '^[A-Za-z0-9._:-]{1,200}$'",
            name="correlation_id",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9._:-]{1,200}$'",
            name="idempotency_key",
        ),
        CheckConstraint(
            "payload_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="payload_digest",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 262144",
            name="payload_shape",
        ),
        CheckConstraint(
            "delivery_state in ('pending','claimed','retryable','acknowledged',"
            "'dead_letter','cancelled')",
            name="delivery_state",
        ),
        CheckConstraint(
            "attempt_count >= 0 and claim_generation >= 0 and attempt_count = claim_generation",
            name="delivery_counters",
        ),
        CheckConstraint(
            "claim_owner is null or claim_owner ~ '^[A-Za-z0-9._:-]{1,120}$'",
            name="claim_owner",
        ),
        CheckConstraint(
            "last_error_code is null or last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'",
            name="error_code",
        ),
        CheckConstraint(
            "(next_attempt_at is null or next_attempt_at >= occurred_at) and "
            "(claimed_at is null or claimed_at >= occurred_at) and "
            "(last_attempt_at is null or last_attempt_at >= occurred_at) and "
            "(claim_expires_at is null or claim_expires_at > claimed_at) and "
            "(finalized_at is null or finalized_at >= occurred_at) and "
            "(finalized_at is null or last_attempt_at is null or finalized_at >= last_attempt_at) and "
            "(archived_at is null or archived_at >= finalized_at)",
            name="delivery_timestamps",
        ),
        CheckConstraint(
            "(delivery_state = 'pending' and attempt_count = 0 and next_attempt_at is not null "
            "and claim_owner is null and claimed_at is null and claim_expires_at is null "
            "and last_attempt_at is null and last_error_code is null and finalized_at is null "
            "and archived_at is null) or "
            "(delivery_state = 'claimed' and attempt_count > 0 and next_attempt_at is null "
            "and claim_owner is not null and claimed_at is not null "
            "and claim_expires_at is not null and last_attempt_at = claimed_at "
            "and finalized_at is null and archived_at is null) or "
            "(delivery_state = 'retryable' and attempt_count > 0 "
            "and next_attempt_at is not null and claim_owner is null and claimed_at is null "
            "and claim_expires_at is null and last_attempt_at is not null "
            "and last_error_code is not null and finalized_at is null and archived_at is null) or "
            "(delivery_state = 'acknowledged' and attempt_count > 0 "
            "and next_attempt_at is null and claim_owner is null and claimed_at is null "
            "and claim_expires_at is null and last_attempt_at is not null "
            "and finalized_at is not null) or "
            "(delivery_state = 'dead_letter' and attempt_count > 0 "
            "and next_attempt_at is null and claim_owner is null and claimed_at is null "
            "and claim_expires_at is null and last_attempt_at is not null "
            "and last_error_code is not null and finalized_at is not null) or "
            "(delivery_state = 'cancelled' and next_attempt_at is null and claim_owner is null "
            "and claimed_at is null and claim_expires_at is null and finalized_at is not null "
            "and attempt_count = 0 and last_attempt_at is null and last_error_code is null)",
            name="delivery_state_shape",
        ),
        Index(
            "uq_submission_finalization_recovery_original", "causation_event_id", unique=True,
            postgresql_where=text("event_type='SubmissionFinalizationRecoveryRequested'"),
        ),
        Index(
            "ix_outbox_events_eligible",
            "event_type",
            "delivery_state",
            "next_attempt_at",
            "occurred_at",
            "event_id",
            postgresql_where=text("delivery_state in ('pending','retryable')"),
        ),
        Index(
            "ix_outbox_events_expired_claims",
            "claim_expires_at",
            "event_id",
            postgresql_where=text("delivery_state = 'claimed'"),
        ),
        Index(
            "ix_outbox_events_project_drain",
            "project_id",
            "delivery_state",
            "occurred_at",
            "event_id",
        ),
        Index(
            "ix_outbox_events_retention",
            "finalized_at",
            "event_id",
            postgresql_where=text(
                "delivery_state in ('acknowledged','dead_letter','cancelled') "
                "and archived_at is null"
            ),
        ),
        Index(
            "ix_outbox_events_aggregate",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
            "event_id",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    producer: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'workstream'")
    )
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(200), nullable=False)
    causation_event_id: Mapped[UUID | None] = mapped_column(Uuid())
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    not_before_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=text("statement_timestamp()")
    )
    claim_owner: Mapped[str | None] = mapped_column(String(120))
    claim_generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxDeliveryAttempt(Base):
    """Retained delivery custody bound to immutable real phase decisions."""

    __tablename__ = "outbox_delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "(stage = 'claimed' and invoke_decision_event_id is null and finalize_decision_event_id is null) or "
            "(stage = 'invoked' and invoke_decision_event_id is not null and finalize_decision_event_id is null) or "
            "(stage = 'completed' and finalize_decision_event_id is not null and "
            "((invoked_at is null and invoke_decision_event_id is null) or "
            "(invoked_at is not null and invoke_decision_event_id is not null)))",
            name="phase_decisions",
        ),
        CheckConstraint("claim_generation between 1 and 2147483647", name="generation"),
        CheckConstraint("claim_owner ~ '^[A-Za-z0-9._:-]{1,120}$'", name="owner"),
        CheckConstraint("payload_digest ~ '^sha256:[0-9a-f]{64}$'", name="payload_digest"),
        CheckConstraint(
            "claim_expires_at > claimed_at and claim_expires_at <= claimed_at + interval '1 hour'",
            name="lease",
        ),
        CheckConstraint(
            "(stage = 'claimed' and invoked_at is null and outcome_json is null "
            "and outcome_digest is null) or "
            "(stage = 'invoked' and invoked_at is not null and invoked_at >= claimed_at and invoked_at < claim_expires_at "
            "and outcome_json is null and outcome_digest is null) or "
            "(stage = 'completed' and outcome_json is not null and outcome_digest is not null "
            "and (invoked_at is null or (invoked_at >= claimed_at and invoked_at < claim_expires_at)))",
            name="stage_shape",
        ),
        CheckConstraint(
            "outcome_json is null or coalesce(outbox_delivery_outcome_valid("
            "outcome_json, outcome_digest, claimed_at, claim_expires_at, invoked_at), false)",
            name="outcome",
        ),
    )

    claim_decision_event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id"), unique=True, nullable=False)
    invoke_decision_event_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id"), unique=True)
    finalize_decision_event_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id"), unique=True)

    event_id: Mapped[UUID] = mapped_column(ForeignKey("outbox_events.event_id"), primary_key=True)
    claim_generation: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    claim_owner: Mapped[str] = mapped_column(String(120), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    invoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_json: Mapped[str | None] = mapped_column(String(2048))
    outcome_digest: Mapped[str | None] = mapped_column(String(71))
