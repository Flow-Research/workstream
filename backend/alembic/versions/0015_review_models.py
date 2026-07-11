"""review_models: Review and ReviewFinding tables

Revision ID: 0015_review_models
Revises: 0014_post_submit_setup
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_review_models"
down_revision = "0014_post_submit_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id"), nullable=False, index=True),
        sa.Column("reviewer_actor_id", sa.String(100), sa.ForeignKey("actor_identities.actor_id"), nullable=False, index=True),
        sa.Column("decision", sa.String(30), nullable=False, index=True),
        sa.Column("acceptance_evidence_refs", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("decision in ('accept', 'needs_revision', 'reject')", name="ck_reviews_decision"),
    )
    op.create_index("ix_reviews_submission_created", "reviews", ["submission_id", "created_at"])

    op.create_table(
        "review_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("reviews.id"), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("area", sa.String(100), nullable=False),
        sa.Column("issue", sa.Text, nullable=False),
        sa.Column("required_fix", sa.Text, nullable=False),
        sa.Column("evidence_ref", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("severity in ('low', 'medium', 'high', 'critical')", name="ck_review_findings_severity"),
    )


def downgrade() -> None:
    op.drop_table("review_findings")
    op.drop_table("reviews")
