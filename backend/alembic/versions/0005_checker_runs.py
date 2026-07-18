"""checker run records

Revision ID: 0005_checker_runs
Revises: 0004_submission_packets
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_checker_runs"
down_revision = "0004_submission_packets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable checker run and result tables."""
    op.create_table(
        "checker_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("trigger_source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("routing_recommendation", sa.String(length=50), nullable=False),
        sa.Column("outcome_source", sa.String(length=50), nullable=False),
        sa.Column("triggered_by", sa.String(length=100), nullable=False),
        sa.Column("triggered_by_subject", sa.String(length=200), nullable=False),
        sa.Column("triggered_by_issuer", sa.String(length=200), nullable=False),
        sa.Column("trigger_auth_source", sa.String(length=30), nullable=False),
        sa.Column("trigger_reason", sa.Text(), nullable=True),
        sa.Column("audit_event_id", sa.String(length=36), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_checker_run_id", sa.String(length=36), nullable=True),
        sa.Column("is_current_for_submission", sa.Boolean(), nullable=False),
        sa.Column("locked_guide_version", sa.String(length=50), nullable=False),
        sa.Column("locked_review_policy_version", sa.String(length=50), nullable=False),
        sa.Column("locked_revision_policy_version", sa.String(length=50), nullable=False),
        sa.Column("locked_payment_policy_version", sa.String(length=50), nullable=False),
        sa.Column("package_hash", sa.String(length=128), nullable=False),
        sa.Column("artifact_hash_manifest", sa.JSON(), nullable=False),
        sa.Column("artifact_manifest_hash", sa.String(length=128), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("blocking_count", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["audit_event_id"],
            ["audit_events.id"],
            name=op.f("fk_checker_runs_audit_event_id_audit_events"),
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_checker_runs_submission_id_submissions"),
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "submission_version"],
            ["submissions.id", "submissions.version"],
            name="fk_checker_runs_submission_version",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_checker_run_id"],
            ["checker_runs.id"],
            name=op.f("fk_checker_runs_supersedes_checker_run_id_checker_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["workstream_tasks.id"],
            name=op.f("fk_checker_runs_task_id_workstream_tasks"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_checker_runs_task_locked_guide",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_review_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_review_policy_version"],
            name="fk_checker_runs_task_locked_review_policy",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_revision_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_revision_policy_version"],
            name="fk_checker_runs_task_locked_revision_policy",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_payment_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_payment_policy_version"],
            name="fk_checker_runs_task_locked_payment_policy",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checker_runs")),
        sa.UniqueConstraint(
            "submission_id",
            "attempt_number",
            name="uq_checker_runs_submission_attempt",
        ),
    )
    op.create_index(op.f("ix_checker_runs_audit_event_id"), "checker_runs", ["audit_event_id"], unique=False)
    op.create_index(op.f("ix_checker_runs_routing_recommendation"), "checker_runs", ["routing_recommendation"], unique=False)
    op.create_index(op.f("ix_checker_runs_status"), "checker_runs", ["status"], unique=False)
    op.create_index(op.f("ix_checker_runs_submission_id"), "checker_runs", ["submission_id"], unique=False)
    op.create_index(
        op.f("ix_checker_runs_supersedes_checker_run_id"),
        "checker_runs",
        ["supersedes_checker_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_checker_runs_task_id"), "checker_runs", ["task_id"], unique=False)
    op.create_index(
        "uq_checker_runs_current_per_submission",
        "checker_runs",
        ["submission_id"],
        unique=True,
        postgresql_where=sa.text("is_current_for_submission = true"),
    )

    op.create_table(
        "checker_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checker_run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("checker_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("blocks_review", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("worker_message", sa.Text(), nullable=True),
        sa.Column("worker_suggested_fix", sa.Text(), nullable=True),
        sa.Column("worker_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("worker_visible", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checker_run_id"],
            ["checker_runs.id"],
            name=op.f("fk_checker_results_checker_run_id_checker_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_checker_results_submission_id_submissions"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["workstream_tasks.id"],
            name=op.f("fk_checker_results_task_id_workstream_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checker_results")),
    )
    op.create_index(op.f("ix_checker_results_checker_name"), "checker_results", ["checker_name"], unique=False)
    op.create_index(op.f("ix_checker_results_checker_run_id"), "checker_results", ["checker_run_id"], unique=False)
    op.create_index(op.f("ix_checker_results_submission_id"), "checker_results", ["submission_id"], unique=False)
    op.create_index(op.f("ix_checker_results_task_id"), "checker_results", ["task_id"], unique=False)
    op.create_index(op.f("ix_checker_results_worker_visible"), "checker_results", ["worker_visible"], unique=False)


def downgrade() -> None:
    """Drop durable checker run and result tables."""
    op.drop_index(op.f("ix_checker_results_worker_visible"), table_name="checker_results")
    op.drop_index(op.f("ix_checker_results_task_id"), table_name="checker_results")
    op.drop_index(op.f("ix_checker_results_submission_id"), table_name="checker_results")
    op.drop_index(op.f("ix_checker_results_checker_run_id"), table_name="checker_results")
    op.drop_index(op.f("ix_checker_results_checker_name"), table_name="checker_results")
    op.drop_table("checker_results")
    op.drop_index("uq_checker_runs_current_per_submission", table_name="checker_runs")
    op.drop_index(op.f("ix_checker_runs_task_id"), table_name="checker_runs")
    op.drop_index(op.f("ix_checker_runs_supersedes_checker_run_id"), table_name="checker_runs")
    op.drop_index(op.f("ix_checker_runs_submission_id"), table_name="checker_runs")
    op.drop_index(op.f("ix_checker_runs_status"), table_name="checker_runs")
    op.drop_index(op.f("ix_checker_runs_routing_recommendation"), table_name="checker_runs")
    op.drop_index(op.f("ix_checker_runs_audit_event_id"), table_name="checker_runs")
    op.drop_table("checker_runs")
