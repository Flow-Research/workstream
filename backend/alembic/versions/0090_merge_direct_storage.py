"""Join deployed direct-storage and submission-custody migration histories."""
revision = "0090_merge_direct_storage"
down_revision = ("0089_observed_upload_cleanup", "0069_remove_artifact_proof")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Both parents retain their own changes; this merge rewrites no product data."""


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
