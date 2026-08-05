"""SQLAlchemy models for projects, guides, and guide-bound policies."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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


class Project(Base):
    """Project container that owns guide versions."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
            "and created_by_admin_role_grant_id is null and creation_scope_type is null "
            "and creation_action_id is null and authorization_decision_event_id is null) or "
            "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
            "and created_by_admin_role_grant_id is not null and creation_scope_type = 'system' "
            "and creation_action_id = 'project.create' and authorization_decision_event_id is not null)",
            name="creation_authority_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
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
class ProjectCreateIdempotencyRecord(Base):
    """Project-owned reservation and replay state for one project creation."""

    __tablename__ = "project_create_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_project_create_replay_namespace",
        ),
        UniqueConstraint("operation_id", name="uq_project_create_operation_identity"),
        UniqueConstraint("project_id", name="uq_project_create_project_identity"),
        CheckConstraint("action_id = 'project.create'", name="ck_project_create_action"),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_project_create_request_digest",
        ),
        CheckConstraint("operation_generation = 1", name="ck_project_create_generation"),
        CheckConstraint("status in ('pending','committed')", name="ck_project_create_status"),
        CheckConstraint(
            "(status = 'pending' and committed_at is null) or "
            "(status = 'committed' and committed_at is not null)",
            name="ck_project_create_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"))
    identity_link_id: Mapped[str] = mapped_column(ForeignKey("actor_identity_links.id"))
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuideMutationIdempotencyRecord(Base):
    """Replay custody for one authorized guide-metadata mutation."""

    __tablename__ = "guide_mutation_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_guide_mutation_replay_namespace",
        ),
        UniqueConstraint("operation_id", name="uq_guide_mutation_operation_identity"),
        CheckConstraint(
            "action_id in ('project.guide.create','project.guide.update',"
            "'project.guide_source_snapshot.create')",
            name="ck_guide_mutation_action",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_mutation_request_digest",
        ),
        CheckConstraint(
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_mutation_resource_context_digest",
        ),
        CheckConstraint("operation_generation > 0", name="ck_guide_mutation_generation"),
        CheckConstraint("status in ('pending','committed')", name="ck_guide_mutation_status"),
        CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null "
            "and setup_run_id is null) or "
            "(status='committed' and response_json is not null and committed_at is not null)",
            name="ck_guide_mutation_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"))
    identity_link_id: Mapped[str] = mapped_column(ForeignKey("actor_identity_links.id"))
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_context_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    response_json: Mapped[dict | None] = mapped_column(JSON)
    setup_run_id: Mapped[str | None] = mapped_column(ForeignKey("project_setup_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuideSufficiencyMutationIdempotencyRecord(Base):
    """Replay custody for one authorized guide-sufficiency mutation."""

    __tablename__ = "guide_sufficiency_mutation_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_profile_id",
            "idempotency_key",
            name="uq_sufficiency_mutation_replay_namespace",
        ),
        UniqueConstraint("operation_id", name="uq_sufficiency_mutation_operation_identity"),
        CheckConstraint(
            "action_id in ('project.guide_sufficiency_report.create',"
            "'project.guide_sufficiency.run',"
            "'project.guide_sufficiency.warnings.acknowledge')",
            name="ck_sufficiency_mutation_action",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_sufficiency_mutation_digests",
        ),
        CheckConstraint("setup_generation > 0", name="ck_sufficiency_mutation_generation"),
        CheckConstraint("status in ('pending','committed')", name="ck_sufficiency_mutation_status"),
        CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null) or "
            "(status='committed' and response_json is not null and committed_at is not null "
            "and ((action_id='project.guide_sufficiency.run' "
            "and (setup_run_id is not null or report_id is not null)) "
            "or (action_id<>'project.guide_sufficiency.run' and report_id is not null)))",
            name="ck_sufficiency_mutation_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"), nullable=False)
    identity_link_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identity_links.id"), nullable=False
    )
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_context_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"), nullable=False
    )
    report_id: Mapped[str | None] = mapped_column(ForeignKey("guide_sufficiency_reports.id"))
    setup_run_id: Mapped[str | None] = mapped_column(ForeignKey("project_setup_runs.id"))
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    response_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubmissionPolicyMutationIdempotencyRecord(Base):
    """Replay custody for one authorized submission-policy mutation."""

    __tablename__ = "submission_policy_mutation_idempotency_records"
    __table_args__ = (
        Index(
            "uq_submission_policy_human_replay_namespace",
            "actor_profile_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("service_identity is null"),
        ),
        Index(
            "uq_submission_policy_service_replay_namespace",
            "actor_profile_id",
            "setup_run_id",
            "setup_generation",
            "setup_task_id",
            "correlation_id",
            "action_id",
            unique=True,
            postgresql_where=text("service_identity is not null"),
        ),
        Index(
            "uq_submission_policy_committed_policy_action",
            "committed_policy_id",
            "action_id",
            unique=True,
            postgresql_where=text("status='committed'"),
        ),
        UniqueConstraint("operation_id", name="uq_submission_policy_operation_identity"),
        CheckConstraint(
            "action_id in ('project.submission_artifact_policy.create',"
            "'project.submission_artifact_policy.derive',"
            "'project.submission_artifact_policy.update',"
            "'project.submission_artifact_policy.approve')",
            name="ck_submission_policy_mutation_action",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_submission_policy_mutation_digests",
        ),
        CheckConstraint("setup_generation > 0", name="ck_submission_policy_generation"),
        CheckConstraint(
            "(service_identity is null and idempotency_key is not null "
            "and setup_run_id is null and setup_task_id is null and correlation_id is null) or "
            "(service_identity is not null "
            "and service_identity = 'workstream.project.setup' and idempotency_key is null "
            "and action_id = 'project.submission_artifact_policy.derive' "
            "and setup_run_id is not null and setup_task_id is not null "
            "and correlation_id is not null)",
            name="ck_submission_policy_replay_principal_shape",
        ),
        CheckConstraint(
            "status in ('pending','committed')", name="ck_submission_policy_replay_status"
        ),
        CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null "
            "and committed_policy_id is null and committed_effective_policy_id is null "
            "and committed_pre_submit_policy_id is null) or "
            "(status='committed' and response_json is not null and committed_at is not null "
            "and committed_policy_id is not null and "
            "((action_id='project.submission_artifact_policy.approve' "
            "and committed_effective_policy_id is not null "
            "and committed_pre_submit_policy_id is not null) or "
            "(action_id<>'project.submission_artifact_policy.approve' "
            "and committed_effective_policy_id is null "
            "and committed_pre_submit_policy_id is null)))",
            name="ck_submission_policy_replay_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"), nullable=False)
    identity_link_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identity_links.id"), nullable=False
    )
    service_identity: Mapped[str | None] = mapped_column(String(160))
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[UUID | None] = mapped_column(Uuid())
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_context_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_context_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"), nullable=False
    )
    policy_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_run_id: Mapped[str | None] = mapped_column(ForeignKey("project_setup_runs.id"))
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    setup_task_id: Mapped[UUID | None] = mapped_column(Uuid())
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid())
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    response_json: Mapped[dict | None] = mapped_column(JSON)
    committed_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("submission_artifact_policies.id")
    )
    committed_effective_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("effective_project_submission_artifact_policies.id")
    )
    committed_pre_submit_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("pre_submit_checker_policies.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyMutationIdempotencyRecord(Base):
    """Replay custody for one guide-bound policy replacement."""

    __tablename__ = "policy_mutation_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_policy_mutation_replay_namespace",
        ),
        UniqueConstraint("operation_id", name="uq_policy_mutation_operation_identity"),
        Index(
            "ix_policy_mutation_custody_lookup",
            "policy_id",
            "action_id",
            "policy_generation",
            "status",
        ),
        CheckConstraint(
            "action_id in ('project.review_policy.update','project.revision_policy.update')",
            name="ck_policy_mutation_action",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "policy_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_policy_mutation_digests",
        ),
        CheckConstraint("policy_generation > 0", name="ck_policy_mutation_generation"),
        CheckConstraint("status in ('pending','committed')", name="ck_policy_mutation_status"),
        CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null) or "
            "(status='committed' and response_json is not null and committed_at is not null)",
            name="ck_policy_mutation_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"))
    identity_link_id: Mapped[str] = mapped_column(ForeignKey("actor_identity_links.id"))
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_context_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(36), nullable=False)
    policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    response_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectGuide(Base):
    """Versioned human-facing project guide material."""

    __tablename__ = "project_guides"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_guides_project_version"),
        CheckConstraint(
            "((selected_review_policy_id is null and "
            "selected_review_policy_generation is null and selected_review_policy_hash is null "
            ") or (selected_review_policy_id is not null and "
            "selected_review_policy_generation is not null and "
            "selected_review_policy_hash is not null)) and "
            "((selected_revision_policy_id is null and "
            "selected_revision_policy_generation is null and "
            "selected_revision_policy_hash is null) or "
            "(selected_revision_policy_id is not null and "
            "selected_revision_policy_generation is not null and "
            "selected_revision_policy_hash is not null))",
            name="policy_selection_shape",
        ),
        CheckConstraint(
            "status not in ('active','superseded') or "
            "(selected_review_policy_id is not null and "
            "selected_review_policy_generation is not null and "
            "selected_review_policy_hash is not null and "
            "selected_revision_policy_id is not null and "
            "selected_revision_policy_generation is not null and "
            "selected_revision_policy_hash is not null)",
            name="active_policy_selection_required",
        ),
        ForeignKeyConstraint(
            [
                "project_id",
                "version",
                "selected_review_policy_id",
                "selected_review_policy_generation",
                "selected_review_policy_hash",
            ],
            [
                "review_policies.project_id",
                "review_policies.guide_version",
                "review_policies.id",
                "review_policies.policy_generation",
                "review_policies.policy_hash",
            ],
            name="fk_project_guides_selected_review_policy",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            [
                "project_id",
                "version",
                "selected_revision_policy_id",
                "selected_revision_policy_generation",
                "selected_revision_policy_hash",
            ],
            [
                "revision_policies.project_id",
                "revision_policies.guide_version",
                "revision_policies.id",
                "revision_policies.policy_generation",
                "revision_policies.policy_hash",
            ],
            name="fk_project_guides_selected_revision_policy",
            use_alter=True,
        ),
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
    change_summary: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    mutation_generation: Mapped[int | None] = mapped_column(Integer)
    last_mutated_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    last_mutated_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    last_mutated_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    last_mutation_scope_type: Mapped[str | None] = mapped_column(String(16))
    last_mutation_scope_project_id: Mapped[str | None] = mapped_column(String(36))
    last_mutation_action_id: Mapped[str | None] = mapped_column(String(160))
    last_authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_review_policy_id: Mapped[str | None] = mapped_column(String(36))
    selected_review_policy_generation: Mapped[int | None] = mapped_column(Integer)
    selected_review_policy_hash: Mapped[str | None] = mapped_column(String(71))
    selected_revision_policy_id: Mapped[str | None] = mapped_column(String(36))
    selected_revision_policy_generation: Mapped[int | None] = mapped_column(Integer)
    selected_revision_policy_hash: Mapped[str | None] = mapped_column(String(71))

    project: Mapped[Project] = relationship(back_populates="guides")


