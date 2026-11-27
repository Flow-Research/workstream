"""Retain exact sealed-source cleanup claims and guard confirmed charge release."""
import re

from alembic import op
from sqlalchemy import text

revision = "0078_submission_cleanup"
down_revision = "0077_submission_recovery"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    """Extend the installed owner guard only at its exact predecessor boundary."""
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("cleanup predecessor shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    """Add tombstones without rewriting any source or retained evidence."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submission_intake_operations, public.submission_source_charges, "
               "public.artifact_replicas, public.submission_bundle_admissions IN ACCESS EXCLUSIVE MODE")
    op.execute(_TABLE)
    op.execute("CREATE INDEX ix_source_cleanup_pending ON public.submission_source_cleanup_claims "
               "(lease_expires_at) WHERE confirmed_at IS NULL")
    for statement in re.split(r"\n(?=CREATE (?:FUNCTION|CONSTRAINT TRIGGER|TRIGGER))", _GUARDS):
        if statement.strip():
            op.execute(statement)
    for name, expression in {
        "positive_charge": "reserved_bytes>0 and accounted_bytes>=0 and accounted_bytes<=reserved_bytes",
        "charge_state": "state in ('reserved','sealed','released')",
        "charge_shape": "(state='reserved' and accounted_bytes=reserved_bytes and sealed_at is null) "
                        "or (state='sealed' and sealed_at is not null and accounted_bytes>0) "
                        "or (state='released' and sealed_at is not null and accounted_bytes=0)",
    }.items():
        op.execute(f"ALTER TABLE public.submission_source_charges DROP CONSTRAINT "
                   f"ck_submission_source_charges_{name}")
        op.execute(f"ALTER TABLE public.submission_source_charges ADD CONSTRAINT "
                   f"ck_submission_source_charges_{name} CHECK ({expression})")
    _replace("public.guard_submission_source_charge()", "  IF TG_OP='INSERT' THEN", _RELEASE + "\n  IF TG_OP='INSERT' THEN")
    _replace("public.check_submission_source_accounting()", "  IF o.id IS NULL OR c.operation_id IS NULL",
             _RELEASE_ACCOUNTING + "\n  IF o.id IS NULL OR c.operation_id IS NULL")


def downgrade():
    """Never discard retained cleanup custody through a downgrade."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_TABLE = """
CREATE TABLE public.submission_source_cleanup_claims (
 operation_id uuid NOT NULL,
 claim_id uuid NOT NULL,
 generation bigint NOT NULL,
 source jsonb NOT NULL,
 claimed_at timestamptz NOT NULL,
 lease_expires_at timestamptz NOT NULL,
 confirmed_at timestamptz,
 CONSTRAINT pk_submission_source_cleanup_claims PRIMARY KEY(operation_id),
 CONSTRAINT fk_source_cleanup_operation FOREIGN KEY(operation_id) REFERENCES public.submission_intake_operations(id),
 CONSTRAINT ck_submission_source_cleanup_claims_claim_bounds CHECK
   (generation>0 AND lease_expires_at>claimed_at AND lease_expires_at<=claimed_at+interval '300 seconds'),
 CONSTRAINT ck_submission_source_cleanup_claims_source_shape CHECK (jsonb_typeof(source)='object'),
 CONSTRAINT ck_submission_source_cleanup_claims_claim_uuid7 CHECK
   ((get_byte(uuid_send(claim_id),6)>>4)=7 AND (get_byte(uuid_send(claim_id),8)&192)=128)
)
"""

_GUARDS = """
CREATE FUNCTION public.require_sealed_source_cleanup(o public.submission_intake_operations)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF o.id IS NULL OR o.state NOT IN ('rejected','failed','abandoned','cancelled')
    OR o.accepted_at IS NOT NULL OR o.provider_generation IS NULL OR o.sealed_at IS NULL
    OR o.terminal_at IS NULL OR greatest(o.terminal_at,o.sealed_at)>clock_timestamp()-interval '2 hours'
    OR EXISTS(SELECT 1 FROM public.workstream_tasks WHERE id=o.task_id AND active_submission_operation_id=o.id)
    OR EXISTS(SELECT 1 FROM public.artifact_replicas WHERE source_operation_id=o.id
       OR (storage_namespace_id=o.namespace_id AND namespace_fingerprint=o.namespace_fingerprint
           AND provider_object_ref=o.object_ref))
    OR EXISTS(SELECT 1 FROM public.submission_bundle_admissions WHERE source_operation_id=o.id) THEN
   RAISE EXCEPTION 'source cleanup is protected' USING ERRCODE='23514';
 END IF;
