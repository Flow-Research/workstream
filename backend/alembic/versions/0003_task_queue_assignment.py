"""task queue assignment

Revision ID: 0003_task_queue_assignment
Revises: 0002_project_guide_foundation
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_task_queue_assignment"
down_revision = "0002_project_guide_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create task queue, assignment, profile, and audit tables."""
    op.create_table(
        "worker_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("external_subject", sa.String(length=200), nullable=False),
        sa.Column("external_issuer", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("skill_tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_profiles")),
        sa.UniqueConstraint("actor_id", name=op.f("uq_worker_profiles_actor_id")),
    )
    op.create_index(op.f("ix_worker_profiles_status"), "worker_profiles", ["status"], unique=False)

    op.create_table(
        "reviewer_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("external_subject", sa.String(length=200), nullable=False),
        sa.Column("external_issuer", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("skill_tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviewer_profiles")),
        sa.UniqueConstraint("actor_id", name=op.f("uq_reviewer_profiles_actor_id")),
    )
    op.create_index(op.f("ix_reviewer_profiles_status"), "reviewer_profiles", ["status"], unique=False)

    op.create_table(
        "workstream_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("locked_guide_version", sa.String(length=50), nullable=True),
        sa.Column("locked_review_policy_version", sa.String(length=50), nullable=True),
        sa.Column("locked_revision_policy_version", sa.String(length=50), nullable=True),
        sa.Column("locked_payment_policy_version", sa.String(length=50), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=True),
        sa.Column("source_payload_hash", sa.String(length=128), nullable=True),
        sa.Column("import_batch_id", sa.String(length=100), nullable=True),
        sa.Column("external_task_id", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=True),
        sa.Column("difficulty", sa.String(length=50), nullable=True),
        sa.Column("skill_tags", sa.JSON(), nullable=False),
        sa.Column("estimated_time_minutes", sa.Integer(), nullable=True),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=20), nullable=True),
        sa.Column("payout_type", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("rejection_criteria", sa.Text(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("assigned_to", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_workstream_tasks_project_id_projects")),
        sa.ForeignKeyConstraint(
            ["project_id", "locked_guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_workstream_tasks_locked_guide",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "locked_review_policy_version"],
            ["review_policies.project_id", "review_policies.guide_version"],
            name="fk_workstream_tasks_locked_review_policy",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "locked_revision_policy_version"],
            ["revision_policies.project_id", "revision_policies.guide_version"],
            name="fk_workstream_tasks_locked_revision_policy",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "locked_payment_policy_version"],
            ["payment_policies.project_id", "payment_policies.guide_version"],
            name="fk_workstream_tasks_locked_payment_policy",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workstream_tasks")),
    )
    op.create_index(op.f("ix_workstream_tasks_assigned_to"), "workstream_tasks", ["assigned_to"], unique=False)
    op.create_index(op.f("ix_workstream_tasks_project_id"), "workstream_tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_workstream_tasks_status"), "workstream_tasks", ["status"], unique=False)

    op.create_table(
        "task_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column("assigned_by", sa.String(length=100), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["workstream_tasks.id"], name=op.f("fk_task_assignments_task_id_workstream_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_assignments")),
    )
    op.create_index(op.f("ix_task_assignments_task_id"), "task_assignments", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_assignments_worker_id"), "task_assignments", ["worker_id"], unique=False)
    op.create_index(op.f("ix_task_assignments_status"), "task_assignments", ["status"], unique=False)
    op.create_index(
        "uq_task_assignments_one_active_per_task",
        "task_assignments",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("external_subject", sa.String(length=200), nullable=False),
        sa.Column("external_issuer", sa.String(length=200), nullable=False),
        sa.Column("actor_roles", sa.JSON(), nullable=False),
        sa.Column("claim_snapshot", sa.JSON(), nullable=False),
        sa.Column("auth_source", sa.String(length=30), nullable=False),
        sa.Column("is_dev_auth", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_events_entity_id"), "audit_events", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_events_entity_type"), "audit_events", ["entity_type"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)


def downgrade() -> None:
    """Drop task queue, assignment, profile, and audit tables."""
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_entity_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_entity_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("uq_task_assignments_one_active_per_task", table_name="task_assignments")
    op.drop_index(op.f("ix_task_assignments_status"), table_name="task_assignments")
    op.drop_index(op.f("ix_task_assignments_worker_id"), table_name="task_assignments")
    op.drop_index(op.f("ix_task_assignments_task_id"), table_name="task_assignments")
    op.drop_table("task_assignments")
    op.drop_index(op.f("ix_workstream_tasks_status"), table_name="workstream_tasks")
    op.drop_index(op.f("ix_workstream_tasks_project_id"), table_name="workstream_tasks")
    op.drop_index(op.f("ix_workstream_tasks_assigned_to"), table_name="workstream_tasks")
    op.drop_table("workstream_tasks")
    op.drop_index(op.f("ix_reviewer_profiles_status"), table_name="reviewer_profiles")
    op.drop_table("reviewer_profiles")
    op.drop_index(op.f("ix_worker_profiles_status"), table_name="worker_profiles")
    op.drop_table("worker_profiles")
