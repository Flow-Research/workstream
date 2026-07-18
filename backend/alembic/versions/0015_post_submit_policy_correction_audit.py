"""preserve post-submit policy correction audit history

Revision ID: 0015_post_submit_correction
Revises: 0014_post_submit_setup
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_post_submit_correction"
down_revision = "0014_post_submit_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make rejected compiled policies append-only correction records."""
    op.add_column(
        "checker_policies",
        sa.Column("supersedes_policy_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("superseded_by_role", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("superseded_by_actor", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("supersession_kind", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("supersession_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_checker_policies_supersedes_policy_id",
        "checker_policies",
        "checker_policies",
        ["supersedes_policy_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_checker_policies_supersedes_policy_id"),
        "checker_policies",
        ["supersedes_policy_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_checker_policies_project_version",
        "checker_policies",
        type_="unique",
    )
    op.create_index(
        "uq_checker_policies_current_project_version",
        "checker_policies",
        ["project_id", "guide_version"],
        unique=True,
        postgresql_where=sa.text("lifecycle_status in ('compiled', 'approved')"),
    )
    op.create_check_constraint(
        "correction_provenance",
        "checker_policies",
        """
        lifecycle_status != 'superseded'
        or (
            superseded_at is not null
            and superseded_by_role in ('admin', 'project_manager')
            and superseded_by_actor is not null
            and supersession_kind in ('correction_requested', 'upstream_policy_changed')
            and supersession_reason is not null
            and length(btrim(supersession_reason)) > 0
        )
        """,
    )


def downgrade() -> None:
    """Restore the single-row checker-policy schema."""
    op.drop_constraint(
        "correction_provenance",
        "checker_policies",
        type_="check",
    )
    op.drop_index(
        "uq_checker_policies_current_project_version",
        table_name="checker_policies",
    )
    op.execute(sa.text("update checker_policies set supersedes_policy_id = null"))
    op.execute(sa.text("delete from checker_policies where lifecycle_status = 'superseded'"))
    op.create_unique_constraint(
        "uq_checker_policies_project_version",
        "checker_policies",
        ["project_id", "guide_version"],
    )
    op.drop_index(
        op.f("ix_checker_policies_supersedes_policy_id"),
        table_name="checker_policies",
    )
    op.drop_constraint(
        "fk_checker_policies_supersedes_policy_id",
        "checker_policies",
        type_="foreignkey",
    )
    op.drop_column("checker_policies", "supersession_reason")
    op.drop_column("checker_policies", "supersession_kind")
    op.drop_column("checker_policies", "superseded_by_actor")
    op.drop_column("checker_policies", "superseded_by_role")
    op.drop_column("checker_policies", "superseded_at")
    op.drop_column("checker_policies", "supersedes_policy_id")
