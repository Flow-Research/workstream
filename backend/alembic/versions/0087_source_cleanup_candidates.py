"""Index terminal source candidates without weakening cleanup custody."""
from alembic import op

revision = "0087_source_cleanup_candidates"
down_revision = "0086_pending_checker_custody"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE INDEX ix_submission_intake_cleanup_candidates
        ON public.submission_intake_operations (terminal_at,id)
        WHERE state IN ('rejected','failed','abandoned','cancelled')
          AND accepted_at IS NULL AND sealed_at IS NOT NULL""")


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
