"""Provider-neutral SQLAlchemy records for immutable artifacts."""

from __future__ import annotations

from datetime import datetime

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
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


SHA256_CHECK = "{column} ~ '^sha256:[0-9a-f]{{64}}$'"
UUID_CHECK = (
    "{column} ~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[1-5][0-9a-f]{{3}}-"
    "[89ab][0-9a-f]{{3}}-[0-9a-f]{{12}}$'"
)


class ArtifactContent(Base):
    """Immutable provider-neutral identity for exact stored bytes."""

    __tablename__ = "artifact_contents"
    __table_args__ = (
        UniqueConstraint("sha256", "byte_count", name="uq_artifact_content_digest_size"),
        CheckConstraint(SHA256_CHECK.format(column="sha256"), name="sha256_shape"),
        CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(71), nullable=False, index=True)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(200))
    normalized_display_name: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreSubmitEvidenceSet(Base):
    """Immutable execution provenance for one exact prepared submission bundle."""

    __tablename__ = "pre_submit_evidence_sets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_pre_submit_evidence_identity_actor",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "task_id", "actor_profile_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_pre_submit_evidence_assignment",
        ),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_pre_submit_evidence_task_project",
        ),
        ForeignKeyConstraint(
            ["task_id", "guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_pre_submit_evidence_task_guide",
        ),
        ForeignKeyConstraint(
            ["guide_id", "project_id", "guide_version"],
            ["project_guides.id", "project_guides.project_id", "project_guides.version"],
            name="fk_pre_submit_evidence_guide_lineage",
        ),
        ForeignKeyConstraint(
            ["task_id", "source_snapshot_id", "source_snapshot_sha256"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_guide_source_snapshot_id",
                "workstream_tasks.locked_guide_source_snapshot_hash",
            ],
            name="fk_pre_submit_evidence_task_source_snapshot",
        ),
        ForeignKeyConstraint(
            ["predecessor_submission_id", "task_id", "predecessor_submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_pre_submit_evidence_predecessor",
        ),
        ForeignKeyConstraint(
            ["task_id", "effective_policy_id", "locked_artifact_policy_sha256"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_effective_project_submission_artifact_policy_id",
                "workstream_tasks.locked_effective_project_submission_artifact_policy_hash",
            ],
            name="fk_pre_submit_evidence_task_artifact_policy",
        ),
        ForeignKeyConstraint(
            ["task_id", "pre_submit_policy_id", "locked_checker_policy_sha256"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_pre_submit_checker_policy_id",
                "workstream_tasks.locked_pre_submit_checker_bundle_hash",
            ],
            name="fk_pre_submit_evidence_task_checker_policy",
        ),
        UniqueConstraint("operation_identity", name="uq_pre_submit_evidence_operation"),
        CheckConstraint(
            SHA256_CHECK.format(column="operation_identity"),
            name="ck_pre_submit_evidence_operation_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="archive_sha256"),
            name="ck_pre_submit_evidence_archive_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="semantic_manifest_sha256"),
            name="ck_pre_submit_evidence_manifest_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="effective_plan_sha256"),
            name="ck_pre_submit_evidence_plan_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="catalogue_manifest_sha256"),
            name="ck_pre_submit_evidence_catalogue_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="locked_guide_sha256"),
            name="ck_pre_submit_evidence_guide_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="source_snapshot_sha256"),
            name="ck_pre_submit_evidence_source_snapshot_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="locked_artifact_policy_sha256"),
            name="ck_pre_submit_evidence_artifact_policy_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="locked_checker_policy_sha256"),
            name="ck_pre_submit_evidence_checker_policy_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="locked_policy_context_hash"),
            name="policy_context_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="result_manifest_sha256"),
            name="ck_pre_submit_evidence_result_manifest_sha256",
        ),
        CheckConstraint("archive_byte_count >= 0", name="ck_pre_submit_evidence_archive_size"),
        CheckConstraint("result_count > 0", name="ck_pre_submit_evidence_result_count"),
        CheckConstraint(
            "(predecessor_submission_id is null and predecessor_submission_version is null) "
            "or (predecessor_submission_id is not null and "
            "predecessor_submission_version is not null)",
            name="ck_pre_submit_evidence_predecessor_shape",
        ),
        CheckConstraint(
            "storage_scheme in ('local','s3')", name="ck_pre_submit_evidence_storage_scheme"
        ),
        CheckConstraint(
            "terminal_status in ('passed','blocked')",
            name="ck_pre_submit_evidence_terminal_status",
        ),
        CheckConstraint(
            "(terminal_status='passed' and eligible) or "
            "(terminal_status='blocked' and not eligible)",
            name="ck_pre_submit_evidence_status_eligibility",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation_identity: Mapped[str] = mapped_column(String(71), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    identity_link_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identity_links.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("task_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    predecessor_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT")
    )
    predecessor_submission_version: Mapped[int | None] = mapped_column(Integer)
    prepared_generation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    archive_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    archive_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    semantic_manifest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    semantic_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    guide_id: Mapped[str] = mapped_column(
        ForeignKey("project_guides.id", ondelete="RESTRICT"), nullable=False
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("guide_source_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    source_snapshot_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_guide_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    effective_policy_id: Mapped[str] = mapped_column(
        ForeignKey("effective_project_submission_artifact_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    locked_artifact_policy_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    pre_submit_policy_id: Mapped[str] = mapped_column(
        ForeignKey("pre_submit_checker_policies.id", ondelete="RESTRICT"), nullable=False
    )
    locked_checker_policy_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_policy_context_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    effective_plan_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    catalogue_id: Mapped[str] = mapped_column(String(160), nullable=False)
    catalogue_version: Mapped[str] = mapped_column(String(40), nullable=False)
    catalogue_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    storage_scheme: Mapped[str] = mapped_column(String(16), nullable=False)
    terminal_status: Mapped[str] = mapped_column(String(16), nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreSubmitEvidenceResult(Base):
    """One immutable ordered member of a pre-submit evidence set."""

    __tablename__ = "pre_submit_evidence_results"
    __table_args__ = (
        UniqueConstraint("evidence_set_id", "result_order", name="uq_pre_submit_result_order"),
        UniqueConstraint(
            "evidence_set_id",
            "definition_id",
            name="uq_pre_submit_result_definition",
        ),
        CheckConstraint("result_order >= 0", name="ck_pre_submit_result_order"),
        CheckConstraint(
            "status in ('passed','warning','advisory_disabled','dependency_not_run','failed')",
            name="ck_pre_submit_result_status",
        ),
        CheckConstraint(
            "(status='failed' and failure_code is not null) or "
            "(status<>'failed' and failure_code is null)",
            name="result_failure_shape",
        ),
        CheckConstraint(
            "phase in ('custody','identity','materialization','default_policy','project_policy')",
            name="ck_pre_submit_result_phase",
        ),
        CheckConstraint(
            "classification in ('mandatory_security','mandatory_integrity',"
            "'mandatory_accountability','advisory')",
            name="ck_pre_submit_result_classification",
        ),
        CheckConstraint(
            "severity in ('blocking','warning')",
            name="ck_pre_submit_result_severity",
        ),
        CheckConstraint(
            "(classification='advisory' and severity='warning') or "
            "(classification<>'advisory' and severity='blocking')",
            name="ck_pre_submit_result_classification_severity",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="effective_plan_sha256"),
            name="ck_pre_submit_result_plan_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="locked_policy_sha256"),
            name="ck_pre_submit_result_policy_sha256",
        ),
        CheckConstraint(
            "(phase='project_policy' and rule_instance_id is not null and "
            "rule_instance_id ~ '^sha256:[0-9a-f]{64}$') or "
            "(phase<>'project_policy' and rule_instance_id is null)",
            name="ck_pre_submit_result_rule_instance_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_set_id: Mapped[str] = mapped_column(
        ForeignKey("pre_submit_evidence_sets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    result_order: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dispatch_authority: Mapped[str] = mapped_column(String(160), nullable=False)
    definition_id: Mapped[str] = mapped_column(String(160), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(40), nullable=False)
    public_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(160))
    message_code: Mapped[str] = mapped_column(String(160), nullable=False)
    effective_plan_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    rule_instance_id: Mapped[str | None] = mapped_column(String(71))
    locked_policy_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactBinding(Base):
    """Immutable attachment of content to one Workstream resource role."""

    __tablename__ = "artifact_bindings"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "resource_type",
            "resource_id",
            "logical_role",
            "scope_version",
            name="uq_artifact_binding_scope_version",
        ),
        UniqueConstraint("supersedes_binding_id", name="uq_artifact_binding_supersedes"),
        CheckConstraint("scope_version > 0", name="scope_version_positive"),
        CheckConstraint(
            "(scope_version = 1 and supersedes_binding_id is null) or "
            "(scope_version > 1 and supersedes_binding_id is not null)",
            name="scope_version_predecessor",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_contents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    logical_role: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    attribution_type: Mapped[str] = mapped_column(String(30), nullable=False)
    supersedes_binding_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_bindings.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceArtifactBinding(Base):
    """Immutable verified content bound to one exact guide setup generation."""

    __tablename__ = "guide_source_artifact_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_snapshot_id", "project_id", "guide_id"],
            [
                "guide_source_snapshots.id",
                "guide_source_snapshots.project_id",
                "guide_source_snapshots.guide_id",
            ],
            name="fk_guide_bindings_exact_snapshot",
        ),
        ForeignKeyConstraint(
            ["source_item_id", "source_snapshot_id"],
            ["guide_source_snapshot_items.id", "guide_source_snapshot_items.source_snapshot_id"],
            name="fk_guide_bindings_exact_item",
        ),
        ForeignKeyConstraint(
            [
                "project_setup_run_id",
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
            name="fk_guide_bindings_exact_setup_generation",
        ),
        ForeignKeyConstraint(
            ["verified_replica_id", "content_id"],
            ["artifact_replicas.id", "artifact_replicas.content_id"],
            name="fk_guide_bindings_verified_replica_content",
        ),
        UniqueConstraint(
            "source_item_id",
            "setup_generation",
            name="uq_guide_bindings_item_generation",
        ),
        UniqueConstraint(
            "id",
            "content_id",
            "setup_generation",
            name="uq_guide_bindings_extraction_attempt_lineage",
        ),
        UniqueConstraint(
            "id",
            "content_id",
            "source_item_id",
            "project_setup_run_id",
            "setup_generation",
            name="uq_guide_bindings_extraction_lineage",
        ),
        UniqueConstraint(
            "id",
            "content_id",
            "verified_replica_id",
            "setup_generation",
            name="uq_guide_bindings_exact_read",
        ),
        UniqueConstraint("supersedes_binding_id", name="uq_guide_bindings_supersedes"),
        CheckConstraint("setup_generation > 0", name="ck_guide_bindings_generation_positive"),
        CheckConstraint("logical_role = 'guide_source_original'", name="ck_guide_bindings_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    guide_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_setup_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_contents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    verified_replica_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    logical_role: Mapped[str] = mapped_column(String(100), nullable=False)
    supersedes_binding_id: Mapped[str | None] = mapped_column(
        ForeignKey("guide_source_artifact_bindings.id", ondelete="RESTRICT"), index=True
    )
    created_by_service: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceFormatClassification(Base):
    """Immutable syntactic classification of one verified guide binding."""

    __tablename__ = "guide_source_format_classifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "content_id", "verified_replica_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.verified_replica_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_classifications_exact_binding",
        ),
        UniqueConstraint("binding_id", name="uq_guide_classifications_binding"),
        UniqueConstraint(
            "id",
            "binding_id",
            "content_id",
            "setup_generation",
            name="uq_guide_classifications_extraction_lineage",
        ),
        CheckConstraint(
            "status in ('classified', 'unsupported', 'ambiguous', 'malformed', 'limit_exceeded')",
            name="ck_guide_classifications_status",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="sha256"),
            name="ck_guide_source_format_classifications_sha256_shape",
        ),
        CheckConstraint(
            "byte_count >= 0",
            name="ck_guide_source_format_classifications_byte_count_nonnegative",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    verified_replica_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_format: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    detector_name: Mapped[str] = mapped_column(String(100), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    classification_facts: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceArtifactIncident(Base):
    """Bounded ART-owned custody failure for one exact guide read."""

    __tablename__ = "guide_source_artifact_incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "content_id", "verified_replica_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.verified_replica_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_incidents_exact_binding",
        ),
        CheckConstraint(
            "code in ('missing', 'changed', 'truncated', 'unavailable', 'stale', 'conflict')",
            name="ck_guide_incidents_code",
        ),
        CheckConstraint(
            "observed_byte_count is null or observed_byte_count >= 0",
            name="ck_guide_source_artifact_incidents_size",
        ),
        CheckConstraint(
            "observed_sha256 is null or " + SHA256_CHECK.format(column="observed_sha256"),
            name="ck_guide_source_artifact_incidents_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    verified_replica_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_sha256: Mapped[str | None] = mapped_column(String(71))
    observed_byte_count: Mapped[int | None] = mapped_column(BigInteger)
    bounded_facts: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceExtractionAttempt(Base):
    """Immutable bounded outcome for one exact extraction execution."""

    __tablename__ = "guide_source_extraction_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "content_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_extraction_attempts_exact_binding",
        ),
        ForeignKeyConstraint(
            ["classification_id", "binding_id", "content_id", "setup_generation"],
            [
                "guide_source_format_classifications.id",
                "guide_source_format_classifications.binding_id",
                "guide_source_format_classifications.content_id",
                "guide_source_format_classifications.setup_generation",
            ],
            name="fk_guide_extraction_attempts_exact_classification",
        ),
        CheckConstraint(
            "status in ('extracted','unsupported','ambiguous','malformed','limit_exceeded',"
            "'parser_failure','cancelled','artifact_incident')",
            name="ck_guide_extraction_attempts_status",
        ),
        CheckConstraint("attempt_number > 0", name="ck_guide_extraction_attempts_number"),
        CheckConstraint(
            "(status = 'extracted') = (error_code is null)",
            name="ck_guide_extraction_attempts_error",
        ),
        UniqueConstraint(
            "binding_id", "policy_version", "attempt_number", name="uq_guide_extraction_attempts"
        ),
        UniqueConstraint(
            "id",
            "binding_id",
            "content_id",
            "setup_generation",
            "status",
            name="uq_guide_extraction_attempts_exact_usage",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    classification_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_format: Mapped[str] = mapped_column(String(40), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    bounded_facts: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceExtractionRetryBudget(Base):
    """Durable two-slot materialization budget for one exact extraction lineage."""

    __tablename__ = "guide_source_extraction_retry_budgets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "content_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_extraction_retry_budgets_exact_binding",
        ),
        ForeignKeyConstraint(
            ["classification_id", "binding_id", "content_id", "setup_generation"],
            [
                "guide_source_format_classifications.id",
                "guide_source_format_classifications.binding_id",
                "guide_source_format_classifications.content_id",
                "guide_source_format_classifications.setup_generation",
            ],
            name="fk_guide_extraction_retry_budgets_exact_classification",
        ),
        CheckConstraint(
            "claimed_slots between 1 and 2",
            name="ck_guide_extraction_retry_budgets_slots",
        ),
    )

    binding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False)
    classification_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    claimed_slots: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GuideSourceExtractedContent(Base):
    """Immutable deterministic successful extraction keyed only by content semantics."""

    __tablename__ = "guide_source_extracted_contents"
    __table_args__ = (
        UniqueConstraint(
            "content_id",
            "detected_format",
            "extractor_name",
            "extractor_version",
            "policy_version",
            name="uq_guide_extracted_contents_identity",
        ),
        UniqueConstraint("id", "content_id", name="uq_guide_extracted_contents_exact_usage"),
        CheckConstraint("status = 'extracted'", name="ck_guide_extracted_contents_status"),
        CheckConstraint(
            SHA256_CHECK.format(column="source_sha256"),
            name="ck_guide_extracted_contents_source_sha256",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="output_sha256"),
            name="ck_guide_extracted_contents_output_sha256",
        ),
        CheckConstraint("source_byte_count >= 0", name="ck_guide_extracted_contents_source_size"),
        CheckConstraint(
            "octet_length(canonical_output) <= 4194304",
            name="ck_guide_extracted_contents_output_size",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_contents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    detected_format: Mapped[str] = mapped_column(String(40), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    source_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    output_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_output: Mapped[str] = mapped_column(Text, nullable=False)
    omission_facts: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuideSourceExtractionUsage(Base):
    """Exact current-lineage use of one deterministic extracted content record."""

    __tablename__ = "guide_source_extraction_usages"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "binding_id",
                "content_id",
                "source_item_id",
                "project_setup_run_id",
                "setup_generation",
            ],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.source_item_id",
                "guide_source_artifact_bindings.project_setup_run_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_extraction_usages_exact_binding",
        ),
        ForeignKeyConstraint(
            [
                "extraction_attempt_id",
                "binding_id",
                "content_id",
                "setup_generation",
                "attempt_status",
            ],
            [
                "guide_source_extraction_attempts.id",
                "guide_source_extraction_attempts.binding_id",
                "guide_source_extraction_attempts.content_id",
                "guide_source_extraction_attempts.setup_generation",
                "guide_source_extraction_attempts.status",
            ],
            name="fk_guide_extraction_usages_exact_attempt",
        ),
        ForeignKeyConstraint(
            ["extracted_content_id", "content_id"],
            ["guide_source_extracted_contents.id", "guide_source_extracted_contents.content_id"],
            name="fk_guide_extraction_usages_exact_content",
        ),
        UniqueConstraint("binding_id", "extracted_content_id", name="uq_guide_extraction_usages"),
        UniqueConstraint(
            "id",
            "source_item_id",
            "binding_id",
            "content_id",
            "extraction_attempt_id",
            "extracted_content_id",
            "project_setup_run_id",
            "setup_generation",
            name="uq_guide_extraction_usages_exact_provenance",
        ),
        CheckConstraint(
            "attempt_status = 'extracted'",
            name="ck_guide_extraction_usages_successful_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extracted_content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    extraction_attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt_status: Mapped[str] = mapped_column(String(40), nullable=False)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_setup_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    setup_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactStorageNamespace(Base):
    """Immutable singleton fencing one deployment to one storage namespace."""

    __tablename__ = "artifact_storage_namespaces"
    __table_args__ = (
        CheckConstraint("id = 'primary'", name="singleton_id"),
        CheckConstraint(
            SHA256_CHECK.format(column="namespace_fingerprint"), name="fingerprint_shape"
        ),
        UniqueConstraint(
            "namespace_fingerprint",
            name="uq_artifact_storage_namespace_fingerprint",
        ),
        UniqueConstraint(
            "id",
            "namespace_fingerprint",
            name="uq_artifact_storage_namespace_id_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    backend: Mapped[str] = mapped_column(String(50), nullable=False)
    adapter: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace_descriptor: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    namespace_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactAdmissionScope(Base):
    """Serialized durable-byte usage for one canonical admission scope."""

    __tablename__ = "artifact_admission_scopes"
    __table_args__ = (
        CheckConstraint(
            "scope_type in ('deployment', 'project', 'producer', 'task')",
            name="scope_type",
        ),
        CheckConstraint("octet_length(scope_id) between 1 and 120", name="scope_id_bounds"),
        CheckConstraint("limit_bytes > 0", name="limit_positive"),
        CheckConstraint(
            "counted_bytes >= 0 and counted_bytes <= limit_bytes",
            name="counted_bytes_within_limit",
        ),
        CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
    )

    scope_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    counted_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cas_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactAdmissionCharge(Base):
    """CAS-protected unique-byte charge for one scope and content identity."""

    __tablename__ = "artifact_admission_charges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["scope_type", "scope_id"],
            ["artifact_admission_scopes.scope_type", "artifact_admission_scopes.scope_id"],
            ondelete="RESTRICT",
            name="fk_artifact_admission_charges_scope",
        ),
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "sha256",
            "byte_count",
            name="uq_artifact_admission_charge_scope_content",
        ),
        CheckConstraint(SHA256_CHECK.format(column="sha256"), name="sha256_shape"),
        CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        CheckConstraint(
            "producer_type in ('actor_profile', 'service_identity')",
            name="producer_type",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="creating_operation_identity"),
            name="operation_identity_shape",
        ),
        CheckConstraint(
            "state in ('provisional', 'completed', 'released')",
            name="state",
        ),
        CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        CheckConstraint(
            "(state = 'completed') = (completed_at is not null)",
            name="completed_timestamp",
        ),
        CheckConstraint(
            "(state = 'released') = (released_at is not null)",
            name="released_timestamp",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    producer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    producer_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    creating_operation_identity: Mapped[str] = mapped_column(String(71), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="provisional")
    cas_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactPutAttempt(Base):
    """Durable pre-I/O commitment created only after complete admission."""

    __tablename__ = "artifact_put_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storage_namespace_id", "namespace_fingerprint"],
            ["artifact_storage_namespaces.id", "artifact_storage_namespaces.namespace_fingerprint"],
            ondelete="RESTRICT",
            name="fk_artifact_put_attempts_namespace_fingerprint",
        ),
        UniqueConstraint("operation_identity", name="uq_artifact_put_attempt_operation"),
        CheckConstraint(
            "producer_request_type in ('guide', 'checker_output', 'submission_bundle')",
            name="producer_request_type",
        ),
        CheckConstraint(
            "producer_type in ('actor_profile', 'service_identity')",
            name="producer_type",
        ),
        CheckConstraint(
            "((producer_request_type = 'guide' "
            "and producer_type = 'actor_profile' and "
            + UUID_CHECK.format(column="producer_ref")
            + ") or (producer_request_type = 'checker_output' "
            "and producer_type = 'service_identity' "
            "and producer_ref = 'workstream.artifact.checker_output') or "
            "(producer_request_type = 'submission_bundle' "
            "and producer_type = 'actor_profile' and "
            + UUID_CHECK.format(column="producer_ref")
            + "))",
            name="producer_identity",
        ),
        CheckConstraint(SHA256_CHECK.format(column="sha256"), name="sha256_shape"),
        CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        CheckConstraint(
            "canonical_target ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{62}$'",
            name="canonical_target_shape",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="operation_identity"),
            name="operation_identity_shape",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="request_digest"),
            name="request_digest_shape",
        ),
        CheckConstraint(
            "status in ('prepared', 'put_in_flight', 'acknowledgement_unknown', "
            "'object_confirmed', 'absent_replay_required', 'integrity_mismatch', "
            "'provider_unavailable', 'conflict')",
            name="status",
        ),
        CheckConstraint(
            "(executor_id is null) = (lease_expires_at is null)",
            name="executor_lease_pair",
        ),
        CheckConstraint(
            "(status = 'put_in_flight') = (executor_id is not null)",
            name="inflight_fence",
        ),
        CheckConstraint(
            "execution_generation >= 0 and cas_version >= 0",
            name="versions_nonnegative",
        ),
        CheckConstraint(
            "observation_count >= 0 and maximum_observations > 0",
            name="observation_counts",
        ),
        CheckConstraint(
            "execution_mode is null or execution_mode in ('caller_put', 'observation')",
            name="execution_mode",
        ),
        CheckConstraint(
            "status != 'provider_unavailable' or "
            "(observation_count >= maximum_observations and next_run_at is null "
            "and terminal_at is not null)",
            name="unavailable_exhausted",
        ),
        CheckConstraint(
            "status != 'prepared' or (next_run_at is null and executor_id is null "
            "and lease_expires_at is null "
            "and execution_generation = 0 and terminal_result_code is null "
            "and terminal_at is null and replica_id is null and receipt_id is null)",
            name="prepared_execution_inactive",
        ),
        CheckConstraint(
            "(producer_request_type = 'guide' and guide_source_item_id is not null "
            "and checker_run_id is null and task_id is null "
            "and logical_role is null) or "
            "(producer_request_type = 'checker_output' and guide_source_item_id is null "
            "and checker_run_id is not null and task_id is not null "
            "and octet_length(logical_role) between 1 and 100) or "
            "(producer_request_type = 'submission_bundle' "
            "and guide_source_item_id is null and checker_run_id is null "
            "and task_id is not null and logical_role is null)",
            name="producer_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    producer_request_type: Mapped[str] = mapped_column(String(30), nullable=False)
    producer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    producer_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), index=True
    )
    guide_source_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("guide_source_snapshot_items.id", ondelete="RESTRICT"), index=True
    )
    checker_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("checker_runs.id", ondelete="RESTRICT"), index=True
    )
    logical_role: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_namespace_id: Mapped[str] = mapped_column(String(20), nullable=False)
    namespace_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_target: Mapped[str] = mapped_column(String(1024), nullable=False)
    operation_identity: Mapped[str] = mapped_column(String(71), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="prepared", index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    executor_id: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    execution_mode: Mapped[str | None] = mapped_column(String(20))
    observation_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    maximum_observations: Mapped[int] = mapped_column(BigInteger, nullable=False, default=5)
    terminal_result_code: Mapped[str | None] = mapped_column(String(100))
    replica_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_replicas.id", ondelete="RESTRICT"), index=True
    )
    receipt_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_operation_receipts.id", ondelete="RESTRICT"), index=True
    )
    cas_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SubmissionBundleDurableIntent(Base):
    """Immutable join fencing one passing evidence set to one provider intent."""

    __tablename__ = "submission_bundle_durable_intents"
    __table_args__ = (
        UniqueConstraint(
            "pre_submit_evidence_set_id",
            name="uq_submission_bundle_intent_evidence",
        ),
        UniqueConstraint(
            "put_attempt_id",
            name="uq_submission_bundle_intent_put_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pre_submit_evidence_set_id: Mapped[str] = mapped_column(
        ForeignKey("pre_submit_evidence_sets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    put_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SubmissionBundleAdmission(Base):
    """Immutable verified submission-bundle lineage awaiting TASK consumption."""

    __tablename__ = "submission_bundle_admissions"
    __table_args__ = (
        UniqueConstraint("durable_intent_id", name="uq_submission_bundle_admission_intent"),
        UniqueConstraint(
            "pre_submit_evidence_set_id", name="uq_submission_bundle_admission_evidence"
        ),
        UniqueConstraint(
            "verification_receipt_id", name="uq_submission_bundle_admission_verification"
        ),
        Index(
            "uq_submission_bundle_admission_consumer",
            "consumed_by_submission_id",
            unique=True,
            postgresql_where=text("consumed_by_submission_id is not null"),
        ),
        CheckConstraint("status in ('ready','consumed','stale')", name="status"),
        CheckConstraint(
            SHA256_CHECK.format(column="locked_policy_context_hash"),
            name="policy_context_hash",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="semantic_manifest_sha256"), name="manifest_sha256"
        ),
        CheckConstraint(SHA256_CHECK.format(column="archive_sha256"), name="archive_sha256"),
        CheckConstraint("archive_byte_count >= 0", name="archive_size"),
        CheckConstraint(
            "(predecessor_submission_id is null) = (predecessor_submission_version is null)",
            name="predecessor_shape",
        ),
        CheckConstraint(
            "((put_operation_receipt_id is not null)::int + "
            "(put_observation_receipt_id is not null)::int) = 1",
            name="write_receipt_shape",
        ),
        CheckConstraint(
            "(status='ready' and consumed_at is null and consumed_by_submission_id is null "
            "and consumed_by_submission_version is null "
            "and stale_at is null and stale_reason is null) or "
            "(status='consumed' and consumed_at is not null and "
            "consumed_by_submission_id is not null and consumed_by_submission_version > 0 "
            "and stale_at is null and stale_reason is null) or "
            "(status='stale' and consumed_at is null and consumed_by_submission_id is null "
            "and consumed_by_submission_version is null "
            "and stale_at is not null and octet_length(stale_reason) between 1 and 500)",
            name="terminal_shape",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    durable_intent_id: Mapped[str] = mapped_column(
        ForeignKey("submission_bundle_durable_intents.id", ondelete="RESTRICT"), nullable=False
    )
    pre_submit_evidence_set_id: Mapped[str] = mapped_column(
        ForeignKey("pre_submit_evidence_sets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    put_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_content_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_contents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    verified_replica_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_replicas.id", ondelete="RESTRICT"), nullable=False
    )
    verification_receipt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_verification_receipts.id", ondelete="RESTRICT"), nullable=False
    )
    put_operation_receipt_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_operation_receipts.id", ondelete="RESTRICT")
    )
    put_observation_receipt_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_put_observation_receipts.id", ondelete="RESTRICT")
    )
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    identity_link_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identity_links.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("task_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    predecessor_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT")
    )
    predecessor_submission_version: Mapped[int | None] = mapped_column(Integer)
    locked_policy_context_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    semantic_manifest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    semantic_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    archive_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    archive_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready", index=True)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT")
    )
    consumed_by_submission_version: Mapped[int | None] = mapped_column(Integer)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArtifactPutAttemptCharge(Base):
    """Immutable link from one put attempt to every required scope charge."""

    __tablename__ = "artifact_put_attempt_charges"

    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    charge_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_admission_charges.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactReplica(Base):
    """Provider observation record for one immutable content object."""

    __tablename__ = "artifact_replicas"
    __table_args__ = (
        UniqueConstraint(
            "storage_namespace_id",
            "provider_object_ref",
            name="uq_artifact_replica_provider_object",
        ),
        UniqueConstraint("id", "content_id", name="uq_artifact_replicas_id_content"),
        CheckConstraint(
            "verification_state in ('pending', 'verified', 'missing', 'integrity_mismatch')",
            name="verification_state",
        ),
        CheckConstraint(
            "availability_state in ('unknown', 'available', 'unavailable')",
            name="availability_state",
        ),
        CheckConstraint(
            "integrity_state in ('unknown', 'valid', 'invalid')",
            name="integrity_state",
        ),
        CheckConstraint(
            SHA256_CHECK.format(column="namespace_fingerprint"), name="fingerprint_shape"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_contents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    storage_namespace_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_storage_namespaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    namespace_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    adapter: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_object_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    verification_state: Mapped[str] = mapped_column(String(30), nullable=False)
    availability_state: Mapped[str] = mapped_column(String(30), nullable=False)
    integrity_state: Mapped[str] = mapped_column(String(30), nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactOperationReceipt(Base):
    """Append-only Workstream evidence for one immutable put acknowledgement."""

    __tablename__ = "artifact_operation_receipts"
    __table_args__ = (
        UniqueConstraint("put_attempt_id", name="uq_artifact_receipt_put_attempt"),
        CheckConstraint(SHA256_CHECK.format(column="request_digest"), name="request_digest_shape"),
        CheckConstraint("operation = 'put'", name="operation"),
        CheckConstraint("outcome = 'stored_pending_verification'", name="outcome"),
        CheckConstraint("attempt_number > 0", name="attempt_positive"),
        CheckConstraint(
            "contract_version = 2 and put_attempt_id is not null and "
            "((guide_source_item_id is not null and checker_run_id is null "
            "and logical_role is null) or "
            "(guide_source_item_id is null and checker_run_id is not null "
            "and octet_length(logical_role) between 1 and 100) or "
            "(guide_source_item_id is null and checker_run_id is null "
            "and logical_role is null))",
            name="contract_producer_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    put_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    guide_source_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("guide_source_snapshot_items.id", ondelete="RESTRICT"), index=True
    )
    checker_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("checker_runs.id", ondelete="RESTRICT"), index=True
    )
    logical_role: Mapped[str | None] = mapped_column(String(100))
    replica_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_replicas.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    provider_object_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    replayed: Mapped[bool] = mapped_column(nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactPutObservationReceipt(Base):
    """Append-only typed evidence for one read-only put observation."""

    __tablename__ = "artifact_put_observation_receipts"
    __table_args__ = (
        UniqueConstraint(
            "put_attempt_id", "execution_generation", name="uq_artifact_put_observation_fence"
        ),
        CheckConstraint(
            "outcome in ('observed_confirmed', 'observed_missing', "
            "'observed_integrity_mismatch', 'conflict')",
            name="outcome",
        ),
        CheckConstraint(SHA256_CHECK.format(column="expected_sha256"), name="expected_sha256"),
        CheckConstraint(
            "observed_sha256 is null or " + SHA256_CHECK.format(column="observed_sha256"),
            name="observed_sha256",
        ),
        CheckConstraint("expected_byte_count >= 0", name="expected_size"),
        CheckConstraint(
            "observed_byte_count is null or observed_byte_count >= 0", name="observed_size"
        ),
        CheckConstraint(
            "(outcome in ('observed_confirmed', 'observed_integrity_mismatch')) = "
            "(observed_sha256 is not null and observed_byte_count is not null)",
            name="observed_facts",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    put_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    execution_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    expected_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_sha256: Mapped[str | None] = mapped_column(String(71))
    observed_byte_count: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactVerificationJob(Base):
    """Durable complete-object observation with lease and generation fencing."""

    __tablename__ = "artifact_verification_jobs"
    __table_args__ = (
        UniqueConstraint("parent_verification_job_id", name="uq_artifact_verification_parent"),
        CheckConstraint(
            "status in ('pending', 'running', 'verified', 'missing', "
            "'integrity_mismatch', 'provider_unavailable', 'conflict')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0 and maximum_attempts > 0", name="attempts"),
        CheckConstraint("execution_generation >= 0 and cas_version >= 0", name="versions"),
        CheckConstraint("(executor_id is null) = (lease_expires_at is null)", name="fence_pair"),
        CheckConstraint("(status = 'running') = (executor_id is not null)", name="running_fence"),
        CheckConstraint(
            "status != 'provider_unavailable' or "
            "((next_run_at is not null and terminal_at is null and attempt_count < maximum_attempts) "
            "or (next_run_at is null and terminal_at is not null and attempt_count >= maximum_attempts))",
            name="unavailable_retryability",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    originating_put_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parent_verification_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_verification_jobs.id", ondelete="RESTRICT"), index=True
    )
    replica_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_replicas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    executor_id: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cas_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    terminal_result_code: Mapped[str | None] = mapped_column(String(100))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index(
    "uq_artifact_verification_initial_origin",
    ArtifactVerificationJob.originating_put_attempt_id,
    unique=True,
    postgresql_where=ArtifactVerificationJob.parent_verification_job_id.is_(None),
)


class ArtifactRecoveryAttempt(Base):
    """Reason-bound idempotent envelope around one verification retry job."""

    __tablename__ = "artifact_recovery_attempts"
    __table_args__ = (
        UniqueConstraint(
            "requester_actor_profile_id",
            "source_verification_job_id",
            "recovery_class",
            "client_idempotency_key",
            name="uq_artifact_recovery_idempotency",
        ),
        UniqueConstraint("source_verification_job_id", name="uq_artifact_recovery_source_job"),
        UniqueConstraint("retry_verification_job_id", name="uq_artifact_recovery_retry_job"),
        CheckConstraint(
            "source_verification_job_id <> retry_verification_job_id",
            name="distinct_jobs",
        ),
        CheckConstraint("recovery_class = 'provider_observation'", name="recovery_class"),
        CheckConstraint("status in ('requested', 'succeeded', 'failed')", name="status"),
        CheckConstraint(SHA256_CHECK.format(column="request_digest"), name="request_digest"),
        CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        CheckConstraint(
            "(status = 'requested' and terminal_result_code is null and terminal_at is null "
            "and terminal_audit_event_id is null) or "
            "(status in ('succeeded', 'failed') and terminal_result_code is not null "
            "and terminal_at is not null and terminal_audit_event_id is not null)",
            name="terminal_shape",
        ),
        CheckConstraint(
            "(status = 'succeeded' and terminal_result_code = 'verified') or "
            "(status = 'failed' and terminal_result_code in "
            "('provider_unavailable', 'missing', 'integrity_mismatch', 'conflict')) or "
            "status = 'requested'",
            name="terminal_result",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requester_actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requester_identity_link_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identity_links.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    authorization_correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="RESTRICT"), index=True
    )
    source_verification_job_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_verification_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    retry_verification_job_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_verification_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    parent_recovery_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_recovery_attempts.id", ondelete="RESTRICT"), index=True
    )
    recovery_class: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    client_idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    terminal_result_code: Mapped[str | None] = mapped_column(String(40))
    initiation_audit_event_id: Mapped[str] = mapped_column(
        ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    terminal_audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="RESTRICT")
    )
    cas_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactVerificationReceipt(Base):
    """Append-only result of one fenced complete-object observation."""

    __tablename__ = "artifact_verification_receipts"
    __table_args__ = (
        UniqueConstraint(
            "verification_job_id", "execution_generation", name="uq_artifact_verification_fence"
        ),
        CheckConstraint(
            "outcome in ('verified', 'missing', 'integrity_mismatch', 'conflict')",
            name="outcome",
        ),
        CheckConstraint(
            "observed_sha256 is null or " + SHA256_CHECK.format(column="observed_sha256"),
            name="observed_sha256",
        ),
        CheckConstraint(
            "observed_byte_count is null or observed_byte_count >= 0", name="observed_size"
        ),
        CheckConstraint(
            "(outcome in ('verified', 'integrity_mismatch')) = "
            "(observed_sha256 is not null and observed_byte_count is not null)",
            name="observed_facts",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    verification_job_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_verification_jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    execution_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_sha256: Mapped[str | None] = mapped_column(String(71))
    observed_byte_count: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index(
    "ix_artifact_bindings_scope",
    ArtifactBinding.project_id,
    ArtifactBinding.resource_type,
    ArtifactBinding.resource_id,
    ArtifactBinding.logical_role,
    ArtifactBinding.scope_version.desc(),
)
