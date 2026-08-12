"""Bind consumed submission version to an ART admission."""

from alembic import op
import sqlalchemy as sa

revision = "0002_admission_version"
down_revision = "0001_v01_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_submission_bundle_admissions_terminal_shape",
        "submission_bundle_admissions",
        type_="check",
    )
    op.add_column(
        "submission_bundle_admissions",
        sa.Column("consumed_by_submission_version", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_submission_bundle_admissions_terminal_shape",
        "submission_bundle_admissions",
        "(status='ready' and consumed_at is null and consumed_by_submission_id is null "
        "and consumed_by_submission_version is null and stale_at is null and stale_reason is null) "
        "or (status='consumed' and consumed_at is not null and "
        "consumed_by_submission_id is not null and consumed_by_submission_version > 0 "
        "and stale_at is null and stale_reason is null) or "
        "(status='stale' and consumed_at is null and consumed_by_submission_id is null "
        "and consumed_by_submission_version is null and stale_at is not null "
        "and octet_length(stale_reason) between 1 and 500)",
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations are forward-only; recreate the database")
