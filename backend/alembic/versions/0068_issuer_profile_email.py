"""Track the latest signed email observation on its exact identity link."""
from alembic import op
import sqlalchemy as sa

revision = "0068_issuer_profile_email"
down_revision = "0067_canonical_json_restore_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("actor_identity_links", sa.Column("email_observed_issued_at", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
