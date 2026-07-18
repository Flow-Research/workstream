"""replace artifact provider v1 with byte-only v2

Revision ID: 0025_artifact_store_v2
Revises: 0024_service_link_verification
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0025_artifact_store_v2"
down_revision = "0024_service_link_verification"
branch_labels = depends_on = None

_ARTIFACT_TABLES = (
    "artifact_operation_receipts",
    "artifact_replicas",
    "artifact_bindings",
    "artifact_upload_items",
    "artifact_contents",
    "artifact_upload_sessions",
)


def _refuse_populated_artifact_rows(*, include_namespace: bool) -> None:
    """Refuse to invent v2 provenance or downgrade durable v2 facts."""
    connection = op.get_bind()
    tables = _ARTIFACT_TABLES + (("artifact_storage_namespaces",) if include_namespace else ())
    connection.execute(
        sa.text(f"lock table {', '.join(tables)} in access exclusive mode")
    )
    populated = [
        table_name
        for table_name in tables
        if connection.execute(
            sa.text(f"select exists(select 1 from {table_name})")
        ).scalar()
    ]
    if populated:
        raise RuntimeError("artifact storage clean cut requires empty pre-production tables")


def upgrade() -> None:
    """Install v2 only when no v1 artifact fact requires fabrication."""
    _refuse_populated_artifact_rows(include_namespace=False)

    op.create_table(
        "artifact_storage_namespaces",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("backend", sa.String(50), nullable=False),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("provider_profile", sa.String(100), nullable=False),
        sa.Column("namespace_descriptor", sa.JSON(), nullable=False),
        sa.Column("namespace_fingerprint", sa.String(71), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 'primary'", name="singleton_id"),
        sa.CheckConstraint(
            "namespace_fingerprint ~ '^sha256:[0-9a-f]{64}$'", name="fingerprint_shape"
        ),
        sa.UniqueConstraint(
            "namespace_fingerprint", name="uq_artifact_storage_namespace_fingerprint"
        ),
    )
    op.execute(
        """
        create trigger trg_artifact_storage_namespaces_immutable
        before update or delete on artifact_storage_namespaces
        for each row execute function reject_artifact_fact_mutation()
        """
    )

    op.drop_constraint(
        op.f("ck_artifact_upload_items_ready_result_required"),
        "artifact_upload_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_artifact_upload_items_state"), "artifact_upload_items", type_="check"
    )
    op.alter_column(
        "artifact_upload_items",
        "provider_operation_reference",
        new_column_name="provider_object_ref",
        type_=sa.String(1024),
        existing_type=sa.String(200),
    )
    op.create_check_constraint(
        "state",
        "artifact_upload_items",
        "state in ('reserved', 'uploading', 'replay_required', "
        "'stored_pending_verification', 'ready', 'failed', 'cancelled')",
    )
    op.create_check_constraint(
        "stored_result_required",
        "artifact_upload_items",
        "((state in ('stored_pending_verification', 'ready')) and "
        "content_id is not null and provider_object_ref is not null) or "
        "((state not in ('stored_pending_verification', 'ready')) and "
        "content_id is null and provider_object_ref is null)",
    )

    op.drop_constraint(
        op.f("uq_artifact_replica_provider"), "artifact_replicas", type_="unique"
    )
    for constraint in (
        "ck_artifact_replicas_verification_state",
        "ck_artifact_replicas_retention_state",
        "ck_artifact_replicas_availability_state",
        "ck_artifact_replicas_integrity_state",
    ):
        op.drop_constraint(op.f(constraint), "artifact_replicas", type_="check")
    op.drop_column("artifact_replicas", "retention_state")
    op.drop_column("artifact_replicas", "provider_manifest_id")
    op.alter_column(
        "artifact_replicas",
        "provider_artifact_id",
        new_column_name="provider_object_ref",
        type_=sa.String(1024),
        existing_type=sa.String(200),
    )
    op.add_column(
        "artifact_replicas", sa.Column("storage_namespace_id", sa.String(20), nullable=False)
    )
    op.add_column(
        "artifact_replicas", sa.Column("namespace_fingerprint", sa.String(71), nullable=False)
    )
    op.add_column(
        "artifact_replicas", sa.Column("provider_profile", sa.String(100), nullable=False)
    )
    op.create_foreign_key(
        op.f("fk_artifact_replicas_storage_namespace_id_artifact_storage_namespaces"),
        "artifact_replicas",
        "artifact_storage_namespaces",
        ["storage_namespace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_artifact_replicas_storage_namespace_id"),
        "artifact_replicas",
        ["storage_namespace_id"],
    )
    op.create_unique_constraint(
        op.f("uq_artifact_replica_provider_object"),
        "artifact_replicas",
        ["storage_namespace_id", "provider_object_ref"],
    )
    op.create_check_constraint(
        "verification_state",
        "artifact_replicas",
        "verification_state in ('pending', 'verified', 'missing', 'integrity_mismatch')",
    )
    op.create_check_constraint(
        "availability_state",
        "artifact_replicas",
        "availability_state in ('unknown', 'available', 'unavailable')",
    )
    op.create_check_constraint(
        "integrity_state",
        "artifact_replicas",
        "integrity_state in ('unknown', 'valid', 'invalid')",
    )
    op.create_check_constraint(
        "fingerprint_shape",
        "artifact_replicas",
        "namespace_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
    )

    op.execute("drop trigger trg_artifact_operation_receipts_immutable on artifact_operation_receipts")
    op.drop_table("artifact_operation_receipts")
    _create_v2_receipts()


def _create_v2_receipts() -> None:
    op.create_table(
        "artifact_operation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("upload_item_id", sa.String(36), nullable=False),
        sa.Column("replica_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("provider_object_ref", sa.String(1024), nullable=False),
        sa.Column("replayed", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["upload_item_id"], ["artifact_upload_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["replica_id"], ["artifact_replicas.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("upload_item_id", name="uq_artifact_receipt_upload_item"),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest_shape"
        ),
        sa.CheckConstraint("operation = 'put'", name="operation"),
        sa.CheckConstraint("outcome = 'stored_pending_verification'", name="outcome"),
        sa.CheckConstraint("attempt_number > 0", name="attempt_positive"),
    )
    op.create_index(
        "ix_artifact_operation_receipts_upload_item_id",
        "artifact_operation_receipts",
        ["upload_item_id"],
    )
    op.create_index(
        "ix_artifact_operation_receipts_replica_id",
        "artifact_operation_receipts",
        ["replica_id"],
    )
    op.execute(
        """
        create trigger trg_artifact_operation_receipts_immutable
        before update or delete on artifact_operation_receipts
        for each row execute function reject_artifact_fact_mutation()
        """
    )


def downgrade() -> None:
    """Restore the empty v1 shape without converting any v2 fact."""
    _refuse_populated_artifact_rows(include_namespace=True)

    op.execute("drop trigger trg_artifact_operation_receipts_immutable on artifact_operation_receipts")
    op.drop_table("artifact_operation_receipts")

    for constraint in (
        "ck_artifact_replicas_verification_state",
        "ck_artifact_replicas_availability_state",
        "ck_artifact_replicas_integrity_state",
        "ck_artifact_replicas_fingerprint_shape",
    ):
        op.drop_constraint(op.f(constraint), "artifact_replicas", type_="check")
    op.drop_constraint(
        op.f("uq_artifact_replica_provider_object"), "artifact_replicas", type_="unique"
    )
    op.drop_index(
        op.f("ix_artifact_replicas_storage_namespace_id"), table_name="artifact_replicas"
    )
    op.drop_constraint(
        op.f("fk_artifact_replicas_storage_namespace_id_artifact_storage_namespaces"),
        "artifact_replicas",
        type_="foreignkey",
    )
    op.drop_column("artifact_replicas", "provider_profile")
    op.drop_column("artifact_replicas", "namespace_fingerprint")
    op.drop_column("artifact_replicas", "storage_namespace_id")
    op.alter_column(
        "artifact_replicas",
        "provider_object_ref",
        new_column_name="provider_artifact_id",
        type_=sa.String(200),
        existing_type=sa.String(1024),
    )
    op.add_column(
        "artifact_replicas", sa.Column("provider_manifest_id", sa.String(200), nullable=True)
    )
    op.add_column(
        "artifact_replicas", sa.Column("retention_state", sa.String(30), nullable=False)
    )
    op.create_unique_constraint(
        "uq_artifact_replica_provider",
        "artifact_replicas",
        ["adapter", "provider_artifact_id"],
    )
    op.create_check_constraint(
        "verification_state",
        "artifact_replicas",
        "verification_state in ('pending', 'verified', 'failed')",
    )
    op.create_check_constraint(
        "retention_state",
        "artifact_replicas",
        "retention_state in ('unretained', 'retained', 'released')",
    )
    op.create_check_constraint(
        "availability_state",
        "artifact_replicas",
        "availability_state in ('available', 'unavailable', 'missing')",
    )
    op.create_check_constraint(
        "integrity_state",
        "artifact_replicas",
        "integrity_state in ('unknown', 'valid', 'quarantined')",
    )

    op.drop_constraint(
        op.f("ck_artifact_upload_items_stored_result_required"),
        "artifact_upload_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_artifact_upload_items_state"),
        "artifact_upload_items",
        type_="check",
    )
    op.alter_column(
        "artifact_upload_items",
        "provider_object_ref",
        new_column_name="provider_operation_reference",
        type_=sa.String(200),
        existing_type=sa.String(1024),
    )
    op.create_check_constraint(
        "state",
        "artifact_upload_items",
        "state in ('reserved', 'uploading', 'provider_committed', "
        "'replay_required', 'ready', 'failed', 'cancelled')",
    )
    op.create_check_constraint(
        "ready_result_required",
        "artifact_upload_items",
        "(state = 'ready') = "
        "(content_id is not null and provider_operation_reference is not null)",
    )

    op.execute("drop trigger trg_artifact_storage_namespaces_immutable on artifact_storage_namespaces")
    op.drop_table("artifact_storage_namespaces")
    _create_v1_receipts()


def _create_v1_receipts() -> None:
    """Restore the exact empty receipt shape expected by migration 0016."""
    op.create_table(
        "artifact_operation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("upload_item_id", sa.String(36), nullable=True),
        sa.Column("replica_id", sa.String(36), nullable=True),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("service_principal", sa.String(200), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("response_digest", sa.String(71), nullable=False),
        sa.Column("provider_receipt_id", sa.String(200), nullable=False),
        sa.Column("provider_operation_reference", sa.String(200), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("retention_reference", sa.String(200), nullable=True),
        sa.Column("retention_class", sa.String(100), nullable=True),
        sa.Column("retention_owner", sa.String(200), nullable=True),
        sa.Column("provider_recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["upload_item_id"], ["artifact_upload_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["replica_id"], ["artifact_replicas.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "adapter",
            "service_principal",
            "operation",
            "idempotency_key",
            name="uq_artifact_receipt_operation",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest_shape"
        ),
        sa.CheckConstraint(
            "response_digest ~ '^sha256:[0-9a-f]{64}$'", name="response_digest_shape"
        ),
        sa.CheckConstraint(
            "operation in ('store', 'verify', 'retain', 'release')", name="operation"
        ),
        sa.CheckConstraint(
            "outcome in ('stored', 'verified', 'retained', 'released')", name="outcome"
        ),
        sa.CheckConstraint(
            "(operation = 'store' and outcome = 'stored') or "
            "(operation = 'verify' and outcome = 'verified') or "
            "(operation = 'retain' and outcome = 'retained') or "
            "(operation = 'release' and outcome = 'released')",
            name="operation_outcome",
        ),
        sa.CheckConstraint("attempt_number > 0", name="attempt_positive"),
        sa.CheckConstraint(
            "operation != 'retain' or "
            "(retention_reference is not null and retention_class is not null "
            "and retention_owner is not null)",
            name="retain_fields",
        ),
        sa.CheckConstraint(
            "operation != 'release' or "
            "(retention_reference is not null and retention_class is not null "
            "and retention_owner is not null)",
            name="release_reference",
        ),
        sa.CheckConstraint(
            "operation in ('retain', 'release') or "
            "(retention_reference is null and retention_class is null "
            "and retention_owner is null)",
            name="non_retention_fields_empty",
        ),
    )
    op.create_index(
        "ix_artifact_operation_receipts_upload_item_id",
        "artifact_operation_receipts",
        ["upload_item_id"],
    )
    op.create_index(
        "ix_artifact_operation_receipts_replica_id",
        "artifact_operation_receipts",
        ["replica_id"],
    )
    op.execute(
        """
        create trigger trg_artifact_operation_receipts_immutable
        before update or delete on artifact_operation_receipts
        for each row execute function reject_artifact_fact_mutation()
        """
    )
