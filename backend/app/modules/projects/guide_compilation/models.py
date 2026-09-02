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
_COMPONENT_NAMES = (
    "sufficiency_hash",
    "artifact_policy_hash",
    "requirement_inventory_hash",
    "pre_submit_hash",
    "post_submit_hash",
    "capability_suggestions_hash",
    "setup_notes_hash",
)


def _component_hashes_check(column: str) -> str:
    """Return the exact seven-key JSON shape and digest checks."""
    pairs = ",".join(f"'{name}',{column}->>'{name}'" for name in _COMPONENT_NAMES)
    hashes = " and ".join(
        f"coalesce(({column}->>'{name}') {_HASH_CHECK},false)"
        for name in _COMPONENT_NAMES
    )
    return (
        f"json_typeof({column})='object' and "
        f"{column}::jsonb=jsonb_build_object({pairs}) and {hashes}"
    )


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
        UniqueConstraint(
            "id",
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "setup_run_id",
            "setup_generation",
            name="uq_compilation_attempt_exact_request",
        ),
        CheckConstraint(
            "status in ('compilation_reserved','compilation_provider_uncertain',"
            "'provider_result_accepted','compilation_invalid_terminal',"
            "'compilation_persisted')",
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
            "component_hashes is null or ("
            + _component_hashes_check("component_hashes")
            + ")",
            name="ck_compilation_attempt_component_hashes",
        ),
        CheckConstraint(
            "(status='compilation_reserved' and provider_uncertain_at is null and accepted_at is null "
            "and terminal_at is null and persisted_at is null and canonical_result is null "
            "and result_hash is null and component_hashes is null and failure_code is null "
            "and persisted_compilation_id is null) or "
            "(status='compilation_provider_uncertain' and provider_uncertain_at is not null "
            "and accepted_at is null and terminal_at is null and persisted_at is null "
            "and canonical_result is null and result_hash is null and component_hashes is null "
            "and failure_code is null and persisted_compilation_id is null) or "
            "(status='provider_result_accepted' and accepted_at is not null and terminal_at is null "
            "and persisted_at is null and canonical_result is not null and result_hash is not null "
            "and component_hashes is not null and failure_code is null "
            "and persisted_compilation_id is null) or "
            "(status='compilation_persisted' and accepted_at is not null and persisted_at is not null "
            "and terminal_at is null and canonical_result is not null and result_hash is not null "
            "and component_hashes is not null and failure_code is null "
            "and persisted_compilation_id is not null) or "
            "(status='compilation_invalid_terminal' and terminal_at is not null and accepted_at is null and persisted_at is null "
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


class ProjectGuideCompilationRequestOperation(Base):
    """Immutable authorized request receipt bound to one exact attempt."""

    __tablename__ = "project_guide_compilation_request_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_compilation_request_actor_link",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "project_id", "guide_id"],
            [
                "guide_source_snapshots.id",
                "guide_source_snapshots.project_id",
                "guide_source_snapshots.guide_id",
            ],
            name="fk_compilation_request_snapshot",
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
            name="fk_compilation_request_setup",
        ),
        ForeignKeyConstraint(
            [
                "attempt_id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_run_id",
                "setup_generation",
            ],
            [
                "project_guide_compilation_attempts.id",
                "project_guide_compilation_attempts.project_id",
                "project_guide_compilation_attempts.guide_id",
                "project_guide_compilation_attempts.source_snapshot_id",
                "project_guide_compilation_attempts.setup_run_id",
                "project_guide_compilation_attempts.setup_generation",
            ],
            name="fk_compilation_request_exact_attempt",
        ),
        ForeignKeyConstraint(
            ["expected_predecessor_compilation_id", "project_id", "guide_id"],
            [
                "project_guide_compilations.id",
                "project_guide_compilations.project_id",
                "project_guide_compilations.guide_id",
            ],
            name="fk_compilation_request_predecessor",
        ),
        UniqueConstraint(
            "actor_profile_id",
            "request_id",
            name="uq_compilation_request_actor_request",
        ),
        UniqueConstraint(
            "actor_profile_id",
            "idempotency_key",
            name="uq_compilation_request_actor_key",
        ),
        UniqueConstraint("attempt_id", name="uq_compilation_request_attempt"),
        UniqueConstraint(
            "authorization_decision_event_id",
            name="uq_compilation_request_authorization_event",
        ),
        CheckConstraint(
            "setup_generation > 0", name="ck_compilation_request_generation"
        ),
        CheckConstraint(
            "request_facts_digest " + _HASH_CHECK,
            name="ck_compilation_request_facts_digest",
        ),
    )

    operation_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(Uuid())
    idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"))
    identity_link_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"))
    source_snapshot_id: Mapped[str] = mapped_column(String(36))
    setup_run_id: Mapped[str] = mapped_column(String(36))
    setup_generation: Mapped[int] = mapped_column(BigInteger)
    expected_predecessor_compilation_id: Mapped[UUID | None] = mapped_column(Uuid())
    request_facts_digest: Mapped[str] = mapped_column(String(71))
    attempt_id: Mapped[UUID] = mapped_column(Uuid())
    authorization_decision_event_id: Mapped[str] = mapped_column(
        ForeignKey("audit_events.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
            + _component_hashes_check("component_hashes"),
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


class ProjectGuideComponentProjectionOperation(Base):
    """Immutable authority and lineage custody for one projected component."""

    __tablename__ = "project_guide_component_projection_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation"],
            [
                "project_guide_compilation_attempts.id",
                "project_guide_compilation_attempts.project_id",
                "project_guide_compilation_attempts.guide_id",
                "project_guide_compilation_attempts.source_snapshot_id",
                "project_guide_compilation_attempts.setup_run_id",
                "project_guide_compilation_attempts.setup_generation",
            ],
            name="fk_projection_operation_exact_attempt",
        ),
        ForeignKeyConstraint(
            ["compilation_id", "attempt_id"],
            ["project_guide_compilations.id", "project_guide_compilations.attempt_id"],
            name="fk_projection_operation_exact_compilation",
        ),
        ForeignKeyConstraint(
            ["setup_run_id", "project_id", "guide_id", "source_snapshot_id", "setup_generation"],
            [
                "project_setup_runs.id",
                "project_setup_runs.project_id",
                "project_setup_runs.guide_id",
                "project_setup_runs.source_snapshot_id",
                "project_setup_runs.setup_generation",
            ],
            name="fk_projection_operation_exact_setup",
        ),
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_projection_operation_actor_link",
        ),
        UniqueConstraint(
            "setup_run_id",
            "setup_generation",
            "component",
            name="uq_projection_operation_setup_component",
        ),
        UniqueConstraint(
            "compilation_id", "component", name="uq_projection_operation_compilation_component"
        ),
        UniqueConstraint("output_id", name="uq_projection_operation_output"),
        UniqueConstraint(
            "authorization_decision_event_id",
            name="uq_projection_operation_decision_event",
        ),
        CheckConstraint(
            "component in ('guide_sufficiency','submission_artifact_policy')",
            name="ck_projection_operation_component",
        ),
        CheckConstraint(
            "setup_generation > 0 and material_byte_count >= 0",
            name="ck_projection_operation_positive_values",
        ),
        CheckConstraint(
            "source_snapshot_hash " + _HASH_CHECK
            + " and source_state_digest " + _HASH_CHECK
            + " and result_hash " + _HASH_CHECK
            + " and component_hash " + _HASH_CHECK
            + " and output_digest " + _HASH_CHECK
            + " and facts_digest " + _HASH_CHECK
            + " and authority_resource_digest " + _HASH_CHECK
            + " and (material_sha256 is null or material_sha256 " + _HASH_CHECK + ")",
            name="ck_projection_operation_hashes",
        ),
        CheckConstraint(
            "(component='guide_sufficiency' and prior_operation_id is null "
            "and prior_output_id is null and prior_output_digest is null "
            "and report_id is not null and policy_id is null "
            "and material_sha256 is not null) or "
            "(component='submission_artifact_policy' and prior_operation_id is not null "
            "and prior_output_id is not null and prior_output_digest is not null "
            "and report_id is null and policy_id is not null "
            "and material_sha256 is null)",
            name="ck_projection_operation_component_shape",
        ),
    )

    operation_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    component: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    guide_id: Mapped[str] = mapped_column(ForeignKey("project_guides.id"), nullable=False)
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    setup_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    celery_task_id: Mapped[str] = mapped_column(String(155), nullable=False)
    source_state_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_operation_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("project_guide_compilation_request_operations.operation_id")
    )
    provider_idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    compilation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    component_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    result_schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    compilation_agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    compilation_agent_version: Mapped[str] = mapped_column(String(100), nullable=False)
    material_sha256: Mapped[str | None] = mapped_column(String(71))
    material_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    prior_operation_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("project_guide_component_projection_operations.operation_id")
    )
    prior_output_id: Mapped[UUID | None] = mapped_column(Uuid())
    prior_output_digest: Mapped[str | None] = mapped_column(String(71))
    output_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    report_id: Mapped[str | None] = mapped_column(
        ForeignKey("guide_sufficiency_reports.id")
    )
    policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("submission_artifact_policies.id")
    )
    output_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    facts_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    authority_resource_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id"), nullable=False
    )
    identity_link_id: Mapped[str] = mapped_column(String(36), nullable=False)
    service_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    permission_id: Mapped[str] = mapped_column(String(120), nullable=False)
    authorization_decision_event_id: Mapped[str] = mapped_column(
        ForeignKey("audit_events.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
