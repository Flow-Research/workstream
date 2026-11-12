"""ART-owned durable foreground and accepted source custody."""

from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer,
    String, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SubmissionIntakeOperation(Base):
    """One immutable command/source with a fenced, non-resumable foreground owner.

    Accepted custody retains the source and task pointer for durable finalization.
    This table grants no provider capability.
    """

    __tablename__ = "submission_intake_operations"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        UniqueConstraint("id", "task_id", name="uq_submission_intake_task_identity"),
        UniqueConstraint("actor_profile_id", "idempotency_key", name="uq_submission_intake_actor_key"),
        UniqueConstraint("namespace_id", "namespace_fingerprint", "object_ref", name="uq_submission_intake_source_key"),
        ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"], name="fk_submission_intake_task", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["assignment_id", "task_id", "actor_profile_id"], ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"], name="fk_submission_intake_assignment", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["identity_link_id", "actor_profile_id"], ["actor_identity_links.id", "actor_identity_links.actor_profile_id"], name="fk_submission_intake_identity", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["namespace_id", "namespace_fingerprint"], ["artifact_storage_namespaces.id", "artifact_storage_namespaces.namespace_fingerprint"], name="fk_submission_intake_namespace"),
        CheckConstraint("state in ('receiving','pre_checking','finalization_pending','rejected','failed','abandoned','cancelled')", name="foreground_state"),
        CheckConstraint("eligible_task_status in ('in_progress','needs_revision')", name="eligible_status"),
        CheckConstraint("metadata_sha256 ~ '^sha256:[0-9a-f]{64}$' and locked_context_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="identity_digests"),
        CheckConstraint("jsonb_typeof(command_metadata)='object' and jsonb_typeof(locked_task_context)='object'", name="command_shape"),
        CheckConstraint("object_ref='submission-source/v1/'||id::text||'/bundle.zip'", name="source_key"),
        CheckConstraint("maximum_raw_bytes between 1 and 524288000", name="raw_limit"),
        CheckConstraint("lease_generation>0 and lease_expires_at<=coalesce(pre_deadline_at,upload_deadline_at) and upload_deadline_at>created_at", name="lease_bounds"),
        CheckConstraint("(raw_sha256 is null and raw_byte_count is null and eof_at is null) or (raw_sha256 is not null and raw_sha256 ~ '^sha256:[0-9a-f]{64}$' and raw_byte_count is not null and raw_byte_count between 1 and maximum_raw_bytes and eof_at is not null)", name="eof_identity"),
        CheckConstraint("(provider_generation is null and sealed_upload_fence is null and sealed_at is null and pre_deadline_at is null) or (provider_generation is not null and sealed_upload_fence is not null and sealed_upload_fence>0 and length(provider_generation)>0 and raw_sha256 is not null and sealed_at is not null and sealed_at>=eof_at and pre_deadline_at is not null and pre_deadline_at>sealed_at and (provider_profile<>'aws-s3-v1' or provider_generation<>'null'))", name="sealed_identity"),
        CheckConstraint("state not in ('pre_checking','finalization_pending') or sealed_at is not null", name="pre_requires_source"),
        CheckConstraint("(state in ('receiving','pre_checking','finalization_pending') and terminal_at is null and failure_code is null) or (state in ('rejected','failed','abandoned','cancelled') and terminal_at is not null and failure_code is not null)", name="terminal_shape"),
        ForeignKeyConstraint(["acceptance_decision_id"], ["audit_events.id"], name="fk_intake_acceptance_decision", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["selected_pre_submit_run_id"], ["selected_pre_submit_runs.id"], name="fk_intake_accepted_pre_run", deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["finalization_event_id"], ["outbox_events.event_id"], name="fk_intake_finalization_event", deferrable=True, initially="DEFERRED"),
        CheckConstraint("(state='finalization_pending' and accepted_at is not null and acceptance_decision_id is not null and selected_pre_submit_run_id is not null and selected_pre_submit_request_sha256 is not null and selected_pre_submit_terminal_sha256 is not null and accepted_source_sha256 is not null and accepted_manifest_sha256 is not null and accepted_context is not null and accepted_context_sha256 is not null and acceptance_receipt is not null and acceptance_receipt_sha256 is not null and finalization_event_id is not null) or (state<>'finalization_pending' and accepted_at is null and acceptance_decision_id is null and selected_pre_submit_run_id is null and selected_pre_submit_request_sha256 is null and selected_pre_submit_terminal_sha256 is null and accepted_source_sha256 is null and accepted_manifest_sha256 is null and accepted_context is null and accepted_context_sha256 is null and acceptance_receipt is null and acceptance_receipt_sha256 is null and finalization_event_id is null)", name="acceptance_shape"),
        UniqueConstraint("selected_pre_submit_run_id", name="uq_intake_accepted_pre_run"),
        UniqueConstraint("acceptance_decision_id", name="uq_intake_acceptance_decision"),
        UniqueConstraint("finalization_event_id", name="uq_intake_finalization_event"),
        Index("uq_submission_intake_active_task", "task_id", unique=True, postgresql_where=text("state in ('receiving','pre_checking','finalization_pending')")),
        Index("ix_submission_intake_expiry", "lease_expires_at", "id", postgresql_where=text("state in ('receiving','pre_checking')")),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    actor_profile_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    idempotency_key: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    command_metadata: Mapped[dict] = mapped_column(JSONB)
    metadata_sha256: Mapped[str] = mapped_column(String(71))
    locked_task_context: Mapped[dict] = mapped_column(JSONB)
    locked_context_sha256: Mapped[str] = mapped_column(String(71))
    eligible_task_status: Mapped[str] = mapped_column(String(30))
    namespace_id: Mapped[str] = mapped_column(String(20))
    namespace_fingerprint: Mapped[str] = mapped_column(String(71))
    provider_profile: Mapped[str] = mapped_column(String(100))
    object_ref: Mapped[str] = mapped_column(String(1024))
    maximum_raw_bytes: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(30))
    lease_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    lease_generation: Mapped[int] = mapped_column(BigInteger)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    upload_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pre_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_sha256: Mapped[str | None] = mapped_column(String(71))
    raw_byte_count: Mapped[int | None] = mapped_column(BigInteger)
    eof_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_generation: Mapped[str | None] = mapped_column(String)
    sealed_upload_fence: Mapped[int | None] = mapped_column(BigInteger)
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acceptance_decision_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    selected_pre_submit_run_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    selected_pre_submit_request_sha256: Mapped[str | None] = mapped_column(String(71))
    selected_pre_submit_terminal_sha256: Mapped[str | None] = mapped_column(String(71))
    accepted_source_sha256: Mapped[str | None] = mapped_column(String(71))
    accepted_manifest_sha256: Mapped[str | None] = mapped_column(String(71))
    accepted_context: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    accepted_context_sha256: Mapped[str | None] = mapped_column(String(71))
    acceptance_receipt: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    acceptance_receipt_sha256: Mapped[str | None] = mapped_column(String(71))
    finalization_event_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class SubmissionSourceCapacityProfile(Base):
    """One explicit source-byte allocation shared by namespace writers."""

    __tablename__ = "submission_source_capacity_profiles"
    __table_args__ = (
        ForeignKeyConstraint(["namespace_id", "namespace_fingerprint"],
                             ["artifact_storage_namespaces.id", "artifact_storage_namespaces.namespace_fingerprint"],
                             name="fk_submission_source_capacity_namespace"),
        CheckConstraint("maximum_total_bytes>0 and (maximum_project_bytes is null or maximum_project_bytes>0) "
                        "and (maximum_producer_bytes is null or maximum_producer_bytes>0) "
                        "and (maximum_task_bytes is null or maximum_task_bytes>0)", name="positive_limits"),
        CheckConstraint("configuration_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="configuration_digest"),
    )

    namespace_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    namespace_fingerprint: Mapped[str] = mapped_column(String(71))
    maximum_total_bytes: Mapped[int] = mapped_column(BigInteger)
    maximum_project_bytes: Mapped[int | None] = mapped_column(BigInteger)
    maximum_producer_bytes: Mapped[int | None] = mapped_column(BigInteger)
    maximum_task_bytes: Mapped[int | None] = mapped_column(BigInteger)
    configuration_sha256: Mapped[str] = mapped_column(String(71))


class SubmissionSourceCharge(Base):
    """Physical source obligation, retained independently of command outcome."""

    __tablename__ = "submission_source_charges"
    __table_args__ = (
        ForeignKeyConstraint(["operation_id"], ["submission_intake_operations.id"],
                             name="fk_submission_source_charge_operation"),
        CheckConstraint("reserved_bytes>0 and accounted_bytes>0 and accounted_bytes<=reserved_bytes",
                        name="positive_charge"),
        CheckConstraint("declared_raw_bytes is null or declared_raw_bytes=reserved_bytes", name="declared_reservation"),
        CheckConstraint("state in ('reserved','sealed')", name="charge_state"),
        CheckConstraint("(state='reserved' and accounted_bytes=reserved_bytes and sealed_at is null) "
                        "or (state='sealed' and sealed_at is not null)", name="charge_shape"),
    )

    operation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    declared_raw_bytes: Mapped[int | None] = mapped_column(BigInteger)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger)
    accounted_bytes: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(20))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubmissionSourceUploadReceipt(Base):
    """Operation-owned initiation and completion facts across provider I/O."""

    __tablename__ = "submission_source_upload_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["operation_id"], ["submission_intake_operations.id"],
                             name="fk_submission_source_upload_operation"),
        CheckConstraint("upload_fence>0 and part_bytes between 5242880 and 16777216 "
                        "and idle_timeout_seconds>0 and idle_timeout_seconds<'Infinity'::float8",
                        name="upload_bounds"),
        CheckConstraint("(provider_upload_id is null and handle_recorded_at is null) or "
                        "(provider_upload_id is not null and length(provider_upload_id) between 1 and 2048 "
                        "and handle_recorded_at is not null)", name="handle_shape"),
        CheckConstraint("(completion_parts is null and completion_recorded_at is null) or "
                        "(completion_parts is not null and jsonb_typeof(completion_parts)='array' "
                        "and jsonb_array_length(completion_parts) between 1 and 100 "
                        "and completion_recorded_at is not null and provider_upload_id is not null)",
                        name="completion_shape"),
    )

    operation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    upload_fence: Mapped[int] = mapped_column(BigInteger)
    part_bytes: Mapped[int] = mapped_column(Integer)
    idle_timeout_seconds: Mapped[float] = mapped_column(DOUBLE_PRECISION)
    provider_upload_id: Mapped[str | None] = mapped_column(String(2048))
    completion_parts: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    handle_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
