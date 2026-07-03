"""SQLAlchemy models for durable checker runs and checker results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CheckerRun(Base):
    """Durable post-submit checker execution bound to one submission version."""

    __tablename__ = "checker_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "locked_guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_checker_runs_task_locked_guide",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_checker_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_checker_policy_version"],
            name="fk_checker_runs_task_locked_checker_policy",
        ),
        ForeignKeyConstraint(
            [
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            ["checker_policies.id", "checker_policies.guide_version", "checker_policies.policy_hash"],
            name="fk_checker_runs_locked_post_submit_policy_hash",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_review_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_review_policy_version"],
            name="fk_checker_runs_task_locked_review_policy",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_revision_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_revision_policy_version"],
            name="fk_checker_runs_task_locked_revision_policy",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_payment_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_payment_policy_version"],
            name="fk_checker_runs_task_locked_payment_policy",
        ),
        ForeignKeyConstraint(
            ["submission_id", "submission_version"],
            ["submissions.id", "submissions.version"],
            name="fk_checker_runs_submission_version",
        ),
        ForeignKeyConstraint(
            [
                "submission_id",
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            [
                "submissions.id",
                "submissions.locked_post_submit_checker_policy_id",
                "submissions.locked_post_submit_checker_policy_version",
                "submissions.locked_post_submit_checker_policy_hash",
            ],
            name="fk_checker_runs_submission_locked_post_submit_policy_hash",
        ),
        UniqueConstraint(
            "submission_id",
            "attempt_number",
            name="uq_checker_runs_submission_attempt",
        ),
        CheckConstraint(
            """
            locked_post_submit_checker_policy_id is not null
            and locked_post_submit_checker_policy_version is not null
            and locked_post_submit_checker_policy_hash is not null
            and locked_post_submit_checker_policy_body is not null
            """,
            name="post_submit_policy_lock_complete",
        ),
        Index(
            "uq_checker_runs_current_per_submission",
            "submission_id",
            unique=True,
            postgresql_where=text("is_current_for_submission = true"),
        ),
        Index(
            "ix_checker_runs_locked_post_submit_policy_hash",
            "locked_post_submit_checker_policy_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("workstream_tasks.id"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    routing_recommendation: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="not_evaluated",
        index=True,
    )
    outcome_source: Mapped[str] = mapped_column(String(50), nullable=False, default="none")
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    triggered_by_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    triggered_by_issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_auth_source: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_reason: Mapped[str | None] = mapped_column(Text)
    audit_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_checker_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("checker_runs.id"),
        index=True,
    )
    is_current_for_submission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    locked_guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_checker_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_post_submit_checker_policy_id: Mapped[str] = mapped_column(String(36), nullable=False)
    locked_post_submit_checker_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    locked_post_submit_checker_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_post_submit_checker_policy_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    locked_review_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_revision_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_payment_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    package_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_hash_manifest: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    artifact_manifest_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    results: Mapped[list[CheckerResult]] = relationship(
        back_populates="checker_run",
        cascade="all, delete-orphan",
    )


class CheckerResult(Base):
    """One immutable checker result produced inside a durable checker run."""

    __tablename__ = "checker_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checker_run_id: Mapped[str] = mapped_column(
        ForeignKey("checker_runs.id"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("workstream_tasks.id"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    checker_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    blocks_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    worker_message: Mapped[str | None] = mapped_column(Text)
    worker_suggested_fix: Mapped[str | None] = mapped_column(Text)
    worker_evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    worker_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    checker_run: Mapped[CheckerRun] = relationship(back_populates="results")
