"""Isolated SQLAlchemy models for hidden unified guide compilation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

_HASH_CHECK = "~ '^sha256:[0-9a-f]{64}$'"


class ProjectGuideCompilationAttempt(Base):
    """Crash fence for one exact setup-generation provider attempt."""

    __tablename__ = "project_guide_compilation_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_compilation_attempt_snapshot_hash",
        ),
        ForeignKeyConstraint(
            [
                "setup_run_id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_generation",
            ],
            [
                "project_setup_runs.id",
                "project_setup_runs.project_id",
                "project_setup_runs.guide_id",
                "project_setup_runs.source_snapshot_id",
                "project_setup_runs.setup_generation",
            ],
            name="fk_compilation_attempt_exact_setup",
        ),
        ForeignKeyConstraint(
            ["persisted_compilation_id", "id"],
            ["project_guide_compilations.id", "project_guide_compilations.attempt_id"],
            name="fk_compilation_attempt_exact_persisted_compilation",
            use_alter=True,
        ),
        UniqueConstraint(
            "setup_run_id",
            "setup_generation",
            name="uq_compilation_attempt_setup_generation",
        ),
        UniqueConstraint(
            "provider_idempotency_key", name="uq_compilation_attempt_provider_key"
        ),
        CheckConstraint(
            "status in ('reserved','provider_uncertain','accepted',"
            "'invalid_terminal','persisted')",
            name="ck_compilation_attempt_status",
        ),
        CheckConstraint(
            "setup_generation > 0", name="ck_compilation_attempt_generation"
        ),
        CheckConstraint(
            "source_snapshot_hash " + _HASH_CHECK + " and canonical_input_hash "
            + _HASH_CHECK + " and guide_material_hash "
            + _HASH_CHECK
            + " and pre_catalogue_manifest_hash "
            + _HASH_CHECK
            + " and post_catalogue_manifest_hash "
            + _HASH_CHECK,
            name="ck_compilation_attempt_identity_hashes",
        ),
        CheckConstraint(
            "result_hash is null or result_hash " + _HASH_CHECK,
            name="ck_compilation_attempt_result_hash",
        ),
        CheckConstraint(
            "canonical_result is null or octet_length(canonical_result::text) <= 4194304",
            name="ck_compilation_attempt_result_size",
        ),
        CheckConstraint(
            "component_hashes is null or (json_typeof(component_hashes)='object' and "
            "component_hashes::jsonb=jsonb_build_object("
            "'sufficiency_hash',component_hashes->>'sufficiency_hash',"
            "'artifact_policy_hash',component_hashes->>'artifact_policy_hash',"
            "'requirement_inventory_hash',component_hashes->>'requirement_inventory_hash',"
            "'pre_submit_hash',component_hashes->>'pre_submit_hash',"
            "'post_submit_hash',component_hashes->>'post_submit_hash',"
            "'capability_suggestions_hash',component_hashes->>'capability_suggestions_hash',"
            "'setup_notes_hash',component_hashes->>'setup_notes_hash') and "
            "coalesce((component_hashes->>'sufficiency_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'artifact_policy_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'requirement_inventory_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'pre_submit_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'post_submit_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'capability_suggestions_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'setup_notes_hash') " + _HASH_CHECK + ",false))",
            name="ck_compilation_attempt_component_hashes",
        ),
        CheckConstraint(
            "(status='reserved' and provider_uncertain_at is null and accepted_at is null "
            "and terminal_at is null and persisted_at is null and canonical_result is null "
            "and result_hash is null and component_hashes is null and failure_code is null "
            "and persisted_compilation_id is null) or "
            "(status='provider_uncertain' and provider_uncertain_at is not null "
            "and accepted_at is null and terminal_at is null and persisted_at is null "
            "and canonical_result is null and result_hash is null and component_hashes is null "
            "and failure_code is null and persisted_compilation_id is null) or "
            "(status='accepted' and accepted_at is not null and terminal_at is null "
            "and persisted_at is null and canonical_result is not null and result_hash is not null "
            "and component_hashes is not null and failure_code is null "
            "and persisted_compilation_id is null) or "
            "(status='persisted' and accepted_at is not null and persisted_at is not null "
            "and terminal_at is null and canonical_result is not null and result_hash is not null "
            "and component_hashes is not null and failure_code is null "
            "and persisted_compilation_id is not null) or "
            "(status='invalid_terminal' and terminal_at is not null and accepted_at is null and persisted_at is null "
            "and canonical_result is null and result_hash is null and component_hashes is null "
            "and persisted_compilation_id is null and "
            "failure_code in ('schema_invalid','unsafe_text','hash_mismatch','context_mismatch'))",
            name="ck_compilation_attempt_state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), index=True)
    guide_version: Mapped[str] = mapped_column(String(50))
    source_snapshot_id: Mapped[str] = mapped_column(String(36), index=True)
    source_snapshot_hash: Mapped[str] = mapped_column(String(71))
    setup_run_id: Mapped[str] = mapped_column(String(36), index=True)
    setup_generation: Mapped[int] = mapped_column(BigInteger)
    canonical_input_hash: Mapped[str] = mapped_column(String(71))
    guide_material_hash: Mapped[str] = mapped_column(String(71))
    pre_catalogue_id: Mapped[str] = mapped_column(String(160))
    pre_catalogue_version: Mapped[str] = mapped_column(String(100))
    pre_catalogue_schema_version: Mapped[str] = mapped_column(String(160))
    pre_catalogue_manifest_hash: Mapped[str] = mapped_column(String(71))
    post_catalogue_id: Mapped[str] = mapped_column(String(160))
    post_catalogue_version: Mapped[str] = mapped_column(String(100))
    post_catalogue_schema_version: Mapped[str] = mapped_column(String(160))
    post_catalogue_manifest_hash: Mapped[str] = mapped_column(String(71))
    agent_identity: Mapped[str] = mapped_column(String(100))
    agent_version: Mapped[str] = mapped_column(String(100))
    instruction_version: Mapped[str] = mapped_column(String(100))
    provider_idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    status: Mapped[str] = mapped_column(String(32))
    canonical_result: Mapped[dict | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(71))
    component_hashes: Mapped[dict | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    persisted_compilation_id: Mapped[UUID | None] = mapped_column(Uuid())
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    provider_uncertain_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    persisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectGuideCompilation(Base):
    """Immutable accepted compilation in one append-only guide lineage."""

    __tablename__ = "project_guide_compilations"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_project_guide_compilation_attempt"),
        UniqueConstraint(
            "id", "attempt_id", name="uq_project_guide_compilation_id_attempt"
        ),
        UniqueConstraint(
            "supersedes_compilation_id", name="uq_project_guide_compilation_predecessor"
        ),
        UniqueConstraint(
            "id", "project_id", "guide_id", name="uq_project_guide_compilation_scope"
        ),
        ForeignKeyConstraint(
            ["supersedes_compilation_id", "project_id", "guide_id"],
            [
                "project_guide_compilations.id",
                "project_guide_compilations.project_id",
                "project_guide_compilations.guide_id",
            ],
            name="fk_project_guide_compilation_predecessor",
        ),
        Index(
            "uq_project_guide_compilation_root",
            "project_id",
            "guide_id",
            unique=True,
            postgresql_where=text("supersedes_compilation_id is null"),
        ),
        CheckConstraint(
            "setup_generation > 0 and created_by_service_identity = "
            "'workstream.project.setup' and creation_action_id = "
            "'project.guide_compilation.execute'",
            name="ck_project_guide_compilation_custody",
        ),
        CheckConstraint(
            "authorization_resource_context_digest " + _HASH_CHECK,
            name="ck_project_guide_compilation_authorization_digest",
        ),
        CheckConstraint(
            "source_snapshot_hash " + _HASH_CHECK + " and canonical_input_hash "
            + _HASH_CHECK + " and guide_material_hash "
            + _HASH_CHECK
            + " and pre_catalogue_manifest_hash "
            + _HASH_CHECK
            + " and post_catalogue_manifest_hash "
            + _HASH_CHECK
            + " and result_hash "
            + _HASH_CHECK,
            name="ck_project_guide_compilation_hashes",
        ),
        CheckConstraint(
            "octet_length(canonical_result::text) <= 4194304 and "
            "json_typeof(component_hashes)='object' and "
            "component_hashes::jsonb=jsonb_build_object("
            "'sufficiency_hash',component_hashes->>'sufficiency_hash',"
            "'artifact_policy_hash',component_hashes->>'artifact_policy_hash',"
            "'requirement_inventory_hash',component_hashes->>'requirement_inventory_hash',"
            "'pre_submit_hash',component_hashes->>'pre_submit_hash',"
            "'post_submit_hash',component_hashes->>'post_submit_hash',"
            "'capability_suggestions_hash',component_hashes->>'capability_suggestions_hash',"
            "'setup_notes_hash',component_hashes->>'setup_notes_hash') and "
            "coalesce((component_hashes->>'sufficiency_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'artifact_policy_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'requirement_inventory_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'pre_submit_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'post_submit_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'capability_suggestions_hash') " + _HASH_CHECK + ",false) and "
            "coalesce((component_hashes->>'setup_notes_hash') " + _HASH_CHECK + ",false)",
            name="ck_project_guide_compilation_result_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("project_guide_compilation_attempts.id"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), index=True)
    guide_version: Mapped[str] = mapped_column(String(50))
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id"), index=True
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(71))
    setup_run_id: Mapped[str] = mapped_column(ForeignKey("project_setup_runs.id"), index=True)
    setup_generation: Mapped[int] = mapped_column(BigInteger)
    canonical_input_hash: Mapped[str] = mapped_column(String(71))
    guide_material_hash: Mapped[str] = mapped_column(String(71))
    pre_catalogue_manifest_hash: Mapped[str] = mapped_column(String(71))
    post_catalogue_manifest_hash: Mapped[str] = mapped_column(String(71))
    agent_identity: Mapped[str] = mapped_column(String(100))
    agent_version: Mapped[str] = mapped_column(String(100))
    instruction_version: Mapped[str] = mapped_column(String(100))
    canonical_result: Mapped[dict] = mapped_column(JSON)
    result_hash: Mapped[str] = mapped_column(String(71))
    component_hashes: Mapped[dict] = mapped_column(JSON)
    supersedes_compilation_id: Mapped[UUID | None] = mapped_column(Uuid())
    created_by_actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"))
    created_via_identity_link_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identity_links.id")
    )
    created_by_service_identity: Mapped[str] = mapped_column(String(160))
    creation_action_id: Mapped[str] = mapped_column(String(160))
    authorization_decision_event_id: Mapped[str] = mapped_column(ForeignKey("audit_events.id"))
    authorization_resource_context_digest: Mapped[str] = mapped_column(String(71))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
