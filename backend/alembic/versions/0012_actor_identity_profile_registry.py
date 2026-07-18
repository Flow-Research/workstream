"""actor identity profile registry

Revision ID: 0012_actor_identity_profiles
Revises: 0011_task_artifact_cleanup
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_actor_identity_profiles"
down_revision = "0011_task_artifact_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create actor registry tables and remove obsolete profile stores."""
    op.create_table(
        "actor_identities",
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("external_subject", sa.String(length=200), nullable=False),
        sa.Column("external_issuer", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("last_seen_roles", sa.JSON(), nullable=False),
        sa.Column("last_claim_snapshot", sa.JSON(), nullable=False),
        sa.Column("auth_source", sa.String(length=50), nullable=False),
        sa.Column("is_dev_auth", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("actor_id", name=op.f("pk_actor_identities")),
        sa.UniqueConstraint(
            "external_issuer",
            "external_subject",
            name="uq_actor_identities_external_identity",
        ),
    )
    op.create_table(
        "actor_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("profile_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("skill_tags", sa.JSON(), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=100), nullable=False),
        sa.Column("profile_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "profile_type in ('worker', 'reviewer', 'admin', 'project_manager', 'project_owner')",
            name="ck_actor_profiles_profile_type",
        ),
        sa.CheckConstraint(
            "status in ('observed', 'active', 'disabled')",
            name="ck_actor_profiles_status",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["actor_identities.actor_id"],
            name=op.f("fk_actor_profiles_actor_id_actor_identities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actor_profiles")),
        sa.UniqueConstraint(
            "actor_id",
            "profile_type",
            "scope_type",
            "scope_id",
            name="uq_actor_profiles_actor_type_scope",
        ),
    )
    op.create_index(op.f("ix_actor_profiles_actor_id"), "actor_profiles", ["actor_id"], unique=False)
    op.create_index(op.f("ix_actor_profiles_profile_type"), "actor_profiles", ["profile_type"], unique=False)
    op.create_index(op.f("ix_actor_profiles_status"), "actor_profiles", ["status"], unique=False)

    op.drop_index(op.f("ix_reviewer_profiles_status"), table_name="reviewer_profiles")
    op.drop_table("reviewer_profiles")
    op.drop_index(op.f("ix_worker_profiles_status"), table_name="worker_profiles")
    op.drop_table("worker_profiles")


def downgrade() -> None:
    """Restore prior schema shape without preserving obsolete profile data."""
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

    op.drop_index(op.f("ix_actor_profiles_status"), table_name="actor_profiles")
    op.drop_index(op.f("ix_actor_profiles_profile_type"), table_name="actor_profiles")
    op.drop_index(op.f("ix_actor_profiles_actor_id"), table_name="actor_profiles")
    op.drop_table("actor_profiles")
    op.drop_table("actor_identities")
