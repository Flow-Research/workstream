"""Persist non-resumable foreground intake before the accepted handoff cutover."""

from alembic import op
import sqlalchemy as sa
from scripts.schema_baseline_sql import split_sql_statements

revision = "0069_submission_intake_custody"
down_revision = "0068_issuer_profile_email"
branch_labels = None
depends_on = None

TABLE_SQL = r"""

CREATE TABLE public.submission_intake_operations (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	task_id UUID NOT NULL,
	assignment_id UUID NOT NULL,
	actor_profile_id UUID NOT NULL,
	identity_link_id UUID NOT NULL,
	idempotency_key UUID NOT NULL,
	command_metadata JSONB NOT NULL,
	metadata_sha256 VARCHAR(71) NOT NULL,
	locked_task_context JSONB NOT NULL,
	locked_context_sha256 VARCHAR(71) NOT NULL,
	eligible_task_status VARCHAR(30) NOT NULL,
	namespace_id VARCHAR(20) NOT NULL,
	namespace_fingerprint VARCHAR(71) NOT NULL,
	provider_profile VARCHAR(100) NOT NULL,
	object_ref VARCHAR(1024) NOT NULL,
	maximum_raw_bytes BIGINT NOT NULL,
	state VARCHAR(30) NOT NULL,
	lease_id UUID NOT NULL,
	lease_generation BIGINT NOT NULL,
	lease_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	upload_deadline_at TIMESTAMP WITH TIME ZONE NOT NULL,
	pre_deadline_at TIMESTAMP WITH TIME ZONE,
	raw_sha256 VARCHAR(71),
	raw_byte_count BIGINT,
	eof_at TIMESTAMP WITH TIME ZONE,
	provider_generation VARCHAR,
	sealed_upload_fence BIGINT,
	sealed_at TIMESTAMP WITH TIME ZONE,
	terminal_at TIMESTAMP WITH TIME ZONE,
	failure_code VARCHAR(100),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	CONSTRAINT pk_submission_intake_operations PRIMARY KEY (id),
	CONSTRAINT ck_submission_intake_operations_id_uuid7 CHECK ((get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128),
	CONSTRAINT uq_submission_intake_task_identity UNIQUE (id, task_id),
	CONSTRAINT uq_submission_intake_actor_key UNIQUE (actor_profile_id, idempotency_key),
	CONSTRAINT uq_submission_intake_source_key UNIQUE (namespace_id, namespace_fingerprint, object_ref),
	CONSTRAINT fk_submission_intake_task FOREIGN KEY(task_id, project_id) REFERENCES public.workstream_tasks (id, project_id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT fk_submission_intake_assignment FOREIGN KEY(assignment_id, task_id, actor_profile_id) REFERENCES public.task_assignments (id, task_id, contributor_id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT fk_submission_intake_identity FOREIGN KEY(identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links (id, actor_profile_id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT fk_submission_intake_namespace FOREIGN KEY(namespace_id, namespace_fingerprint) REFERENCES public.artifact_storage_namespaces (id, namespace_fingerprint),
	CONSTRAINT ck_submission_intake_operations_foreground_state CHECK (state in ('receiving','pre_checking','rejected','failed','abandoned','cancelled')),
	CONSTRAINT ck_submission_intake_operations_eligible_status CHECK (eligible_task_status in ('in_progress','needs_revision')),
	CONSTRAINT ck_submission_intake_operations_identity_digests CHECK (metadata_sha256 ~ '^sha256:[0-9a-f]{64}$' and locked_context_sha256 ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_submission_intake_operations_command_shape CHECK (jsonb_typeof(command_metadata)='object' and jsonb_typeof(locked_task_context)='object'),
	CONSTRAINT ck_submission_intake_operations_source_key CHECK (object_ref='submission-source/v1/'||id::text||'/bundle.zip'),
	CONSTRAINT ck_submission_intake_operations_raw_limit CHECK (maximum_raw_bytes between 1 and 524288000),
	CONSTRAINT ck_submission_intake_operations_lease_bounds CHECK (lease_generation>0 and lease_expires_at<=coalesce(pre_deadline_at,upload_deadline_at) and upload_deadline_at>created_at),
	CONSTRAINT ck_submission_intake_operations_eof_identity CHECK ((raw_sha256 is null and raw_byte_count is null and eof_at is null) or (raw_sha256 is not null and raw_sha256 ~ '^sha256:[0-9a-f]{64}$' and raw_byte_count is not null and raw_byte_count between 1 and maximum_raw_bytes and eof_at is not null)),
	CONSTRAINT ck_submission_intake_operations_sealed_identity CHECK ((provider_generation is null and sealed_upload_fence is null and sealed_at is null and pre_deadline_at is null) or (provider_generation is not null and sealed_upload_fence is not null and sealed_upload_fence>0 and length(provider_generation)>0 and raw_sha256 is not null and sealed_at is not null and sealed_at>=eof_at and pre_deadline_at is not null and pre_deadline_at>sealed_at and (provider_profile<>'aws-s3-v1' or provider_generation<>'null'))),
	CONSTRAINT ck_submission_intake_operations_pre_requires_source CHECK (state<>'pre_checking' or sealed_at is not null),
	CONSTRAINT ck_submission_intake_operations_terminal_shape CHECK ((state in ('receiving','pre_checking') and terminal_at is null and failure_code is null) or (state in ('rejected','failed','abandoned','cancelled') and terminal_at is not null and failure_code is not null))
)

;
CREATE INDEX ix_submission_intake_expiry ON public.submission_intake_operations (lease_expires_at, id) WHERE state in ('receiving','pre_checking');
CREATE UNIQUE INDEX uq_submission_intake_active_task ON public.submission_intake_operations (task_id) WHERE state in ('receiving','pre_checking')
"""

