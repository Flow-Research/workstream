"""Immutable source-rooted revision preparations; successors never edit history."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.db.base import Base


class TaskRevisionPreparation(Base):
    """A frozen next-attempt context and clock, bound to one exact source."""

    __tablename__ = "task_revision_preparations"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"], name="fk_revision_preparation_task_project"),
        ForeignKeyConstraint(["assignment_id", "task_id", "contributor_id"], ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"], name="fk_revision_preparation_assignment"),
        ForeignKeyConstraint(["submission_id", "task_id", "source_submission_version"], ["submissions.id", "submissions.task_id", "submissions.version"], name="fk_revision_preparation_submission"),
        UniqueConstraint("id", "preparation_sha256", name="uq_revision_preparation_identity_digest"),
        UniqueConstraint("repair_actor_id", "repair_idempotency_key", name="uq_revision_repair_actor_key"),
        UniqueConstraint("predecessor_id", name="uq_revision_preparation_successor"),
        UniqueConstraint("routing_manifest_id", "sequence", name="uq_revision_preparation_sequence"),
        Index("uq_revision_preparation_root", "routing_manifest_id", unique=True, postgresql_where=text("predecessor_id IS NULL")),
        CheckConstraint("sequence > 0 and source_submission_version > 0 and next_revision_round >= 0 and max_revision_rounds >= 0", name="positive_rounds"),
        CheckConstraint("(sequence = 1) = (predecessor_id IS NULL)", name="chain_shape"),
        CheckConstraint("outcome in ('kept','rebased','blocked')", name="outcome"),
        CheckConstraint("blocked_reason is null or blocked_reason in ('context_blocked','revision_limit_reached','revision_deadline_expired')", name="blocked_reason"),
        CheckConstraint("(outcome = 'blocked') = (blocked_reason IS NOT NULL)", name="blocked_shape"),
        CheckConstraint("preparation_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="digest"),
        CheckConstraint("deadline_at > requested_at", name="deadline"),
        CheckConstraint("(deadline_at IS NOT NULL AND remaining_microseconds IS NULL) OR (deadline_at IS NULL AND remaining_microseconds IS NOT NULL AND remaining_microseconds > 0)", name="clock_shape"),
        CheckConstraint(
            "(predecessor_id IS NULL AND repair_actor_id IS NULL AND repair_idempotency_key IS NULL "
            "AND repair_request_digest IS NULL AND repair_reason IS NULL AND repair_authority_context IS NULL) "
            "OR (repair_actor_id IS NOT NULL AND repair_idempotency_key IS NOT NULL "
            "AND repair_request_digest IS NOT NULL AND repair_request_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND repair_reason IS NOT NULL AND octet_length(btrim(repair_reason)) BETWEEN 1 AND 1000 "
            "AND repair_authority_context IS NOT NULL AND jsonb_typeof(repair_authority_context)='object')",
            name=conv("ck_revision_preparation_repair_shape"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    contributor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    routing_manifest_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("task_post_submit_routing_manifests.id", ondelete="RESTRICT"), nullable=False)
    predecessor_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey("task_revision_preparations.id", ondelete="RESTRICT"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    next_revision_round: Mapped[int] = mapped_column(Integer, nullable=False)
    max_revision_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remaining_microseconds: Mapped[int | None] = mapped_column(BigInteger)
    clock_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    creation_xid: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("pg_current_xact_id()::text"))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(40))
    packet: Mapped[dict] = mapped_column(JSONB, nullable=False)
    preparation_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    authorization_decision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"), nullable=False)

    repair_actor_id: Mapped[UUID | None] = mapped_column(Uuid())
    repair_idempotency_key: Mapped[UUID | None] = mapped_column(Uuid())
    repair_request_digest: Mapped[str | None] = mapped_column(String(71))
    repair_reason: Mapped[str | None] = mapped_column(String(1000))
    repair_authority_context: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))


class TaskRevisionExpiration(Base):
    """One immutable deadline rejection for a routed failure, including its final head."""

    __tablename__ = "task_revision_expirations"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"], name="fk_revision_expiration_task_project"),
        ForeignKeyConstraint(["assignment_id", "task_id", "contributor_id"], ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"], name="fk_revision_expiration_assignment"),
        ForeignKeyConstraint(["root_preparation_id", "root_preparation_sha256"], ["task_revision_preparations.id", "task_revision_preparations.preparation_sha256"], name="fk_revision_expiration_root_preparation"),
        ForeignKeyConstraint(["head_preparation_id", "head_preparation_sha256"], ["task_revision_preparations.id", "task_revision_preparations.preparation_sha256"], name="fk_revision_expiration_head_preparation"),
        UniqueConstraint("routing_manifest_id", name="uq_revision_expiration_manifest"),
        UniqueConstraint("head_preparation_id", name="uq_revision_expiration_head"),
        UniqueConstraint("delivery_event_id", name="uq_revision_expiration_delivery"),
        UniqueConstraint("outcome_event_id", name="uq_revision_expiration_outcome"),
        UniqueConstraint("audit_event_id", name="uq_revision_expiration_audit"),
        CheckConstraint("root_preparation_sha256 ~ '^sha256:[0-9a-f]{64}$' and head_preparation_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="digests"),
        CheckConstraint("expired_at >= deadline_at", name="deadline"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    contributor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    source_submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False)
    routing_manifest_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("task_post_submit_routing_manifests.id", ondelete="RESTRICT"), nullable=False)
    root_preparation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    root_preparation_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    head_preparation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    head_preparation_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_event_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("outbox_events.event_id", ondelete="RESTRICT"), nullable=False)
    outcome_event_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("outbox_events.event_id", ondelete="RESTRICT"), nullable=False)
    authorization_decision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False)
    authority_context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    audit_event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    creation_xid: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("pg_current_xact_id()::text"))


class TaskRevisionExhaustion(Base):
    """A routing consequence with no fabricated preparation or deadline window."""

    __tablename__ = "task_revision_exhaustions"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"], name="fk_revision_exhaustion_task_project"),
        ForeignKeyConstraint(["assignment_id", "task_id", "contributor_id"], ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"], name="fk_revision_exhaustion_assignment"),
        UniqueConstraint("routing_manifest_id", name="uq_revision_exhaustion_manifest"),
        UniqueConstraint("assignment_id", name="uq_revision_exhaustion_assignment"),
        UniqueConstraint("source_submission_id", name="uq_revision_exhaustion_submission"),
        UniqueConstraint("audit_event_id", name="uq_revision_exhaustion_audit"),
        UniqueConstraint("outcome_event_id", name="uq_revision_exhaustion_outcome"),
        CheckConstraint("revision_round >= 0 and max_revision_rounds >= 0 and revision_round = max_revision_rounds", name="rounds"),
        CheckConstraint("revision_policy_generation > 0 and revision_policy_hash ~ '^sha256:[0-9a-f]{64}$'", name="policy"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    contributor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    source_submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False)
    routing_manifest_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("task_post_submit_routing_manifests.id", ondelete="RESTRICT"), nullable=False)
    revision_round: Mapped[int] = mapped_column(Integer, nullable=False)
    max_revision_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("revision_policies.id", ondelete="RESTRICT"), nullable=False)
    revision_policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    exhausted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authorization_decision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"), nullable=False)
    outcome_event_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("outbox_events.event_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    creation_xid: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("pg_current_xact_id()::text"))
