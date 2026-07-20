"""add shared transactional outbox persistence

Revision ID: 0029_shared_transactional_outbox
Revises: 0028_artifact_admission
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029_shared_transactional_outbox"
down_revision = "0028_artifact_admission"
branch_labels = depends_on = None


def upgrade() -> None:
    """Create immutable event truth and the closed generic delivery-state shape."""
    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("event_version", sa.SmallInteger(), nullable=False),
        sa.Column("producer", sa.String(32), nullable=False, server_default="workstream"),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("correlation_id", sa.String(200), nullable=False),
        sa.Column("causation_event_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_digest", sa.String(71), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column("delivery_state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column("claim_owner", sa.String(120)),
        sa.Column("claim_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("event_id", name="pk_outbox_events"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency_key"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_outbox_events_project_id_projects"
        ),
        sa.CheckConstraint(
            "event_type ~ '^[A-Za-z][A-Za-z0-9._:-]{0,127}$'",
            name="event_type",
        ),
        sa.CheckConstraint(
            "event_version between 1 and 32767",
            name="event_version",
        ),
        sa.CheckConstraint("producer = 'workstream'", name="producer"),
        sa.CheckConstraint(
            "aggregate_type ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="aggregate_type",
        ),
        sa.CheckConstraint(
            "project_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="project_id",
        ),
        sa.CheckConstraint(
            "correlation_id ~ '^[A-Za-z0-9._:-]{1,200}$'",
            name="correlation_id",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9._:-]{1,200}$'",
            name="idempotency_key",
        ),
        sa.CheckConstraint(
            "payload_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="payload_digest",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 262144",
            name="payload_shape",
        ),
        sa.CheckConstraint(
            "delivery_state in ('pending','claimed','retryable','acknowledged',"
            "'dead_letter','cancelled')",
            name="delivery_state",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 and claim_generation >= 0 "
            "and attempt_count = claim_generation",
            name="delivery_counters",
        ),
        sa.CheckConstraint(
            "claim_owner is null or claim_owner ~ '^[A-Za-z0-9._:-]{1,120}$'",
            name="claim_owner",
        ),
        sa.CheckConstraint(
            "last_error_code is null or last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'",
            name="error_code",
        ),
        sa.CheckConstraint(
            "(next_attempt_at is null or next_attempt_at >= occurred_at) and "
            "(claimed_at is null or claimed_at >= occurred_at) and "
            "(last_attempt_at is null or last_attempt_at >= occurred_at) and "
            "(claim_expires_at is null or claim_expires_at > claimed_at) and "
            "(finalized_at is null or finalized_at >= occurred_at) and "
            "(finalized_at is null or last_attempt_at is null or finalized_at >= last_attempt_at) and "
            "(archived_at is null or archived_at >= finalized_at)",
            name="delivery_timestamps",
        ),
        sa.CheckConstraint(_state_shape(), name="delivery_state_shape"),
    )
    _create_indexes()
    _create_custody_triggers()


def _state_shape() -> str:
    """Return the frozen closed-state constraint shared with the ORM model."""
    return (
        "(delivery_state = 'pending' and attempt_count = 0 and next_attempt_at is not null "
        "and claim_owner is null and claimed_at is null and claim_expires_at is null "
        "and last_attempt_at is null and last_error_code is null and finalized_at is null "
        "and archived_at is null) or "
        "(delivery_state = 'claimed' and attempt_count > 0 and next_attempt_at is null "
        "and claim_owner is not null and claimed_at is not null "
        "and claim_expires_at is not null and last_attempt_at = claimed_at "
        "and finalized_at is null and archived_at is null) or "
        "(delivery_state = 'retryable' and attempt_count > 0 and next_attempt_at is not null "
        "and claim_owner is null and claimed_at is null and claim_expires_at is null "
        "and last_attempt_at is not null and last_error_code is not null "
        "and finalized_at is null and archived_at is null) or "
        "(delivery_state = 'acknowledged' and attempt_count > 0 and next_attempt_at is null "
        "and claim_owner is null and claimed_at is null and claim_expires_at is null "
        "and last_attempt_at is not null and finalized_at is not null) or "
        "(delivery_state = 'dead_letter' and attempt_count > 0 and next_attempt_at is null "
        "and claim_owner is null and claimed_at is null and claim_expires_at is null "
        "and last_attempt_at is not null and last_error_code is not null "
        "and finalized_at is not null) or "
        "(delivery_state = 'cancelled' and next_attempt_at is null and claim_owner is null "
        "and claimed_at is null and claim_expires_at is null and finalized_at is not null "
        "and ((attempt_count = 0 and last_attempt_at is null and last_error_code is null) "
        "or (attempt_count > 0 and last_attempt_at is not null)))"
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_outbox_events_eligible",
        "outbox_events",
        ["event_type", "delivery_state", "next_attempt_at", "occurred_at", "event_id"],
        postgresql_where=sa.text("delivery_state in ('pending','retryable')"),
    )
    op.create_index(
        "ix_outbox_events_expired_claims",
        "outbox_events",
        ["claim_expires_at", "event_id"],
        postgresql_where=sa.text("delivery_state = 'claimed'"),
    )
    op.create_index(
        "ix_outbox_events_project_drain",
        "outbox_events",
        ["project_id", "delivery_state", "occurred_at", "event_id"],
    )
    op.create_index(
        "ix_outbox_events_retention",
        "outbox_events",
        ["finalized_at", "event_id"],
        postgresql_where=sa.text(
            "delivery_state in ('acknowledged','dead_letter','cancelled') "
            "and archived_at is null"
        ),
    )
    op.create_index(
        "ix_outbox_events_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id", "occurred_at", "event_id"],
    )


def _create_custody_triggers() -> None:
    op.execute(
        """
        create function guard_outbox_event() returns trigger
        language plpgsql as $$
        declare event_time timestamptz;
        begin
          if tg_op = 'TRUNCATE' then
            raise exception 'outbox events cannot be truncated' using errcode='55000';
          elsif tg_op = 'DELETE' then
            raise exception 'outbox events cannot be deleted' using errcode='55000';
          elsif tg_op = 'INSERT' then
            event_time := statement_timestamp();
            new.producer := 'workstream';
            new.occurred_at := event_time;
            new.delivery_state := 'pending';
            new.attempt_count := 0;
            new.next_attempt_at := event_time;
            new.claim_owner := null;
            new.claim_generation := 0;
            new.claimed_at := null;
            new.claim_expires_at := null;
            new.last_attempt_at := null;
            new.last_error_code := null;
            new.finalized_at := null;
            new.archived_at := null;
            return new;
          end if;

          if (new.event_id, new.event_type, new.event_version, new.producer,
              new.aggregate_type, new.aggregate_id, new.project_id,
              new.correlation_id, new.causation_event_id, new.idempotency_key,
              new.payload, new.payload_digest, new.occurred_at)
             is distinct from
             (old.event_id, old.event_type, old.event_version, old.producer,
              old.aggregate_type, old.aggregate_id, old.project_id,
              old.correlation_id, old.causation_event_id, old.idempotency_key,
              old.payload, old.payload_digest, old.occurred_at) then
            raise exception 'outbox event envelope is immutable' using errcode='55000';
          end if;
          if new.attempt_count < old.attempt_count
             or new.claim_generation < old.claim_generation
             or new.attempt_count <> new.claim_generation then
            raise exception 'outbox counters cannot regress' using errcode='23514';
          end if;
          if old.archived_at is not null and
             (new.delivery_state, new.attempt_count, new.next_attempt_at,
              new.claim_owner, new.claim_generation, new.claimed_at,
              new.claim_expires_at, new.last_attempt_at, new.last_error_code,
              new.finalized_at, new.archived_at)
             is distinct from
             (old.delivery_state, old.attempt_count, old.next_attempt_at,
              old.claim_owner, old.claim_generation, old.claimed_at,
              old.claim_expires_at, old.last_attempt_at, old.last_error_code,
              old.finalized_at, old.archived_at) then
            raise exception 'archived outbox event is closed' using errcode='55000';
          end if;

          if old.delivery_state in ('pending', 'retryable')
             and new.delivery_state = 'claimed' then
            if new.attempt_count <> old.attempt_count + 1
               or new.claim_generation <> old.claim_generation + 1
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox claim generation must increment once' using errcode='23514';
            end if;
          elsif old.delivery_state = 'claimed'
                and new.delivery_state in ('retryable','acknowledged','dead_letter','cancelled') then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at then
              raise exception 'outbox outcome cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state = 'dead_letter'
                and new.delivery_state = 'retryable' and old.archived_at is null then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox requeue cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state in ('pending','retryable')
                and new.delivery_state = 'cancelled' then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox cancellation cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state in ('pending','retryable')
                and new.delivery_state = old.delivery_state then
            if (new.attempt_count, new.claim_owner, new.claim_generation,
                new.claimed_at, new.claim_expires_at, new.last_attempt_at,
                new.last_error_code, new.finalized_at, new.archived_at)
               is distinct from
               (old.attempt_count, old.claim_owner, old.claim_generation,
                old.claimed_at, old.claim_expires_at, old.last_attempt_at,
                old.last_error_code, old.finalized_at, old.archived_at) then
              raise exception 'outbox eligibility update changed unrelated state' using errcode='23514';
            end if;
          elsif old.delivery_state in ('acknowledged','dead_letter','cancelled')
                and new.delivery_state = old.delivery_state then
            if (new.attempt_count, new.next_attempt_at, new.claim_owner,
                new.claim_generation, new.claimed_at, new.claim_expires_at,
                new.last_attempt_at, new.last_error_code, new.finalized_at)
               is distinct from
               (old.attempt_count, old.next_attempt_at, old.claim_owner,
                old.claim_generation, old.claimed_at, old.claim_expires_at,
                old.last_attempt_at, old.last_error_code, old.finalized_at)
               or (old.archived_at is not null and new.archived_at is distinct from old.archived_at)
               or (old.archived_at is null and new.archived_at is null) then
              raise exception 'terminal outbox event permits archival only' using errcode='23514';
            end if;
          else
            raise exception 'illegal outbox delivery transition' using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger outbox_events_custody before insert or update or delete "
        "on outbox_events for each row execute function guard_outbox_event()"
    )
    op.execute(
        "create trigger outbox_events_reject_truncate before truncate on outbox_events "
        "for each statement execute function guard_outbox_event()"
    )


def downgrade() -> None:
    """Remove the empty outbox only after excluding concurrent append writers."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table outbox_events in access exclusive mode"))
    if bind.execute(sa.text("select exists(select 1 from outbox_events)")).scalar_one():
        raise RuntimeError("cannot downgrade with shared outbox events")
    op.execute("drop trigger outbox_events_reject_truncate on outbox_events")
    op.execute("drop trigger outbox_events_custody on outbox_events")
    op.execute("drop function guard_outbox_event()")
    op.drop_table("outbox_events")
