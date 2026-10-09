"""SQLAlchemy models for durable checker runs and checker results."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Uuid
from sqlalchemy import (
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CheckerRun(Base):
    """Durable post-submit checker execution bound to one submission version."""

    __tablename__ = "checker_runs"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["task_id", "locked_guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_checker_runs_task_locked_guide",
        ),
        ForeignKeyConstraint(
            [
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            [
                "checker_policies.id",
                "checker_policies.guide_version",
                "checker_policies.policy_hash",
            ],
            name="fk_checker_runs_locked_post_submit_policy_hash",
        ),
        ForeignKeyConstraint(
            [
                "task_id",
                "locked_review_policy_id",
                "locked_review_policy_generation",
                "locked_review_policy_hash",
            ],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_review_policy_id",
                "workstream_tasks.locked_review_policy_generation",
                "workstream_tasks.locked_review_policy_hash",
            ],
            name="fk_checker_runs_task_locked_review_policy",
        ),
        ForeignKeyConstraint(
            [
                "task_id",
                "locked_revision_policy_id",
                "locked_revision_policy_generation",
                "locked_revision_policy_hash",
            ],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_revision_policy_id",
                "workstream_tasks.locked_revision_policy_generation",
                "workstream_tasks.locked_revision_policy_hash",
            ],
            name="fk_checker_runs_task_locked_revision_policy",
        ),
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
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
        UniqueConstraint("id", "task_id", "submission_id", name="uq_checker_runs_ownership"),
        ForeignKeyConstraint(
            ["supersedes_checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_checker_runs_predecessor_ownership",
        ),
        UniqueConstraint("evaluation_request_id", "phase", name="uq_checker_runs_request_phase"),
        UniqueConstraint("submission_id", "phase", "evaluation_generation", name="uq_checker_runs_generation"),
        UniqueConstraint("id", "submission_id", name="uq_checker_runs_submission"),
        ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"],
                             name="fk_checker_runs_task_project"),
        CheckConstraint("phase = 'post_submission'", name="phase"),
        CheckConstraint("evaluation_generation > 0 and worker_lease_generation >= 0", name="generations"),
        CheckConstraint("status in ('queued','running','completed','infrastructure_failed')", name="state"),
        CheckConstraint("octet_length(request_json) <= 1048576 and request_digest = 'sha256:' || encode(sha256(convert_to(request_json, 'UTF8')), 'hex')", name="request_digest"),
        CheckConstraint("result_json is null or result_digest = 'sha256:' || encode(sha256(convert_to(result_json, 'UTF8')), 'hex')", name="result_digest"),
        Index(
            "ix_checker_runs_locked_post_submit_policy_hash",
            "locked_post_submit_checker_policy_hash",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id"), nullable=False, index=True
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
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
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    evaluation_request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    evaluation_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    worker_lease_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    worker_lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execute_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", name="fk_checker_runs_execute_evidence", deferrable=True, initially="DEFERRED"),
    )
    finalize_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", name="fk_checker_runs_finalize_evidence", deferrable=True, initially="DEFERRED"),
    )
    result_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, unique=True)
    result_json: Mapped[str | None] = mapped_column(Text)
    result_digest: Mapped[str | None] = mapped_column(String(71))
    input_materialization_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", name="fk_checker_input_materialization_evidence"),
    )
    material_custody: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    completion_event_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey("outbox_events.event_id"))
    supersedes_checker_run_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        index=True,
    )
    locked_guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_post_submit_checker_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    locked_post_submit_checker_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    locked_post_submit_checker_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_review_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    locked_review_policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_review_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_revision_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    locked_revision_policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_revision_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    results: Mapped[list[CheckerResult]] = relationship(
        back_populates="checker_run",
        cascade="save-update, merge",
    )


class CheckerResult(Base):
    """One immutable checker result produced inside a durable checker run."""

    __tablename__ = "checker_results"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_checker_results_run_ownership",
        ),
        UniqueConstraint("checker_run_id", "member_order", name="uq_checker_results_order"),
        UniqueConstraint("checker_run_id", "checker_name", name="uq_checker_results_member"),
        CheckConstraint("member_order between 0 and 8", name="member_order"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    checker_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    member_order: Mapped[int] = mapped_column(Integer, nullable=False)
    checker_name: Mapped[str] = mapped_column(String(100), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(50), nullable=False)
    implementation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    failure_category: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    counters: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    checker_run: Mapped[CheckerRun] = relationship(back_populates="results")


class CheckerSubmissionFence(Base):
    """The sole current request for a submission; never a second result store."""

    __tablename__ = "checker_submission_fences"
    __table_args__ = (
        ForeignKeyConstraint(["current_run_id", "submission_id"], ["checker_runs.id", "checker_runs.submission_id"],
                             name="fk_checker_submission_fences_run"),
    )
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), primary_key=True)
    current_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, unique=True)
