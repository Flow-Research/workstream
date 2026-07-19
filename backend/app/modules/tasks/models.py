"""SQLAlchemy models for task queue, assignment, submissions, and audit events."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class WorkstreamTask(Base):
    """Task queue record with server-stamped guide and policy context."""

    __tablename__ = "workstream_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "locked_guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_workstream_tasks_locked_guide",
        ),
        ForeignKeyConstraint(
            [
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            ["checker_policies.id", "checker_policies.guide_version", "checker_policies.policy_hash"],
            name="fk_workstream_tasks_locked_post_submit_policy_hash",
        ),
        ForeignKeyConstraint(
            ["project_id", "locked_review_policy_version"],
            ["review_policies.project_id", "review_policies.guide_version"],
            name="fk_workstream_tasks_locked_review_policy",
        ),
        ForeignKeyConstraint(
            ["project_id", "locked_revision_policy_version"],
            ["revision_policies.project_id", "revision_policies.guide_version"],
            name="fk_workstream_tasks_locked_revision_policy",
        ),
        ForeignKeyConstraint(
            ["project_id", "locked_payment_policy_version"],
            ["payment_policies.project_id", "payment_policies.guide_version"],
            name="fk_workstream_tasks_locked_payment_policy",
        ),
        ForeignKeyConstraint(
            ["locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_workstream_tasks_locked_source_snapshot_hash",
        ),
        ForeignKeyConstraint(
            [
                "locked_effective_project_submission_artifact_policy_id",
                "locked_effective_project_submission_artifact_policy_hash",
            ],
            [
                "effective_project_submission_artifact_policies.id",
                "effective_project_submission_artifact_policies.effective_policy_hash",
            ],
            name="fk_workstream_tasks_locked_effective_policy_hash",
        ),
        ForeignKeyConstraint(
            ["locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
            ["pre_submit_checker_policies.id", "pre_submit_checker_policies.compiled_bundle_hash"],
            name="fk_workstream_tasks_locked_pre_submit_checker_hash",
        ),
        UniqueConstraint("id", "locked_guide_version", name="uq_workstream_tasks_id_locked_guide"),
        UniqueConstraint(
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
            name="uq_workstream_tasks_id_locked_post_submit_policy_hash",
        ),
        UniqueConstraint(
            "id",
            "locked_review_policy_version",
            name="uq_workstream_tasks_id_locked_review_policy",
        ),
        UniqueConstraint(
            "id",
            "locked_revision_policy_version",
            name="uq_workstream_tasks_id_locked_revision_policy",
        ),
        UniqueConstraint(
            "id",
            "locked_payment_policy_version",
            name="uq_workstream_tasks_id_locked_payment_policy",
        ),
        UniqueConstraint(
            "id",
            "locked_guide_source_snapshot_id",
            "locked_guide_source_snapshot_hash",
            name="uq_workstream_tasks_id_locked_source_snapshot_hash",
        ),
        UniqueConstraint(
            "id",
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
            name="uq_workstream_tasks_id_locked_effective_policy_hash",
        ),
        UniqueConstraint(
            "id",
            "locked_pre_submit_checker_policy_id",
            "locked_pre_submit_checker_bundle_hash",
            name="uq_workstream_tasks_id_locked_pre_submit_checker_hash",
        ),
        CheckConstraint(
            """
            status = 'draft'
            or (
                locked_post_submit_checker_policy_id is not null
                and locked_post_submit_checker_policy_version is not null
                and locked_post_submit_checker_policy_hash is not null
                and locked_post_submit_checker_policy_body is not null
            )
            """,
            name="post_submit_policy_lock_complete",
        ),
        Index(
            "ix_workstream_tasks_locked_source_snapshot",
            "locked_guide_source_snapshot_id",
        ),
        Index(
            "ix_workstream_tasks_locked_effective_policy_hash",
            "locked_effective_project_submission_artifact_policy_hash",
        ),
        Index(
            "ix_workstream_tasks_locked_pre_submit_checker_hash",
            "locked_pre_submit_checker_bundle_hash",
        ),
        Index(
            "ix_workstream_tasks_locked_post_submit_policy_hash",
            "locked_post_submit_checker_policy_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    locked_guide_version: Mapped[str | None] = mapped_column(String(50))
    locked_post_submit_checker_policy_id: Mapped[str | None] = mapped_column(String(36))
    locked_post_submit_checker_policy_version: Mapped[str | None] = mapped_column(String(50))
    locked_post_submit_checker_policy_hash: Mapped[str | None] = mapped_column(String(71))
    locked_post_submit_checker_policy_body: Mapped[dict | None] = mapped_column(JSON)
    locked_review_policy_version: Mapped[str | None] = mapped_column(String(50))
    locked_revision_policy_version: Mapped[str | None] = mapped_column(String(50))
    locked_payment_policy_version: Mapped[str | None] = mapped_column(String(50))
    locked_guide_source_snapshot_id: Mapped[str | None] = mapped_column(String(36))
    locked_guide_source_snapshot_hash: Mapped[str | None] = mapped_column(String(71))
    locked_effective_project_submission_artifact_policy_id: Mapped[str | None] = mapped_column(
        String(36),
    )
    locked_effective_project_submission_artifact_policy_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    locked_pre_submit_checker_policy_id: Mapped[str | None] = mapped_column(String(36))
    locked_pre_submit_checker_bundle_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(500))
    source_payload_hash: Mapped[str | None] = mapped_column(String(128))
    import_batch_id: Mapped[str | None] = mapped_column(String(100))
    external_task_id: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str | None] = mapped_column(String(100))
    difficulty: Mapped[str | None] = mapped_column(String(50))
    skill_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    estimated_time_minutes: Mapped[int | None] = mapped_column(Integer)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(20))
    payout_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    rejection_criteria: Mapped[str | None] = mapped_column(Text)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    assignments: Mapped[list[TaskAssignment]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        foreign_keys="Submission.task_id",
    )


class TaskAssignment(Base):
    """Contributor assignment record for a task claim."""

    __tablename__ = "task_assignments"
    __table_args__ = (
        Index(
            "uq_task_assignments_one_active_per_task",
            "task_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id"),
        nullable=False,
        index=True,
    )
    contributor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("actor_profiles.id"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)

    task: Mapped[WorkstreamTask] = relationship(back_populates="assignments")


class Submission(Base):
    """Immutable contributor submission packet version for a task."""

    __tablename__ = "submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "locked_guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_submissions_task_locked_guide",
        ),
        ForeignKeyConstraint(
            [
                "task_id",
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_post_submit_checker_policy_id",
                "workstream_tasks.locked_post_submit_checker_policy_version",
                "workstream_tasks.locked_post_submit_checker_policy_hash",
            ],
            name="fk_submissions_task_locked_post_submit_policy_hash",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_review_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_review_policy_version"],
            name="fk_submissions_task_locked_review_policy",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_revision_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_revision_policy_version"],
            name="fk_submissions_task_locked_revision_policy",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_payment_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_payment_policy_version"],
            name="fk_submissions_task_locked_payment_policy",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_guide_source_snapshot_id",
                "workstream_tasks.locked_guide_source_snapshot_hash",
            ],
            name="fk_submissions_task_locked_source_snapshot_hash",
        ),
        ForeignKeyConstraint(
            [
                "task_id",
                "locked_effective_project_submission_artifact_policy_id",
                "locked_effective_project_submission_artifact_policy_hash",
            ],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_effective_project_submission_artifact_policy_id",
                "workstream_tasks.locked_effective_project_submission_artifact_policy_hash",
            ],
            name="fk_submissions_task_locked_effective_policy_hash",
        ),
        ForeignKeyConstraint(
            ["task_id", "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_pre_submit_checker_policy_id",
                "workstream_tasks.locked_pre_submit_checker_bundle_hash",
            ],
            name="fk_submissions_task_locked_pre_submit_checker_hash",
        ),
        ForeignKeyConstraint(
            ["locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_submissions_locked_source_snapshot_hash",
        ),
        ForeignKeyConstraint(
            [
                "locked_effective_project_submission_artifact_policy_id",
                "locked_effective_project_submission_artifact_policy_hash",
            ],
            [
                "effective_project_submission_artifact_policies.id",
                "effective_project_submission_artifact_policies.effective_policy_hash",
            ],
            name="fk_submissions_locked_effective_policy_hash",
        ),
        ForeignKeyConstraint(
            ["locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
            ["pre_submit_checker_policies.id", "pre_submit_checker_policies.compiled_bundle_hash"],
            name="fk_submissions_locked_pre_submit_checker_hash",
        ),
        ForeignKeyConstraint(
            [
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            ["checker_policies.id", "checker_policies.guide_version", "checker_policies.policy_hash"],
            name="fk_submissions_locked_post_submit_policy_hash",
        ),
        UniqueConstraint("task_id", "version", name="uq_submissions_task_version"),
        UniqueConstraint("id", "version", name="uq_submissions_id_version"),
        UniqueConstraint(
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
            name="uq_submissions_id_locked_post_submit_policy_hash",
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
            "ix_submissions_locked_source_snapshot",
            "locked_guide_source_snapshot_id",
        ),
        Index(
            "ix_submissions_locked_effective_policy_hash",
            "locked_effective_project_submission_artifact_policy_hash",
        ),
        Index(
            "ix_submissions_locked_pre_submit_checker_hash",
            "locked_pre_submit_checker_bundle_hash",
        ),
        Index(
            "ix_submissions_locked_post_submit_policy_hash",
            "locked_post_submit_checker_policy_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("workstream_tasks.id"), nullable=False, index=True)
    contributor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("actor_profiles.id"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    package_uri: Mapped[str | None] = mapped_column(String(1000))
    package_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_hash_manifest: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    worker_attestation: Mapped[str] = mapped_column(Text, nullable=False)
    locked_guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
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
    locked_guide_source_snapshot_id: Mapped[str | None] = mapped_column(String(36))
    locked_guide_source_snapshot_hash: Mapped[str | None] = mapped_column(String(71))
    locked_effective_project_submission_artifact_policy_id: Mapped[str | None] = mapped_column(
        String(36),
    )
    locked_effective_project_submission_artifact_policy_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    locked_pre_submit_checker_policy_id: Mapped[str | None] = mapped_column(String(36))
    locked_pre_submit_checker_bundle_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id"),
        nullable=True,
        index=True,
    )

    task: Mapped[WorkstreamTask] = relationship(
        back_populates="submissions",
        foreign_keys=[task_id],
    )
    evidence_items: Mapped[list[EvidenceItem]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class EvidenceItem(Base):
    """Evidence reference bound to one submission version."""

    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    uri: Mapped[str | None] = mapped_column(String(1000))
    hash: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped[Submission] = relationship(back_populates="evidence_items")


class AuditEvent(Base):
    """Shared append-only lifecycle and authority audit evidence."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_subject: Mapped[str | None] = mapped_column(String(200))
    external_issuer: Mapped[str | None] = mapped_column(String(200))
    actor_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    claim_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    auth_source: Mapped[str] = mapped_column(String(30), nullable=False)
    is_dev_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    event_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_domain: Mapped[str] = mapped_column(
        String(24), nullable=False, default="legacy_lifecycle", server_default="legacy_lifecycle"
    )
    event_version: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_ref_kind: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    correlation_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    target_actor_ref_kind: Mapped[str | None] = mapped_column(String(32))
    target_actor_ref: Mapped[str | None] = mapped_column(String(100))
    matched_grant_id: Mapped[str | None] = mapped_column(String(100))
    permission_id: Mapped[str | None] = mapped_column(String(120))
    action_id: Mapped[str | None] = mapped_column(String(160))
    project_id: Mapped[str | None] = mapped_column(String(36))
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    target_ref_kind: Mapped[str | None] = mapped_column(String(32))
    target_ref_id: Mapped[str | None] = mapped_column(String(100))
    denial_code: Mapped[str | None] = mapped_column(String(80))
    idempotency_reference: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    invalidation_cause_event_id: Mapped[str | None] = mapped_column(String(36))
    invalidation_target_kind: Mapped[str | None] = mapped_column(String(32))
    invalidation_target_ref: Mapped[str | None] = mapped_column(String(100))
    before_facts: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    after_facts: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
