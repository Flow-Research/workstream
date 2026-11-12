"""Permit uncertain accepted-finalization delivery to replay exact T5 custody."""

from alembic import op
from sqlalchemy import text

revision = "0076_submission_delivery_retry"
down_revision = "0075_source_post_custody"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.outbox_events IN SHARE ROW EXCLUSIVE MODE")
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef('public.check_outbox_delivery_projection()'::regprocedure)"
    )).scalar_one()
    old = "e.event_type not in ('TaskRevisionExpiryRequested','TaskRevisionExpired')"
    new = "e.event_type not in ('TaskRevisionExpiryRequested','TaskRevisionExpired','SubmissionFinalizationRequested')"
    if body.count(old) != 1:
        raise RuntimeError("submission delivery retry predecessor shape changed")
    op.execute(body.replace(old, new))


def downgrade():
    raise RuntimeError("Retained finalization retry custody cannot be downgraded")
