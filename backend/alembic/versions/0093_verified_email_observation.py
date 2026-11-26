"""Require a fresh signed mailbox verification observation for email delivery."""

from alembic import op
import sqlalchemy as sa

revision = "0093_verified_email_observation"
down_revision = "0092_submission_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Treat all historical signed mailbox addresses as unverified."""
    op.add_column("actor_identity_links", sa.Column(
        "email_verified", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.create_check_constraint(
        "ck_actor_identity_links_email_verified_observation", "actor_identity_links",
        "not email_verified or (subject_kind = 'human' and email_observed_issued_at is not null)",
    )


def downgrade() -> None:
    """Refuse removal of retained mailbox-verification custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
