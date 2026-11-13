"""Register the dedicated source-cleanup principal and exact audit action."""
from alembic import op
from sqlalchemy import text

revision = "0079_cleanup_authority"
down_revision = "0078_submission_cleanup"
branch_labels = None
depends_on = None


def _extend(table, name, anchor, addition, occurrences):
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid=CAST(:table AS regclass) AND conname=:name"
    ), {"table": "public." + table, "name": name}).scalar_one()
    if definition.count(anchor) != occurrences or "source_cleanup" in definition or "submission_source.cleanup" in definition:
        raise RuntimeError("cleanup authority predecessor constraint changed: " + name)
    op.execute(f"ALTER TABLE public.{table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE public.{table} ADD CONSTRAINT {name} " + definition.replace(anchor, anchor + addition))


def upgrade():
    """Preserve all retained rows and every preceding closed authority entry."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.actor_profiles, public.audit_events IN ACCESS EXCLUSIVE MODE")
    _extend("actor_profiles", "ck_actor_profiles_kind_service_identity",
            "('workstream.artifact.binding'::character varying)::text",
            ", ('workstream.artifact.source_cleanup'::character varying)::text", 1)
    _extend("audit_events", "ck_audit_events_authority_registries",
            "('artifact.binding.create'::character varying)::text",
            ", ('artifact.submission_source.cleanup'::character varying)::text", 1)
    _extend("audit_events", "ck_audit_events_authorization_action_evidence",
            "(((action_id)::text = 'artifact.submission.finalize'::text) AND ((permission_id)::text = 'artifact.binding.create'::text))",
            " OR (((action_id)::text = 'artifact.submission_source.cleanup'::text) AND ((permission_id)::text = 'artifact.submission_source.cleanup'::text))", 2)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
