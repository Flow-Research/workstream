"""Register exact task authority evidence without altering retained data."""

from alembic import op
import sqlalchemy as sa

revision = "0017_task_project_authority"
down_revision = "0016_guide_document_runtime"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
_PAIRS = (
    ("task.claim", "task.claim"),
    ("task.start", "task.claim"),
    ("task.work_context.read", "task.queue.read"),
    ("project.task.work_context.read", "project.task.manage"),
)


def _pair(action: str, permission: str) -> str:
    return (
        f"(((action_id)::text = '{action}'::text) "
        f"AND ((permission_id)::text = '{permission}'::text))"
    )


def _amend(add: bool) -> None:
    definition = op.get_bind().execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='audit_events'::regclass and conname=:name"
    ), {"name": _CONSTRAINT}).scalar_one()
    anchor = _pair("operations.task.start_override", "operations.task.start_override")
    # The canonical constraint repeats exact pairs in the action registry and
    # in its permission-binding branch. Both must admit the same new pairs.
    if definition.count(anchor) != 2:
        raise RuntimeError("task authority audit anchor changed")
    extension = "".join(" OR " + _pair(action, permission) for action, permission in _PAIRS)
    if add:
        if any(_pair(*pair) in definition for pair in _PAIRS):
            raise RuntimeError("task authority actions already registered")
        definition = definition.replace(anchor, anchor + extension)
    else:
        if definition.count(extension) != 2:
            raise RuntimeError("task authority audit extension changed")
        definition = definition.replace(extension, "")
    op.execute(f"alter table audit_events drop constraint {_CONSTRAINT}")
    op.execute(f"alter table audit_events add constraint {_CONSTRAINT} " + definition)


def upgrade() -> None:
    _amend(True)


def downgrade() -> None:
    # Constraint validation intentionally refuses to erase evidence for these
    # actions. No downgrade deletes retained audit or eligibility rows.
    _amend(False)
