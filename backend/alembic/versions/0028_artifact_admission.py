"""add durable-byte admission and prepared put attempts

Revision ID: 0028_artifact_admission
Revises: 0027_contributor_foundation
Create Date: 2026-07-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0028_artifact_admission"
down_revision = "0027_contributor_foundation"
branch_labels = depends_on = None

_ADMISSION_TABLES = (
    "artifact_put_attempt_charges",
    "artifact_put_attempts",
    "artifact_admission_charges",
    "artifact_admission_scopes",
)


def _refuse_populated_admission_downgrade() -> None:
    """Refuse to destroy durable admission, charge, or attempt evidence."""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "lock table "
            + ", ".join(_ADMISSION_TABLES)
            + " in access exclusive mode"
        )
    )
    if any(
        connection.execute(
            sa.text(f"select exists(select 1 from {table_name})")
        ).scalar()
        for table_name in _ADMISSION_TABLES
    ):
        raise RuntimeError("cannot downgrade populated artifact admission ledger")


def upgrade() -> None:
    """Install generic admission and pre-I/O attempt state."""
    op.create_unique_constraint(
        "uq_artifact_storage_namespace_id_fingerprint",
        "artifact_storage_namespaces",
        ["id", "namespace_fingerprint"],
    )

    op.create_table(
        "artifact_admission_scopes",
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.String(120), nullable=False),
        sa.Column("limit_bytes", sa.BigInteger(), nullable=False),
        sa.Column("counted_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cas_version", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.CheckConstraint(
            "scope_type in ('deployment', 'project', 'producer', 'task')",
            name="scope_type",
        ),
        sa.CheckConstraint(
            "octet_length(scope_id) between 1 and 120",
            name="scope_id_bounds",
        ),
        sa.CheckConstraint("limit_bytes > 0", name="limit_positive"),
        sa.CheckConstraint(
            "counted_bytes >= 0 and counted_bytes <= limit_bytes",
            name="counted_bytes_within_limit",
        ),
        sa.CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        sa.PrimaryKeyConstraint("scope_type", "scope_id"),
    )

    op.create_table(
        "artifact_admission_charges",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("producer_type", sa.String(30), nullable=False),
        sa.Column("producer_ref", sa.String(120), nullable=False),
        sa.Column("creating_operation_identity", sa.String(71), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="provisional"),
        sa.Column("cas_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "reserved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="sha256_shape",
        ),
        sa.CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        sa.CheckConstraint(
            "producer_type in ('actor_profile', 'service_identity')",
            name="producer_type",
        ),
        sa.CheckConstraint(
            "creating_operation_identity ~ '^sha256:[0-9a-f]{64}$'",
            name="operation_identity_shape",
        ),
        sa.CheckConstraint(
            "state in ('provisional', 'completed', 'released')",
            name="state",
        ),
        sa.CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        sa.CheckConstraint(
            "(state = 'completed') = (completed_at is not null)",
            name="completed_timestamp",
        ),
        sa.CheckConstraint(
            "(state = 'released') = (released_at is not null)",
            name="released_timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["scope_type", "scope_id"],
            [
                "artifact_admission_scopes.scope_type",
                "artifact_admission_scopes.scope_id",
            ],
            name="fk_artifact_admission_charges_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type",
            "scope_id",
            "sha256",
            "byte_count",
            name="uq_artifact_admission_charge_scope_content",
        ),
    )

    op.create_table(
        "artifact_put_attempts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("producer_request_type", sa.String(30), nullable=False),
        sa.Column("producer_type", sa.String(30), nullable=False),
        sa.Column("producer_ref", sa.String(120), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("guide_source_item_id", sa.String(36), nullable=True),
        sa.Column("upload_item_id", sa.String(36), nullable=True),
        sa.Column("checker_run_id", sa.String(36), nullable=True),
        sa.Column("logical_role", sa.String(100), nullable=True),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("storage_namespace_id", sa.String(20), nullable=False),
        sa.Column("namespace_fingerprint", sa.String(71), nullable=False),
        sa.Column("canonical_target", sa.String(1024), nullable=False),
        sa.Column("operation_identity", sa.String(71), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="prepared"),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("executor_id", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("terminal_result_code", sa.String(100), nullable=True),
        sa.Column("replica_id", sa.String(36), nullable=True),
        sa.Column("receipt_id", sa.String(36), nullable=True),
        sa.Column("cas_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "prepared_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "producer_request_type in ('guide', 'contributor', 'checker_output')",
            name="producer_request_type",
        ),
        sa.CheckConstraint(
            "producer_type in ('actor_profile', 'service_identity')",
            name="producer_type",
        ),
        sa.CheckConstraint(
            "((producer_request_type in ('guide', 'contributor') "
            "and producer_type = 'actor_profile' and "
            "producer_ref ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            "[89ab][0-9a-f]{3}-[0-9a-f]{12}$') or "
            "(producer_request_type = 'checker_output' "
            "and producer_type = 'service_identity' "
            "and producer_ref = 'workstream.artifact.checker_output'))",
            name="producer_identity",
        ),
        sa.CheckConstraint("sha256 ~ '^sha256:[0-9a-f]{64}$'", name="sha256_shape"),
        sa.CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        sa.CheckConstraint(
            "canonical_target ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{62}$'",
            name="canonical_target_shape",
        ),
        sa.CheckConstraint(
            "operation_identity ~ '^sha256:[0-9a-f]{64}$'",
            name="operation_identity_shape",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="request_digest_shape",
        ),
        sa.CheckConstraint(
            "status in ('prepared', 'put_in_flight', 'acknowledgement_unknown', "
            "'object_confirmed', 'absent_replay_required', 'integrity_mismatch', "
            "'provider_unavailable', 'conflict')",
            name="status",
        ),
        sa.CheckConstraint(
            "(executor_id is null) = (lease_expires_at is null)",
            name="executor_lease_pair",
        ),
        sa.CheckConstraint(
            "execution_generation >= 0 and cas_version >= 0",
            name="versions_nonnegative",
        ),
        sa.CheckConstraint(
            "status != 'prepared' or (next_run_at is null and executor_id is null "
            "and lease_expires_at is null "
            "and execution_generation = 0 and terminal_result_code is null "
            "and terminal_at is null and replica_id is null and receipt_id is null)",
            name="prepared_execution_inactive",
        ),
        sa.CheckConstraint(
            "(producer_request_type = 'guide' and guide_source_item_id is not null "
            "and upload_item_id is null and checker_run_id is null and task_id is null "
            "and logical_role is null) or "
            "(producer_request_type = 'contributor' and guide_source_item_id is null "
            "and upload_item_id is not null and checker_run_id is null "
            "and task_id is not null and logical_role is null) or "
            "(producer_request_type = 'checker_output' and guide_source_item_id is null "
            "and upload_item_id is null and checker_run_id is not null "
            "and task_id is not null and octet_length(logical_role) between 1 and 100)",
            name="producer_reference",
        ),
        sa.ForeignKeyConstraint(
            ["storage_namespace_id", "namespace_fingerprint"],
            [
                "artifact_storage_namespaces.id",
                "artifact_storage_namespaces.namespace_fingerprint",
            ],
            name="fk_artifact_put_attempts_namespace_fingerprint",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["workstream_tasks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["guide_source_item_id"],
            ["guide_source_snapshot_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["upload_item_id"], ["artifact_upload_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["checker_run_id"], ["checker_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["replica_id"], ["artifact_replicas.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"], ["artifact_operation_receipts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_identity",
            name="uq_artifact_put_attempt_operation",
        ),
    )
    for column in (
        "project_id",
        "task_id",
        "guide_source_item_id",
        "upload_item_id",
        "checker_run_id",
        "status",
        "next_run_at",
        "replica_id",
        "receipt_id",
    ):
        op.create_index(
            f"ix_artifact_put_attempts_{column}",
            "artifact_put_attempts",
            [column],
        )

    op.create_table(
        "artifact_put_attempt_charges",
        sa.Column("attempt_id", sa.String(36), nullable=False),
        sa.Column("charge_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["artifact_put_attempts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["charge_id"], ["artifact_admission_charges.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("attempt_id", "charge_id"),
    )


def downgrade() -> None:
    """Remove only an empty admission foundation."""
    _refuse_populated_admission_downgrade()
    op.drop_table("artifact_put_attempt_charges")
    for column in reversed(
        (
            "project_id",
            "task_id",
            "guide_source_item_id",
            "upload_item_id",
            "checker_run_id",
            "status",
            "next_run_at",
            "replica_id",
            "receipt_id",
        )
    ):
        op.drop_index(
            f"ix_artifact_put_attempts_{column}",
            table_name="artifact_put_attempts",
        )
    op.drop_table("artifact_put_attempts")
    op.drop_table("artifact_admission_charges")
    op.drop_table("artifact_admission_scopes")
    op.drop_constraint(
        "uq_artifact_storage_namespace_id_fingerprint",
        "artifact_storage_namespaces",
        type_="unique",
    )
