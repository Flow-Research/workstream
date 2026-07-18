"""task locked submission context

Revision ID: 0007_task_locked_context
Revises: 0006_submission_policy
Create Date: 2026-07-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_task_locked_context"
down_revision = "0006_submission_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add locked project policy context to tasks and submissions."""
    op.create_unique_constraint(
        "uq_pre_submit_checker_policies_id_compiled_bundle_hash",
        "pre_submit_checker_policies",
        ["id", "compiled_bundle_hash"],
    )
    op.add_column(
        "workstream_tasks",
        sa.Column("locked_guide_source_snapshot_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "workstream_tasks",
        sa.Column("locked_guide_source_snapshot_hash", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "workstream_tasks",
        sa.Column(
            "locked_effective_project_submission_artifact_policy_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.add_column(
        "workstream_tasks",
        sa.Column(
            "locked_effective_project_submission_artifact_policy_hash",
            sa.String(length=71),
            nullable=True,
        ),
    )
    op.add_column(
        "workstream_tasks",
        sa.Column("locked_pre_submit_checker_policy_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "workstream_tasks",
        sa.Column("locked_pre_submit_checker_bundle_hash", sa.String(length=71), nullable=True),
    )
    op.create_foreign_key(
        "fk_workstream_tasks_locked_source_snapshot_hash",
        "workstream_tasks",
        "guide_source_snapshots",
        ["locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
        ["id", "bundle_hash"],
    )
    op.create_foreign_key(
        "fk_workstream_tasks_locked_effective_policy_hash",
        "workstream_tasks",
        "effective_project_submission_artifact_policies",
        [
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
        ["id", "effective_policy_hash"],
    )
    op.create_foreign_key(
        "fk_workstream_tasks_locked_pre_submit_checker_hash",
        "workstream_tasks",
        "pre_submit_checker_policies",
        ["locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
        ["id", "compiled_bundle_hash"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_source_snapshot_hash",
        "workstream_tasks",
        ["id", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_effective_policy_hash",
        "workstream_tasks",
        [
            "id",
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_pre_submit_checker_hash",
        "workstream_tasks",
        ["id", "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
    )
    op.create_index(
        "ix_workstream_tasks_locked_source_snapshot",
        "workstream_tasks",
        ["locked_guide_source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_workstream_tasks_locked_effective_policy_hash",
        "workstream_tasks",
        ["locked_effective_project_submission_artifact_policy_hash"],
        unique=False,
    )
    op.create_index(
        "ix_workstream_tasks_locked_pre_submit_checker_hash",
        "workstream_tasks",
        ["locked_pre_submit_checker_bundle_hash"],
        unique=False,
    )

    op.add_column(
        "submissions",
        sa.Column("locked_guide_source_snapshot_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("locked_guide_source_snapshot_hash", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "locked_effective_project_submission_artifact_policy_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "locked_effective_project_submission_artifact_policy_hash",
            sa.String(length=71),
            nullable=True,
        ),
    )
    op.add_column(
        "submissions",
        sa.Column("locked_pre_submit_checker_policy_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("locked_pre_submit_checker_bundle_hash", sa.String(length=71), nullable=True),
    )
    op.create_foreign_key(
        "fk_submissions_locked_source_snapshot_hash",
        "submissions",
        "guide_source_snapshots",
        ["locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
        ["id", "bundle_hash"],
    )
    op.create_foreign_key(
        "fk_submissions_locked_effective_policy_hash",
        "submissions",
        "effective_project_submission_artifact_policies",
        [
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
        ["id", "effective_policy_hash"],
    )
    op.create_foreign_key(
        "fk_submissions_task_locked_source_snapshot_hash",
        "submissions",
        "workstream_tasks",
        ["task_id", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
        ["id", "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"],
    )
    op.create_foreign_key(
        "fk_submissions_task_locked_effective_policy_hash",
        "submissions",
        "workstream_tasks",
        [
            "task_id",
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
        [
            "id",
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
    )
    op.create_foreign_key(
        "fk_submissions_task_locked_pre_submit_checker_hash",
        "submissions",
        "workstream_tasks",
        ["task_id", "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
        ["id", "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
    )
    op.create_foreign_key(
        "fk_submissions_locked_pre_submit_checker_hash",
        "submissions",
        "pre_submit_checker_policies",
        ["locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"],
        ["id", "compiled_bundle_hash"],
    )
    op.create_index(
        "ix_submissions_locked_source_snapshot",
        "submissions",
        ["locked_guide_source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_submissions_locked_effective_policy_hash",
        "submissions",
        ["locked_effective_project_submission_artifact_policy_hash"],
        unique=False,
    )
    op.create_index(
        "ix_submissions_locked_pre_submit_checker_hash",
        "submissions",
        ["locked_pre_submit_checker_bundle_hash"],
        unique=False,
    )


def downgrade() -> None:
    """Remove locked project policy context from tasks and submissions."""
    op.drop_index("ix_submissions_locked_pre_submit_checker_hash", table_name="submissions")
    op.drop_index("ix_submissions_locked_effective_policy_hash", table_name="submissions")
    op.drop_index("ix_submissions_locked_source_snapshot", table_name="submissions")
    op.drop_constraint(
        "fk_submissions_locked_pre_submit_checker_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_task_locked_pre_submit_checker_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_task_locked_effective_policy_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_task_locked_source_snapshot_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_locked_effective_policy_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submissions_locked_source_snapshot_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_column("submissions", "locked_pre_submit_checker_bundle_hash")
    op.drop_column("submissions", "locked_pre_submit_checker_policy_id")
    op.drop_column("submissions", "locked_effective_project_submission_artifact_policy_hash")
    op.drop_column("submissions", "locked_effective_project_submission_artifact_policy_id")
    op.drop_column("submissions", "locked_guide_source_snapshot_hash")
    op.drop_column("submissions", "locked_guide_source_snapshot_id")

    op.drop_index("ix_workstream_tasks_locked_pre_submit_checker_hash", table_name="workstream_tasks")
    op.drop_index("ix_workstream_tasks_locked_effective_policy_hash", table_name="workstream_tasks")
    op.drop_index("ix_workstream_tasks_locked_source_snapshot", table_name="workstream_tasks")
    op.drop_constraint(
        "fk_workstream_tasks_locked_pre_submit_checker_hash",
        "workstream_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_workstream_tasks_locked_effective_policy_hash",
        "workstream_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_workstream_tasks_locked_source_snapshot_hash",
        "workstream_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_pre_submit_checker_hash",
        "workstream_tasks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_effective_policy_hash",
        "workstream_tasks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_source_snapshot_hash",
        "workstream_tasks",
        type_="unique",
    )
    op.drop_column("workstream_tasks", "locked_pre_submit_checker_bundle_hash")
    op.drop_column("workstream_tasks", "locked_pre_submit_checker_policy_id")
    op.drop_column(
        "workstream_tasks",
        "locked_effective_project_submission_artifact_policy_hash",
    )
    op.drop_column(
        "workstream_tasks",
        "locked_effective_project_submission_artifact_policy_id",
    )
    op.drop_column("workstream_tasks", "locked_guide_source_snapshot_hash")
    op.drop_column("workstream_tasks", "locked_guide_source_snapshot_id")
    op.drop_constraint(
        "uq_pre_submit_checker_policies_id_compiled_bundle_hash",
        "pre_submit_checker_policies",
        type_="unique",
    )
