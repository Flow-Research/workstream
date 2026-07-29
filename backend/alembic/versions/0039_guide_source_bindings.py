"""add exact guide source bindings and setup generations

Revision ID: 0039_guide_source_bindings
Revises: 0038_guide_source_ingest
Create Date: 2026-07-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0039_guide_source_bindings"
down_revision = "0038_guide_source_ingest"
branch_labels = depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_setup_runs",
        sa.Column("setup_generation", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            with generations as (
                select id,
                       row_number() over (
                           partition by guide_id
                           order by created_at, id
                       ) as setup_generation
                from project_setup_runs
            )
            update project_setup_runs as runs
            set setup_generation = generations.setup_generation
            from generations
            where runs.id = generations.id
            """
        )
    )
    op.alter_column("project_setup_runs", "setup_generation", nullable=False)
    op.create_check_constraint(
        "ck_project_setup_runs_generation_positive",
        "project_setup_runs",
        "setup_generation > 0",
    )
    op.create_unique_constraint(
        "uq_project_setup_runs_guide_generation",
        "project_setup_runs",
        ["guide_id", "setup_generation"],
    )
    op.create_unique_constraint(
        "uq_project_setup_runs_exact_generation",
        "project_setup_runs",
        ["id", "project_id", "guide_id", "source_snapshot_id", "setup_generation"],
    )
    op.create_unique_constraint(
        "uq_guide_source_snapshots_exact_lineage",
        "guide_source_snapshots",
        ["id", "project_id", "guide_id"],
    )
    op.create_unique_constraint(
        "uq_guide_source_snapshot_items_exact_lineage",
        "guide_source_snapshot_items",
        ["id", "source_snapshot_id"],
    )
    op.create_unique_constraint(
        "uq_artifact_replicas_id_content",
        "artifact_replicas",
        ["id", "content_id"],
    )

    op.create_table(
        "guide_source_artifact_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source_item_id", sa.String(length=36), nullable=False),
        sa.Column("project_setup_run_id", sa.String(length=36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("verified_replica_id", sa.String(length=36), nullable=False),
        sa.Column("logical_role", sa.String(length=100), nullable=False),
        sa.Column("supersedes_binding_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_service", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "setup_generation > 0",
            name="ck_guide_bindings_generation_positive",
        ),
        sa.CheckConstraint(
            "logical_role = 'guide_source_original'",
            name="ck_guide_bindings_role",
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["artifact_contents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "project_id", "guide_id"],
            [
                "guide_source_snapshots.id",
                "guide_source_snapshots.project_id",
                "guide_source_snapshots.guide_id",
            ],
            name="fk_guide_bindings_exact_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id", "source_snapshot_id"],
            ["guide_source_snapshot_items.id", "guide_source_snapshot_items.source_snapshot_id"],
            name="fk_guide_bindings_exact_item",
        ),
        sa.ForeignKeyConstraint(
            [
                "project_setup_run_id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_generation",
            ],
            [
                "project_setup_runs.id",
                "project_setup_runs.project_id",
                "project_setup_runs.guide_id",
                "project_setup_runs.source_snapshot_id",
                "project_setup_runs.setup_generation",
            ],
            name="fk_guide_bindings_exact_setup_generation",
        ),
        sa.ForeignKeyConstraint(
            ["verified_replica_id", "content_id"],
            ["artifact_replicas.id", "artifact_replicas.content_id"],
            name="fk_guide_bindings_verified_replica_content",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_binding_id"],
            ["guide_source_artifact_bindings.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_item_id",
            "setup_generation",
            name="uq_guide_bindings_item_generation",
        ),
        sa.UniqueConstraint(
            "supersedes_binding_id",
            name="uq_guide_bindings_supersedes",
        ),
    )
    for column in (
        "project_id",
        "guide_id",
        "source_snapshot_id",
        "source_item_id",
        "project_setup_run_id",
        "content_id",
        "verified_replica_id",
        "supersedes_binding_id",
    ):
        op.create_index(
            op.f(f"ix_guide_source_artifact_bindings_{column}"),
            "guide_source_artifact_bindings",
            [column],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table guide_source_artifact_bindings in access exclusive mode"))
    if bind.execute(
        sa.text("select exists(select 1 from guide_source_artifact_bindings)")
    ).scalar_one():
        raise RuntimeError("cannot downgrade populated guide source artifact bindings")
    op.drop_table("guide_source_artifact_bindings")
    op.drop_constraint(
        "uq_artifact_replicas_id_content",
        "artifact_replicas",
        type_="unique",
    )
    op.drop_constraint(
        "uq_guide_source_snapshot_items_exact_lineage",
        "guide_source_snapshot_items",
        type_="unique",
    )
    op.drop_constraint(
        "uq_guide_source_snapshots_exact_lineage",
        "guide_source_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "uq_project_setup_runs_exact_generation",
        "project_setup_runs",
        type_="unique",
    )
    op.drop_constraint(
        "uq_project_setup_runs_guide_generation",
        "project_setup_runs",
        type_="unique",
    )
    op.drop_constraint(
        "ck_project_setup_runs_generation_positive",
        "project_setup_runs",
        type_="check",
    )
    op.drop_column("project_setup_runs", "setup_generation")