class PostSubmitCheckerPolicy(Base):
    """Post-submit checker requirements attached to a project guide version."""

    __tablename__ = "checker_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_checker_policies_project_guide",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_checker_policies_source_snapshot_hash",
        ),
        ForeignKeyConstraint(
            ["effective_policy_id", "effective_policy_hash"],
            [
                "effective_project_submission_artifact_policies.id",
                "effective_project_submission_artifact_policies.effective_policy_hash",
            ],
            name="fk_checker_policies_effective_policy_hash",
        ),
        ForeignKeyConstraint(
            ["pre_submit_checker_policy_id", "pre_submit_checker_bundle_hash"],
            [
                "pre_submit_checker_policies.id",
                "pre_submit_checker_policies.compiled_bundle_hash",
            ],
            name="fk_checker_policies_pre_submit_checker_hash",
        ),
        CheckConstraint(
            "policy_hash is null or policy_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="policy_hash_shape",
        ),
        CheckConstraint(
            "lifecycle_status in ('compiled', 'approved', 'superseded')",
            name="lifecycle_status",
        ),
        CheckConstraint(
            """
            lifecycle_status != 'approved'
            or (
                approved_by_role in ('admin', 'project_manager')
                and approved_by_actor is not null
                and approved_at is not null
            )
            """,
            name="approval_provenance",
        ),
        CheckConstraint(
            """
            lifecycle_status != 'superseded'
            or (
                superseded_at is not null
                and superseded_by_role in ('admin', 'project_manager')
                and superseded_by_actor is not null
                and supersession_kind in ('correction_requested', 'upstream_policy_changed')
                and supersession_reason is not null
                and length(btrim(supersession_reason)) > 0
            )
            """,
            name="correction_provenance",
        ),
        Index(
            "uq_checker_policies_current_project_version",
            "project_id",
            "guide_version",
            unique=True,
            postgresql_where=text("lifecycle_status in ('compiled', 'approved')"),
        ),
        UniqueConstraint(
            "id",
            "guide_version",
            "policy_hash",
            name="uq_checker_policies_id_version_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    effective_policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    effective_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    pre_submit_checker_policy_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    pre_submit_checker_bundle_hash: Mapped[str] = mapped_column(
        String(71),
        nullable=False,
        index=True,
    )
    required_checkers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warning_checkers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    blocking_severities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_hash: Mapped[str | None] = mapped_column(String(71), index=True)
    policy_body: Mapped[dict | None] = mapped_column(JSON)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="compiled")
    approved_by_role: Mapped[str | None] = mapped_column(String(50))
    approved_by_actor: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("checker_policies.id"),
        index=True,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_role: Mapped[str | None] = mapped_column(String(50))
    superseded_by_actor: Mapped[str | None] = mapped_column(String(100))
    supersession_kind: Mapped[str | None] = mapped_column(String(50))
    supersession_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
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
        UniqueConstraint(
            "project_id",
            "guide_version",
            "policy_generation",
            name="uq_review_policies_project_version_generation",
        ),
        UniqueConstraint("id", "policy_generation", "policy_hash", name="uq_review_policy_lineage"),
        UniqueConstraint(
            "project_id",
            "guide_version",
            "id",
            "policy_generation",
            "policy_hash",
            name="uq_review_policy_scoped_lineage",
        ),
        CheckConstraint(
            "policy_generation > 0 and policy_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "semantics_status in ('complete','legacy_incomplete')",
            name="review_policy_identity_shape",
        ),
        CheckConstraint(
            "semantics_status='legacy_incomplete' or "
            "(created_by_actor_profile_id is not null and "
            "created_via_identity_link_id is not null and "
            "created_by_admin_role_grant_id is not null and "
            "creation_scope_type in ('system','project') and creation_action_id = "
            "'project.review_policy.update' and authorization_decision_event_id is not null)",
            name="review_policy_authority_shape",
        ),
        CheckConstraint(
            "semantics_status='legacy_incomplete' or "
            "((supersedes_policy_id is null and predecessor_policy_hash is null and "
            "policy_generation=1) or (supersedes_policy_id is not null and "
            "predecessor_policy_hash ~ '^sha256:[0-9a-f]{64}$' and policy_generation>1))",
            name="review_policy_predecessor_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    semantics_status: Mapped[str] = mapped_column(String(24), nullable=False)
    supersedes_policy_id: Mapped[str | None] = mapped_column(ForeignKey("review_policies.id"))
    predecessor_policy_hash: Mapped[str | None] = mapped_column(String(71))
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(String(36))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
    review_preference_window_seconds: Mapped[int | None] = mapped_column(Integer)
    review_lease_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    max_active_review_leases_per_reviewer: Mapped[int | None] = mapped_column(Integer)
    self_review_allowed: Mapped[bool | None] = mapped_column(Boolean)
    reject_policy: Mapped[str | None] = mapped_column(String(32))
    finding_evidence_requirement: Mapped[str | None] = mapped_column(String(32))
    requires_second_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_decisions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    minimum_finding_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
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
            "policy_generation",
            name="uq_revision_policies_project_version_generation",
        ),
        UniqueConstraint(
            "id", "policy_generation", "policy_hash", name="uq_revision_policy_lineage"
        ),
        UniqueConstraint(
            "project_id",
            "guide_version",
            "id",
            "policy_generation",
            "policy_hash",
            name="uq_revision_policy_scoped_lineage",
        ),
        CheckConstraint(
            "policy_generation > 0 and policy_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "semantics_status in ('complete','legacy_incomplete')",
            name="revision_policy_identity_shape",
        ),
        CheckConstraint(
            "semantics_status='legacy_incomplete' or "
            "(created_by_actor_profile_id is not null and "
            "created_via_identity_link_id is not null and "
            "created_by_admin_role_grant_id is not null and "
            "creation_scope_type in ('system','project') and creation_action_id = "
            "'project.revision_policy.update' and authorization_decision_event_id is not null)",
            name="revision_policy_authority_shape",
        ),
        CheckConstraint(
            "semantics_status='legacy_incomplete' or "
            "((supersedes_policy_id is null and predecessor_policy_hash is null and "
            "policy_generation=1) or (supersedes_policy_id is not null and "
            "predecessor_policy_hash ~ '^sha256:[0-9a-f]{64}$' and policy_generation>1))",
            name="revision_policy_predecessor_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    semantics_status: Mapped[str] = mapped_column(String(24), nullable=False)
    supersedes_policy_id: Mapped[str | None] = mapped_column(ForeignKey("revision_policies.id"))
    predecessor_policy_hash: Mapped[str | None] = mapped_column(String(71))
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(String(36))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
    max_revision_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False)
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
            "id",
            "project_id",
            "guide_id",
            name="uq_guide_source_snapshots_exact_lineage",
        ),
        UniqueConstraint(
            "project_id",
            "guide_version",
            "bundle_hash",
            name="uq_guide_source_snapshots_project_version_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    bundle_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    captured_by: Mapped[str] = mapped_column(String(100), nullable=False)
    creation_generation: Mapped[int | None] = mapped_column(Integer)
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(String(36))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GuideSourceSnapshotItem(Base):
    """Sanitized source item included in a guide-source snapshot bundle."""

    __tablename__ = "guide_source_snapshot_items"
    __table_args__ = (
        UniqueConstraint(
            "source_snapshot_id",
            "item_order",
            name="uq_guide_source_snapshot_items_snapshot_order",
        ),
        UniqueConstraint(
            "id",
            "source_snapshot_id",
            name="uq_guide_source_snapshot_items_exact_lineage",
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
    source_label: Mapped[str] = mapped_column(Text, nullable=False)
    ingestion_adapter: Mapped[str] = mapped_column(String(100), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceArtifactIngest(Base):
    """Server-owned prepared-byte facts for one not-yet-bound guide item."""

    __tablename__ = "guide_source_artifact_ingests"
    __table_args__ = (
        CheckConstraint("byte_count >= 0", name="ck_guide_source_artifact_ingests_bytes"),
        CheckConstraint(
            "sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_source_artifact_ingests_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_item_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshot_items.id"), nullable=False, unique=True, index=True
    )
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id"), nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectSetupRun(Base):
    """Non-authoritative ledger for automatic project setup execution."""

    __tablename__ = "project_setup_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ("
            "'queued', "
            "'dispatch_pending', "
            "'enqueue_failed', "
            "'enqueue_identity_mismatch', "
            "'running_sufficiency_agent', "
            "'sufficiency_blocked', "
            "'running_policy_derivation_agent', "
            "'policy_draft_ready', "
            "'running_post_submit_derivation_agent', "
            "'post_submit_setup_blocked', "
            "'post_submit_policy_compiled', "
            "'setup_blocked', "
            "'failed'"
            ")",
            name="ck_project_setup_runs_status",
        ),
        ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_project_setup_runs_project_guide",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_project_setup_runs_source_snapshot_hash",
        ),
        UniqueConstraint(
            "guide_id",
            "setup_generation",
            name="uq_project_setup_runs_guide_generation",
        ),
        UniqueConstraint(
            "id",
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "setup_generation",
            name="uq_project_setup_runs_exact_generation",
        ),
        CheckConstraint("setup_generation > 0", name="ck_project_setup_runs_generation_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(155), index=True)
    continuation_verification_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_verification_jobs.id"), index=True
    )
    continuation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    current_step: Mapped[str] = mapped_column(String(100), nullable=False)
    output_sufficiency_report_id: Mapped[str | None] = mapped_column(
        ForeignKey("guide_sufficiency_reports.id"),
        index=True,
    )
    output_submission_artifact_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("submission_artifact_policies.id"),
        index=True,
    )
    output_post_submit_checker_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("checker_policies.id", name="fk_project_setup_runs_post_submit_checker_policy"),
        index=True,
    )
    post_submit_derivation_summary: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_artifact_incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("guide_source_artifact_incidents.id", use_alter=True), index=True
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    authorized_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    authorized_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    authorized_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    authorization_scope_type: Mapped[str | None] = mapped_column(String(16))
    authorization_scope_project_id: Mapped[str | None] = mapped_column(String(36))
    authorization_action_id: Mapped[str | None] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
        Index(
            "uq_guide_sufficiency_reports_verified_snapshot",
            "source_snapshot_id",
            unique=True,
            postgresql_where=text("project_setup_run_id is not null"),
        ),
        Index(
            "uq_guide_sufficiency_reports_diagnostic_snapshot",
            "source_snapshot_id",
            unique=True,
            postgresql_where=text("project_setup_run_id is null"),
        ),
        CheckConstraint(
            "setup_generation is null or setup_generation > 0",
            name="ck_guide_sufficiency_reports_generation_positive",
        ),
        CheckConstraint(
            "agent_material_sha256 is null or agent_material_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_sufficiency_reports_material_sha256",
        ),
        CheckConstraint(
            "agent_material_byte_count is null or agent_material_byte_count >= 0",
            name="ck_guide_sufficiency_reports_material_size",
        ),
        CheckConstraint(
            "(project_setup_run_id is null and setup_generation is null "
            "and agent_material_sha256 is null and agent_material_byte_count is null) or "
            "(project_setup_run_id is not null and setup_generation is not null "
            "and agent_material_sha256 is not null and agent_material_byte_count is not null)",
            name="ck_guide_sufficiency_reports_material_provenance_shape",
        ),
        CheckConstraint(
            "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
            "and created_by_admin_role_grant_id is null and created_by_service_identity is null "
            "and creation_scope_type is null and creation_scope_project_id is null "
            "and creation_action_id is null and authorization_decision_event_id is null) or "
            "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
            "and creation_scope_project_id is not null and creation_action_id in "
            "('project.guide_sufficiency_report.create','project.guide_sufficiency.run') "
            "and authorization_decision_event_id is not null and "
            "((created_by_admin_role_grant_id is not null and created_by_service_identity is null "
            "and creation_scope_type in ('system','project')) or "
            "(created_by_admin_role_grant_id is null "
            "and created_by_service_identity = 'workstream.project.setup' "
            "and creation_scope_type = 'service' "
            "and creation_action_id = 'project.guide_sufficiency.run' "
            "and project_setup_run_id is not null and setup_generation is not null "
            "and agent_material_sha256 is not null and agent_material_byte_count is not null)))",
            name="ck_guide_sufficiency_creation_authority_shape",
        ),
        CheckConstraint(
            "(warnings_acknowledged_by_actor_profile_id is null "
            "and warnings_acknowledged_via_identity_link_id is null "
            "and warnings_acknowledged_by_admin_role_grant_id is null "
            "and warning_acknowledgement_scope_type is null "
            "and warning_acknowledgement_scope_project_id is null "
            "and warning_acknowledgement_action_id is null "
            "and warning_acknowledgement_decision_event_id is null) or "
            "(warnings_acknowledged_by_actor_profile_id is not null "
            "and warnings_acknowledged_via_identity_link_id is not null "
            "and warnings_acknowledged_by_admin_role_grant_id is not null "
            "and warning_acknowledgement_scope_type in ('system','project') "
            "and warning_acknowledgement_scope_project_id is not null "
            "and warning_acknowledgement_action_id = "
            "'project.guide_sufficiency.warnings.acknowledge' "
            "and warning_acknowledgement_decision_event_id is not null)",
            name="ck_guide_sufficiency_ack_authority_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
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
    project_setup_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_setup_runs.id", use_alter=True), index=True
    )
    setup_generation: Mapped[int | None] = mapped_column(BigInteger)
    agent_material_sha256: Mapped[str | None] = mapped_column(String(71))
    agent_material_byte_count: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    created_by_service_identity: Mapped[str | None] = mapped_column(String(160))
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    warnings_acknowledged_by_role: Mapped[str | None] = mapped_column(String(50))
    warnings_acknowledged_by_actor: Mapped[str | None] = mapped_column(String(100))
    warnings_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement_note: Mapped[str | None] = mapped_column(Text)
    warnings_acknowledged_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    warnings_acknowledged_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    warnings_acknowledged_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    warning_acknowledgement_scope_type: Mapped[str | None] = mapped_column(String(16))
    warning_acknowledgement_scope_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id")
    )
    warning_acknowledgement_action_id: Mapped[str | None] = mapped_column(String(160))
    warning_acknowledgement_decision_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id")
    )


