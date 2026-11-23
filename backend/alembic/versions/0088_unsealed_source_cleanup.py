"""Admit exact unsealed cleanup targets without synthesizing sealed custody."""
from alembic import op
from sqlalchemy import text

revision = "0088_unsealed_source_cleanup"
down_revision = "0087_source_cleanup_candidates"
branch_labels = None
depends_on = None


def _definition(name):
    return op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:name AS regprocedure))"
    ), {"name": name}).scalar_one()


def _replace(body, old, new):
    if body.count(old) != 1:
        raise RuntimeError("unsealed cleanup predecessor shape changed")
    return body.replace(old, new)


def upgrade():
    """Retain old source/claim/audit values; broaden only proved cleanup release."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submission_intake_operations, public.submission_source_charges, "
               "public.submission_source_cleanup_claims, public.submission_source_upload_receipts "
               "IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE public.submission_source_cleanup_claims ADD COLUMN observed_source jsonb, "
               "ADD COLUMN observed_at timestamptz")
    op.execute("ALTER TABLE public.submission_source_cleanup_claims ADD CONSTRAINT "
               "ck_submission_source_cleanup_claims_observed_shape CHECK "
               "((observed_source is null and observed_at is null) or "
               "(jsonb_typeof(observed_source)='object' and observed_at is not null))")
    requirement = _definition("public.require_sealed_source_cleanup(public.submission_intake_operations)")
    requirement = requirement.replace("require_sealed_source_cleanup", "require_submission_source_cleanup")
    requirement = _replace(requirement,
        "OR o.accepted_at IS NOT NULL OR o.provider_generation IS NULL OR o.sealed_at IS NULL",
        "OR o.accepted_at IS NOT NULL")
    requirement = _replace(requirement,
        "greatest(o.terminal_at,o.sealed_at)",
        "greatest(o.terminal_at,o.sealed_at,(SELECT observed_at FROM public.submission_source_cleanup_claims WHERE operation_id=o.id))")
    op.execute(requirement)
    op.execute(_TARGET)
    for name in ("guard_submission_source_cleanup", "guard_submission_source_charge", "check_submission_source_accounting"):
        body = _definition("public." + name + "()")
        body = body.replace("require_sealed_source_cleanup", "require_submission_source_cleanup")
        if name == "guard_submission_source_cleanup":
            start = body.index(" expected:=jsonb_build_object")
            end = body.index(" IF NEW.source", start)
            body = body[:start] + " expected:=public.submission_source_cleanup_target(o);\n" + body[end:]
            body = _replace(body, " IF TG_OP='INSERT' THEN", _OBSERVATION + "\n IF TG_OP='INSERT' THEN")
            body = _replace(body, "IF NEW.generation<>1 OR NEW.confirmed_at IS NOT NULL OR NEW.confirmation_decision_id IS NOT NULL THEN",
                "IF NEW.generation<>1 OR NEW.confirmed_at IS NOT NULL OR NEW.confirmation_decision_id IS NOT NULL "
                "OR NEW.observed_source IS NOT NULL OR NEW.observed_at IS NOT NULL THEN")
        elif name == "guard_submission_source_charge":
            body = _replace(body, "OLD.state NOT IN ('sealed','released')", "OLD.state NOT IN ('reserved','sealed','released')")
        op.execute(body)
    op.execute("DROP FUNCTION public.require_sealed_source_cleanup(public.submission_intake_operations)")
    authority = _definition("public.source_cleanup_authority_valid(public.submission_source_cleanup_claims,text)")
    authority = _replace(authority,
        "c.source || jsonb_build_object('schema_version','workstream.sealed_submission_source.v1')",
        "CASE WHEN c.observed_source IS NOT NULL THEN jsonb_build_object("
        "'schema_version','workstream.observed_submission_source_cleanup.v1',"
        "'source',c.source,'observed_source',c.observed_source) ELSE c.source || "
        "jsonb_build_object('schema_version',CASE WHEN c.source->>'kind'='unsealed' "
        "THEN 'workstream.unsealed_submission_source.v1' ELSE 'workstream.sealed_submission_source.v1' END) END")
    op.execute(authority)
    op.execute("ALTER TABLE public.submission_source_charges DROP CONSTRAINT ck_submission_source_charges_charge_shape")
    op.execute("ALTER TABLE public.submission_source_charges ADD CONSTRAINT ck_submission_source_charges_charge_shape CHECK "
               "((state='reserved' and accounted_bytes=reserved_bytes and sealed_at is null) "
               "or (state='sealed' and sealed_at is not null and accounted_bytes>0) "
               "or (state='released' and accounted_bytes=0))")
    op.drop_index("ix_submission_intake_cleanup_candidates", table_name="submission_intake_operations")
    op.create_index("ix_submission_intake_cleanup_candidates", "submission_intake_operations", ["terminal_at", "id"],
                    postgresql_where=text("state in ('rejected','failed','abandoned','cancelled') and accepted_at is null"))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_TARGET = """
