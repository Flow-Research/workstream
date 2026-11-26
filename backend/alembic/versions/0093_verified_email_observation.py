"""Persist verified mailbox proof and allow bounded recovery of feedback email."""

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
    ), schema="public")
    op.create_check_constraint(
        "ck_actor_identity_links_email_verified_observation", "actor_identity_links",
        "not email_verified or (subject_kind = 'human' and email_observed_issued_at is not null)",
        schema="public",
    )
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.outbox_events IN SHARE ROW EXCLUSIVE MODE")
    body = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_functiondef('public.check_outbox_delivery_projection()'::regprocedure)"
    )).scalar_one()
    old = "'TaskRevisionExpired','SubmissionFinalizationRequested','SubmissionFinalizationRecoveryRequested')"
    if body.count(old) != 1:
        raise RuntimeError("feedback email retry predecessor shape changed")
    op.execute(body.replace(old, old[:-1] + ",'SubmissionFeedbackEmailRequested')"))


def downgrade() -> None:
    """Refuse removal of retained mailbox-verification custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
