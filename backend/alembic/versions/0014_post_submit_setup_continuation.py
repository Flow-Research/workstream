"""post-submit setup continuation state

Revision ID: 0014_post_submit_setup
Revises: 0013_project_setup_runs
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_post_submit_setup"
down_revision = "0013_project_setup_runs"
branch_labels = None
depends_on = None


def _preflight_no_legacy_checker_policy_rows() -> None:
    """Reject old checker rows that cannot be bound to setup provenance."""
    bind = op.get_bind()
    count = bind.scalar(sa.text("select count(*) from checker_policies"))
    if count:
        raise RuntimeError(
            "0014_post_submit_setup cannot infer setup provenance for existing "
            "checker_policies rows. Reset those draft-era rows before upgrading."
        )


def upgrade() -> None:
    """Add post-submit setup continuation outputs to setup runs."""
    _preflight_no_legacy_checker_policy_rows()

    op.add_column(
        "checker_policies",
        sa.Column("guide_id", sa.String(length=36), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column("source_snapshot_hash", sa.String(length=71), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column("effective_policy_id", sa.String(length=36), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column("effective_policy_hash", sa.String(length=71), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column("pre_submit_checker_policy_id", sa.String(length=36), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column("pre_submit_checker_bundle_hash", sa.String(length=71), nullable=False),
    )
    op.add_column(
        "checker_policies",
        sa.Column(
            "lifecycle_status",
            sa.String(length=30),
            nullable=False,
            server_default="compiled",
        ),
    )
    op.alter_column("checker_policies", "lifecycle_status", server_default=None)
    op.add_column(
        "checker_policies",
        sa.Column("approved_by_role", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("approved_by_actor", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "checker_policies",
        sa.Column("created_by", sa.String(length=100), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_checker_policies_guide_id_project_guides"),
        "checker_policies",
        "project_guides",
        ["guide_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_checker_policies_source_snapshot_hash"),
        "checker_policies",
        "guide_source_snapshots",
        ["source_snapshot_id", "source_snapshot_hash"],
        ["id", "bundle_hash"],
    )
    op.create_foreign_key(
        op.f("fk_checker_policies_effective_policy_hash"),
        "checker_policies",
        "effective_project_submission_artifact_policies",
        ["effective_policy_id", "effective_policy_hash"],
        ["id", "effective_policy_hash"],
    )
    op.create_foreign_key(
        op.f("fk_checker_policies_pre_submit_checker_hash"),
        "checker_policies",
        "pre_submit_checker_policies",
        ["pre_submit_checker_policy_id", "pre_submit_checker_bundle_hash"],
        ["id", "compiled_bundle_hash"],
    )
    op.create_index(
        op.f("ix_checker_policies_guide_id"),
        "checker_policies",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checker_policies_source_snapshot_id"),
        "checker_policies",
        ["source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checker_policies_effective_policy_id"),
        "checker_policies",
        ["effective_policy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checker_policies_effective_policy_hash"),
        "checker_policies",
        ["effective_policy_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checker_policies_pre_submit_checker_policy_id"),
        "checker_policies",
        ["pre_submit_checker_policy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checker_policies_pre_submit_checker_bundle_hash"),
        "checker_policies",
        ["pre_submit_checker_bundle_hash"],
        unique=False,
    )
    op.create_check_constraint(
        "lifecycle_status",
        "checker_policies",
        "lifecycle_status in ('compiled', 'approved', 'superseded')",
    )
    op.create_check_constraint(
        "approval_provenance",
        "checker_policies",
        """
        lifecycle_status != 'approved'
        or (
            approved_by_role in ('admin', 'project_manager')
            and approved_by_actor is not null
            and approved_at is not null
        )
        """,
    )
    op.add_column(
        "project_setup_runs",
        sa.Column("output_post_submit_checker_policy_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "project_setup_runs",
        sa.Column("post_submit_derivation_summary", sa.JSON(), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_setup_runs_post_submit_checker_policy",
        "project_setup_runs",
        "checker_policies",
        ["output_post_submit_checker_policy_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_project_setup_runs_output_post_submit_checker_policy_id"),
        "project_setup_runs",
        ["output_post_submit_checker_policy_id"],
        unique=False,
    )
    op.drop_constraint(
        "ck_project_setup_runs_status",
        "project_setup_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_setup_runs_status",
        "project_setup_runs",
        "status in ("
        "'queued', "
        "'enqueue_failed', "
        "'running_sufficiency_agent', "
        "'sufficiency_blocked', "
        "'running_policy_derivation_agent', "
        "'policy_draft_ready', "
        "'running_post_submit_derivation_agent', "
        "'post_submit_setup_blocked', "
        "'post_submit_policy_compiled', "
        "'setup_blocked', "
        "'failed'"
        ")",
    )


def downgrade() -> None:
    """Remove post-submit setup continuation outputs."""
    op.drop_constraint(
        "ck_project_setup_runs_status",
        "project_setup_runs",
        type_="check",
    )
    op.execute(
        sa.text(
            "update project_setup_runs set status = 'setup_blocked' "
            "where status in ("
            "'running_post_submit_derivation_agent', "
            "'post_submit_setup_blocked'"
            ")"
        )
    )
    op.execute(
        sa.text(
            "update project_setup_runs set status = 'policy_draft_ready' "
            "where status = 'post_submit_policy_compiled'"
        )
    )
    op.create_check_constraint(
        "ck_project_setup_runs_status",
        "project_setup_runs",
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
    )
    op.execute(
        sa.text(
            "drop index if exists ix_project_setup_runs_output_post_submit_checker_policy_id"
        )
    )
    op.execute(
        sa.text(
            "alter table project_setup_runs "
            "drop constraint if exists fk_project_setup_runs_post_submit_checker_policy"
        )
    )
    op.execute(
        sa.text("alter table project_setup_runs drop column if exists post_submit_derivation_summary")
    )
    op.execute(
        sa.text(
            "alter table project_setup_runs "
            "drop column if exists output_post_submit_checker_policy_id"
        )
    )
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop constraint if exists ck_checker_policies_approval_provenance"
        )
    )
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop constraint if exists ck_checker_policies_ck_checker_policies_approval_provenance"
        )
    )
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop constraint if exists ck_checker_policies_lifecycle_status"
        )
    )
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop constraint if exists ck_checker_policies_ck_checker_policies_lifecycle_status"
        )
    )
    op.execute(sa.text("alter table checker_policies drop column if exists approved_at"))
    op.execute(sa.text("alter table checker_policies drop column if exists approved_by_actor"))
    op.execute(sa.text("alter table checker_policies drop column if exists approved_by_role"))
    op.execute(sa.text("alter table checker_policies drop column if exists lifecycle_status"))
    op.execute(
        sa.text(
            "drop index if exists ix_checker_policies_pre_submit_checker_bundle_hash"
        )
    )
    op.execute(
        sa.text(
            "drop index if exists ix_checker_policies_pre_submit_checker_policy_id"
        )
    )
    op.execute(sa.text("drop index if exists ix_checker_policies_effective_policy_hash"))
    op.execute(sa.text("drop index if exists ix_checker_policies_effective_policy_id"))
    op.execute(sa.text("drop index if exists ix_checker_policies_source_snapshot_id"))
    op.execute(sa.text("drop index if exists ix_checker_policies_guide_id"))
    op.drop_constraint(
        op.f("fk_checker_policies_pre_submit_checker_hash"),
        "checker_policies",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_checker_policies_effective_policy_hash"),
        "checker_policies",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_checker_policies_source_snapshot_hash"),
        "checker_policies",
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop constraint if exists fk_checker_policies_guide_id_project_guides"
        )
    )
    op.execute(sa.text("alter table checker_policies drop column if exists created_by"))
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop column if exists pre_submit_checker_bundle_hash"
        )
    )
    op.execute(
        sa.text(
            "alter table checker_policies "
            "drop column if exists pre_submit_checker_policy_id"
        )
    )
    op.execute(sa.text("alter table checker_policies drop column if exists effective_policy_hash"))
    op.execute(sa.text("alter table checker_policies drop column if exists effective_policy_id"))
    op.execute(sa.text("alter table checker_policies drop column if exists source_snapshot_hash"))
    op.execute(sa.text("alter table checker_policies drop column if exists source_snapshot_id"))
    op.execute(sa.text("alter table checker_policies drop column if exists guide_id"))
