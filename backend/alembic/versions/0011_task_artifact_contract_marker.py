"""task artifact contract marker

Revision ID: 0011_task_artifact_cleanup
Revises: 0010_guide_cleanup
Create Date: 2026-07-05
"""

from __future__ import annotations

revision = "0011_task_artifact_cleanup"
down_revision = "0010_guide_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op marker after squashing removed task-owned artifact fields."""


def downgrade() -> None:
    """No-op downgrade; discarded task-owned artifact fields are not restored."""