END $$;
CREATE FUNCTION public.guard_submission_source_cleanup()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE o public.submission_intake_operations%ROWTYPE; task_key uuid; expected jsonb; lease_span interval;
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN
   RAISE EXCEPTION 'source cleanup tombstone is retained' USING ERRCODE='23514'; END IF;
 SELECT task_id INTO task_key FROM public.submission_intake_operations WHERE id=NEW.operation_id;
 PERFORM 1 FROM public.workstream_tasks WHERE id=task_key FOR UPDATE;
 SELECT * INTO o FROM public.submission_intake_operations WHERE id=NEW.operation_id FOR UPDATE;
 PERFORM public.require_sealed_source_cleanup(o);
 expected:=jsonb_build_object('location',jsonb_build_object('operation_id',o.id::text,
   'namespace_id',o.namespace_id,'namespace_fingerprint',o.namespace_fingerprint,'provider_profile',o.provider_profile),
   'provider_generation',o.provider_generation,'raw_sha256',o.raw_sha256,'raw_byte_count',o.raw_byte_count,
   'sealed_upload_fence',o.sealed_upload_fence,'media_type','application/zip');
 IF NEW.source IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'source cleanup target differs' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
   IF NEW.generation<>1 OR NEW.confirmed_at IS NOT NULL THEN
     RAISE EXCEPTION 'source cleanup initial claim differs' USING ERRCODE='23514'; END IF;
   lease_span:=NEW.lease_expires_at-NEW.claimed_at;
   NEW.claimed_at:=clock_timestamp();
   NEW.lease_expires_at:=NEW.claimed_at+lease_span;
 ELSE
   IF OLD.confirmed_at IS NOT NULL THEN
     IF NEW IS DISTINCT FROM OLD THEN
       RAISE EXCEPTION 'confirmed source cleanup is immutable' USING ERRCODE='23514'; END IF;
     RETURN NEW;
   END IF;
   IF NEW.operation_id IS DISTINCT FROM OLD.operation_id OR NEW.source IS DISTINCT FROM OLD.source THEN
     RAISE EXCEPTION 'source cleanup identity is immutable' USING ERRCODE='23514'; END IF;
   IF NEW.claim_id=OLD.claim_id THEN
     IF (to_jsonb(NEW)-'confirmed_at') IS DISTINCT FROM (to_jsonb(OLD)-'confirmed_at')
        OR OLD.lease_expires_at<=clock_timestamp() OR NEW.confirmed_at IS NULL THEN
       RAISE EXCEPTION 'source cleanup fence is stale' USING ERRCODE='23514'; END IF;
     NEW.confirmed_at:=clock_timestamp();
   ELSE
     IF OLD.lease_expires_at>clock_timestamp() OR NEW.generation<>OLD.generation+1 OR NEW.confirmed_at IS NOT NULL THEN
       RAISE EXCEPTION 'source cleanup claim is busy' USING ERRCODE='23514'; END IF;
     lease_span:=NEW.lease_expires_at-NEW.claimed_at;
     NEW.claimed_at:=clock_timestamp();
     NEW.lease_expires_at:=NEW.claimed_at+lease_span;
   END IF;
 END IF;
 IF NEW.lease_expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'source cleanup lease expired' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER submission_source_cleanup_guard
