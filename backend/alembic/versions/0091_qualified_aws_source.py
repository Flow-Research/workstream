"""Admit the qualified AWS source profile to the existing selected PRE guard."""

from alembic import op
from sqlalchemy import text

revision = "0091_qualified_aws_source"
down_revision = "0090_merge_direct_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change only the profile/scheme predicate; retain every other source fence."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.selected_pre_submit_runs IN ACCESS EXCLUSIVE MODE")
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef("
        "'public.require_selected_pre_source(public.selected_pre_submit_runs)'::regprocedure)"
    )).scalar_one()
    replacements = (
        ("o.provider_profile NOT IN ('local-v2','minio-v1')",
         "o.provider_profile NOT IN ('local-v2','minio-v1','aws-s3-v1')"),
        ("WHEN 'minio-v1' THEN 's3' END",
         "WHEN 'minio-v1' THEN 's3' WHEN 'aws-s3-v1' THEN 's3' END"),
    )
    for old, new in replacements:
        if definition.count(old) != 1:
            raise RuntimeError("qualified AWS source predecessor shape changed")
        definition = definition.replace(old, new)
    op.execute(definition)


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
