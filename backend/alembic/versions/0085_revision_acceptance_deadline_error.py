"""Identify a conclusive revision-deadline rejection without masking custody errors."""
from alembic import op
from sqlalchemy import text

revision = "0085_revision_deadline_error"
down_revision = "0084_submission_source_binding"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.workstream_tasks, public.submission_intake_operations, "
               "public.task_revision_preparations IN ACCESS EXCLUSIVE MODE")
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef("
        "'public.require_submission_acceptance_current(public.submission_intake_operations)'::regprocedure)"
    )).scalar_one()
    old_deadline = "OR p.deadline_at IS NULL OR p.deadline_at<=clock_timestamp()"
    old_end = """     RAISE EXCEPTION 'revision acceptance is no longer eligible' USING ERRCODE='23514';
   END IF;"""
    if body.count(old_deadline) != 1 or body.count(old_end) != 1:
        raise RuntimeError("revision acceptance deadline predecessor changed")
    body = body.replace(old_deadline, "OR p.deadline_at IS NULL")
    body = body.replace(old_end, old_end + """
   IF p.deadline_at<=clock_timestamp() THEN
     RAISE EXCEPTION 'revision acceptance deadline expired'
       USING ERRCODE='23514', CONSTRAINT='ck_submission_revision_acceptance_deadline';
   END IF;""")
    op.execute(body)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
