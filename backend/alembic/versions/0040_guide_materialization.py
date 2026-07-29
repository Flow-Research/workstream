"""add verified guide classifications and bounded incidents

Revision ID: 0040_guide_materialization
Revises: 0039_guide_source_bindings
Create Date: 2026-07-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0040_guide_materialization"
down_revision = "0039_guide_source_bindings"
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_guide_bindings_exact_read",
        "guide_source_artifact_bindings",
        ["id", "content_id", "verified_replica_id", "setup_generation"],
    )
    op.create_table(
        "guide_source_format_classifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("verified_replica_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("detected_format", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("detector_name", sa.String(100), nullable=False),
        sa.Column("detector_version", sa.String(40), nullable=False),
        sa.Column("classification_facts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["binding_id", "content_id", "verified_replica_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.verified_replica_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_classifications_exact_binding",
        ),
        sa.UniqueConstraint("binding_id", name="uq_guide_classifications_binding"),
        sa.CheckConstraint(
            "status in ('classified','unsupported','ambiguous','malformed','limit_exceeded')",
            name="ck_guide_classifications_status",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_source_format_classifications_sha256_shape",
        ),
        sa.CheckConstraint(
            "byte_count >= 0", name="ck_guide_source_format_classifications_byte_count_nonnegative"
        ),
    )
    op.create_table(
        "guide_source_artifact_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("verified_replica_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("observed_sha256", sa.String(71), nullable=True),
        sa.Column("observed_byte_count", sa.BigInteger(), nullable=True),
        sa.Column("bounded_facts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["binding_id", "content_id", "verified_replica_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.verified_replica_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_incidents_exact_binding",
        ),
        sa.CheckConstraint(
            "code in ('missing','changed','truncated','unavailable','stale','conflict')",
            name="ck_guide_incidents_code",
        ),
        sa.CheckConstraint(
            "observed_byte_count is null or observed_byte_count >= 0",
            name="ck_guide_source_artifact_incidents_size",
        ),
        sa.CheckConstraint(
            "observed_sha256 is null or observed_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_source_artifact_incidents_sha256",
        ),
    )
    for table in ("guide_source_format_classifications", "guide_source_artifact_incidents"):
        for column in ("binding_id", "content_id", "verified_replica_id"):
            op.create_index(op.f(f"ix_{table}_{column}"), table, [column])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table guide_source_format_classifications, guide_source_artifact_incidents in access exclusive mode"
        )
    )
    if bind.execute(
        sa.text(
            "select exists(select 1 from guide_source_format_classifications) or exists(select 1 from guide_source_artifact_incidents)"
        )
    ).scalar_one():
        raise RuntimeError("cannot downgrade populated guide materialization evidence")
    op.drop_table("guide_source_artifact_incidents")
    op.drop_table("guide_source_format_classifications")
    op.drop_constraint(
        "uq_guide_bindings_exact_read", "guide_source_artifact_bindings", type_="unique"
    )
