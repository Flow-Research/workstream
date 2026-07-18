"""add durable API rate controls

Revision ID: 0017_api_controls
Revises: 0016_artifact_domain
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_api_controls"
down_revision = "0016_artifact_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the privacy-keyed cross-replica counter table."""
    op.create_table(
        "api_rate_control_counters",
        sa.Column("control_scope", sa.String(32), nullable=False),
        sa.Column("key_digest", sa.LargeBinary(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "control_scope",
            "key_digest",
            name="pk_api_rate_control_counters",
        ),
        sa.CheckConstraint(
            "control_scope in ('first_access', 'admin_mutation')",
            name=op.f("ck_api_rate_control_counters_scope_token"),
        ),
        sa.CheckConstraint(
            "octet_length(key_digest) = 32",
            name=op.f("ck_api_rate_control_counters_digest_length"),
        ),
        sa.CheckConstraint(
            "request_count between 1 and 9223372036854775807",
            name=op.f("ck_api_rate_control_counters_request_count"),
        ),
        sa.CheckConstraint(
            "window_started_at < window_expires_at",
            name=op.f("ck_api_rate_control_counters_window_order"),
        ),
    )
    op.create_index(
        "ix_api_rate_control_counters_window_expires_at",
        "api_rate_control_counters",
        ["window_expires_at"],
    )


def downgrade() -> None:
    """Drop only an empty rate-control table."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table api_rate_control_counters in access exclusive mode"))
    has_rows = bind.execute(
        sa.text("select exists(select 1 from api_rate_control_counters)")
    ).scalar_one()
    if has_rows:
        raise RuntimeError("cannot downgrade non-empty API rate controls")
    op.drop_index(
        "ix_api_rate_control_counters_window_expires_at",
        table_name="api_rate_control_counters",
    )
    op.drop_table("api_rate_control_counters")
