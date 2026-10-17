"""Admit the Project Manager and Finance project-wide read decisions and index the project preparation list."""

from alembic import op
from sqlalchemy import text

revision = "0051_project_reads"
down_revision = "0050_contributor_reads"
branch_labels = None
depends_on = None

_ACTIONS = (
    ("project.guide.list", "project.guide.manage"),
    ("project.guide.read", "project.guide.manage"),
    ("project.guide.activation_readiness.read", "project.guide.manage"),
    ("project.guide.document.read", "project.guide.manage"),
    ("project.submission.list", "project.task.manage"),
    ("project.assignment.list", "project.task.manage"),
    ("project.summary.read", "project.task.manage"),
    ("project.task.import_batch.list", "project.task.manage"),
    ("project.submission_bundle_preparation.list", "project.task.manage"),
    ("contribution.policy.list", "compensation.policy.manage"),
)


def upgrade():
    """Extend the closed action/permission evidence vocabulary and add one read index; no data changes."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = (
        "(((action_id)::text = 'contribution.read_self'::text) AND "
        "((permission_id)::text = 'contribution.read_self'::text))"
    )
    addition = "".join(
        f" OR (((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
        for action, permission in _ACTIONS
    )
    if definition.count(anchor) != 2 or any(action in definition for action, _ in _ACTIONS):
        raise RuntimeError("project read audit action constraint shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " "
               + definition.replace(anchor, anchor + addition))
    # The project preparation list reads newest first by (queued_at, id) within one project.
    op.create_index(
        "ix_selected_pre_submit_runs_project_queued", "selected_pre_submit_runs",
        ["project_id", text("queued_at DESC"), text("id DESC")],
    )


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