BEFORE INSERT OR UPDATE OR DELETE ON public.submission_source_cleanup_claims
FOR EACH ROW EXECUTE FUNCTION public.guard_submission_source_cleanup();
CREATE TRIGGER submission_source_cleanup_no_truncate BEFORE TRUNCATE ON public.submission_source_cleanup_claims
FOR EACH STATEMENT EXECUTE FUNCTION public.guard_submission_source_cleanup();
CREATE FUNCTION public.check_source_cleanup_release()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE c public.submission_source_cleanup_claims%ROWTYPE; s public.submission_source_charges%ROWTYPE;
BEGIN
 SELECT * INTO c FROM public.submission_source_cleanup_claims WHERE operation_id=NEW.operation_id;
 SELECT * INTO s FROM public.submission_source_charges WHERE operation_id=NEW.operation_id;
 IF s.operation_id IS NULL OR (c.confirmed_at IS NOT NULL) IS DISTINCT FROM (s.state='released') THEN
   RAISE EXCEPTION 'source cleanup release must be atomic' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER source_cleanup_release_atomic AFTER INSERT OR UPDATE ON public.submission_source_cleanup_claims
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_source_cleanup_release();
CREATE FUNCTION public.guard_cleanup_retention_barrier()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE candidate record; namespace_key text; fingerprint text; object_key text;
BEGIN
 IF TG_TABLE_NAME='artifact_replicas' THEN
   namespace_key:=NEW.storage_namespace_id;
   fingerprint:=NEW.namespace_fingerprint;
   object_key:=NEW.provider_object_ref;
 END IF;
 FOR candidate IN SELECT id,task_id FROM public.submission_intake_operations
     WHERE id=NEW.source_operation_id OR (namespace_id=namespace_key
       AND namespace_fingerprint=fingerprint AND object_ref=object_key)
     ORDER BY task_id,id LOOP
   PERFORM 1 FROM public.workstream_tasks WHERE id=candidate.task_id FOR UPDATE;
   PERFORM 1 FROM public.submission_intake_operations WHERE id=candidate.id FOR UPDATE;
   IF EXISTS(SELECT 1 FROM public.submission_source_cleanup_claims WHERE operation_id=candidate.id) THEN
     RAISE EXCEPTION 'cleanup claimed source cannot become retained' USING ERRCODE='23514'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER source_cleanup_replica_retention BEFORE INSERT OR UPDATE ON public.artifact_replicas
FOR EACH ROW EXECUTE FUNCTION public.guard_cleanup_retention_barrier();
CREATE TRIGGER source_cleanup_admission_retention BEFORE INSERT OR UPDATE ON public.submission_bundle_admissions
FOR EACH ROW EXECUTE FUNCTION public.guard_cleanup_retention_barrier();
"""

_RELEASE = """
  IF TG_OP='UPDATE' AND OLD.state='released' AND NEW.state<>'released' THEN
    RAISE EXCEPTION 'released source charge is immutable' USING ERRCODE='23514'; END IF;
  IF TG_OP='UPDATE' AND NEW.state='released' THEN
    IF OLD.state NOT IN ('sealed','released') OR NEW.accounted_bytes<>0
       OR (to_jsonb(NEW)-ARRAY['state','accounted_bytes']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['state','accounted_bytes'])
       OR NOT EXISTS(SELECT 1 FROM public.submission_source_cleanup_claims
          WHERE operation_id=o.id AND confirmed_at IS NOT NULL) THEN
      RAISE EXCEPTION 'source charge requires confirmed cleanup' USING ERRCODE='23514'; END IF;
    PERFORM public.require_sealed_source_cleanup(o);
    RETURN NEW;
  END IF;
"""

_RELEASE_ACCOUNTING = """
  IF c.state='released' THEN
    PERFORM public.require_sealed_source_cleanup(o);
    IF c.accounted_bytes<>0 OR NOT EXISTS(SELECT 1 FROM public.submission_source_cleanup_claims
       WHERE operation_id=o.id AND confirmed_at IS NOT NULL) THEN
      RAISE EXCEPTION 'source charge requires confirmed cleanup' USING ERRCODE='23514'; END IF;
    RETURN NULL;
  END IF;
"""
