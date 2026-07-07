"""project setup run ledger

Revision ID: 0013_project_setup_runs
Revises: 0012_actor_identity_profiles
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_project_setup_runs"
down_revision = "0012_actor_identity_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the automatic project setup run ledger."""
    op.create_table(
        "project_setup_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=71), nullable=False),
        sa.Column("celery_task_id", sa.String(length=155), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=False),
        sa.Column("output_sufficiency_report_id", sa.String(length=36), nullable=True),
        sa.Column("output_submission_artifact_policy_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ("
            "'queued', "
            "'enqueue_failed', "
            "'running_sufficiency_agent', "
            "'sufficiency_blocked', "
            "'running_policy_derivation_agent', "
            "'policy_draft_ready', "
            "'setup_blocked', "
            "'failed'"
            ")",
            name="ck_project_setup_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["project_guides.id"],
            name=op.f("fk_project_setup_runs_guide_id_project_guides"),
        ),
        sa.ForeignKeyConstraint(
            ["output_submission_artifact_policy_id"],
            ["submission_artifact_policies.id"],
            name="fk_project_setup_runs_submission_artifact_policy",
        ),
        sa.ForeignKeyConstraint(
            ["output_sufficiency_report_id"],
            ["guide_sufficiency_reports.id"],
            name="fk_project_setup_runs_sufficiency_report",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_setup_runs_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_project_setup_runs_project_guide",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["guide_source_snapshots.id"],
            name=op.f("fk_project_setup_runs_source_snapshot_id_guide_source_snapshots"),
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_project_setup_runs_source_snapshot_hash",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_setup_runs")),
    )
    op.create_index(
        op.f("ix_project_setup_runs_celery_task_id"),
        "project_setup_runs",
        ["celery_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_setup_runs_guide_id"),
        "project_setup_runs",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_setup_runs_output_submission_artifact_policy_id"),
        "project_setup_runs",
        ["output_submission_artifact_policy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_setup_runs_output_sufficiency_report_id"),
        "project_setup_runs",
        ["output_sufficiency_report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_setup_runs_project_id"),
        "project_setup_runs",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_setup_runs_source_snapshot_id"),
        "project_setup_runs",
        ["source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_setup_runs_status"),
        "project_setup_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the automatic project setup run ledger."""
    op.drop_index(op.f("ix_project_setup_runs_status"), table_name="project_setup_runs")
    op.drop_index(
        op.f("ix_project_setup_runs_source_snapshot_id"),
        table_name="project_setup_runs",
    )
    op.drop_index(op.f("ix_project_setup_runs_project_id"), table_name="project_setup_runs")
    op.drop_index(
        op.f("ix_project_setup_runs_output_sufficiency_report_id"),
        table_name="project_setup_runs",
    )
    op.drop_index(
        op.f("ix_project_setup_runs_output_submission_artifact_policy_id"),
        table_name="project_setup_runs",
    )
    op.drop_index(op.f("ix_project_setup_runs_guide_id"), table_name="project_setup_runs")
    op.drop_index(
        op.f("ix_project_setup_runs_celery_task_id"),
        table_name="project_setup_runs",
    )
    op.drop_table("project_setup_runs")