CREATE FUNCTION public.submission_source_cleanup_target(o public.submission_intake_operations)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT CASE WHEN o.sealed_at IS NOT NULL THEN jsonb_build_object(
   'location',jsonb_build_object('operation_id',o.id::text,'namespace_id',o.namespace_id,
     'namespace_fingerprint',o.namespace_fingerprint,'provider_profile',o.provider_profile),
   'provider_generation',o.provider_generation,'raw_sha256',o.raw_sha256,'raw_byte_count',o.raw_byte_count,
   'sealed_upload_fence',o.sealed_upload_fence,'media_type','application/zip')
 ELSE jsonb_build_object(
   'kind','unsealed',
   'location',jsonb_build_object('operation_id',o.id::text,'namespace_id',o.namespace_id,
     'namespace_fingerprint',o.namespace_fingerprint,'provider_profile',o.provider_profile),
   'upload_fence',r.upload_fence,'provider_upload_id',r.provider_upload_id,
   'raw_sha256',o.raw_sha256,'raw_byte_count',o.raw_byte_count)
 END FROM (SELECT 1) singleton LEFT JOIN public.submission_source_upload_receipts r ON r.operation_id=o.id
$$
"""


_OBSERVATION = """
 IF TG_OP='UPDATE' AND OLD.observed_source IS NULL AND NEW.observed_source IS NOT NULL THEN
   IF OLD.confirmed_at IS NOT NULL OR OLD.lease_expires_at<=clock_timestamp()
      OR OLD.source->>'kind' IS DISTINCT FROM 'unsealed' OR o.sealed_at IS NOT NULL
      OR o.raw_sha256 IS NULL OR o.raw_byte_count IS NULL
      OR (to_jsonb(NEW)-ARRAY['observed_source','observed_at']) IS DISTINCT FROM
         (to_jsonb(OLD)-ARRAY['observed_source','observed_at'])
      OR NOT public.source_cleanup_authority_valid(OLD,'claim')
      OR NOT EXISTS(SELECT 1 FROM public.submission_source_upload_receipts
         WHERE operation_id=o.id AND completion_parts IS NOT NULL AND provider_upload_id IS NOT NULL)
      OR coalesce(length(NEW.observed_source->>'provider_generation'),0) NOT BETWEEN 1 AND 2048
      OR (o.provider_profile='aws-s3-v1' AND NEW.observed_source->>'provider_generation'='null')
      OR NEW.observed_source IS DISTINCT FROM jsonb_build_object(
        'location',OLD.source->'location','provider_generation',NEW.observed_source->>'provider_generation',
        'raw_sha256',o.raw_sha256,'raw_byte_count',o.raw_byte_count,
        'sealed_upload_fence',OLD.source->'upload_fence','media_type','application/zip') THEN
     RAISE EXCEPTION 'source cleanup completion observation differs' USING ERRCODE='23514';
   END IF;
   NEW.observed_at:=clock_timestamp();
   -- The old claim no longer authorizes deletion. A later aged generation must
   -- obtain a fresh decision bound to this exact observed version.
   RETURN NEW;
 END IF;
 IF TG_OP='UPDATE' AND (NEW.observed_source IS DISTINCT FROM OLD.observed_source
                       OR NEW.observed_at IS DISTINCT FROM OLD.observed_at) THEN
   RAISE EXCEPTION 'source cleanup observation is immutable' USING ERRCODE='23514';
 END IF;
"""
