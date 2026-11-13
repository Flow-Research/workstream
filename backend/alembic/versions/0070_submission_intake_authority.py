"""Admit exact source-reservation and own-operation read authorization evidence."""
from alembic import op
from sqlalchemy import text

revision = "0070_submission_intake_authority"
down_revision = "0069_submission_intake_custody"
branch_labels = None
depends_on = None


def _definition(name):
    return op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()


def _replace(name, definition):
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " " + definition)


def upgrade():
    """Extend closed evidence vocabulary without rewriting retained decisions."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition(name)
    anchor = "(((action_id)::text = 'contribution.read_self'::text) AND ((permission_id)::text = 'contribution.read_self'::text))"
    actions = (("submission.intake.reserve", "submission.create"),
               ("task.submission_operation.read", "submission.read_own"))
    if definition.count(anchor) != 2 or any(action in definition for action, _ in actions):
        raise RuntimeError("intake authorization audit action constraint shape changed")
    addition = "".join(f" OR (((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
                       for action, permission in actions)
    _replace(name, definition.replace(anchor, anchor + addition))
    name = "ck_audit_events_authority_privacy_bounds"
    definition = _definition(name)
    if "'submission_operation'::character varying" in definition:
        raise RuntimeError("intake audit target constraint already changed")
    positions = [definition.index("resource_type IS NULL"), definition.index("target_ref_kind IS NULL")]
    for start in sorted(positions, reverse=True):
        index = definition.index("ARRAY[", start) + len("ARRAY[")
        definition = definition[:index] + "('submission_operation'::character varying)::text, " + definition[index:]
    _replace(name, definition)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
