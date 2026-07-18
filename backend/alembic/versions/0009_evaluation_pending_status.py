"""evaluation pending task status marker

Revision ID: 0009_evaluation_pending_status
Revises: 0008_post_submit_checker_policy
Create Date: 2026-07-04
"""

from __future__ import annotations

revision = "0009_evaluation_pending_status"
down_revision = "0008_post_submit_checker_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op marker; the current schema only uses evaluation_pending."""


def downgrade() -> None:
    """No-op downgrade; discarded task status names are not restored."""
