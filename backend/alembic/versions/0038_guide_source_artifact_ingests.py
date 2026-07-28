"""add server-owned guide source artifact ingest facts

Revision ID: 0038_guide_source_ingest
Revises: 0037_art_auth_context_evidence
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0038_guide_source_ingest"
down_revision = "0037_art_auth_context_evidence"
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_table(
        "guide_source_artifact_ingests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_item_id", sa.String(length=36), nullable=False),
        sa.Column("actor_profile_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_count >= 0",
            name="ck_guide_source_artifact_ingests_bytes",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_source_artifact_ingests_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"],
            ["actor_profiles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id"],
            ["guide_source_snapshot_items.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_item_id"),
    )
    op.create_index(
        op.f("ix_guide_source_artifact_ingests_actor_profile_id"),
        "guide_source_artifact_ingests",
        ["actor_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guide_source_artifact_ingests_source_item_id"),
        "guide_source_artifact_ingests",
        ["source_item_id"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table guide_source_artifact_ingests in access exclusive mode"))
    if bind.execute(
        sa.text("select exists(select 1 from guide_source_artifact_ingests)")
    ).scalar_one():
        raise RuntimeError("cannot downgrade populated guide source artifact ingests")
    op.drop_index(
        op.f("ix_guide_source_artifact_ingests_source_item_id"),
        table_name="guide_source_artifact_ingests",
    )
    op.drop_index(
        op.f("ix_guide_source_artifact_ingests_actor_profile_id"),
        table_name="guide_source_artifact_ingests",
    )
    op.drop_table("guide_source_artifact_ingests")
