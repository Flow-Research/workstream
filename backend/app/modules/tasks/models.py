"""SQLAlchemy models for task queue, assignment, submissions, and audit events."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    FetchedValue,
    Boolean,
    BigInteger,
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
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class TaskCommandReceipt(Base):
    """TASK-owned immutable success and actor/action-scoped retry reservation."""

    __tablename__ = "task_command_receipts"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        UniqueConstraint("actor_profile_id", "action_id", "idempotency_key", name="uq_task_command_namespace"),
        Index("ix_task_command_receipts_batch_transition_receipt_id", "batch_transition_receipt_id"),
        ForeignKeyConstraint(
            ["assignment_id", "task_id", "contributor_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_task_command_assignment",
        ),
        CheckConstraint(
            "action_id in ('task.claim','task.start','operations.task.start_override',"
            "'project.task.create','project.task.screen','project.task.release')",
            name="task_command_action",
        ),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="task_command_request_digest"),
        CheckConstraint("batch_transition_receipt_id is null or action_id in ('project.task.screen','project.task.release')",
                        name="task_command_batch_transition_action"),
        CheckConstraint(
            "(status='pending' and assignment_id is null and contributor_id is null "
            "and locked_context_hash is null and response is null and committed_at is null) or "
            "(status='committed' and ((action_id in ('task.claim','task.start','operations.task.start_override') "
            "and assignment_id is not null and contributor_id is not null) or "
            "(action_id in ('project.task.create','project.task.screen','project.task.release') "
            "and assignment_id is null and contributor_id is null)) "
            "and locked_context_hash is not null and locked_context_hash ~ '^sha256:[0-9a-f]{64}$' "
            "and response is not null and jsonb_typeof(response)='object' and committed_at is not null)",
            name="task_command_state_shape",
        ),
        CheckConstraint(
            "status='pending' or action_id in ('project.task.create','project.task.screen','project.task.release') "
            "or (action_id='operations.task.start_override' and actor_profile_id<>contributor_id) "
            "or (action_id in ('task.claim','task.start') and actor_profile_id=contributor_id)",
            name="task_command_contributor",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    # Reservation precedes AUTH: defer the FK's implicit actor KEY SHARE lock
    # until after AUTH has acquired its canonical actor lock.
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey(
        "actor_profiles.id", deferrable=True, initially="DEFERRED",
    ))
    action_id: Mapped[str] = mapped_column(String(160))
    idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    request_digest: Mapped[str] = mapped_column(String(71))
    # Existing single-Task/CREATE receipts remain null. Bulk participation is
    # immutable receipt provenance, never an AUTH selector or a mutable Task flag.
    batch_transition_receipt_id: Mapped[UUID | None] = mapped_column(ForeignKey(
        "task_batch_transition_receipts.id", name="fk_task_command_batch_transition",
        ondelete="RESTRICT", deferrable=True, initially="DEFERRED",
    ))
    # Defer TASK custody until after reservation and proposed-task insertion.
    task_id: Mapped[str] = mapped_column(ForeignKey(
        "workstream_tasks.id", name="fk_task_command_task", deferrable=True, initially="DEFERRED",
    ))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    assignment_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    contributor_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_context_hash: Mapped[str | None] = mapped_column(String(71))
    response: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkstreamTask(Base):
    """Task queue record with server-stamped guide and policy context."""

    __tablename__ = "workstream_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["active_submission_operation_id", "id"],
            ["submission_intake_operations.id", "submission_intake_operations.task_id"],
            name="fk_task_active_submission_intake", deferrable=True, initially="DEFERRED",
            use_alter=True,
        ),
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        CheckConstraint(
            "status in ('draft','screening','ready','in_progress','submitted','evaluation_pending','review_pending','needs_revision','accepted')",
            name="status",
        ),
        CheckConstraint(
            "status = 'draft' or locked_contribution_policy_version_id is not null",
            name="contribution_policy_required",
        ),
        CheckConstraint(
            "locked_contribution_policy_version_id is null or locked_guide_version is not null",
            name="contribution_policy_guide_required",
        ),
        ForeignKeyConstraint(
            ["project_id", "locked_guide_version", "locked_contribution_policy_version_id"],
            ["project_guides.project_id", "project_guides.version",
             "project_guides.contribution_policy_version_id"],
            name="fk_tasks_guide_contribution_policy",
        ),
        CheckConstraint(
            "(locked_review_policy_id is null and locked_review_policy_generation is null "
            "and locked_review_policy_hash is null and locked_revision_policy_id is null "
            "and locked_revision_policy_generation is null and locked_revision_policy_hash is null) "
            "or (locked_review_policy_id is not null and "
            "locked_review_policy_generation is not null and locked_review_policy_hash is not null "
            "and locked_revision_policy_id is not null and "
            "locked_revision_policy_generation is not null and "
            "locked_revision_policy_hash is not null)",
            name="review_revision_policy_lock_shape",
        ),
        CheckConstraint(
            "status = 'draft' or (locked_review_policy_id is not null and "
            "locked_review_policy_generation is not null and locked_review_policy_hash is not null "
            "and locked_revision_policy_id is not null and "
            "locked_revision_policy_generation is not null and "
            "locked_revision_policy_hash is not null)",
            name="review_revision_policy_lock_required",
        ),
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
            [
                "checker_policies.id",
                "checker_policies.guide_version",
                "checker_policies.policy_hash",
            ],
            name="fk_workstream_tasks_locked_post_submit_policy_hash",
        ),
        ForeignKeyConstraint(
            [
                "project_id",
                "locked_guide_version",
                "locked_review_policy_id",
                "locked_review_policy_generation",
                "locked_review_policy_hash",
            ],
            [
                "review_policies.project_id",
                "review_policies.guide_version",
                "review_policies.id",
                "review_policies.policy_generation",
                "review_policies.policy_hash",
            ],
            name="fk_workstream_tasks_locked_review_policy",
        ),
        ForeignKeyConstraint(
            [
                "project_id",
                "locked_guide_version",
                "locked_revision_policy_id",
                "locked_revision_policy_generation",
                "locked_revision_policy_hash",
            ],
            [
                "revision_policies.project_id",
                "revision_policies.guide_version",
                "revision_policies.id",
                "revision_policies.policy_generation",
                "revision_policies.policy_hash",
            ],
            name="fk_workstream_tasks_locked_revision_policy",
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
        UniqueConstraint("id", "project_id", name="uq_workstream_tasks_id_project"),
        UniqueConstraint("project_id", "external_task_id", name="uq_workstream_tasks_project_external_id"),
        UniqueConstraint(
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
            name="uq_workstream_tasks_id_locked_post_submit_policy_hash",
        ),
        UniqueConstraint(
            "id",
            "locked_review_policy_id",
            "locked_review_policy_generation",
            "locked_review_policy_hash",
            name="uq_workstream_tasks_id_locked_review_policy",
        ),
        UniqueConstraint(
            "id",
            "locked_revision_policy_id",
            "locked_revision_policy_generation",
            "locked_revision_policy_hash",
            name="uq_workstream_tasks_id_locked_revision_policy",
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

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    locked_contribution_policy_version_id: Mapped[UUID | None] = mapped_column(Uuid())
    locked_guide_version: Mapped[str | None] = mapped_column(String(50))
    locked_post_submit_checker_policy_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_post_submit_checker_policy_version: Mapped[str | None] = mapped_column(String(50))
    locked_post_submit_checker_policy_hash: Mapped[str | None] = mapped_column(String(71))
    locked_post_submit_checker_policy_body: Mapped[dict | None] = mapped_column(JSON)
    locked_review_policy_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_review_policy_generation: Mapped[int | None] = mapped_column(Integer)
    locked_review_policy_hash: Mapped[str | None] = mapped_column(String(71))
    locked_revision_policy_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_revision_policy_generation: Mapped[int | None] = mapped_column(Integer)
    locked_revision_policy_hash: Mapped[str | None] = mapped_column(String(71))
    locked_guide_source_snapshot_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_guide_source_snapshot_hash: Mapped[str | None] = mapped_column(String(71))
    locked_effective_project_submission_artifact_policy_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
    )
    locked_effective_project_submission_artifact_policy_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    locked_pre_submit_checker_policy_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
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
    difficulty: Mapped[str | None] = mapped_column(String(80))
    skill_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    estimated_time_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    rejection_criteria: Mapped[str | None] = mapped_column(Text)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    active_submission_operation_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # PostgreSQL owns this stamp on every committed change, including raw SQL updates.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )

    assignments: Mapped[list[TaskAssignment]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        foreign_keys="TaskAssignment.task_id",
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
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_assignments_task_project",
        ),
        ForeignKeyConstraint(
            ["submitter_contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_assignments_contribution_project",
        ),
        UniqueConstraint(
            "id", "task_id", "contributor_id", name="uq_task_assignments_id_task_contributor"
        ),
        Index("ix_task_assignments_contributor_updated", "contributor_id", "updated_at", "id"),
        Index(
            "uq_task_assignments_one_active_per_task",
            "task_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submitter_contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id"),
        nullable=False,
        index=True,
    )
    contributor_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("actor_profiles.id"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    # Set once when claim starts work; PostgreSQL guards it against the started task.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # PostgreSQL owns this stamp on every committed change.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        server_onupdate=FetchedValue(),
    )

    task: Mapped[WorkstreamTask] = relationship(back_populates="assignments", foreign_keys=[task_id])


class Submission(Base):
    """Immutable contributor submission packet version for a task."""

    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        CheckConstraint(
            "attempt_status in ('evaluation_pending','review_pending','accepted',"
            "'needs_revision','rejected')",
            name="attempt_status",
        ),
        CheckConstraint(
            "(attempt_status in ('accepted','needs_revision','rejected')) = "
            "(decided_at is not null)",
            name="attempt_decision",
        ),
        CheckConstraint(
            "status_reason is null or (attempt_status='rejected' and "
            "status_reason in ('revision_deadline_expired','revision_limit_reached')) or "
            "(attempt_status='needs_revision' and "
            "status_reason='checker_coverage_incomplete')",
            name="status_reason",
        ),
        Index("ix_submissions_contributor_updated", "contributor_id", "updated_at", "id"),
        ForeignKeyConstraint(
            ["task_assignment_id", "task_id", "contributor_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_submissions_assignment_identity",
        ),
        ForeignKeyConstraint(
            ["locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash"],
            ["review_policies.id", "review_policies.policy_generation", "review_policies.policy_hash"],
            name="fk_submissions_review_policy_lineage",
        ),
        ForeignKeyConstraint(
            ["locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash"],
            ["revision_policies.id", "revision_policies.policy_generation", "revision_policies.policy_hash"],
            name="fk_submissions_revision_policy_lineage",
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
            [
                "checker_policies.id",
                "checker_policies.guide_version",
                "checker_policies.policy_hash",
            ],
            name="fk_submissions_locked_post_submit_policy_hash",
        ),
        UniqueConstraint("task_id", "version", name="uq_submissions_task_version"),
        UniqueConstraint("id", "version", name="uq_submissions_id_version"),
        UniqueConstraint(
            "id", "task_id", "version", name="uq_submissions_id_task_version"
        ),
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
        CheckConstraint(
            "(submission_bundle_admission_id is null "
            "and artifact_binding_id is null and artifact_content_id is null) or "
            "(submission_bundle_admission_id is not null "
            "and artifact_binding_id is not null and artifact_content_id is not null)",
            name="artifact_lineage_shape",
        ),
        CheckConstraint(
            "(selected_post_submit_policy_sha256 is null and "
            "selected_post_submit_policy_body is null) or "
            "(selected_post_submit_policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "jsonb_typeof(selected_post_submit_policy_body)='object')",
            name="selected_post_submit_policy",
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

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    task_assignment_id: Mapped[str] = mapped_column(
        ForeignKey("task_assignments.id"), nullable=False, index=True
    )
    submission_bundle_admission_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), unique=True, index=True
    )
    artifact_binding_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), unique=True)
    artifact_content_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id"), nullable=False, index=True
    )
    contributor_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("actor_profiles.id"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Intake liveness fact used by evaluation, routing and replay guards; always "submitted".
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", index=True)
    # Outcome of this attempt, written by the deciding owner and guarded by its evidence.
    attempt_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="evaluation_pending"
    )
    status_reason: Mapped[str | None] = mapped_column(String(40))
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_onupdate=FetchedValue()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        server_onupdate=FetchedValue(),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    package_uri: Mapped[str | None] = mapped_column(String(1000))
    package_hash: Mapped[str | None] = mapped_column(String(128))
    artifact_hash_manifest: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    worker_attestation: Mapped[str] = mapped_column(Text, nullable=False)
    locked_guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_post_submit_checker_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    locked_post_submit_checker_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    locked_post_submit_checker_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_post_submit_checker_policy_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    selected_post_submit_policy_sha256: Mapped[str | None] = mapped_column(String(71))
    selected_post_submit_policy_body: Mapped[dict | None] = mapped_column(JSONB)
    locked_review_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    locked_review_policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_review_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_revision_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    locked_revision_policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_revision_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_guide_source_snapshot_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_guide_source_snapshot_hash: Mapped[str | None] = mapped_column(String(71))
    locked_effective_project_submission_artifact_policy_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
    )
    locked_effective_project_submission_artifact_policy_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    locked_pre_submit_checker_policy_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    locked_pre_submit_checker_bundle_hash: Mapped[str | None] = mapped_column(
        String(71),
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
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
    __table_args__ = (CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
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
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        Index(
            "uq_audit_assignment_release_cause",
            text("(event_payload->'references'->>'assignment_id')"),
            text("(event_payload->'references'->>'authority_invalidation_event_id')"),
            unique=True,
            postgresql_where=text("event_type = 'TaskAssignmentAuthorityRevoked'"),
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
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
    project_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    target_ref_kind: Mapped[str | None] = mapped_column(String(32))
    target_ref_id: Mapped[str | None] = mapped_column(String(100))
    denial_code: Mapped[str | None] = mapped_column(String(80))
    idempotency_reference: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    invalidation_cause_event_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    invalidation_target_kind: Mapped[str | None] = mapped_column(String(32))
    invalidation_target_ref: Mapped[str | None] = mapped_column(String(100))
    before_facts: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    after_facts: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class SubmissionDispatch(Base):
    """One committed creation result; CHECKERS and outbox retain operational state."""

    __tablename__ = "submission_dispatches"
    __table_args__ = (
        ForeignKeyConstraint(["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["assignment_id", "task_id", "contributor_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"], ondelete="RESTRICT"),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$' and "
                        "evaluation_request_digest ~ '^sha256:[0-9a-f]{64}$'", name="sha256_shapes"),
        CheckConstraint("(submission_version > 0 and creation_kind = 'initial' and creation_status = 'in_progress' "
                        "and checker_remediation_manifest_id is null) "
                        "or (submission_version > 1 and creation_kind = 'checker_remediation' "
                        "and creation_status = 'needs_revision' and checker_remediation_manifest_id is not null)",
                        name="creation_shape"),
        CheckConstraint("creation_decision_id <> binding_decision_id", name="distinct_authority"),
    )

    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    contributor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    admission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("submission_bundle_admissions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    artifact_binding_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("artifact_bindings.id", ondelete="RESTRICT"), nullable=False, unique=True)
    artifact_content_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("artifact_contents.id", ondelete="RESTRICT"), nullable=False)
    creation_decision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False, unique=True)
    binding_decision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False, unique=True)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    creation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    creation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    checker_remediation_manifest_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("task_post_submit_routing_manifests.id", ondelete="RESTRICT",
                           name="fk_submission_dispatches_checker_remediation_manifest")
    )
    evaluation_request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, unique=True)
    evaluation_request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    evaluation_attempt_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("checker_runs.id", ondelete="RESTRICT"), nullable=False, unique=True)
    evaluation_result_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, unique=True)
    evaluation_event_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("outbox_events.event_id", ondelete="RESTRICT"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def result(self):
        """Expose only committed identities, never private request or policy bodies."""
        from app.modules.tasks.api import SubmissionCreationResult
        return SubmissionCreationResult(**{
            name: UUID(str(getattr(self, name))) if name.endswith("_id") else getattr(self, name)
            for name in SubmissionCreationResult.__dataclass_fields__
        })


class TaskImportBatch(Base):
    """One exact received JSON file and its immutable ordered creation result."""

    __tablename__ = "task_import_batches"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        UniqueConstraint("project_id", "sha256", "byte_count", name="uq_task_import_batch_file"),
        UniqueConstraint("id", "project_id", name="uq_task_import_batch_project"),
        UniqueConstraint("creation_command_receipt_id", name="uq_task_import_batch_creation_command"),
        ForeignKeyConstraint(
            ["source_id", "project_id", "sha256", "byte_count", "media_type"],
            ["artifact_task_import_sources.id", "artifact_task_import_sources.project_id",
             "artifact_task_import_sources.sha256", "artifact_task_import_sources.byte_count",
             "artifact_task_import_sources.media_type"],
            name="fk_task_import_batch_source", ondelete="RESTRICT", deferrable=True, initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_task_import_batch_actor_link", ondelete="RESTRICT", deferrable=True, initially="DEFERRED",
        ),
        CheckConstraint("sha256 ~ '^sha256:[0-9a-f]{64}$'", name="source_hash"),
        CheckConstraint("source_operation_identity ~ '^sha256:[0-9a-f]{64}$'", name="source_operation"),
        CheckConstraint("manifest_digest ~ '^sha256:[0-9a-f]{64}$'", name="manifest_hash"),
        CheckConstraint("byte_count between 1 and 8388608 and row_count between 1 and 500", name="bounds"),
        CheckConstraint("media_type='application/json' and schema_version='workstream.task_import.v1' "
                        "and mapping_version='workstream.task_import.draft_mapping.v1'", name="format"),
        CheckConstraint(
            "(status='pending' and response is null and authorization_decision_id is null and committed_at is null) or "
            "(status='committed' and response is not null and jsonb_typeof(response)='object' "
            "and authorization_decision_id is not null and committed_at is not null "
            "and put_attempt_id is not null and content_id is not null and replica_id is not null "
            "and verification_job_id is not null and verification_generation is not null "
            "and verification_generation>0 and verification_receipt_id is not null "
            "and ((operation_receipt_id is not null and observation_receipt_id is null) "
            "or (operation_receipt_id is null and observation_receipt_id is not null)))", name="state_shape",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    source_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    creation_command_receipt_id: Mapped[str] = mapped_column(ForeignKey(
        "task_import_batch_command_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED",
    ))
    sha256: Mapped[str] = mapped_column(String(71))
    byte_count: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(255), default="application/json")
    schema_version: Mapped[str] = mapped_column(String(80))
    mapping_version: Mapped[str] = mapped_column(String(80))
    manifest_digest: Mapped[str] = mapped_column(String(71))
    row_count: Mapped[int] = mapped_column(Integer)
    metadata_label: Mapped[str | None] = mapped_column(String(255))
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    authorization_decision_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    response: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_operation_identity: Mapped[str] = mapped_column(String(71))
    put_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    content_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_contents.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    replica_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_replicas.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    verification_job_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_verification_jobs.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    verification_generation: Mapped[int | None] = mapped_column(BigInteger)
    verification_receipt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_verification_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    operation_receipt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_operation_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    observation_receipt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_put_observation_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))


class TaskImportBatchMember(Base):
    """Append-only document row bound to its canonical Task creation receipt."""

    __tablename__ = "task_import_batch_members"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        UniqueConstraint("task_id", name="uq_task_import_member_task"),
        UniqueConstraint("batch_id", "row_index", name="uq_task_import_member_row"),
        UniqueConstraint("project_id", "external_task_id", name="uq_task_import_member_external_id"),
        UniqueConstraint("task_command_receipt_id", name="uq_task_import_member_creation"),
        ForeignKeyConstraint(["batch_id", "project_id"], ["task_import_batches.id", "task_import_batches.project_id"],
                             name="fk_task_import_member_batch", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"],
                             name="fk_task_import_member_task", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        CheckConstraint("row_index between 0 and 499", name="row_index"),
        CheckConstraint("row_digest ~ '^sha256:[0-9a-f]{64}$'", name="row_hash"),
        CheckConstraint("jsonb_typeof(response)='object'", name="response_shape"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    row_index: Mapped[int] = mapped_column(Integer)
    external_task_id: Mapped[str] = mapped_column(String(200))
    row_digest: Mapped[str] = mapped_column(String(71))
    create_idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    task_command_receipt_id: Mapped[UUID] = mapped_column(ForeignKey("task_command_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    authorization_decision_id: Mapped[str] = mapped_column(ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskImportBatchCommandReceipt(Base):
    """Actor/action/key retry custody with independently verified selected-source ancestry."""

    __tablename__ = "task_import_batch_command_receipts"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        UniqueConstraint("actor_profile_id", "action_id", "idempotency_key", name="uq_task_import_command_namespace"),
        ForeignKeyConstraint(["batch_id", "project_id"], ["task_import_batches.id", "task_import_batches.project_id"],
                             name="fk_task_import_command_batch", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["identity_link_id", "actor_profile_id"],
                             ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
                             name="fk_task_import_command_actor_link", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(
            ["source_id", "project_id", "sha256", "byte_count", "media_type"],
            ["artifact_task_import_sources.id", "artifact_task_import_sources.project_id",
             "artifact_task_import_sources.sha256", "artifact_task_import_sources.byte_count",
             "artifact_task_import_sources.media_type"],
            name="fk_task_import_command_source", ondelete="RESTRICT", deferrable=True, initially="DEFERRED",
        ),
        CheckConstraint("action_id='project.task.import'", name="action"),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_hash"),
        CheckConstraint("sha256 ~ '^sha256:[0-9a-f]{64}$' and source_operation_identity ~ '^sha256:[0-9a-f]{64}$'", name="source_hash"),
        CheckConstraint("byte_count between 1 and 8388608 and media_type='application/json'", name="bounds"),
        CheckConstraint(
            "(status='pending' and response is null and authorization_decision_id is null and committed_at is null) or "
            "(status='committed' and batch_id is not null and response is not null and jsonb_typeof(response)='object' "
            "and authorization_decision_id is not null and committed_at is not null "
            "and put_attempt_id is not null and content_id is not null and replica_id is not null "
            "and verification_job_id is not null and verification_generation is not null "
            "and verification_generation>0 and verification_receipt_id is not null "
            "and ((operation_receipt_id is not null and observation_receipt_id is null) "
            "or (operation_receipt_id is null and observation_receipt_id is not null)))", name="state_shape",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    action_id: Mapped[str] = mapped_column(String(160))
    idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    request_digest: Mapped[str] = mapped_column(String(71))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    source_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    sha256: Mapped[str] = mapped_column(String(71))
    byte_count: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(255), default="application/json")
    batch_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    authorization_decision_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    response: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_operation_identity: Mapped[str] = mapped_column(String(71))
    put_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    content_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_contents.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    replica_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_replicas.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    verification_job_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_verification_jobs.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    verification_generation: Mapped[int | None] = mapped_column(BigInteger)
    verification_receipt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_verification_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    operation_receipt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_operation_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
    observation_receipt_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_put_observation_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"))
