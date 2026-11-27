"""Keep old attempts historical while an accepted replacement awaits finalization."""
from alembic import op
from sqlalchemy import text

revision = "0086_pending_checker_custody"
down_revision = "0085_revision_deadline_error"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.workstream_tasks, public.submissions, public.checker_runs "
               "IN ACCESS EXCLUSIVE MODE")
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef('public.require_new_checker_task_stamps()'::regprocedure)"
    )).scalar_one()
    anchor = "THEN RAISE EXCEPTION 'checker task context differs' USING ERRCODE='23514'; END IF;"
    if body.count(anchor) != 1:
        raise RuntimeError("checker pending-custody predecessor changed")
    op.execute(body.replace(anchor, anchor + """
      IF t.status='evaluation_pending' AND t.active_submission_operation_id IS NOT NULL
         AND s.attempt_status<>'evaluation_pending' THEN
        RAISE EXCEPTION 'accepted submission supersedes checker target'
          USING ERRCODE='23514', CONSTRAINT='ck_checker_pending_submission_current';
      END IF;"""))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
