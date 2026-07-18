"""project guide foundation

Revision ID: 0002_project_guide_foundation
Revises: 0001_initial_baseline
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_project_guide_foundation"
down_revision = "0001_initial_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("slug", name=op.f("uq_projects_slug")),
    )
    op.create_index(op.f("ix_projects_slug"), "projects", ["slug"], unique=False)
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)

    op.create_table(
        "project_guides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_project_guides_project_id_projects")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_guides")),
        sa.UniqueConstraint("project_id", "version", name="uq_project_guides_project_version"),
    )
    op.create_index(op.f("ix_project_guides_project_id"), "project_guides", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_guides_status"), "project_guides", ["status"], unique=False)
    op.create_index(
        "uq_project_guides_one_active_per_project",
        "project_guides",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "checker_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("required_checkers", sa.JSON(), nullable=False),
        sa.Column("warning_checkers", sa.JSON(), nullable=False),
        sa.Column("blocking_severities", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_checker_policies_project_id_projects")),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_checker_policies_project_guide",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checker_policies")),
        sa.UniqueConstraint("project_id", "guide_version", name="uq_checker_policies_project_version"),
    )
    op.create_index(op.f("ix_checker_policies_project_id"), "checker_policies", ["project_id"], unique=False)

    op.create_table(
        "payment_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=20), nullable=True),
        sa.Column("payout_type", sa.String(length=50), nullable=True),
        sa.Column("revision_payment_rule", sa.Text(), nullable=True),
        sa.Column("rejection_payment_rule", sa.Text(), nullable=True),
        sa.Column("accepted_payment_rule", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_payment_policies_project_id_projects")),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_payment_policies_project_guide",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_policies")),
        sa.UniqueConstraint("project_id", "guide_version", name="uq_payment_policies_project_version"),
    )
    op.create_index(op.f("ix_payment_policies_project_id"), "payment_policies", ["project_id"], unique=False)

    op.create_table(
        "review_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("requires_second_review", sa.Boolean(), nullable=False),
        sa.Column("allowed_decisions", sa.JSON(), nullable=False),
        sa.Column("minimum_finding_fields", sa.JSON(), nullable=False),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_review_policies_project_id_projects")),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_review_policies_project_guide",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_policies")),
        sa.UniqueConstraint("project_id", "guide_version", name="uq_review_policies_project_version"),
    )
    op.create_index(op.f("ix_review_policies_project_id"), "review_policies", ["project_id"], unique=False)

    op.create_table(
        "revision_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("max_revision_rounds", sa.Integer(), nullable=False),
        sa.Column("revision_deadline_hours", sa.Integer(), nullable=False),
        sa.Column("auto_reject_after_limit", sa.Boolean(), nullable=False),
        sa.Column("allowed_resubmission_states", sa.JSON(), nullable=False),
        sa.Column("reviewer_reassignment_rule", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_revision_policies_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_revision_policies_project_guide",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_revision_policies")),
        sa.UniqueConstraint("project_id", "guide_version", name="uq_revision_policies_project_version"),
    )
    op.create_index(op.f("ix_revision_policies_project_id"), "revision_policies", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_revision_policies_project_id"), table_name="revision_policies")
    op.drop_table("revision_policies")
    op.drop_index(op.f("ix_review_policies_project_id"), table_name="review_policies")
    op.drop_table("review_policies")
    op.drop_index(op.f("ix_payment_policies_project_id"), table_name="payment_policies")
    op.drop_table("payment_policies")
    op.drop_index(op.f("ix_checker_policies_project_id"), table_name="checker_policies")
    op.drop_table("checker_policies")
    op.drop_index("uq_project_guides_one_active_per_project", table_name="project_guides")
    op.drop_index(op.f("ix_project_guides_status"), table_name="project_guides")
    op.drop_index(op.f("ix_project_guides_project_id"), table_name="project_guides")
    op.drop_table("project_guides")
    op.drop_index(op.f("ix_projects_status"), table_name="projects")
    op.drop_index(op.f("ix_projects_slug"), table_name="projects")
    op.drop_table("projects")
