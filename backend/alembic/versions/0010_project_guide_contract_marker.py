"""project guide contract marker

Revision ID: 0010_guide_cleanup
Revises: 0009_evaluation_pending_status
Create Date: 2026-07-05
"""

from __future__ import annotations

revision = "0010_guide_cleanup"
down_revision = "0009_evaluation_pending_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op marker after squashing removed construction-state guide fields."""


def downgrade() -> None:
    """No-op downgrade; discarded construction-state guide fields are not restored."""
