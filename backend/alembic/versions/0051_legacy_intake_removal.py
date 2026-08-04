"""remove the inactive multi-step contributor artifact intake

Revision ID: 0051_legacy_intake_removal
Revises: 0050_guide_source_v2
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0051_legacy_intake_removal"
down_revision = "0050_guide_source_v2"
branch_labels = depends_on = None


_PUT_PRODUCER_REFERENCE = (
    "(producer_request_type = 'guide' and guide_source_item_id is not null "
    "and checker_run_id is null and task_id is null and logical_role is null) or "
    "(producer_request_type = 'checker_output' and guide_source_item_id is null "
    "and checker_run_id is not null and task_id is not null "
    "and octet_length(logical_role) between 1 and 100)"
)
_PUT_PRODUCER_IDENTITY = (
    "((producer_request_type = 'guide' and producer_type = 'actor_profile' and "
    "producer_ref ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    "[89ab][0-9a-f]{3}-[0-9a-f]{12}$') or "
    "(producer_request_type = 'checker_output' and producer_type = 'service_identity' "
    "and producer_ref = 'workstream.artifact.checker_output'))"
)
_LEGACY_PUT_PRODUCER_IDENTITY = (
    "((producer_request_type in ('guide', 'contributor') and "
    "producer_type = 'actor_profile' and producer_ref ~ "
    "'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    "[89ab][0-9a-f]{3}-[0-9a-f]{12}$') or "
    "(producer_request_type = 'checker_output' and producer_type = 'service_identity' "
    "and producer_ref = 'workstream.artifact.checker_output'))"
)
_LEGACY_PUT_PRODUCER_REFERENCE = (
    "(producer_request_type = 'guide' and guide_source_item_id is not null "
    "and upload_item_id is null and checker_run_id is null and task_id is null "
    "and logical_role is null) or "
    "(producer_request_type = 'contributor' and guide_source_item_id is null "
    "and upload_item_id is not null and checker_run_id is null and task_id is not null "
    "and logical_role is null) or "
    "(producer_request_type = 'checker_output' and guide_source_item_id is null "
    "and upload_item_id is null and checker_run_id is not null and task_id is not null "
    "and octet_length(logical_role) between 1 and 100)"
)
_RECEIPT_PRODUCER_REFERENCE = (
    "contract_version = 2 and put_attempt_id is not null and "
    "((guide_source_item_id is not null)::int + "
    "(checker_run_id is not null)::int) = 1"
)
_LEGACY_RECEIPT_PRODUCER_REFERENCE = (
    "(contract_version = 1 and put_attempt_id is null and upload_item_id is not null "
    "and guide_source_item_id is null and checker_run_id is null) or "
    "(contract_version = 2 and put_attempt_id is not null and "
    "((upload_item_id is not null)::int + (guide_source_item_id is not null)::int + "
    "(checker_run_id is not null)::int) = 1)"
)


def _lock_and_refuse_populated_legacy_intake() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table artifact_upload_sessions, artifact_upload_items, "
            "artifact_put_attempts, artifact_operation_receipts in access exclusive mode"
        )
    )
    populated = bind.execute(
        sa.text(
            "select exists(select 1 from artifact_upload_sessions) "
            "or exists(select 1 from artifact_upload_items) "
            "or exists(select 1 from artifact_put_attempts "
            "where producer_request_type = 'contributor' or upload_item_id is not null) "
            "or exists(select 1 from artifact_operation_receipts "
            "where contract_version = 1 or upload_item_id is not null)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "legacy contributor artifact intake is populated; preserve the existing "
            "schema and use a separately approved maintenance migration"
        )


def upgrade() -> None:
    """Remove only a proven-empty legacy contributor intake."""
    _lock_and_refuse_populated_legacy_intake()

    op.drop_constraint("producer_reference", "artifact_put_attempts", type_="check")
    op.drop_constraint("producer_identity", "artifact_put_attempts", type_="check")
    op.drop_constraint("producer_request_type", "artifact_put_attempts", type_="check")
    op.drop_constraint("contract_producer_reference", "artifact_operation_receipts", type_="check")
    op.drop_constraint(
        "fk_artifact_put_attempts_upload_item_id_artifact_upload_items",
        "artifact_put_attempts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_artifact_operation_receipts_upload_item_id_artifact__cc40",
        "artifact_operation_receipts",
        type_="foreignkey",
    )
    op.drop_index("ix_artifact_put_attempts_upload_item_id", table_name="artifact_put_attempts")
    op.drop_index(
        "ix_artifact_operation_receipts_upload_item_id",
        table_name="artifact_operation_receipts",
    )
    op.drop_column("artifact_put_attempts", "upload_item_id")
    op.drop_column("artifact_operation_receipts", "upload_item_id")
    op.alter_column(
        "artifact_operation_receipts",
        "put_attempt_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_check_constraint(
        "producer_request_type",
        "artifact_put_attempts",
        "producer_request_type in ('guide', 'checker_output')",
    )
    op.create_check_constraint("producer_identity", "artifact_put_attempts", _PUT_PRODUCER_IDENTITY)
    op.create_check_constraint(
        "producer_reference", "artifact_put_attempts", _PUT_PRODUCER_REFERENCE
    )
    op.create_check_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        _RECEIPT_PRODUCER_REFERENCE,
    )
    op.drop_table("artifact_upload_items")
    op.drop_table("artifact_upload_sessions")


def downgrade() -> None:
    """Recreate the exact empty legacy schema without fabricating lineage."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table artifact_put_attempts, artifact_operation_receipts in access exclusive mode"
        )
    )
    if bind.execute(
        sa.text(
            "select exists(select 1 from artifact_put_attempts "
            "where producer_request_type = 'contributor') "
            "or exists(select 1 from artifact_operation_receipts where contract_version = 1)"
        )
    ).scalar_one():
        raise RuntimeError("cannot truthfully recreate legacy contributor intake")

    op.create_table(
        "artifact_upload_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("guide_id", sa.String(36), nullable=True),
        sa.Column("permitted_roles", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("maximum_bytes", sa.Integer(), nullable=False),
        sa.Column("current_bytes", sa.Integer(), nullable=False),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("maximum_items", sa.Integer(), nullable=False),
        sa.Column("current_items", sa.Integer(), nullable=False),
        sa.Column("reserved_items", sa.Integer(), nullable=False),
        sa.Column("artifact_set_hash", sa.String(71), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cas_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "state in ('open', 'sealed', 'consumed', 'expired', 'cancelled')", name="state"
        ),
        sa.CheckConstraint(
            "maximum_bytes >= 0 and current_bytes >= 0 and reserved_bytes >= 0",
            name="byte_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "maximum_items >= 0 and current_items >= 0 and reserved_items >= 0",
            name="item_counts_nonnegative",
        ),
        sa.CheckConstraint("current_bytes + reserved_bytes <= maximum_bytes", name="byte_limit"),
        sa.CheckConstraint("current_items + reserved_items <= maximum_items", name="item_limit"),
        sa.CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        sa.CheckConstraint(
            "artifact_set_hash is null or artifact_set_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="artifact_set_hash_shape",
        ),
        sa.CheckConstraint(
            "(state = 'consumed') = (consumed_at is not null)", name="consumed_timestamp"
        ),
        sa.CheckConstraint(
            "state not in ('sealed', 'consumed') or artifact_set_hash is not null",
            name="sealed_hash_required",
        ),
    )
    for column in ("actor_id", "project_id", "task_id", "guide_id", "state"):
        op.create_index(
            f"ix_artifact_upload_sessions_{column}",
            "artifact_upload_sessions",
            [column],
        )

    op.create_table(
        "artifact_upload_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("logical_role", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=True),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(71), nullable=True),
        sa.Column("expected_size", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("cas_version", sa.Integer(), nullable=False),
        sa.Column("provider_object_ref", sa.String(1024), nullable=True),
        sa.Column("content_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["artifact_upload_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["content_id"], ["artifact_contents.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_artifact_item_operation"),
        sa.CheckConstraint(
            "state in ('reserved', 'uploading', 'replay_required', "
            "'stored_pending_verification', 'ready', 'failed', 'cancelled')",
            name="state",
        ),
        sa.CheckConstraint(
            "reserved_bytes >= 0 and cas_version >= 0 and "
            "(expected_size is null or expected_size >= 0)",
            name="counts_nonnegative",
        ),
        sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest_shape"),
        sa.CheckConstraint(
            "expected_sha256 is null or expected_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="expected_sha256_shape",
        ),
        sa.CheckConstraint(
            "((state in ('stored_pending_verification', 'ready')) and content_id is not null "
            "and provider_object_ref is not null) or "
            "((state not in ('stored_pending_verification', 'ready')) and content_id is null "
            "and provider_object_ref is null)",
            name="stored_result_required",
        ),
        sa.CheckConstraint(
            "state != 'failed' or error_code is not null", name="failed_error_required"
        ),
    )
    for column in ("session_id", "content_id", "state"):
        op.create_index(f"ix_artifact_upload_items_{column}", "artifact_upload_items", [column])

    op.drop_constraint("producer_reference", "artifact_put_attempts", type_="check")
    op.drop_constraint("producer_identity", "artifact_put_attempts", type_="check")
    op.drop_constraint("producer_request_type", "artifact_put_attempts", type_="check")
    op.drop_constraint("contract_producer_reference", "artifact_operation_receipts", type_="check")
    op.alter_column(
        "artifact_operation_receipts",
        "put_attempt_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.add_column(
        "artifact_put_attempts", sa.Column("upload_item_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "artifact_operation_receipts",
        sa.Column("upload_item_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_artifact_put_attempts_upload_item_id_artifact_upload_items",
        "artifact_put_attempts",
        "artifact_upload_items",
        ["upload_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_artifact_operation_receipts_upload_item_id_artifact__cc40",
        "artifact_operation_receipts",
        "artifact_upload_items",
        ["upload_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_artifact_put_attempts_upload_item_id",
        "artifact_put_attempts",
        ["upload_item_id"],
    )
    op.create_index(
        "ix_artifact_operation_receipts_upload_item_id",
        "artifact_operation_receipts",
        ["upload_item_id"],
    )
    op.create_check_constraint(
        "producer_request_type",
        "artifact_put_attempts",
        "producer_request_type in ('guide', 'contributor', 'checker_output')",
    )
    op.create_check_constraint(
        "producer_identity", "artifact_put_attempts", _LEGACY_PUT_PRODUCER_IDENTITY
    )
    op.create_check_constraint(
        "producer_reference", "artifact_put_attempts", _LEGACY_PUT_PRODUCER_REFERENCE
    )
    op.create_check_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        _LEGACY_RECEIPT_PRODUCER_REFERENCE,
    )
