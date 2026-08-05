"""SQLAlchemy persistence for the hidden review queue foundation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewQueueEntry(Base):
    """Mutable routing identity for exactly one reviewable Submission."""

    __tablename__ = "review_queue_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_review_queue_submission_lineage",
        ),
        ForeignKeyConstraint(
            ["active_lease_id", "id"],
            ["review_leases.id", "review_leases.review_queue_entry_id"],
            name="fk_review_queue_active_lease",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("submission_id", name="uq_review_queue_submission"),
        UniqueConstraint(
            "id",
            "project_id",
            "task_id",
            "submission_id",
            "submission_version",
            name="uq_review_queue_lease_lineage",
        ),
        UniqueConstraint(
            "id",
            "project_id",
            "task_id",
            "submission_id",
            "submission_version",
            "admitting_checker_run_id",
            name="uq_review_queue_admission_identity",
        ),
        CheckConstraint("submission_version > 0", name="submission_version_positive"),
        CheckConstraint("queue_state in ('pending','leased','closed')", name="queue_state"),
        CheckConstraint(
            "routing_mode in ('open','preferred')",
            name="routing_mode",
        ),
        CheckConstraint(
            "routing_reason in ('first_submission','revision_return','admin_assignment')",
            name="routing_reason",
        ),
        CheckConstraint(
            "(routing_mode='open' and preferred_reviewer_id is null "
            "and preference_expires_at is null) or "
            "(routing_mode='preferred' and preferred_reviewer_id is not null "
            "and preference_expires_at is not null "
            "and preference_expires_at > first_queued_at)",
            name="routing_shape",
        ),
        CheckConstraint(
            "(queue_state='pending' and active_lease_id is null "
            "and closed_at is null and closed_reason is null) or "
            "(queue_state='leased' and active_lease_id is not null "
            "and closed_at is null and closed_reason is null) or "
            "(queue_state='closed' and closed_at is not null and "
            "active_lease_id is null and "
            "closed_reason in ('review_recorded','task_closed','admin_cancelled') "
            "and closed_at >= first_queued_at)",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            "available_since >= first_queued_at",
            name="availability_time",
        ),
        CheckConstraint(
            "routing_generation > 0 and lifecycle_generation > 0",
            name="generations_positive",
        ),
        Index(
            "ix_review_queue_selection",
            "project_id",
            "queue_state",
            "routing_mode",
            "first_queued_at",
            "id",
        ),
        Index(
            "ix_review_queue_preference",
            "preferred_reviewer_id",
            "queue_state",
            "preference_expires_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_review_queue_project"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id", name="fk_review_queue_task"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", name="fk_review_queue_submission"), nullable=False
    )
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    admitting_checker_run_id: Mapped[str] = mapped_column(
        ForeignKey("checker_runs.id", name="fk_review_queue_checker"), nullable=False
    )
    queue_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    active_lease_id: Mapped[UUID | None] = mapped_column(Uuid())
    routing_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    routing_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    first_queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    available_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    preferred_reviewer_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_review_queue_preferred_reviewer")
    )
    preference_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(32))
    routing_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    lifecycle_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )


class ReviewAdmissionIdempotencyRecord(Base):
    """Reservation and replay identity for one future queue admission."""

    __tablename__ = "review_admission_idempotency_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_review_admission_submission_lineage",
        ),
        ForeignKeyConstraint(
            [
                "review_queue_entry_id",
                "project_id",
                "task_id",
                "submission_id",
                "submission_version",
                "admitting_checker_run_id",
            ],
            [
                "review_queue_entries.id",
                "review_queue_entries.project_id",
                "review_queue_entries.task_id",
                "review_queue_entries.submission_id",
                "review_queue_entries.submission_version",
                "review_queue_entries.admitting_checker_run_id",
            ],
            name="fk_review_admission_committed_queue",
        ),
        UniqueConstraint("idempotency_key", name="uq_review_admission_replay_key"),
        UniqueConstraint("operation_id", name="uq_review_admission_operation"),
        UniqueConstraint("admitting_checker_run_id", name="uq_review_admission_checker_run"),
        CheckConstraint("submission_version > 0", name="submission_version_positive"),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="request_digest",
        ),
        CheckConstraint("status in ('pending','committed')", name="status"),
        CheckConstraint(
            "(status='pending' and review_queue_entry_id is null and committed_at is null) or "
            "(status='committed' and review_queue_entry_id is not null "
            "and committed_at is not null)",
            name="state_shape",
        ),
        Index(
            "ix_review_admission_submission",
            "submission_id",
            "status",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_review_admission_project"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id", name="fk_review_admission_task"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", name="fk_review_admission_submission"), nullable=False
    )
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    admitting_checker_run_id: Mapped[str] = mapped_column(
        ForeignKey("checker_runs.id", name="fk_review_admission_checker"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    review_queue_entry_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("review_queue_entries.id", name="fk_review_admission_queue")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewLease(Base):
    """Immutable identity and terminal provenance for one review claim attempt."""

    __tablename__ = "review_leases"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "review_queue_entry_id",
                "project_id",
                "task_id",
                "submission_id",
                "submission_version",
            ],
            [
                "review_queue_entries.id",
                "review_queue_entries.project_id",
                "review_queue_entries.task_id",
                "review_queue_entries.submission_id",
                "review_queue_entries.submission_version",
            ],
            name="fk_review_lease_queue_lineage",
        ),
        ForeignKeyConstraint(
            ["reviewer_contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_review_lease_policy_version",
        ),
        UniqueConstraint(
            "review_queue_entry_id", "id", name="uq_review_lease_queue_identity"
        ),
        UniqueConstraint(
            "review_queue_entry_id", "attempt_generation", name="uq_review_lease_attempt"
        ),
        CheckConstraint("attempt_generation > 0", name="attempt_generation_positive"),
        CheckConstraint(
            "status in ('active','consumed','released','expired','revoked')",
            name="status",
        ),
        CheckConstraint("expires_at > claimed_at", name="expiry_after_claim"),
        CheckConstraint(
            "(status='active' and closed_at is null and close_reason is null) or "
            "(status='consumed' and closed_at is not null and close_reason='review_recorded') or "
            "(status='released' and closed_at is not null and close_reason='manual_release') or "
            "(status='expired' and closed_at is not null and close_reason='lease_expired') or "
            "(status='revoked' and closed_at is not null "
            "and close_reason in ('grant_revoked','admin_override'))",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            "closed_at is null or closed_at >= claimed_at", name="closure_after_claim"
        ),
        Index(
            "uq_review_lease_active_queue",
            "review_queue_entry_id",
            unique=True,
            postgresql_where=text("status='active'"),
        ),
        Index(
            "uq_review_lease_active_reviewer",
            "reviewer_id",
            unique=True,
            postgresql_where=text("status='active'"),
        ),
        Index("ix_review_lease_expiry", "status", "expires_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    review_queue_entry_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_review_lease_project"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id", name="fk_review_lease_task"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", name="fk_review_lease_submission"), nullable=False
    )
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_review_lease_reviewer"), nullable=False
    )
    reviewer_contribution_policy_version_id: Mapped[UUID] = mapped_column(
        Uuid(), nullable=False
    )
    attempt_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'")
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(32))