GUARDS = r"""
CREATE FUNCTION public.submission_intake_task_snapshot(t public.workstream_tasks)
RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT
SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT jsonb_object_agg(key,value) FROM jsonb_each(to_jsonb(t))
  WHERE starts_with(key,'locked_')
     OR key IN ('id','project_id','assigned_to','acceptance_criteria')
$$;

CREATE FUNCTION public.guard_submission_intake_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  m jsonb;
  canonical text;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'submission intake custody cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' THEN
    NEW.created_at := clock_timestamp();
    IF NEW.state<>'receiving' OR NEW.lease_generation<>1
       OR NEW.raw_sha256 IS NOT NULL OR NEW.provider_generation IS NOT NULL
       OR NEW.lease_expires_at<=NEW.created_at THEN
      RAISE EXCEPTION 'invalid initial submission intake' USING ERRCODE='23514';
    END IF;
    m:=NEW.command_metadata;
    IF NOT (m ?& ARRAY['task_id','assignment_id','predecessor_submission_id','summary',
        'contributor_attestation','revision_preparation_id','revision_preparation_sha256'])
       OR m - ARRAY['task_id','assignment_id','predecessor_submission_id','summary',
        'contributor_attestation','revision_preparation_id','revision_preparation_sha256'] <> '{}'::jsonb
       OR m->>'task_id' IS DISTINCT FROM NEW.task_id::text
       OR m->>'assignment_id' IS DISTINCT FROM NEW.assignment_id::text
       OR jsonb_typeof(m->'summary') IS DISTINCT FROM 'string'
       OR jsonb_typeof(m->'contributor_attestation') IS DISTINCT FROM 'string'
       OR octet_length(m->>'summary')>65536 OR octet_length(m->>'contributor_attestation')>65536
       OR (m->>'summary') COLLATE "C" ~ '[^ -~]'
       OR (m->>'contributor_attestation') COLLATE "C" ~ '[^ -~]'
       OR btrim(m->>'summary') IS DISTINCT FROM m->>'summary'
       OR btrim(m->>'contributor_attestation') IS DISTINCT FROM m->>'contributor_attestation'
       OR ((m->>'revision_preparation_id' IS NULL)<>(m->>'revision_preparation_sha256' IS NULL))
       OR (m->>'predecessor_submission_id' IS NULL AND m->>'revision_preparation_id' IS NOT NULL)
       OR (m->>'revision_preparation_sha256' IS NOT NULL AND
           m->>'revision_preparation_sha256' !~ '^sha256:[0-9a-f]{64}$') THEN
      RAISE EXCEPTION 'invalid intake metadata' USING ERRCODE='23514';
    END IF;
    canonical:=public.project_guide_projection_canonical_json(
      m || jsonb_build_object('schema_version','workstream.submission_intake_metadata.v1'));
    IF NEW.metadata_sha256 IS DISTINCT FROM 'sha256:'||encode(sha256(convert_to(canonical,'UTF8')),'hex')
       OR NEW.locked_context_sha256 IS DISTINCT FROM 'sha256:'||encode(sha256(convert_to(
         public.project_guide_projection_canonical_json(NEW.locked_task_context),'UTF8')),'hex') THEN
      RAISE EXCEPTION 'intake identity digest mismatch' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.artifact_storage_namespaces n
       WHERE n.id=NEW.namespace_id AND n.namespace_fingerprint=NEW.namespace_fingerprint
         AND n.provider_profile=NEW.provider_profile) THEN
      RAISE EXCEPTION 'intake namespace mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF (to_jsonb(NEW)-ARRAY['state','lease_generation','lease_expires_at','raw_sha256',
       'raw_byte_count','eof_at','provider_generation','sealed_upload_fence','sealed_at','pre_deadline_at',
       'terminal_at','failure_code']) IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY['state','lease_generation','lease_expires_at','raw_sha256',
       'raw_byte_count','eof_at','provider_generation','sealed_upload_fence','sealed_at','pre_deadline_at',
       'terminal_at','failure_code']) THEN
    RAISE EXCEPTION 'intake command and source location are immutable' USING ERRCODE='23514';
  END IF;
  IF OLD.state NOT IN ('receiving','pre_checking') THEN
    IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
      RAISE EXCEPTION 'terminal intake is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.raw_sha256 IS NOT NULL AND ROW(NEW.raw_sha256,NEW.raw_byte_count,NEW.eof_at)
       IS DISTINCT FROM ROW(OLD.raw_sha256,OLD.raw_byte_count,OLD.eof_at) THEN
    RAISE EXCEPTION 'intake EOF identity is immutable' USING ERRCODE='23514';
  END IF;
  IF OLD.provider_generation IS NOT NULL AND
       ROW(NEW.provider_generation,NEW.sealed_upload_fence,NEW.sealed_at,NEW.pre_deadline_at) IS DISTINCT FROM
       ROW(OLD.provider_generation,OLD.sealed_upload_fence,OLD.sealed_at,OLD.pre_deadline_at) THEN
    RAISE EXCEPTION 'intake sealed source is immutable' USING ERRCODE='23514';
  END IF;
  IF NEW.state IN ('rejected','failed','abandoned','cancelled') THEN
    IF NEW.lease_generation<>OLD.lease_generation+1
       OR (NEW.state='rejected' AND OLD.state<>'pre_checking')
       OR ROW(NEW.raw_sha256,NEW.raw_byte_count,NEW.eof_at,NEW.provider_generation,NEW.sealed_upload_fence,
              NEW.sealed_at,NEW.pre_deadline_at,NEW.lease_expires_at) IS DISTINCT FROM
          ROW(OLD.raw_sha256,OLD.raw_byte_count,OLD.eof_at,OLD.provider_generation,OLD.sealed_upload_fence,
              OLD.sealed_at,OLD.pre_deadline_at,OLD.lease_expires_at) THEN
      RAISE EXCEPTION 'invalid intake terminal fence' USING ERRCODE='23514';
    END IF;
    IF OLD.lease_expires_at<=clock_timestamp() AND NEW.state<>'abandoned' THEN
      RAISE EXCEPTION 'expired intake requires abandonment' USING ERRCODE='23514';
    END IF;
    IF NEW.state='abandoned' AND OLD.lease_expires_at>clock_timestamp() THEN
      RAISE EXCEPTION 'live intake cannot be abandoned' USING ERRCODE='23514';
    END IF;
    NEW.terminal_at:=clock_timestamp();
    RETURN NEW;
  END IF;
  IF OLD.lease_expires_at<=clock_timestamp() OR NEW.lease_generation<>OLD.lease_generation
     OR (OLD.state='pre_checking' AND NEW.state<>'pre_checking') THEN
    RAISE EXCEPTION 'stale intake foreground owner' USING ERRCODE='23514';
  END IF;
  IF OLD.raw_sha256 IS NULL AND NEW.raw_sha256 IS NOT NULL THEN
    NEW.eof_at:=clock_timestamp();
  END IF;
  IF OLD.provider_generation IS NULL AND NEW.provider_generation IS NOT NULL THEN
    IF OLD.raw_sha256 IS NULL OR NEW.state<>'pre_checking' THEN
      RAISE EXCEPTION 'source sealing requires recorded EOF' USING ERRCODE='23514';
    END IF;
    NEW.sealed_at:=clock_timestamp();
    NEW.sealed_upload_fence:=OLD.lease_generation;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER submission_intake_mutation
BEFORE INSERT OR UPDATE OR DELETE ON public.submission_intake_operations
FOR EACH ROW EXECUTE FUNCTION public.guard_submission_intake_mutation();

CREATE FUNCTION public.check_submission_intake_custody()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  task_key uuid;
  t public.workstream_tasks%ROWTYPE;
  o public.submission_intake_operations%ROWTYPE;
BEGIN
  IF TG_TABLE_NAME='workstream_tasks' THEN
    task_key:=coalesce(NEW.id,OLD.id);
  ELSE
    task_key:=coalesce(NEW.task_id,OLD.task_id);
  END IF;
  SELECT * INTO t FROM public.workstream_tasks WHERE id=task_key FOR UPDATE;
  SELECT * INTO o FROM public.submission_intake_operations
    WHERE task_id=task_key AND state IN ('receiving','pre_checking');
  IF o.id IS NULL THEN
    IF t.active_submission_operation_id IS NOT NULL THEN
      RAISE EXCEPTION 'intake pointer has no active owner' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
  END IF;
  IF t.id IS NULL OR t.active_submission_operation_id IS DISTINCT FROM o.id
     OR t.status IS DISTINCT FROM o.eligible_task_status
     OR t.assigned_to IS DISTINCT FROM o.actor_profile_id
     OR public.submission_intake_task_snapshot(t) IS DISTINCT FROM o.locked_task_context
     OR NOT EXISTS (SELECT 1 FROM public.task_assignments a
         WHERE a.id=o.assignment_id AND a.task_id=o.task_id AND a.project_id=o.project_id
           AND a.contributor_id=o.actor_profile_id AND a.status='active') THEN
    RAISE EXCEPTION 'intake task custody mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER submission_intake_owner_closure
AFTER INSERT OR UPDATE OR DELETE ON public.submission_intake_operations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_intake_custody();
CREATE CONSTRAINT TRIGGER task_submission_intake_closure
AFTER INSERT OR UPDATE OR DELETE ON public.workstream_tasks
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_intake_custody();
CREATE CONSTRAINT TRIGGER assignment_submission_intake_closure
AFTER INSERT OR UPDATE OR DELETE ON public.task_assignments
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_intake_custody();
"""


def upgrade() -> None:
    """Add closed foreground custody without touching existing artifact bytes or rows."""
    for statement in split_sql_statements(TABLE_SQL):
        op.execute(statement)
    op.add_column("workstream_tasks", sa.Column("active_submission_operation_id", sa.Uuid(), nullable=True), schema="public")
    op.create_foreign_key("fk_task_active_submission_intake", "workstream_tasks",
                         "submission_intake_operations", ["active_submission_operation_id", "id"],
                         ["id", "task_id"], source_schema="public", referent_schema="public", deferrable=True, initially="DEFERRED")
    for statement in split_sql_statements(GUARDS):
        op.execute(statement)


def downgrade() -> None:
    """Retain custody and tombstones; restore only into a fresh database."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
