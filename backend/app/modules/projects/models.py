"""SQLAlchemy models for projects, guides, and guide-bound policies."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Project(Base):
    """Project container that owns guide versions and shared payout defaults."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    guides: Mapped[list[ProjectGuide]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectGuide(Base):
    """Versioned project guide that defines task and submission expectations."""

    __tablename__ = "project_guides"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_guides_project_version"),
        Index(
            "uq_project_guides_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    required_task_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    required_submission_fields: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    task_instructions: Mapped[str | None] = mapped_column(Text)
    output_requirements: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    rejection_criteria: Mapped[str | None] = mapped_column(Text)
    reviewer_rubric: Mapped[str | None] = mapped_column(Text)
    forbidden_actions: Mapped[str | None] = mapped_column(Text)
    required_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    difficulty_scale: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estimated_time_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    common_rejection_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_policy: Mapped[dict | None] = mapped_column(JSON)
    unacceptable_work_policy: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="guides")


class CheckerPolicy(Base):
    """Checker requirements attached to a project guide version."""

    __tablename__ = "checker_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_checker_policies_project_guide",
        ),
        UniqueConstraint("project_id", "guide_version", name="uq_checker_policies_project_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    required_checkers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warning_checkers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    blocking_severities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewPolicy(Base):
    """Review rules attached to a project guide version."""

    __tablename__ = "review_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_review_policies_project_guide",
        ),
        UniqueConstraint("project_id", "guide_version", name="uq_review_policies_project_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    requires_second_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_decisions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    minimum_finding_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevisionPolicy(Base):
    """Revision-loop rules attached to a project guide version."""

    __tablename__ = "revision_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_revision_policies_project_guide",
        ),
        UniqueConstraint(
            "project_id",
            "guide_version",
            name="uq_revision_policies_project_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    max_revision_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_reject_after_limit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allowed_resubmission_states: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    reviewer_reassignment_rule: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentPolicy(Base):
    """Payment rules attached to a project guide version."""

    __tablename__ = "payment_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_payment_policies_project_guide",
        ),
        UniqueConstraint("project_id", "guide_version", name="uq_payment_policies_project_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(20))
    payout_type: Mapped[str | None] = mapped_column(String(50))
    revision_payment_rule: Mapped[str | None] = mapped_column(Text)
    rejection_payment_rule: Mapped[str | None] = mapped_column(Text)
    accepted_payment_rule: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceSnapshot(Base):
    """Immutable bundle of guide material evaluated for one guide version."""

    __tablename__ = "guide_source_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_guide_source_snapshots_project_guide",
        ),
        UniqueConstraint("id", "bundle_hash", name="uq_guide_source_snapshots_id_hash"),
        UniqueConstraint(
            "project_id",
            "guide_version",
            "bundle_hash",
            name="uq_guide_source_snapshots_project_version_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    bundle_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    captured_by: Mapped[str] = mapped_column(String(100), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceSnapshotItem(Base):
    """Sanitized source item included in a guide-source snapshot bundle."""

    __tablename__ = "guide_source_snapshot_items"
    __table_args__ = (
        UniqueConstraint(
            "source_snapshot_id",
            "source_kind",
            "durable_ref",
            name="uq_guide_source_snapshot_items_snapshot_kind_ref",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    durable_ref: Mapped[str] = mapped_column(Text, nullable=False)
    ingestion_adapter: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    content_cid: Mapped[str | None] = mapped_column(String(200))
    media_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSufficiencyReport(Base):
    """Workstream assessment of whether a guide snapshot is usable."""

    __tablename__ = "guide_sufficiency_reports"
    __table_args__ = (
        CheckConstraint(
            "status in ('passed', 'blocked', 'passed_with_warnings')",
            name="ck_guide_sufficiency_reports_status",
        ),
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_guide_sufficiency_reports_project_guide",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_guide_sufficiency_reports_source_snapshot_hash",
        ),
        UniqueConstraint(
            "source_snapshot_id",
            name="uq_guide_sufficiency_reports_source_snapshot",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    findings: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    agent_name: Mapped[str | None] = mapped_column(String(100))
    agent_version: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    warnings_acknowledged_by_role: Mapped[str | None] = mapped_column(String(50))
    warnings_acknowledged_by_actor: Mapped[str | None] = mapped_column(String(100))
    warnings_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement_note: Mapped[str | None] = mapped_column(Text)


class SubmissionArtifactPolicy(Base):
    """Workstream-derived machine intake policy for one guide snapshot."""

    __tablename__ = "submission_artifact_policies"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status in ('draft', 'approved', 'superseded')",
            name="ck_submission_artifact_policies_lifecycle_status",
        ),
        CheckConstraint(
            "lifecycle_status != 'approved' or "
            "(approved_by_role in ('admin', 'project_manager') and "
            "approved_by_actor is not null and approved_at is not null)",
            name="ck_submission_artifact_policies_approval_provenance",
        ),
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_submission_artifact_policies_project_guide",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_submission_artifact_policies_source_snapshot_hash",
        ),
        UniqueConstraint(
            "id",
            "policy_hash",
            name="uq_submission_artifact_policies_id_hash",
        ),
        UniqueConstraint(
            "project_id",
            "guide_version",
            "policy_version",
            name="uq_submission_artifact_policies_project_version_policy",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    policy_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    derivation_source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_material_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    derivation_agent_name: Mapped[str | None] = mapped_column(String(100))
    derivation_agent_version: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    approved_by_role: Mapped[str | None] = mapped_column(String(50))
    approved_by_actor: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("submission_artifact_policies.id"),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_summary: Mapped[str | None] = mapped_column(Text)


class EffectiveProjectSubmissionArtifactPolicy(Base):
    """Immutable effective intake policy after merging defaults and project policy."""

    __tablename__ = "effective_project_submission_artifact_policies"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status in ('approved', 'superseded')",
            name="ck_effective_psap_lifecycle_status",
        ),
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_effective_project_submission_artifact_policies_project_guide",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_effective_psap_source_snapshot_hash",
        ),
        ForeignKeyConstraint(
            ["submission_artifact_policy_id", "submission_artifact_policy_hash"],
            ["submission_artifact_policies.id", "submission_artifact_policies.policy_hash"],
            name="fk_effective_psap_submission_policy_hash",
        ),
        UniqueConstraint(
            "id",
            "effective_policy_hash",
            name="uq_effective_project_submission_artifact_policies_id_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    submission_artifact_policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    submission_artifact_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="approved", index=True)
    merge_algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    effective_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    supersedes_effective_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("effective_project_submission_artifact_policies.id"),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PreSubmitCheckerPolicy(Base):
    """Project-scoped pre-submit checker bundle contract for one effective policy."""

    __tablename__ = "pre_submit_checker_policies"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status in ('pending_compilation', 'compiled', 'superseded')",
            name="ck_pre_submit_checker_policies_lifecycle_status",
        ),
        CheckConstraint(
            "lifecycle_status != 'compiled' or "
            "(compiler_version is not null and compiled_bundle is not null and "
            "compiled_bundle_hash is not null and "
            "compiled_bundle_hash ~ '^sha256:[0-9a-f]{64}$')",
            name="ck_pre_submit_checker_policies_compiled_fields",
        ),
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_pre_submit_checker_policies_project_guide",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_pre_submit_checker_policies_source_snapshot_hash",
        ),
        ForeignKeyConstraint(
            ["effective_policy_id", "effective_policy_hash"],
            [
                "effective_project_submission_artifact_policies.id",
                "effective_project_submission_artifact_policies.effective_policy_hash",
            ],
            name="fk_pre_submit_checker_policies_effective_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    effective_policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    effective_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_compilation",
        index=True,
    )
    compiler_version: Mapped[str | None] = mapped_column(String(50))
    compiled_bundle: Mapped[dict | None] = mapped_column(JSON)
    compiled_bundle_hash: Mapped[str | None] = mapped_column(String(71), index=True)
    checker_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    checker_configs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    supersedes_pre_submit_checker_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("pre_submit_checker_policies.id"),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
