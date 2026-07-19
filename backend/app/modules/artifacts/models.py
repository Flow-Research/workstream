"""Provider-neutral SQLAlchemy records for immutable artifacts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


SHA256_CHECK = "{column} ~ '^sha256:[0-9a-f]{{64}}$'"
UUID_CHECK = (
    "{column} ~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[1-5][0-9a-f]{{3}}-"
    "[89ab][0-9a-f]{{3}}-[0-9a-f]{{12}}$'"
)


class ArtifactUploadSession(Base):
    """Mutable staging authority for one bounded artifact set."""

    __tablename__ = "artifact_upload_sessions"
    __table_args__ = (
        CheckConstraint(
            "state in ('open', 'sealed', 'consumed', 'expired', 'cancelled')",
            name="state",
        ),
        CheckConstraint(
            "maximum_bytes >= 0 and current_bytes >= 0 and reserved_bytes >= 0",
            name="byte_counts_nonnegative",
        ),
        CheckConstraint(
            "maximum_items >= 0 and current_items >= 0 and reserved_items >= 0",
            name="item_counts_nonnegative",
        ),
        CheckConstraint(
            "current_bytes + reserved_bytes <= maximum_bytes",
            name="byte_limit",
        ),
        CheckConstraint(
            "current_items + reserved_items <= maximum_items",
            name="item_limit",
        ),
        CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        CheckConstraint(
            "artifact_set_hash is null or " + SHA256_CHECK.format(column="artifact_set_hash"),
            name="artifact_set_hash_shape",
        ),
        CheckConstraint(
            "(state = 'consumed') = (consumed_at is not null)",
            name="consumed_timestamp",
        ),
        CheckConstraint(
            "state not in ('sealed', 'consumed') or artifact_set_hash is not null",
            name="sealed_hash_required",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    guide_id: Mapped[str | None] = mapped_column(String(36), index=True)
    permitted_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    maximum_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    current_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_items: Mapped[int] = mapped_column(Integer, nullable=False)
    current_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_set_hash: Mapped[str | None] = mapped_column(String(71))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cas_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactUploadItem(Base):
    """Per-item staging and recovery ledger under an upload session."""

    __tablename__ = "artifact_upload_items"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key", name="uq_artifact_item_operation"),
        CheckConstraint(
            "state in ('reserved', 'uploading', 'replay_required', "
            "'stored_pending_verification', 'ready', 'failed', 'cancelled')",
            name="state",
        ),
        CheckConstraint(
            "reserved_bytes >= 0 and cas_version >= 0 and "
            "(expected_size is null or expected_size >= 0)",
            name="counts_nonnegative",
        ),
        CheckConstraint(SHA256_CHECK.format(column="request_digest"), name="request_digest_shape"),
        CheckConstraint(
            "expected_sha256 is null or " + SHA256_CHECK.format(column="expected_sha256"),
            name="expected_sha256_shape",
        ),
        CheckConstraint(
            "((state in ('stored_pending_verification', 'ready')) and "
            "content_id is not null and provider_object_ref is not null) or "
            "((state not in ('stored_pending_verification', 'ready')) and "
            "content_id is null and provider_object_ref is null)",
            name="stored_result_required",
        ),
        CheckConstraint(
            "state != 'failed' or error_code is not null",
            name="failed_error_required",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_upload_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    logical_role: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(200))
    reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_sha256: Mapped[str | None] = mapped_column(String(71))
    expected_size: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="reserved", index=True)
    cas_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_object_ref: Mapped[str | None] = mapped_column(String(1024))
    content_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_contents.id", ondelete="RESTRICT"), index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
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


class ArtifactBinding(Base):
    """Immutable attachment of content to one Workstream resource role."""

    __tablename__ = "artifact_bindings"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "resource_type", "resource_id", "logical_role", "scope_version",
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


class ArtifactStorageNamespace(Base):
    """Immutable singleton fencing one deployment to one storage namespace."""

    __tablename__ = "artifact_storage_namespaces"
    __table_args__ = (
        CheckConstraint("id = 'primary'", name="singleton_id"),
        CheckConstraint(SHA256_CHECK.format(column="namespace_fingerprint"), name="fingerprint_shape"),
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
            "producer_request_type in ('guide', 'contributor', 'checker_output')",
            name="producer_request_type",
        ),
        CheckConstraint(
            "producer_type in ('actor_profile', 'service_identity')",
            name="producer_type",
        ),
        CheckConstraint(
            "((producer_request_type in ('guide', 'contributor') "
            "and producer_type = 'actor_profile' and "
            + UUID_CHECK.format(column="producer_ref")
            + ") or (producer_request_type = 'checker_output' "
            "and producer_type = 'service_identity' "
            "and producer_ref = 'workstream.artifact.checker_output'))",
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
            "execution_generation >= 0 and cas_version >= 0",
            name="versions_nonnegative",
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
            "and upload_item_id is null and checker_run_id is null and task_id is null "
            "and logical_role is null) or "
            "(producer_request_type = 'contributor' and guide_source_item_id is null "
            "and upload_item_id is not null and checker_run_id is null and task_id is not null "
            "and logical_role is null) or "
            "(producer_request_type = 'checker_output' and guide_source_item_id is null "
            "and upload_item_id is null and checker_run_id is not null and task_id is not null "
            "and octet_length(logical_role) between 1 and 100)",
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
    upload_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifact_upload_items.id", ondelete="RESTRICT"), index=True
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
        CheckConstraint(SHA256_CHECK.format(column="namespace_fingerprint"), name="fingerprint_shape"),
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
        UniqueConstraint("upload_item_id", name="uq_artifact_receipt_upload_item"),
        CheckConstraint(SHA256_CHECK.format(column="request_digest"), name="request_digest_shape"),
        CheckConstraint("operation = 'put'", name="operation"),
        CheckConstraint("outcome = 'stored_pending_verification'", name="outcome"),
        CheckConstraint("attempt_number > 0", name="attempt_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    upload_item_id: Mapped[str] = mapped_column(
        ForeignKey("artifact_upload_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
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


Index(
    "ix_artifact_bindings_scope",
    ArtifactBinding.project_id,
    ArtifactBinding.resource_type,
    ArtifactBinding.resource_id,
    ArtifactBinding.logical_role,
    ArtifactBinding.scope_version.desc(),
)
