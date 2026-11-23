"""Remove the expiring provider proof tables and their private triggers."""

from alembic import op

revision = "0069_remove_artifact_proof"
down_revision = "0068_issuer_profile_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop only standalone proof custody, without cascading into product data."""
    op.drop_table("artifact_provider_activations", schema="public")
    op.drop_table("artifact_provider_probe_results", schema="public")
    op.execute("DROP FUNCTION public.guard_artifact_provider_activation()")
    op.execute("DROP FUNCTION public.guard_artifact_provider_probe_result()")


def downgrade() -> None:
    """Retired proof rows cannot be reconstructed."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
