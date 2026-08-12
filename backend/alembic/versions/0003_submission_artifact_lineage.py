"""Add canonical admission and artifact lineage to TASK Submissions."""

from alembic import op
import sqlalchemy as sa

revision = "0003_submission_lineage"
down_revision = "0002_admission_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("submissions", "package_hash", existing_type=sa.String(128), nullable=True)
    op.add_column("submissions", sa.Column("task_assignment_id", sa.String(36)))
    op.add_column("submissions", sa.Column("submission_bundle_admission_id", sa.String(36)))
    op.add_column("submissions", sa.Column("artifact_binding_id", sa.String(36)))
    op.add_column("submissions", sa.Column("artifact_content_id", sa.String(36)))
    op.create_foreign_key(
        "fk_submissions_task_assignment_id_task_assignments",
        "submissions",
        "task_assignments",
        ["task_assignment_id"],
        ["id"],
    )
    op.create_index("ix_submissions_task_assignment_id", "submissions", ["task_assignment_id"])
    op.create_index(
        "ix_submissions_submission_bundle_admission_id",
        "submissions",
        ["submission_bundle_admission_id"],
        unique=True,
    )
    op.create_unique_constraint(
        "uq_submissions_artifact_binding_id", "submissions", ["artifact_binding_id"]
    )
    op.create_check_constraint(
        op.f("ck_submissions_artifact_lineage_shape"),
        "submissions",
        "(task_assignment_id is null and submission_bundle_admission_id is null "
        "and artifact_binding_id is null and artifact_content_id is null) or "
        "(task_assignment_id is not null and submission_bundle_admission_id is not null "
        "and artifact_binding_id is not null and artifact_content_id is not null)",
    )
    op.create_index("ix_submissions_artifact_content_id", "submissions", ["artifact_content_id"])


def downgrade() -> None:
    raise RuntimeError(
        "Workstream v0.1 migrations cannot be downgraded; recreate the database"
    )
