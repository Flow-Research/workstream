"""Keep canonical JSON validation independent of the restore session search path."""

from alembic import op

revision = "0067_canonical_json_restore_path"
down_revision = "0066_guide_check_specification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bind unchanged recursive and outbox validator bodies to their public owner."""
    for signature in (
        "public.project_guide_projection_canonical_json(jsonb)",
        "public.outbox_delivery_outcome_valid(text,text,timestamptz,timestamptz,timestamptz)",
        "public.project_role_availability_is_safe(jsonb)",
        "public.project_role_reference_array_is_safe(jsonb,boolean)",
    ):
        op.execute(f"ALTER FUNCTION {signature} SET search_path=pg_catalog,public,pg_temp")


def downgrade() -> None:
    """Never restore session-dependent recursion on retained evidence."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
