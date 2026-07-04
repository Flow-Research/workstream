"""rename auto checking task status to evaluation pending

Revision ID: 0009_evaluation_pending_status
Revises: 0008_post_submit_checker_policy
Create Date: 2026-07-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_evaluation_pending_status"
down_revision = "0008_post_submit_checker_policy"
branch_labels = None
depends_on = None


OLD_STATUS = "auto_checking"
NEW_STATUS = "evaluation_pending"


def _replace_status(old_status: str, new_status: str) -> None:
    """Rewrite persisted task and audit status tokens."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "update workstream_tasks set status = :new_status where status = :old_status"
        ),
        {"old_status": old_status, "new_status": new_status},
    )
    bind.execute(
        sa.text(
            "update audit_events set from_status = :new_status where from_status = :old_status"
        ),
        {"old_status": old_status, "new_status": new_status},
    )
    bind.execute(
        sa.text("update audit_events set to_status = :new_status where to_status = :old_status"),
        {"old_status": old_status, "new_status": new_status},
    )


def upgrade() -> None:
    """Move existing persisted rows to the clearer evaluation status."""
    _replace_status(OLD_STATUS, NEW_STATUS)


def downgrade() -> None:
    """Restore the previous persisted status token on downgrade."""
    _replace_status(NEW_STATUS, OLD_STATUS)
