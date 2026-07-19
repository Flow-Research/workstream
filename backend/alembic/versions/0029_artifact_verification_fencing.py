"""add artifact verification publication and execution fencing

Revision ID: 0029_artifact_verification
Revises: 0028_artifact_admission
Create Date: 2026-07-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0029_artifact_verification"
down_revision = "0028_artifact_admission"
branch_labels = depends_on = None


def upgrade() -> None:
    """Install polymorphic receipts, verification jobs, and generation fences."""
    op.add_column(
        "artifact_put_attempts",
        sa.Column("execution_mode", sa.String(20), nullable=True),
    )
    op.add_column(
        "artifact_put_attempts",
        sa.Column("observation_count", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "artifact_put_attempts",
        sa.Column("maximum_observations", sa.BigInteger(), nullable=False, server_default="5"),
    )
    op.create_check_constraint(
        "execution_mode",
        "artifact_put_attempts",
        "execution_mode is null or execution_mode in ('caller_put', 'observation')",
    )
    op.create_check_constraint(
        "observation_counts",
        "artifact_put_attempts",
        "observation_count >= 0 and maximum_observations > 0",
    )
    op.create_check_constraint(
        "unavailable_exhausted",
        "artifact_put_attempts",
        "status != 'provider_unavailable' or (observation_count >= maximum_observations "
        "and next_run_at is null and terminal_at is not null)",
    )
    op.create_check_constraint(
        "inflight_fence",
        "artifact_put_attempts",
        "(status = 'put_in_flight') = (executor_id is not null)",
    )

    op.drop_constraint(
        "uq_artifact_receipt_upload_item", "artifact_operation_receipts", type_="unique"
    )
    op.alter_column("artifact_operation_receipts", "upload_item_id", nullable=True)
    op.add_column(
        "artifact_operation_receipts",
        sa.Column("contract_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "artifact_operation_receipts", sa.Column("put_attempt_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "artifact_operation_receipts",
        sa.Column("guide_source_item_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "artifact_operation_receipts", sa.Column("checker_run_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "artifact_operation_receipts", sa.Column("logical_role", sa.String(100), nullable=True)
    )
    # The receipt table is append-only at runtime. Migration-owned promotion
    # of linked v1 contributor receipts is the sole controlled update.
    op.execute(
        "alter table artifact_operation_receipts "
        "disable trigger trg_artifact_operation_receipts_immutable"
    )
    op.execute(
        "update artifact_operation_receipts r set put_attempt_id = a.id, contract_version = 2 "
        "from artifact_put_attempts a where a.receipt_id = r.id"
    )
    op.execute(
        "alter table artifact_operation_receipts "
        "enable trigger trg_artifact_operation_receipts_immutable"
    )
    op.create_foreign_key(
        "fk_artifact_receipt_put_attempt",
        "artifact_operation_receipts",
        "artifact_put_attempts",
        ["put_attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_artifact_receipt_guide_item",
        "artifact_operation_receipts",
        "guide_source_snapshot_items",
        ["guide_source_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_artifact_receipt_checker_run",
        "artifact_operation_receipts",
        "checker_runs",
        ["checker_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_artifact_receipt_put_attempt", "artifact_operation_receipts", ["put_attempt_id"]
    )
    op.create_check_constraint(
        "contract_producer_reference",
        "artifact_operation_receipts",
        "(contract_version = 1 and put_attempt_id is null and upload_item_id is not null "
        "and guide_source_item_id is null and checker_run_id is null) or "
        "(contract_version = 2 and put_attempt_id is not null and "
        "((upload_item_id is not null)::int + (guide_source_item_id is not null)::int + "
        "(checker_run_id is not null)::int) = 1)",
    )
    op.create_index(
        "ix_artifact_operation_receipts_put_attempt_id",
        "artifact_operation_receipts",
        ["put_attempt_id"],
    )

    op.create_table(
        "artifact_put_observation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("put_attempt_id", sa.String(36), nullable=False, index=True),
        sa.Column("execution_generation", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("expected_sha256", sa.String(71), nullable=False),
        sa.Column("expected_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("observed_sha256", sa.String(71), nullable=True),
        sa.Column("observed_byte_count", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["put_attempt_id"], ["artifact_put_attempts.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "put_attempt_id", "execution_generation", name="uq_artifact_put_observation_fence"
        ),
        sa.CheckConstraint(
            "outcome in ('observed_confirmed', 'observed_missing', "
            "'observed_integrity_mismatch', 'conflict')",
            name="outcome",
        ),
        sa.CheckConstraint("expected_sha256 ~ '^sha256:[0-9a-f]{64}$'", name="expected_sha256"),
        sa.CheckConstraint(
            "observed_sha256 is null or observed_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="observed_sha256",
        ),
        sa.CheckConstraint("expected_byte_count >= 0", name="expected_size"),
        sa.CheckConstraint(
            "observed_byte_count is null or observed_byte_count >= 0", name="observed_size"
        ),
        sa.CheckConstraint(
            "(outcome in ('observed_confirmed', 'observed_integrity_mismatch')) = "
            "(observed_sha256 is not null and observed_byte_count is not null)",
            name="observed_facts",
        ),
    )
    op.execute(
        """
        create trigger trg_artifact_put_observation_receipts_immutable
        before update or delete on artifact_put_observation_receipts
        for each row execute function reject_artifact_fact_mutation()
        """
    )

    op.create_table(
        "artifact_verification_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("originating_put_attempt_id", sa.String(36), nullable=False),
        sa.Column("replica_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximum_attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executor_id", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cas_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("terminal_result_code", sa.String(100), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["originating_put_attempt_id"], ["artifact_put_attempts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["replica_id"], ["artifact_replicas.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("originating_put_attempt_id", name="uq_artifact_verification_origin"),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'verified', 'missing', 'integrity_mismatch', 'provider_unavailable', 'conflict')",
            name="status",
        ),
        sa.CheckConstraint("attempt_count >= 0 and maximum_attempts > 0", name="attempts"),
        sa.CheckConstraint("execution_generation >= 0 and cas_version >= 0", name="versions"),
        sa.CheckConstraint("(executor_id is null) = (lease_expires_at is null)", name="fence_pair"),
        sa.CheckConstraint(
            "(status = 'running') = (executor_id is not null)", name="running_fence"
        ),
        sa.CheckConstraint(
            "status != 'provider_unavailable' or ((next_run_at is not null and terminal_at is null and attempt_count < maximum_attempts) or (next_run_at is null and terminal_at is not null and attempt_count >= maximum_attempts))",
            name="unavailable_retryability",
        ),
    )
    for column in ("originating_put_attempt_id", "replica_id", "status", "next_run_at"):
        op.create_index(
            f"ix_artifact_verification_jobs_{column}", "artifact_verification_jobs", [column]
        )

    op.create_table(
        "artifact_verification_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("verification_job_id", sa.String(36), nullable=False),
        sa.Column("execution_generation", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("observed_sha256", sa.String(71), nullable=True),
        sa.Column("observed_byte_count", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["verification_job_id"], ["artifact_verification_jobs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "verification_job_id", "execution_generation", name="uq_artifact_verification_fence"
        ),
        sa.CheckConstraint(
            "outcome in ('verified', 'missing', 'integrity_mismatch', 'conflict')", name="outcome"
        ),
        sa.CheckConstraint(
            "observed_sha256 is null or observed_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="observed_sha256",
        ),
        sa.CheckConstraint(
            "observed_byte_count is null or observed_byte_count >= 0", name="observed_size"
        ),
        sa.CheckConstraint(
            "(outcome in ('verified', 'integrity_mismatch')) = "
            "(observed_sha256 is not null and observed_byte_count is not null)",
            name="observed_facts",
        ),
    )
    op.execute(
        """
        create trigger trg_artifact_verification_receipts_immutable
        before update or delete on artifact_verification_receipts
        for each row execute function reject_artifact_fact_mutation()
        """
    )
    op.create_index(
        "ix_artifact_verification_receipts_verification_job_id",
        "artifact_verification_receipts",
        ["verification_job_id"],
    )


def downgrade() -> None:
    """Remove verification mechanics only when all new evidence is empty."""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "lock table artifact_verification_receipts, artifact_verification_jobs, artifact_put_observation_receipts, artifact_operation_receipts, artifact_put_attempts in access exclusive mode"
        )
    )
    if any(
        connection.execute(sa.text(f"select exists(select 1 from {table})")).scalar()
        for table in (
            "artifact_verification_receipts",
            "artifact_verification_jobs",
            "artifact_put_observation_receipts",
        )
    ):
        raise RuntimeError("cannot downgrade populated artifact verification evidence")
    if connection.execute(
        sa.text(
            "select exists(select 1 from artifact_operation_receipts where upload_item_id is null)"
        )
    ).scalar():
        raise RuntimeError("cannot downgrade polymorphic artifact operation receipts")
    op.drop_index(
        "ix_artifact_verification_receipts_verification_job_id",
        table_name="artifact_verification_receipts",
    )
    op.execute(
        "drop trigger trg_artifact_verification_receipts_immutable "
        "on artifact_verification_receipts"
    )
    op.drop_table("artifact_verification_receipts")
    for column in reversed(("originating_put_attempt_id", "replica_id", "status", "next_run_at")):
        op.drop_index(
            f"ix_artifact_verification_jobs_{column}", table_name="artifact_verification_jobs"
        )
    op.drop_table("artifact_verification_jobs")
    op.execute(
        "drop trigger trg_artifact_put_observation_receipts_immutable "
        "on artifact_put_observation_receipts"
    )
    op.drop_table("artifact_put_observation_receipts")
    op.drop_index(
        "ix_artifact_operation_receipts_put_attempt_id", table_name="artifact_operation_receipts"
    )
    op.drop_constraint("contract_producer_reference", "artifact_operation_receipts", type_="check")
    op.drop_constraint(
        "uq_artifact_receipt_put_attempt", "artifact_operation_receipts", type_="unique"
    )
    op.drop_constraint(
        "fk_artifact_receipt_checker_run", "artifact_operation_receipts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_artifact_receipt_guide_item", "artifact_operation_receipts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_artifact_receipt_put_attempt", "artifact_operation_receipts", type_="foreignkey"
    )
    for column in (
        "logical_role",
        "checker_run_id",
        "guide_source_item_id",
        "put_attempt_id",
        "contract_version",
    ):
        op.drop_column("artifact_operation_receipts", column)
    op.alter_column("artifact_operation_receipts", "upload_item_id", nullable=False)
    op.create_unique_constraint(
        "uq_artifact_receipt_upload_item", "artifact_operation_receipts", ["upload_item_id"]
    )
    op.drop_constraint("execution_mode", "artifact_put_attempts", type_="check")
    op.drop_constraint("inflight_fence", "artifact_put_attempts", type_="check")
    op.drop_constraint("unavailable_exhausted", "artifact_put_attempts", type_="check")
    op.drop_constraint("observation_counts", "artifact_put_attempts", type_="check")
    op.drop_column("artifact_put_attempts", "maximum_observations")
    op.drop_column("artifact_put_attempts", "observation_count")
    op.drop_column("artifact_put_attempts", "execution_mode")
