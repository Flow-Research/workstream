"""allow unverified service identity links

Revision ID: 0024_service_link_verification
Revises: 0023_service_actor_identity
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0024_service_link_verification"
down_revision = "0023_service_actor_identity"
branch_labels = depends_on = None


def upgrade() -> None:
    """Make service verification explicit while preserving human invariants."""
    op.alter_column(
        "actor_identity_links",
        "last_verified_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        nullable=True,
    )
    op.create_check_constraint(
        op.f("ck_actor_identity_links_human_verified"),
        "actor_identity_links",
        "subject_kind = 'service' or last_verified_at is not null",
    )


def downgrade() -> None:
    """Restore the historical implicit timestamp only when no proof is lost."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table actor_identity_links in access exclusive mode"))
    has_unverified_service = bind.execute(
        sa.text(
            "select exists(select 1 from actor_identity_links "
            "where subject_kind='service' and last_verified_at is null)"
        )
    ).scalar_one()
    if has_unverified_service:
        raise RuntimeError("cannot downgrade with unverified service identity links")
    op.drop_constraint(
        op.f("ck_actor_identity_links_human_verified"),
        "actor_identity_links",
        type_="check",
    )
    op.alter_column(
        "actor_identity_links",
        "last_verified_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
