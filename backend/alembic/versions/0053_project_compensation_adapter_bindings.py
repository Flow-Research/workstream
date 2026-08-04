"""add project compensation adapter-binding persistence

Revision ID: 0053_compensation_bindings
Revises: 0052_legacy_intake_removal
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0053_compensation_bindings"
down_revision = "0052_legacy_intake_removal"
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_compensation_adapter_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("instrument_type", sa.String(32), nullable=False),
        sa.Column("adapter_actor_id", sa.String(36), nullable=False),
        sa.Column("route_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("binding_lifecycle_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("suspended_by", sa.String(36)),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("retired_by", sa.String(36)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "instrument_type in ('money','project_points')",
            name="ck_project_compensation_adapter_bindings_instrument_type",
        ),
        sa.CheckConstraint(
            "route_key ~ '^[A-Za-z][A-Za-z0-9._:-]{0,119}$'",
            name="ck_project_compensation_adapter_bindings_route_key",
        ),
        sa.CheckConstraint(
            "route_key not like '%..%'",
            name="ck_project_compensation_adapter_bindings_route_key_no_traversal",
        ),
        sa.CheckConstraint(
            "status in ('active','suspended','retired')",
            name="ck_project_compensation_adapter_bindings_status",
        ),
        sa.CheckConstraint(
            "binding_lifecycle_version > 0",
            name="ck_project_compensation_adapter_bindings_lifecycle_version_positive",
        ),
        sa.CheckConstraint(
            "status='active' and binding_lifecycle_version=1 "
            "and suspended_by is null and suspended_at is null "
            "and retired_by is null and retired_at is null",
            name="ck_project_compensation_adapter_bindings_lifecycle_shape",
        ),
        sa.CheckConstraint(
            "(suspended_at is null or suspended_at >= created_at) and "
            "(retired_at is null or retired_at >= created_at) and "
            "(retired_at is null or suspended_at is null or retired_at >= suspended_at)",
            name="ck_project_compensation_adapter_bindings_lifecycle_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_compensation_binding_project"
        ),
        sa.ForeignKeyConstraint(
            ["adapter_actor_id"],
            ["actor_profiles.id"],
            name="fk_compensation_binding_adapter_actor",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["actor_profiles.id"], name="fk_compensation_binding_created_by"
        ),
        sa.ForeignKeyConstraint(
            ["suspended_by"], ["actor_profiles.id"], name="fk_compensation_binding_suspended_by"
        ),
        sa.ForeignKeyConstraint(
            ["retired_by"], ["actor_profiles.id"], name="fk_compensation_binding_retired_by"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_compensation_adapter_bindings"),
        sa.UniqueConstraint(
            "id", "project_id", "instrument_type", name="uq_compensation_binding_ownership"
        ),
    )
    op.create_index(
        "uq_compensation_binding_active_project_instrument",
        "project_compensation_adapter_bindings",
        ["project_id", "instrument_type"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )
    op.create_index(
        "ix_compensation_binding_adapter_actor",
        "project_compensation_adapter_bindings",
        ["adapter_actor_id", "status", "id"],
    )
    op.execute(
        """
        create function enforce_compensation_binding_lifecycle() returns trigger
        language plpgsql as $$
        begin
          raise exception 'compensation_binding_updates_deferred';
          return new;
        end;
        $$;
        """
    )
    op.execute(
        """
        create trigger project_compensation_binding_update_guard
        before update on project_compensation_adapter_bindings
        for each row execute function enforce_compensation_binding_lifecycle();
        """
    )


def downgrade() -> None:
    op.execute(
        "drop trigger project_compensation_binding_update_guard "
        "on project_compensation_adapter_bindings"
    )
    op.execute("drop function enforce_compensation_binding_lifecycle()")
    op.drop_index(
        "ix_compensation_binding_adapter_actor",
        table_name="project_compensation_adapter_bindings",
    )
    op.drop_index(
        "uq_compensation_binding_active_project_instrument",
        table_name="project_compensation_adapter_bindings",
    )
    op.drop_table("project_compensation_adapter_bindings")
