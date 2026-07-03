"""post submit checker policy provenance

Revision ID: 0008_post_submit_checker_policy
Revises: 0007_task_locked_context
Create Date: 2026-07-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_post_submit_checker_policy"
down_revision = "0007_task_locked_context"
branch_labels = None
depends_on = None


def _preflight_no_legacy_runtime_rows() -> None:
    """Stop before schema changes when legacy runtime rows cannot be backfilled."""
    bind = op.get_bind()
    counts = {
        "non_draft_tasks": bind.scalar(
            sa.text("select count(*) from workstream_tasks where status <> 'draft'")
        ),
        "submissions": bind.scalar(sa.text("select count(*) from submissions")),
        "checker_runs": bind.scalar(sa.text("select count(*) from checker_runs")),
    }
    if any(counts.values()):
        detail = ", ".join(f"{name}={count}" for name, count in counts.items())
        raise RuntimeError(
            "0008_post_submit_checker_policy cannot infer locked post-submit "
            "checker policy provenance for existing v0.1 runtime rows. "
            f"Found {detail}. Export or reset those runtime rows before upgrading."
        )


def upgrade() -> None:
    """Add explicit post-submit checker policy provenance locks."""
    _preflight_no_legacy_runtime_rows()

    op.add_column(
        "checker_policies",
        sa.Column("policy_hash", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("policy_body", sa.JSON(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_checker_policies_id_version_hash",
        "checker_policies",
        ["id", "guide_version", "policy_hash"],
    )
    op.create_check_constraint(
        "policy_hash_shape",
        "checker_policies",
        "policy_hash is null or policy_hash ~ '^sha256:[0-9a-f]{64}$'",
    )

    for table_name in ("workstream_tasks", "submissions", "checker_runs"):
        op.add_column(
            table_name,
            sa.Column(
                "locked_post_submit_checker_policy_id",
                sa.String(length=36),
                nullable=True,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "locked_post_submit_checker_policy_version",
                sa.String(length=50),
                nullable=True,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "locked_post_submit_checker_policy_hash",
                sa.String(length=71),
                nullable=True,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "locked_post_submit_checker_policy_body",
                sa.JSON(),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            f"fk_{table_name}_locked_post_submit_policy_hash",
            table_name,
            "checker_policies",
            [
                "locked_post_submit_checker_policy_id",
                "locked_post_submit_checker_policy_version",
                "locked_post_submit_checker_policy_hash",
            ],
            ["id", "guide_version", "policy_hash"],
        )
        op.create_index(
            f"ix_{table_name}_locked_post_submit_policy_hash",
            table_name,
            ["locked_post_submit_checker_policy_hash"],
            unique=False,
        )

    op.create_check_constraint(
        "post_submit_policy_lock_complete",
        "workstream_tasks",
        """
        status = 'draft'
        or (
            locked_post_submit_checker_policy_id is not null
            and locked_post_submit_checker_policy_version is not null
            and locked_post_submit_checker_policy_hash is not null
            and locked_post_submit_checker_policy_body is not null
        )
        """,
    )
    op.create_check_constraint(
        "post_submit_policy_lock_complete",
        "submissions",
        """
        locked_post_submit_checker_policy_id is not null
        and locked_post_submit_checker_policy_version is not null
        and locked_post_submit_checker_policy_hash is not null
        and locked_post_submit_checker_policy_body is not null
        """,
    )
    op.create_check_constraint(
        "post_submit_policy_lock_complete",
        "checker_runs",
        """
        locked_post_submit_checker_policy_id is not null
        and locked_post_submit_checker_policy_version is not null
        and locked_post_submit_checker_policy_hash is not null
        and locked_post_submit_checker_policy_body is not null
        """,
    )

    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_post_submit_policy_hash",
        "workstream_tasks",
        [
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    )
    op.create_foreign_key(
        "fk_submissions_task_locked_post_submit_policy_hash",
        "submissions",
        "workstream_tasks",
        [
            "task_id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
        [
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    )
    op.create_unique_constraint(
        "uq_submissions_id_locked_post_submit_policy_hash",
        "submissions",
        [
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    )
    op.create_foreign_key(
        "fk_checker_runs_submission_locked_post_submit_policy_hash",
        "checker_runs",
        "submissions",
        [
            "submission_id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
        [
            "id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    )


def downgrade() -> None:
    """Remove explicit post-submit checker policy provenance locks."""
    op.drop_constraint(
        "post_submit_policy_lock_complete",
        "checker_runs",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "ck_checker_runs_post_submit_policy_lock_complete",
        "checker_runs",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "post_submit_policy_lock_complete",
        "submissions",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "ck_submissions_post_submit_policy_lock_complete",
        "submissions",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "post_submit_policy_lock_complete",
        "workstream_tasks",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "ck_workstream_tasks_post_submit_policy_lock_complete",
        "workstream_tasks",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "fk_checker_runs_submission_locked_post_submit_policy_hash",
        "checker_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_submissions_id_locked_post_submit_policy_hash",
        "submissions",
        type_="unique",
    )
    op.drop_constraint(
        "fk_submissions_task_locked_post_submit_policy_hash",
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_post_submit_policy_hash",
        "workstream_tasks",
        type_="unique",
    )
    for table_name in ("checker_runs", "submissions", "workstream_tasks"):
        op.drop_index(
            f"ix_{table_name}_locked_post_submit_policy_hash",
            table_name=table_name,
        )
        op.drop_constraint(
            f"fk_{table_name}_locked_post_submit_policy_hash",
            table_name,
            type_="foreignkey",
        )
        op.execute(
            sa.text(
                f"alter table {table_name} "
                "drop column if exists locked_post_submit_checker_policy_body"
            )
        )
        op.drop_column(table_name, "locked_post_submit_checker_policy_hash")
        op.drop_column(table_name, "locked_post_submit_checker_policy_version")
        op.drop_column(table_name, "locked_post_submit_checker_policy_id")

    op.drop_constraint(
        "policy_hash_shape",
        "checker_policies",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "ck_checker_policies_policy_hash_shape",
        "checker_policies",
        type_="check",
        if_exists=True,
    )
    op.drop_constraint(
        "uq_checker_policies_id_version_hash",
        "checker_policies",
        type_="unique",
    )
    op.execute(sa.text("alter table checker_policies drop column if exists policy_body"))
    op.drop_column("checker_policies", "policy_hash")
