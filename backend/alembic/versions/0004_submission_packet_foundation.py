"""submission packet foundation

Revision ID: 0004_submission_packets
Revises: 0003_task_queue_assignment
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_submission_packets"
down_revision = "0003_task_queue_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create submission packet and evidence tables."""
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_guide",
        "workstream_tasks",
        ["id", "locked_guide_version"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_review_policy",
        "workstream_tasks",
        ["id", "locked_review_policy_version"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_revision_policy",
        "workstream_tasks",
        ["id", "locked_revision_policy_version"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_payment_policy",
        "workstream_tasks",
        ["id", "locked_payment_policy_version"],
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("package_uri", sa.String(length=1000), nullable=True),
        sa.Column("package_hash", sa.String(length=128), nullable=False),
        sa.Column("artifact_hash_manifest", sa.JSON(), nullable=False),
        sa.Column("worker_attestation", sa.Text(), nullable=False),
        sa.Column("locked_guide_version", sa.String(length=50), nullable=False),
        sa.Column("locked_review_policy_version", sa.String(length=50), nullable=False),
        sa.Column("locked_revision_policy_version", sa.String(length=50), nullable=False),
        sa.Column("locked_payment_policy_version", sa.String(length=50), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_submission_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["workstream_tasks.id"], name=op.f("fk_submissions_task_id_workstream_tasks")),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_submissions_task_locked_guide",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_review_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_review_policy_version"],
            name="fk_submissions_task_locked_review_policy",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_revision_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_revision_policy_version"],
            name="fk_submissions_task_locked_revision_policy",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "locked_payment_policy_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_payment_policy_version"],
            name="fk_submissions_task_locked_payment_policy",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_submission_id"],
            ["submissions.id"],
            name=op.f("fk_submissions_supersedes_submission_id_submissions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
        sa.UniqueConstraint("task_id", "version", name="uq_submissions_task_version"),
        sa.UniqueConstraint("id", "version", name="uq_submissions_id_version"),
    )
    op.create_index(op.f("ix_submissions_task_id"), "submissions", ["task_id"], unique=False)
    op.create_index(op.f("ix_submissions_worker_id"), "submissions", ["worker_id"], unique=False)
    op.create_index(op.f("ix_submissions_status"), "submissions", ["status"], unique=False)
    op.create_index(
        op.f("ix_submissions_supersedes_submission_id"),
        "submissions",
        ["supersedes_submission_id"],
        unique=False,
    )

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("uri", sa.String(length=1000), nullable=True),
        sa.Column("hash", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_evidence_items_submission_id_submissions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_items")),
    )
    op.create_index(op.f("ix_evidence_items_submission_id"), "evidence_items", ["submission_id"], unique=False)
    op.create_index(op.f("ix_evidence_items_type"), "evidence_items", ["type"], unique=False)


def downgrade() -> None:
    """Drop submission packet and evidence tables."""
    op.drop_index(op.f("ix_evidence_items_type"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_submission_id"), table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index(op.f("ix_submissions_supersedes_submission_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_status"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_worker_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_task_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_payment_policy",
        "workstream_tasks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_revision_policy",
        "workstream_tasks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_review_policy",
        "workstream_tasks",
        type_="unique",
    )
    op.drop_constraint("uq_workstream_tasks_id_locked_guide", "workstream_tasks", type_="unique")
