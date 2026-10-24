"""SQLAlchemy models for durable checker runs and checker results."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Uuid
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text

from app.db.base import Base


class ExternalCheckerRegistryEntryRecord(Base):
    """Immutable authorized external-image registry publication."""

    __tablename__ = "external_checker_registry_entries"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and "
            "(get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint(
            "registration_operation_id",
            name="registry_operation",
        ),
        UniqueConstraint(
            "capability_id", "capability_version", "phase",
            name="registry_identity",
        ),
        UniqueConstraint("entry_digest", name="registry_digest"),
        UniqueConstraint(
            "authorization_decision_event_id", name="registry_authority"
        ),
        CheckConstraint(
            "capability_id ~ '^[a-z][a-z0-9_.-]{0,99}$' and "
            "capability_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$'",
            name="identifiers",
        ),
        CheckConstraint("phase in ('pre_submit','post_submit')", name="phase"),
        CheckConstraint(
            "image_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "configuration_schema_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "input_schema_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "output_schema_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "entry_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="sha256_shapes",
        ),
        CheckConstraint(
            "configuration_schema_id ~ '^[a-z][a-z0-9_.-]{0,99}$' and "
            "configuration_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$' and "
            "input_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$' and "
            "output_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$'",
            name="schema_identifiers",
        ),
        CheckConstraint(
            "(phase='pre_submit' and input_schema_id='external_checker_pre_submit_input') or "
            "(phase='post_submit' and input_schema_id='external_checker_post_submit_input')",
            name="input_schema_phase",
        ),
        CheckConstraint(
            "output_schema_id='external_checker_result'",
            name="output_schema",
        ),
        CheckConstraint(
            "jsonb_typeof(configuration_schema_document)='object' and "
            "jsonb_typeof(input_schema_document)='object' and "
            "jsonb_typeof(output_schema_document)='object' and "
            "octet_length(convert_to(public.external_checker_registry_canonical_json("
            "configuration_schema_document),'UTF8'))<=65536 and "
            "octet_length(convert_to(public.external_checker_registry_canonical_json("
            "input_schema_document),'UTF8'))<=65536 and "
            "octet_length(convert_to(public.external_checker_registry_canonical_json("
            "output_schema_document),'UTF8'))<=65536",
            name="schema_documents",
        ),
        CheckConstraint(
            "cpu_millis between 100 and 64000 and "
            "memory_bytes between 16777216 and 68719476736 and "
            "deadline_ms between 100 and 3600000 and "
            "maximum_output_bytes between 256 and 65536",
            name="resource_limits",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    registration_operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    capability_id: Mapped[str] = mapped_column(String(100), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(50), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    configuration_schema_id: Mapped[str] = mapped_column(String(100), nullable=False)
    configuration_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    configuration_schema_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    configuration_schema_document: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    input_schema_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_schema_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    input_schema_document: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    output_schema_id: Mapped[str] = mapped_column(String(100), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    output_schema_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    output_schema_document: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    cpu_millis: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deadline_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_output_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    registered_by_actor_profile_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("actor_profiles.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    authorization_decision_event_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CheckerRun(Base):
    """Durable post-submit checker execution bound to one submission version."""

    __tablename__ = "checker_runs"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["project_id", "locked_guide_version", "locked_review_policy_id",
             "locked_review_policy_generation", "locked_review_policy_hash"],
            ["review_policies.project_id", "review_policies.guide_version", "review_policies.id",
             "review_policies.policy_generation", "review_policies.policy_hash"],
            name="fk_checker_runs_review_policy_lineage",
        ),
        ForeignKeyConstraint(
            ["project_id", "locked_guide_version", "locked_revision_policy_id",
             "locked_revision_policy_generation", "locked_revision_policy_hash"],
            ["revision_policies.project_id", "revision_policies.guide_version", "revision_policies.id",
             "revision_policies.policy_generation", "revision_policies.policy_hash"],
            name="fk_checker_runs_revision_policy_lineage",
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
        CheckConstraint(
            "(selected_post_submit_policy_sha256 is null and "
            "selected_post_submit_policy_body is null) or "
            "(selected_post_submit_policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "jsonb_typeof(selected_post_submit_policy_body)='object')",
            name="selected_post_submit_policy",
        ),
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
    input_context_custody: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
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
    selected_post_submit_policy_sha256: Mapped[str | None] = mapped_column(String(71))
    selected_post_submit_policy_body: Mapped[dict | None] = mapped_column(JSONB)
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


class CheckerTrialEvidence(Base):
    """One immutable trial address and its first authorized receipt commitment."""

    __tablename__ = "checker_trial_evidence"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and "
            "(get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7",
        ),
        UniqueConstraint("address_digest", name="uq_checker_trial_evidence_address"),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_checker_trial_evidence_task_project",
        ),
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_checker_trial_evidence_submission",
        ),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_checker_trial_evidence_origin",
        ),
        CheckConstraint("maximum_bytes between 1 and 1048576", name="bounded_receipt"),
        CheckConstraint(
            "jsonb_typeof(subject)='object' and jsonb_typeof(origin)='object'",
            name="closed_facts",
        ),
        CheckConstraint(
            "address_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "(content_sha256 is null or content_sha256 ~ '^sha256:[0-9a-f]{64}$')",
            name="digest_shapes",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("task_assignments.id"), nullable=False,
    )
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    checker_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    registry_entry_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("external_checker_registry_entries.id"), nullable=False,
    )
    address_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    subject: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    origin: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    maximum_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(71))
    execute_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False,
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


class CheckerResultFinding(Base):
    """One immutable finding of one checker member, copied from the stored result."""

    __tablename__ = "checker_result_findings"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_checker_result_findings_run_ownership",
        ),
        ForeignKeyConstraint(
            ["checker_result_id"], ["checker_results.id"],
            name="fk_checker_result_findings_member",
        ),
        UniqueConstraint(
            "checker_result_id", "finding_order", name="uq_checker_result_findings_order"
        ),
        CheckConstraint("member_order between 0 and 8", name="member_order"),
        CheckConstraint("finding_order between 0 and 255", name="finding_order"),
        CheckConstraint(
            "level in ('info','warning','error','coverage_incomplete')", name="level"
        ),
        CheckConstraint(
            "line is null or (path is not null and line between 1 and 10000000)",
            name="location",
        ),
        Index(
            "ix_checker_result_findings_submission_level",
            "submission_id", "checker_run_id", "level",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    checker_result_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    checker_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    member_order: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_order: Mapped[int] = mapped_column(Integer, nullable=False)
    check_id: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    path: Mapped[str | None] = mapped_column(String(1000))
    line: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CheckerSubmissionFence(Base):
    """The sole current request for a submission; never a second result store."""

    __tablename__ = "checker_submission_fences"
    __table_args__ = (
        ForeignKeyConstraint(["current_run_id", "submission_id"], ["checker_runs.id", "checker_runs.submission_id"],
                             name="fk_checker_submission_fences_run"),
    )
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), primary_key=True)
    current_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, unique=True)


class CheckerRetryReceipt(Base):
    """Immutable Operator decision and exact successor of one failed source run."""

    __tablename__ = "checker_retry_receipts"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        CheckConstraint("successor_generation = source_generation + 1 and source_generation > 0", name="generation"),
        CheckConstraint("length(reason) between 1 and 500 and reason !~ '[[:cntrl:]]'", name="reason"),
        CheckConstraint("source_request_digest ~ '^sha256:[0-9a-f]{64}$' and source_result_digest ~ '^sha256:[0-9a-f]{64}$' and successor_request_digest ~ '^sha256:[0-9a-f]{64}$' and resource_digest ~ '^sha256:[0-9a-f]{64}$'", name="digests"),
        CheckConstraint("octet_length(resource_json) <= 8192 and resource_json = public.project_guide_projection_canonical_json(resource_json::jsonb) and resource_digest = 'sha256:' || encode(sha256(convert_to(resource_json, 'UTF8')), 'hex')", name="resource_json_digest"),
        UniqueConstraint("actor_profile_id", "request_key", name="uq_checker_retry_actor_key"),
        UniqueConstraint("source_run_id", name="uq_checker_retry_source"),
        UniqueConstraint("successor_run_id", name="uq_checker_retry_successor"),
        UniqueConstraint("event_id", name="uq_checker_retry_event"),
        UniqueConstraint("audit_event_id", name="uq_checker_retry_audit"),
        ForeignKeyConstraint(["source_run_id", "task_id", "submission_id"],
                             ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
                             name="fk_checker_retry_source_ownership"),
        ForeignKeyConstraint(["successor_run_id", "task_id", "submission_id"],
                             ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
                             name="fk_checker_retry_successor_ownership"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("actor_profiles.id"), nullable=False)
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("actor_identity_links.id"), nullable=False)
    request_key: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("task_assignments.id"), nullable=False)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("submissions.id"), nullable=False)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    source_request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    source_request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    source_result_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    source_result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    source_finalize_evidence_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id"), nullable=False)
    source_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str] = mapped_column(String(100), nullable=False)
    successor_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    successor_request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    successor_request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    successor_result_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    successor_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("outbox_events.event_id"), nullable=False)
    audit_event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id"), nullable=False)
    authorization_decision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("audit_events.id"), nullable=False)
    resource_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SelectedPreSubmitRun(Base):
    """Durable selected PRE lease and terminal facts before any Submission exists."""

    __tablename__ = "selected_pre_submit_runs"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and "
            "(get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_selected_pre_run_task_project",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "task_id", "actor_profile_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_selected_pre_run_assignment",
        ),
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_selected_pre_run_actor_link",
        ),
        CheckConstraint(
            "status in ('queued','running','completed','infrastructure_failed')",
            name="status",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "default_behavior_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "default_input_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "archive_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "semantic_manifest_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "(terminal_digest is null or terminal_digest ~ '^sha256:[0-9a-f]{64}$')",
            name="digests",
        ),
        CheckConstraint("archive_byte_count > 0", name="archive_size"),
        CheckConstraint(
            "execution_budget_ms between 100 and 14400000",
            name="execution_budget",
        ),
        CheckConstraint("lease_generation >= 0", name="lease_generation"),
        CheckConstraint(
            "(status='queued' and lease_id is null and lease_expires_at is null "
            "and terminal_json is null and terminal_digest is null and eligible is null "
            "and started_at is null and completed_at is null "
            "and execute_evidence_id is null and finalize_evidence_id is null) or "
            "(status='running' and lease_id is not null and lease_generation > 0 "
            "and lease_expires_at is not null and terminal_json is null "
            "and terminal_digest is null and eligible is null and started_at is not null "
            "and completed_at is null "
            "and execute_evidence_id is not null and finalize_evidence_id is null) or "
            "(status='completed' and lease_id is not null and lease_generation > 0 "
            "and lease_expires_at is not null and terminal_json is not null "
            "and terminal_digest is not null and eligible is not null "
            "and started_at is not null and completed_at is not null "
            "and execute_evidence_id is not null and finalize_evidence_id is not null) or "
            "(status='infrastructure_failed' and lease_id is not null "
            "and lease_generation > 0 and lease_expires_at is not null "
            "and terminal_json is not null and terminal_digest is not null "
            "and eligible is null and started_at is not null and completed_at is not null "
            "and execute_evidence_id is not null and finalize_evidence_id is not null)",
            name="lifecycle",
        ),
        CheckConstraint(
            "jsonb_typeof(request_json)='object' and "
            "(terminal_json is null or jsonb_typeof(terminal_json)='object')",
            name="json_objects",
        ),
        UniqueConstraint("request_digest", name="request_digest"),
        UniqueConstraint(
            "actor_profile_id",
            "idempotency_key",
            name="uq_selected_pre_run_actor_key",
        ),
        Index("ix_selected_pre_runs_task", "task_id"),
        Index("ix_selected_pre_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    prepared_generation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    default_behavior_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    default_input_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    archive_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    archive_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    semantic_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    execution_budget_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    lease_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execute_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
    )
    finalize_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
    )
    terminal_json: Mapped[dict | None] = mapped_column(JSONB())
    terminal_digest: Mapped[str | None] = mapped_column(String(71))
    eligible: Mapped[bool | None] = mapped_column(Boolean)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# A project's preparation list reads newest first by (queued_at, id).
Index(
    "ix_selected_pre_submit_runs_project_queued",
    SelectedPreSubmitRun.project_id,
    SelectedPreSubmitRun.queued_at.desc(),
    SelectedPreSubmitRun.id.desc(),
)
