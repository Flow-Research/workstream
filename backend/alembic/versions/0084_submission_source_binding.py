"""Require accepted source custody for new admission consumption."""

from alembic import op
from sqlalchemy import text

revision = "0084_submission_source_binding"
down_revision = "0083_accepted_revision"
branch_labels = None
depends_on = None


def upgrade():
    """Preserve retained rows while closing the retired consumption transition."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submission_bundle_admissions IN ACCESS EXCLUSIVE MODE")
    signature = "public.guard_submission_bundle_admission_lineage()"
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    anchor = " if old.status<>'ready' or new.status not in ('consumed','stale') then"
    if body.count(anchor) != 1:
        raise RuntimeError("source binding predecessor changed: " + signature)
    guard = """ if old.status='ready' and new.status='consumed'
    and old.source_operation_id is null then
  raise exception 'new submission binding requires accepted source custody' using errcode='55000';
 end if;
"""
    op.execute(body.replace(anchor, guard + anchor))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
