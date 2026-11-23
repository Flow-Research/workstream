"""Retain discovered multipart handles before uncertain abort operations."""
from alembic import op
from sqlalchemy import text

revision = "0089_observed_upload_cleanup"
down_revision = "0088_unsealed_source_cleanup"
branch_labels = None
depends_on = None


def _definition(name):
    return op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:name AS regprocedure))"
    ), {"name": name}).scalar_one()


def _replace(body, old, new):
    if body.count(old) != 1:
        raise RuntimeError("observed upload cleanup predecessor shape changed")
    return body.replace(old, new)


def upgrade():
    """Extend existing claims; preserve every prior source and audit digest."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submission_intake_operations, public.submission_source_cleanup_claims, "
               "public.submission_source_upload_receipts IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE public.submission_source_cleanup_claims ADD COLUMN observed_upload_ids jsonb")
    op.execute("ALTER TABLE public.submission_source_cleanup_claims ADD CONSTRAINT "
               "ck_submission_source_cleanup_claims_observed_upload_shape CHECK "
               "(observed_upload_ids is null or (jsonb_typeof(observed_upload_ids)='array' "
               "and jsonb_array_length(observed_upload_ids) between 1 and 100 and observed_source is null))")
    authority = _definition("public.source_cleanup_authority_valid(public.submission_source_cleanup_claims,text)")
    authority = _replace(authority, "CASE WHEN c.observed_source IS NOT NULL THEN",
        "CASE WHEN c.observed_upload_ids IS NOT NULL THEN jsonb_build_object("
        "'schema_version','workstream.observed_submission_uploads_cleanup.v1',"
        "'source',c.source,'observed_upload_ids',c.observed_upload_ids) "
        "WHEN c.observed_source IS NOT NULL THEN")
    op.execute(authority)
    guard = _definition("public.guard_submission_source_cleanup()")
    marker = " IF TG_OP='UPDATE' AND OLD.observed_source IS NULL AND NEW.observed_source IS NOT NULL THEN"
    guard = _replace(guard, marker, _OBSERVATION + "\n" + marker)
    guard = _replace(guard, "OR NEW.observed_source IS NOT NULL OR NEW.observed_at IS NOT NULL THEN",
        "OR NEW.observed_source IS NOT NULL OR NEW.observed_at IS NOT NULL "
        "OR NEW.observed_upload_ids IS NOT NULL THEN")
    op.execute(guard)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_OBSERVATION = """
 IF TG_OP='UPDATE' AND NEW.observed_upload_ids IS DISTINCT FROM OLD.observed_upload_ids THEN
   IF OLD.confirmed_at IS NOT NULL OR OLD.lease_expires_at<=clock_timestamp()
      OR OLD.source->>'kind' IS DISTINCT FROM 'unsealed'
      OR OLD.source->'provider_upload_id' IS DISTINCT FROM 'null'::jsonb
      OR o.provider_profile NOT IN ('minio-v1','aws-s3-v1')
      OR o.sealed_at IS NOT NULL OR o.raw_sha256 IS NOT NULL OR OLD.observed_source IS NOT NULL
      OR (to_jsonb(NEW)-'observed_upload_ids') IS DISTINCT FROM (to_jsonb(OLD)-'observed_upload_ids')
      OR NOT public.source_cleanup_authority_valid(OLD,'claim')
      OR NOT EXISTS(SELECT 1 FROM public.submission_source_upload_receipts
         WHERE operation_id=o.id AND provider_upload_id IS NULL AND completion_parts IS NULL)
      OR NEW.observed_upload_ids IS NULL OR jsonb_typeof(NEW.observed_upload_ids)<>'array' THEN
     RAISE EXCEPTION 'source cleanup upload observation differs' USING ERRCODE='23514';
   END IF;
   IF jsonb_array_length(NEW.observed_upload_ids) NOT BETWEEN 1 AND 100
      OR NOT coalesce(OLD.observed_upload_ids,'[]'::jsonb) <@ NEW.observed_upload_ids
      OR jsonb_array_length(NEW.observed_upload_ids)<=jsonb_array_length(coalesce(OLD.observed_upload_ids,'[]'::jsonb))
      OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.observed_upload_ids) v
         WHERE jsonb_typeof(v)<>'string' OR length(v #>> '{}') NOT BETWEEN 1 AND 2048)
      OR NEW.observed_upload_ids IS DISTINCT FROM
         (SELECT jsonb_agg(value ORDER BY value COLLATE "C") FROM
           (SELECT DISTINCT value FROM jsonb_array_elements_text(NEW.observed_upload_ids)) canonical) THEN
     RAISE EXCEPTION 'source cleanup upload observation is not canonical growth' USING ERRCODE='23514';
   END IF;
   -- Old authority cannot authorize deletion of newly discovered handles.
   -- A later claim generation binds the complete retained handle set.
   RETURN NEW;
 END IF;
"""