class GuideSufficiencyReportSourceUsage(Base):
    """Exact ART extraction usages consumed by one agent-created report."""

    __tablename__ = "guide_sufficiency_report_source_usages"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "extraction_usage_id",
                "source_item_id",
                "binding_id",
                "content_id",
                "extraction_attempt_id",
                "extracted_content_id",
                "project_setup_run_id",
                "setup_generation",
            ],
            [
                "guide_source_extraction_usages.id",
                "guide_source_extraction_usages.source_item_id",
                "guide_source_extraction_usages.binding_id",
                "guide_source_extraction_usages.content_id",
                "guide_source_extraction_usages.extraction_attempt_id",
                "guide_source_extraction_usages.extracted_content_id",
                "guide_source_extraction_usages.project_setup_run_id",
                "guide_source_extraction_usages.setup_generation",
            ],
            name="fk_sufficiency_report_source_usage_exact_extraction",
        ),
        UniqueConstraint("report_id", "item_order", name="uq_sufficiency_report_item_order"),
        UniqueConstraint(
            "report_id", "extraction_usage_id", name="uq_sufficiency_report_extraction_usage"
        ),
        CheckConstraint("item_order >= 0", name="ck_sufficiency_report_item_order"),
        CheckConstraint("setup_generation > 0", name="ck_sufficiency_report_usage_generation"),
        CheckConstraint(
            "canonical_output_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_sufficiency_report_output_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("guide_sufficiency_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False)
    extraction_usage_id: Mapped[str] = mapped_column(String(36), nullable=False)
    extraction_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    extracted_content_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_setup_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    canonical_output_sha256: Mapped[str] = mapped_column(String(71), nullable=False)


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
        CheckConstraint(
            "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
            "and created_by_admin_role_grant_id is null and created_by_service_identity is null "
            "and creation_scope_type is null and creation_scope_project_id is null "
            "and creation_action_id is null and creation_decision_event_id is null) or "
            "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
            "and creation_scope_type is not null and creation_action_id is not null "
            "and creation_scope_project_id is not null "
            "and creation_scope_project_id=project_id and creation_decision_event_id is not null "
            "and creation_action_id in ('project.submission_artifact_policy.create',"
            "'project.submission_artifact_policy.derive',"
            "'project.submission_artifact_policy.update') and "
            "((created_by_admin_role_grant_id is not null and created_by_service_identity is null "
            "and creation_scope_type in ('system','project')) or "
            "(created_by_admin_role_grant_id is null "
            "and created_by_service_identity is not null "
            "and created_by_service_identity='workstream.project.setup' "
            "and creation_scope_type='service' "
            "and creation_action_id='project.submission_artifact_policy.derive')))",
            name="ck_submission_policy_creation_authority_shape",
        ),
        CheckConstraint(
            "(approved_by_actor_profile_id is null and approved_via_identity_link_id is null "
            "and approved_by_admin_role_grant_id is null and approval_scope_type is null "
            "and approval_scope_project_id is null and approval_action_id is null "
            "and approval_decision_event_id is null) or "
            "(approved_by_actor_profile_id is not null and approved_via_identity_link_id is not null "
            "and approved_by_admin_role_grant_id is not null "
            "and approval_scope_type is not null and approval_action_id is not null "
            "and approval_scope_type in ('system','project') "
            "and approval_scope_project_id is not null "
            "and approval_scope_project_id=project_id "
            "and approval_action_id='project.submission_artifact_policy.approve' "
            "and approval_decision_event_id is not null)",
            name="ck_submission_policy_approval_authority_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", index=True
    )
    policy_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    derivation_source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_material_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    derivation_agent_name: Mapped[str | None] = mapped_column(String(100))
    derivation_agent_version: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    created_by_service_identity: Mapped[str | None] = mapped_column(String(160))
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    creation_decision_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    approved_by_role: Mapped[str | None] = mapped_column(String(50))
    approved_by_actor: Mapped[str | None] = mapped_column(String(100))
    approved_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    approved_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    approved_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    approval_scope_type: Mapped[str | None] = mapped_column(String(16))
    approval_scope_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    approval_action_id: Mapped[str | None] = mapped_column(String(160))
    approval_decision_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id"))
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
        CheckConstraint(
            "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
            "and created_by_admin_role_grant_id is null and creation_scope_type is null "
            "and creation_scope_project_id is null and creation_action_id is null "
            "and creation_decision_event_id is null) or "
            "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
            "and created_by_admin_role_grant_id is not null "
            "and creation_scope_type is not null and creation_action_id is not null "
            "and creation_scope_type in ('system','project') "
            "and creation_scope_project_id is not null "
            "and creation_scope_project_id=project_id "
            "and creation_action_id='project.submission_artifact_policy.approve' "
            "and creation_decision_event_id is not null)",
            name="ck_effective_submission_policy_authority_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"),
        nullable=False,
        index=True,
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    submission_artifact_policy_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    submission_artifact_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="approved", index=True
    )
    merge_algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    effective_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    creation_decision_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id"))
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
        UniqueConstraint(
            "id",
            "compiled_bundle_hash",
            name="uq_pre_submit_checker_policies_id_compiled_bundle_hash",
        ),
        CheckConstraint(
            "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
            "and created_by_admin_role_grant_id is null and creation_scope_type is null "
            "and creation_scope_project_id is null and creation_action_id is null "
            "and creation_decision_event_id is null) or "
            "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
            "and created_by_admin_role_grant_id is not null "
            "and creation_scope_type is not null and creation_action_id is not null "
            "and creation_scope_type in ('system','project') "
            "and creation_scope_project_id is not null "
            "and creation_scope_project_id=project_id "
            "and creation_action_id='project.submission_artifact_policy.approve' "
            "and creation_decision_event_id is not null)",
            name="ck_pre_submit_policy_authority_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id"), nullable=False, index=True
    )
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
    created_by_actor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id")
    )
    created_via_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("admin_role_grants.id")
    )
    creation_scope_type: Mapped[str | None] = mapped_column(String(16))
    creation_scope_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    creation_action_id: Mapped[str | None] = mapped_column(String(160))
    creation_decision_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    supersedes_pre_submit_checker_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("pre_submit_checker_policies.id"),
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
