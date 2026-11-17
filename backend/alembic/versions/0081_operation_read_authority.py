"""Admit exact management operation-read audit evidence without rewriting history."""
from alembic import op
from sqlalchemy import text

revision = "0081_operation_read_authority"
down_revision = "0080_cleanup_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "(((action_id)::text = 'task.submission_operation.read'::text) AND ((permission_id)::text = 'submission.read_own'::text))"
    if definition.count(anchor) != 2 or "project.task.submission_operation.read" in definition:
        raise RuntimeError("operation read audit action constraint shape changed")
    addition = " OR (((action_id)::text = 'project.task.submission_operation.read'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " " + definition.replace(anchor, anchor + addition))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
