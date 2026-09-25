"""Admit only the three exact locked-context read authorization evidence pairs."""

from alembic import op
import sqlalchemy as sa

revision = "0004_task_context_authority"
down_revision = "0003_task_read_authority"
branch_labels = None
depends_on = None


def upgrade():
    """Extend the closed decision constraint without rewriting retained evidence."""
    name = "ck_audit_events_authorization_action_evidence"
    op.execute("lock table audit_events in access exclusive mode")
    definition = op.get_bind().execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='audit_events'::regclass and conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "(((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    addition = " OR ".join(
        f"(((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
        for action, permission in (
            ("project.task.locked_context.read", "project.task.manage"),
            ("operations.task.locked_context.read", "operations.status.read"),
            ("audit.task.locked_context.read", "audit.read"),
        )
    )
    if definition.count(anchor) != 2:
        raise RuntimeError("task locked-context authority constraint shape changed")
    op.execute(f"alter table audit_events drop constraint {name}")
    op.execute(f"alter table audit_events add constraint {name} " + definition.replace(anchor, anchor + " OR " + addition))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
