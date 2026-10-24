"""Retain exact checker trial receipts through verified ART custody."""

from alembic import op
import sqlalchemy as sa


revision = "0064_checker_trial_evidence"
down_revision = "0063_checker_revision_input"
branch_labels = None
depends_on = None


def _replace_function(signature: str, old: str, new: str, *, count: int = 1) -> None:
    definition = (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_catalog.pg_get_functiondef(cast(:signature as pg_catalog.regprocedure))"
            ),
            {"signature": signature},
        )
        .scalar_one()
    )
    if definition.count(old) != count:
        raise RuntimeError("checker trial ART function shape changed: " + signature)
    op.execute(definition.replace(old, new))


def upgrade() -> None:
    """Add trial ownership and one exact verified ART lineage without rewriting rows."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute(
        "lock table public.task_assignments, public.submissions, public.checker_runs, "
        "public.checker_submission_fences, public.external_checker_registry_entries, "
        "public.audit_events, public.artifact_put_attempts, "
        "public.artifact_operation_receipts, public.artifact_bindings, "
        "public.artifact_verification_jobs, public.artifact_replicas "
        "in access exclusive mode"
    )
    _create_owner_table()
    _extend_art_lineage()
    _create_owner_guards()
    _extend_art_guards()


def _create_owner_table() -> None:
    op.execute(
        r"""
CREATE TABLE public.checker_trial_evidence (
  id uuid PRIMARY KEY,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL,
  assignment_id uuid NOT NULL,
  submission_id uuid NOT NULL,
  submission_version integer NOT NULL,
  checker_run_id uuid NOT NULL,
  registry_entry_id uuid NOT NULL,
  address_digest varchar(71) NOT NULL,
  subject jsonb NOT NULL,
  origin jsonb NOT NULL,
  maximum_bytes integer NOT NULL,
  content_sha256 varchar(71),
  execute_evidence_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  CONSTRAINT ck_checker_trial_evidence_id_uuid7 CHECK (
    (pg_catalog.get_byte(pg_catalog.uuid_send(id),6)>>4)=7
    AND (pg_catalog.get_byte(pg_catalog.uuid_send(id),8)&192)=128),
  CONSTRAINT uq_checker_trial_evidence_address UNIQUE(address_digest),
  CONSTRAINT fk_checker_trial_evidence_task_project
    FOREIGN KEY(task_id,project_id) REFERENCES public.workstream_tasks(id,project_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_checker_trial_evidence_assignment
    FOREIGN KEY(assignment_id) REFERENCES public.task_assignments(id) ON DELETE RESTRICT,
  CONSTRAINT fk_checker_trial_evidence_submission
    FOREIGN KEY(submission_id,task_id,submission_version)
    REFERENCES public.submissions(id,task_id,version) ON DELETE RESTRICT,
  CONSTRAINT fk_checker_trial_evidence_origin
    FOREIGN KEY(checker_run_id,task_id,submission_id)
    REFERENCES public.checker_runs(id,task_id,submission_id) ON DELETE RESTRICT,
  CONSTRAINT fk_checker_trial_evidence_registry
    FOREIGN KEY(registry_entry_id) REFERENCES public.external_checker_registry_entries(id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_checker_trial_evidence_execute
    FOREIGN KEY(execute_evidence_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT,
  CONSTRAINT ck_checker_trial_evidence_version CHECK(submission_version>0),
  CONSTRAINT ck_checker_trial_evidence_bounded_receipt
    CHECK(maximum_bytes BETWEEN 1 AND 1048576),
  CONSTRAINT ck_checker_trial_evidence_closed_facts CHECK(
    pg_catalog.jsonb_typeof(subject)='object'
    AND pg_catalog.jsonb_typeof(origin)='object'),
  CONSTRAINT ck_checker_trial_evidence_digest_shapes CHECK(
    address_digest ~ '^sha256:[0-9a-f]{64}$'
    AND (content_sha256 IS NULL OR content_sha256 ~ '^sha256:[0-9a-f]{64}$')),
  CONSTRAINT ck_checker_trial_evidence_address_digest CHECK(
    address_digest='sha256:' || pg_catalog.encode(sha256(pg_catalog.convert_to(
      public.external_checker_registry_canonical_json(
        subject-ARRAY['plan_sha256','input_digest','materials_digest']),
      'UTF8')),'hex'))
)
        """
    )
    for column in (
        "project_id",
        "task_id",
        "assignment_id",
        "submission_id",
        "checker_run_id",
        "registry_entry_id",
        "execute_evidence_id",
    ):
        op.execute(
            f"create index ix_checker_trial_evidence_{column} "
            f"on public.checker_trial_evidence({column})"
        )


def _extend_art_lineage() -> None:
    op.execute(
        "alter table public.artifact_put_attempts add column "
        "checker_trial_evidence_id uuid references public.checker_trial_evidence(id) "
        "on delete restrict"
    )
    op.execute(
        "create index ix_artifact_put_attempts_checker_trial_evidence_id "
        "on public.artifact_put_attempts(checker_trial_evidence_id)"
    )
    op.execute(
        "alter table public.artifact_operation_receipts add column "
        "checker_trial_evidence_id uuid references public.checker_trial_evidence(id) "
        "on delete restrict"
    )
    op.execute(
        "create index ix_artifact_operation_receipts_checker_trial_evidence_id "
        "on public.artifact_operation_receipts(checker_trial_evidence_id)"
    )
    op.execute(
        "alter table public.artifact_put_attempts drop constraint "
        "ck_artifact_put_attempts_producer_reference"
    )
    op.execute(
        r"""
ALTER TABLE public.artifact_put_attempts ADD CONSTRAINT
ck_artifact_put_attempts_producer_reference CHECK (
  (producer_request_type='guide' AND task_import_source_id IS NULL
   AND guide_source_item_id IS NOT NULL AND checker_run_id IS NULL
   AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NULL
   AND task_id IS NULL AND submission_id IS NULL AND submission_version IS NULL
   AND logical_role IS NULL)
  OR
  (producer_request_type='checker_output' AND task_import_source_id IS NULL
   AND guide_source_item_id IS NULL AND task_id IS NOT NULL
   AND submission_id IS NOT NULL AND submission_version IS NOT NULL
   AND ((checker_run_id IS NOT NULL AND model_call_attempt_id IS NULL
         AND checker_trial_evidence_id IS NULL
         AND pg_catalog.octet_length(logical_role) BETWEEN 1 AND 100)
        OR (checker_run_id IS NULL AND model_call_attempt_id IS NOT NULL
            AND checker_trial_evidence_id IS NULL
            AND logical_role IN ('model_request','model_response'))
        OR (checker_run_id IS NULL AND model_call_attempt_id IS NULL
            AND checker_trial_evidence_id IS NOT NULL
            AND logical_role='trial_receipt')))
  OR
  (producer_request_type='setup_model_output' AND task_import_source_id IS NULL
   AND guide_source_item_id IS NULL AND checker_run_id IS NULL
   AND model_call_attempt_id IS NOT NULL AND checker_trial_evidence_id IS NULL
   AND task_id IS NULL AND submission_id IS NULL AND submission_version IS NULL
   AND logical_role IN ('model_request','model_response'))
  OR
  (producer_request_type='submission_bundle' AND task_import_source_id IS NULL
   AND guide_source_item_id IS NULL AND checker_run_id IS NULL
   AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NULL
   AND task_id IS NOT NULL AND submission_id IS NULL AND submission_version IS NULL
   AND logical_role IS NULL)
  OR
  (producer_request_type='task_import_source' AND task_import_source_id IS NOT NULL
   AND guide_source_item_id IS NULL AND checker_run_id IS NULL
   AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NULL
   AND task_id IS NULL AND submission_id IS NULL AND submission_version IS NULL
   AND logical_role IS NOT DISTINCT FROM 'task_import_source'))
        """
    )
    op.execute(
        "alter table public.artifact_operation_receipts drop constraint "
        "ck_artifact_operation_receipts_contract_producer_reference"
    )
    op.execute(
        r"""
ALTER TABLE public.artifact_operation_receipts ADD CONSTRAINT
ck_artifact_operation_receipts_contract_producer_reference CHECK (
  contract_version=2 AND put_attempt_id IS NOT NULL AND (
    (guide_source_item_id IS NOT NULL AND checker_run_id IS NULL
     AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NULL
     AND logical_role IS NULL)
    OR (guide_source_item_id IS NULL AND checker_run_id IS NOT NULL
        AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NULL
        AND pg_catalog.octet_length(logical_role) BETWEEN 1 AND 100)
    OR (guide_source_item_id IS NULL AND checker_run_id IS NULL
        AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NULL
        AND (logical_role IS NULL OR logical_role='task_import_source'))
    OR (guide_source_item_id IS NULL AND checker_run_id IS NULL
        AND model_call_attempt_id IS NOT NULL AND checker_trial_evidence_id IS NULL
        AND logical_role IN ('model_request','model_response'))
    OR (guide_source_item_id IS NULL AND checker_run_id IS NULL
        AND model_call_attempt_id IS NULL AND checker_trial_evidence_id IS NOT NULL
        AND logical_role='trial_receipt')))
        """
    )
    op.execute(
        "alter table public.artifact_bindings drop constraint "
        "ck_artifact_bindings_checker_output_lineage"
    )
    op.execute(
        r"""
ALTER TABLE public.artifact_bindings ADD CONSTRAINT
ck_artifact_bindings_checker_output_lineage CHECK (
  (resource_type IN ('checker_run','checker_model_call','setup_model_call','checker_trial_evidence')
   AND scope_version=1 AND put_attempt_id IS NOT NULL
   AND verification_receipt_id IS NOT NULL)
  OR
  (resource_type NOT IN ('checker_run','checker_model_call','setup_model_call','checker_trial_evidence')
   AND put_attempt_id IS NULL AND verification_receipt_id IS NULL))
        """
    )


def _create_owner_guards() -> None:
    op.execute(
        r"""
CREATE FUNCTION public.checker_trial_execute_receipt_valid(
  evidence_id uuid, run public.checker_runs
) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT coalesce(EXISTS(
    SELECT 1 FROM public.audit_events event
    JOIN public.actor_profiles profile ON profile.id::text=event.actor_id
    JOIN public.actor_identity_links link ON link.actor_profile_id=profile.id
    WHERE event.id=evidence_id
      AND event.event_domain='authority'
      AND event.event_type='SensitiveAuthorizationAllowed'
      AND event.actor_ref_kind='actor_profile'
      AND profile.actor_kind='service'
      AND profile.service_identity='workstream.checker.post_submit'
      AND profile.status='active'
      AND link.subject_kind='service' AND link.status='active'
      AND event.action_id='checker.post_submit.execute'
      AND event.permission_id='checker.post_submit.execute'
      AND event.denial_code IS NULL AND event.matched_grant_id IS NULL
      AND event.project_id=run.project_id
      AND event.resource_type='checker_run' AND event.resource_id=run.id::text
      AND event.target_ref_kind='project' AND event.target_ref_id=run.project_id::text
      AND event.request_id=run.evaluation_request_id
      AND event.correlation_id=run.evaluation_request_id
      AND event.after_facts::jsonb=pg_catalog.jsonb_build_object(
        'allowed',true,
        'resource_context_digest',public.checker_post_submit_authority_digest(run,'execute'))
  ),false)
$$
        """
    )
    op.execute(
        r"""
CREATE FUNCTION public.guard_checker_trial_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  run public.checker_runs%ROWTYPE;
  registry public.external_checker_registry_entries%ROWTYPE;
  binding jsonb;
  configuration jsonb;
  matches integer;
  expected_subject jsonb;
  expected_origin jsonb;
BEGIN
  IF TG_OP IN ('DELETE','TRUNCATE') THEN
    RAISE EXCEPTION 'checker trial evidence is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' THEN
    IF pg_catalog.to_jsonb(NEW)=pg_catalog.to_jsonb(OLD) THEN RETURN NEW; END IF;
    IF OLD.content_sha256 IS NOT NULL OR NEW.content_sha256 IS NULL
       OR (pg_catalog.to_jsonb(NEW)-'content_sha256') IS DISTINCT FROM
          (pg_catalog.to_jsonb(OLD)-'content_sha256') THEN
      RAISE EXCEPTION 'checker trial evidence is immutable' USING ERRCODE='23514';
    END IF;
    SELECT current_run.* INTO run
    FROM public.checker_submission_fences fence
    JOIN public.checker_runs current_run ON current_run.id=fence.current_run_id
    WHERE fence.submission_id=NEW.submission_id
    FOR KEY SHARE OF current_run;
    SELECT pg_catalog.count(*),(pg_catalog.jsonb_agg(value)->0) INTO matches,binding
    FROM pg_catalog.jsonb_array_elements(run.request_json::jsonb#>'{policy,entries}') entry
    WHERE entry.value->>'requirement_id'=NEW.subject->>'requirement_id'
      AND entry.value#>>'{registry,registry_entry_id}'=NEW.registry_entry_id::text
      AND entry.value#>>'{registry,entry_digest}'=NEW.subject->>'registry_entry_digest'
      AND entry.value->>'configuration_sha256'=NEW.subject->>'configuration_sha256';
    IF run.id IS NULL OR run.status<>'running'
       OR run.worker_lease_expires_at<=pg_catalog.clock_timestamp()
       OR matches<>1 OR run.project_id IS DISTINCT FROM NEW.project_id
       OR run.task_id IS DISTINCT FROM NEW.task_id
       OR run.submission_id IS DISTINCT FROM NEW.submission_id
       OR run.submission_version IS DISTINCT FROM NEW.submission_version
       OR run.request_json::jsonb->>'assignment_id' IS DISTINCT FROM NEW.assignment_id::text
       OR public.checker_post_submit_receipt_valid(run,'execute',true) IS NOT TRUE THEN
      RAISE EXCEPTION 'checker trial content pin lacks current execution'
        USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.content_sha256 IS NOT NULL THEN
    RAISE EXCEPTION 'checker trial evidence must reserve before content pin'
      USING ERRCODE='23514';
  END IF;
  SELECT * INTO run FROM public.checker_runs WHERE id=NEW.checker_run_id FOR KEY SHARE;
  SELECT * INTO registry FROM public.external_checker_registry_entries
    WHERE id=NEW.registry_entry_id;
  SELECT pg_catalog.count(*),(pg_catalog.jsonb_agg(value)->0) INTO matches,binding
  FROM pg_catalog.jsonb_array_elements(run.request_json::jsonb#>'{policy,entries}') entry
  WHERE entry.value->>'requirement_id'=NEW.subject->>'requirement_id'
    AND entry.value#>>'{registry,registry_entry_id}'=NEW.registry_entry_id::text
    AND entry.value#>>'{registry,entry_digest}'=NEW.subject->>'registry_entry_digest'
    AND entry.value->>'configuration_sha256'=NEW.subject->>'configuration_sha256';
  configuration:=binding->'configuration';
  IF run.id IS NULL OR registry.id IS NULL OR matches<>1
     OR run.status<>'running' OR run.worker_lease_expires_at<=pg_catalog.clock_timestamp()
     OR public.checker_trial_execute_receipt_valid(NEW.execute_evidence_id,run) IS NOT TRUE
     OR NOT EXISTS(SELECT 1 FROM public.checker_submission_fences fence
        WHERE fence.submission_id=run.submission_id AND fence.current_run_id=run.id)
     OR run.project_id IS DISTINCT FROM NEW.project_id
     OR run.task_id IS DISTINCT FROM NEW.task_id
     OR run.submission_id IS DISTINCT FROM NEW.submission_id
     OR run.submission_version IS DISTINCT FROM NEW.submission_version
     OR run.request_json::jsonb->>'assignment_id' IS DISTINCT FROM NEW.assignment_id::text
     OR registry.phase<>'post_submit'
     OR registry.entry_digest IS DISTINCT FROM NEW.subject->>'registry_entry_digest'
     OR pg_catalog.jsonb_typeof(configuration) IS DISTINCT FROM 'object'
     OR NOT configuration ?& ARRAY[
          'trial_profile_id','trial_profile_version','trial_profile_digest',
          'trial_projection_id','trial_projection_version','trial_projection_digest']
     OR pg_catalog.jsonb_typeof(configuration->'trial_profile_id') IS DISTINCT FROM 'string'
     OR (configuration->>'trial_profile_id')::uuid IS NULL
     OR pg_catalog.jsonb_typeof(configuration->'trial_profile_version') IS DISTINCT FROM 'number'
     OR configuration->>'trial_profile_version' !~ '^[1-9][0-9]*$'
     OR pg_catalog.jsonb_typeof(configuration->'trial_profile_digest') IS DISTINCT FROM 'string'
     OR (configuration->>'trial_profile_digest' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE
     OR pg_catalog.jsonb_typeof(configuration->'trial_projection_id') IS DISTINCT FROM 'string'
     OR (configuration->>'trial_projection_id')::uuid IS NULL
     OR pg_catalog.jsonb_typeof(configuration->'trial_projection_version') IS DISTINCT FROM 'number'
     OR configuration->>'trial_projection_version' !~ '^[1-9][0-9]*$'
     OR pg_catalog.jsonb_typeof(configuration->'trial_projection_digest') IS DISTINCT FROM 'string'
     OR (configuration->>'trial_projection_digest' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE
     OR configuration ? 'trial_execution'
     OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_object_keys(configuration) key
         WHERE key LIKE 'trial_%')<>6
     OR binding->>'configuration_sha256' IS DISTINCT FROM
        'sha256:' || pg_catalog.encode(sha256(pg_catalog.convert_to(
          public.external_checker_registry_canonical_json(configuration),'UTF8')),'hex') THEN
    RAISE EXCEPTION 'checker trial evidence owner mismatch' USING ERRCODE='23514';
  END IF;
  IF NEW.subject-ARRAY[
       'project_id','task_id','assignment_id','submission_id','submission_version',
       'requirement_id','registry_entry_id','registry_entry_digest','configuration_sha256',
       'trial_kind','slot_index','plan_sha256','input_digest','materials_digest']<>'{}'::jsonb
     OR NOT NEW.subject ?& ARRAY[
       'project_id','task_id','assignment_id','submission_id','submission_version',
       'requirement_id','registry_entry_id','registry_entry_digest','configuration_sha256',
       'trial_kind','slot_index','plan_sha256','input_digest','materials_digest']
     OR pg_catalog.jsonb_typeof(NEW.subject->'requirement_id') IS DISTINCT FROM 'string'
     OR (NEW.subject->>'requirement_id' ~ '^[a-z][a-z0-9_.-]{0,99}$') IS NOT TRUE
     OR pg_catalog.jsonb_typeof(NEW.subject->'trial_kind') IS DISTINCT FROM 'string'
     OR (NEW.subject->>'trial_kind' ~ '^[a-z][a-z0-9_.-]{0,99}$') IS NOT TRUE
     OR pg_catalog.jsonb_typeof(NEW.subject->'slot_index') IS DISTINCT FROM 'number'
     OR NEW.subject->>'slot_index' IS DISTINCT FROM '0'
     OR pg_catalog.jsonb_typeof(NEW.subject->'plan_sha256') IS DISTINCT FROM 'string'
     OR (NEW.subject->>'plan_sha256' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE
     OR pg_catalog.jsonb_typeof(NEW.subject->'input_digest') IS DISTINCT FROM 'string'
     OR (NEW.subject->>'input_digest' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE
     OR pg_catalog.jsonb_typeof(NEW.subject->'materials_digest') IS DISTINCT FROM 'string'
     OR (NEW.subject->>'materials_digest' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE THEN
    RAISE EXCEPTION 'checker trial evidence subject is invalid' USING ERRCODE='23514';
  END IF;
  expected_subject:=pg_catalog.jsonb_build_object(
    'project_id',NEW.project_id,'task_id',NEW.task_id,'assignment_id',NEW.assignment_id,
    'submission_id',NEW.submission_id,'submission_version',NEW.submission_version,
    'requirement_id',binding->>'requirement_id','registry_entry_id',registry.id,
    'registry_entry_digest',registry.entry_digest,
    'configuration_sha256',binding->>'configuration_sha256',
    'trial_kind',NEW.subject->>'trial_kind',
    'slot_index',(NEW.subject->>'slot_index')::integer,
    'plan_sha256',NEW.subject->>'plan_sha256',
    'input_digest',NEW.subject->>'input_digest',
    'materials_digest',NEW.subject->>'materials_digest');
  IF NEW.subject IS DISTINCT FROM expected_subject
     OR NEW.origin-ARRAY['checker_run_id','worker_lease_id','worker_lease_generation',
                         'worker_lease_expires_at','external_request_digest']<>'{}'::jsonb
     OR NOT NEW.origin ?& ARRAY['checker_run_id','worker_lease_id','worker_lease_generation',
                                'worker_lease_expires_at','external_request_digest']
     OR pg_catalog.jsonb_typeof(NEW.origin->'external_request_digest') IS DISTINCT FROM 'string'
     OR (NEW.origin->>'external_request_digest' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE THEN
    RAISE EXCEPTION 'checker trial evidence facts are invalid' USING ERRCODE='23514';
  END IF;
  expected_origin:=pg_catalog.jsonb_build_object(
    'checker_run_id',run.id,'worker_lease_id',run.worker_lease_id,
    'worker_lease_generation',run.worker_lease_generation,
    'worker_lease_expires_at',pg_catalog.replace(
      public.outbox_dispatch_utc(run.worker_lease_expires_at),'+00:00','Z'),
    'external_request_digest',NEW.origin->>'external_request_digest');
  IF NEW.origin IS DISTINCT FROM expected_origin THEN
    RAISE EXCEPTION 'checker trial evidence origin mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
EXCEPTION WHEN data_exception THEN
  RAISE EXCEPTION 'checker trial evidence is malformed' USING ERRCODE='23514';
END $$
        """
    )
    op.execute(
        "create trigger checker_trial_evidence_guard before insert or update or delete "
        "on public.checker_trial_evidence for each row "
        "execute function public.guard_checker_trial_evidence()"
    )
    op.execute(
        "create trigger checker_trial_evidence_no_truncate before truncate "
        "on public.checker_trial_evidence for each statement "
        "execute function public.guard_checker_trial_evidence()"
    )
    op.execute(
        r"""
CREATE FUNCTION public.guard_checker_trial_content_custody() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF NEW.content_sha256 IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM public.artifact_put_attempts attempt
    WHERE attempt.checker_trial_evidence_id=NEW.id
      AND attempt.project_id=NEW.project_id AND attempt.task_id=NEW.task_id
      AND attempt.submission_id=NEW.submission_id
      AND attempt.submission_version=NEW.submission_version
      AND attempt.checker_run_id IS NULL AND attempt.model_call_attempt_id IS NULL
      AND attempt.logical_role='trial_receipt'
      AND attempt.sha256=NEW.content_sha256
      AND attempt.media_type='application/json'
      AND attempt.byte_count BETWEEN 1 AND NEW.maximum_bytes)
  THEN RAISE EXCEPTION 'checker trial content lacks exact ART action'
    USING ERRCODE='23514'; END IF;
  RETURN NULL;
END $$
        """
    )
    op.execute(
        "create constraint trigger checker_trial_content_custody "
        "after insert or update on public.checker_trial_evidence "
        "deferrable initially deferred for each row "
        "execute function public.guard_checker_trial_content_custody()"
    )


def _extend_art_guards() -> None:
    _replace_receipt_guard()
    _replace_function(
        "public.guard_checker_output_put_attempt_custody()",
        "binding.resource_type IN ('checker_run','checker_model_call','setup_model_call')",
        "binding.resource_type IN ('checker_run','checker_model_call','setup_model_call','checker_trial_evidence')",
    )
    _replace_function(
        "public.guard_checker_output_put_attempt_custody()",
        "NEW.checker_run_id, NEW.model_call_attempt_id,\n                 NEW.submission_id",
        "NEW.checker_run_id, NEW.model_call_attempt_id, NEW.checker_trial_evidence_id,\n"
        "                 NEW.submission_id",
    )
    _replace_function(
        "public.guard_checker_output_put_attempt_custody()",
        "OLD.checker_run_id, OLD.model_call_attempt_id,\n                 OLD.submission_id",
        "OLD.checker_run_id, OLD.model_call_attempt_id, OLD.checker_trial_evidence_id,\n"
        "                 OLD.submission_id",
    )
    for signature in (
        "public.guard_checker_output_verification_job_custody()",
        "public.guard_checker_output_replica_custody()",
    ):
        _replace_function(
            signature,
            "binding.resource_type IN ('checker_run','checker_model_call','setup_model_call')",
            "binding.resource_type IN "
            "('checker_run','checker_model_call','setup_model_call','checker_trial_evidence')",
        )
    _replace_function(
        "public.seal_checker_output_binding_ancestry()",
        "NEW.resource_type NOT IN ('checker_run','checker_model_call','setup_model_call')",
        "NEW.resource_type NOT IN ('checker_run','checker_model_call','setup_model_call','checker_trial_evidence')",
    )
    _replace_binding_guard()
    op.execute(
        r"""
CREATE FUNCTION public.guard_checker_trial_artifact_ancestry() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE evidence public.checker_trial_evidence%ROWTYPE;
        run public.checker_runs%ROWTYPE;
        binding jsonb;
        matches integer;
        expected_request_digest text;
        expected_operation_identity text;
BEGIN
  IF NEW.checker_trial_evidence_id IS NULL THEN RETURN NEW; END IF;
  SELECT * INTO evidence FROM public.checker_trial_evidence
    WHERE id=NEW.checker_trial_evidence_id FOR KEY SHARE;
  SELECT current_run.* INTO run
  FROM public.checker_submission_fences fence
  JOIN public.checker_runs current_run ON current_run.id=fence.current_run_id
  WHERE fence.submission_id=evidence.submission_id
  FOR KEY SHARE OF current_run;
  SELECT pg_catalog.count(*),(pg_catalog.jsonb_agg(value)->0) INTO matches,binding
  FROM pg_catalog.jsonb_array_elements(run.request_json::jsonb#>'{policy,entries}') entry
  WHERE entry.value->>'requirement_id'=evidence.subject->>'requirement_id'
    AND entry.value#>>'{registry,registry_entry_id}'=evidence.registry_entry_id::text
    AND entry.value#>>'{registry,entry_digest}'=evidence.subject->>'registry_entry_digest'
    AND entry.value->>'configuration_sha256'=evidence.subject->>'configuration_sha256';
  expected_request_digest:='sha256:' || pg_catalog.encode(sha256(
    pg_catalog.convert_to(public.external_checker_registry_canonical_json(
      pg_catalog.jsonb_build_object(
        'subject',evidence.subject,
        'slot',pg_catalog.jsonb_build_object(
          'key','trial_receipt','media_type','application/json',
          'maximum_bytes',evidence.maximum_bytes),
        'content_sha256',evidence.content_sha256)), 'UTF8')),'hex');
  expected_operation_identity:='sha256:' || pg_catalog.encode(sha256(
    pg_catalog.convert_to(public.external_checker_registry_canonical_json(
      pg_catalog.jsonb_build_object(
        'request_type','checker_trial_evidence',
        'trial_evidence_id',evidence.id::text,
        'logical_role','trial_receipt')), 'UTF8')),'hex');
  IF evidence.id IS NULL OR evidence.content_sha256 IS NULL OR run.id IS NULL
     OR run.status<>'running' OR run.worker_lease_expires_at<=pg_catalog.clock_timestamp()
     OR matches<>1 OR run.project_id IS DISTINCT FROM evidence.project_id
     OR run.task_id IS DISTINCT FROM evidence.task_id
     OR run.submission_id IS DISTINCT FROM evidence.submission_id
     OR run.submission_version IS DISTINCT FROM evidence.submission_version
     OR run.request_json::jsonb->>'assignment_id' IS DISTINCT FROM evidence.assignment_id::text
     OR public.checker_post_submit_receipt_valid(run,'execute',true) IS NOT TRUE
     OR ROW(NEW.project_id,NEW.task_id,NEW.submission_id,NEW.submission_version)
        IS DISTINCT FROM ROW(evidence.project_id,evidence.task_id,
                             evidence.submission_id,evidence.submission_version)
     OR NEW.checker_run_id IS NOT NULL OR NEW.model_call_attempt_id IS NOT NULL
     OR NEW.logical_role IS DISTINCT FROM 'trial_receipt'
     OR NEW.producer_request_type IS DISTINCT FROM 'checker_output'
     OR NEW.producer_type IS DISTINCT FROM 'service_identity'
     OR NEW.producer_ref IS DISTINCT FROM 'workstream.artifact.checker_output'
     OR NEW.sha256 IS DISTINCT FROM evidence.content_sha256
     OR NEW.byte_count NOT BETWEEN 1 AND evidence.maximum_bytes
     OR NEW.media_type IS DISTINCT FROM 'application/json'
     OR NEW.checker_request_digest IS DISTINCT FROM expected_request_digest
     OR NEW.operation_identity IS DISTINCT FROM expected_operation_identity THEN
    RAISE EXCEPTION 'trial artifact owner ancestry mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
        """
    )
    op.execute(
        "create trigger checker_trial_artifact_ancestry before insert "
        "on public.artifact_put_attempts for each row "
        "execute function public.guard_checker_trial_artifact_ancestry()"
    )


def _replace_receipt_guard() -> None:
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.guard_artifact_receipt_producer_reference()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE attempt public.artifact_put_attempts%ROWTYPE;
BEGIN
  SELECT value.* INTO attempt FROM public.artifact_put_attempts value
  WHERE value.id=NEW.put_attempt_id;
  IF attempt.id IS NULL
     OR (attempt.producer_request_type='guide' AND NOT (
       NEW.guide_source_item_id IS NOT NULL AND NEW.checker_run_id IS NULL
       AND NEW.model_call_attempt_id IS NULL AND NEW.checker_trial_evidence_id IS NULL
       AND NEW.logical_role IS NULL))
     OR (attempt.producer_request_type IN ('checker_output','setup_model_output') AND NOT (
       NEW.guide_source_item_id IS NULL AND (
         (attempt.checker_run_id IS NOT NULL
          AND NEW.checker_run_id IS NOT NULL
          AND NEW.model_call_attempt_id IS NULL
          AND NEW.checker_trial_evidence_id IS NULL
          AND pg_catalog.octet_length(NEW.logical_role) BETWEEN 1 AND 100)
         OR (attempt.model_call_attempt_id IS NOT NULL
          AND NEW.checker_run_id IS NULL
          AND NEW.model_call_attempt_id IS NOT DISTINCT FROM attempt.model_call_attempt_id
          AND NEW.checker_trial_evidence_id IS NULL
          AND NEW.logical_role IS NOT DISTINCT FROM attempt.logical_role
          AND NEW.logical_role IN ('model_request','model_response'))
         OR (attempt.checker_trial_evidence_id IS NOT NULL
          AND NEW.checker_run_id IS NULL AND NEW.model_call_attempt_id IS NULL
          AND NEW.checker_trial_evidence_id IS NOT DISTINCT FROM
              attempt.checker_trial_evidence_id
          AND NEW.logical_role IS NOT DISTINCT FROM attempt.logical_role
          AND NEW.logical_role='trial_receipt'))))
     OR (attempt.producer_request_type='submission_bundle' AND NOT (
       NEW.guide_source_item_id IS NULL AND NEW.checker_run_id IS NULL
       AND NEW.model_call_attempt_id IS NULL AND NEW.checker_trial_evidence_id IS NULL
       AND NEW.logical_role IS NULL))
     OR (attempt.producer_request_type='task_import_source' AND (
       NEW.guide_source_item_id IS NOT NULL OR NEW.checker_run_id IS NOT NULL
       OR NEW.model_call_attempt_id IS NOT NULL OR NEW.checker_trial_evidence_id IS NOT NULL
       OR NEW.logical_role IS DISTINCT FROM 'task_import_source'))
     OR attempt.producer_request_type NOT IN (
       'guide','checker_output','setup_model_output','submission_bundle','task_import_source') THEN
    RAISE EXCEPTION 'artifact receipt producer reference mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
        """
    )


def _replace_binding_guard() -> None:
    signature = "public.guard_checker_output_binding_insert()"
    _replace_function(
        signature,
        "NEW.resource_type NOT IN ('checker_run','checker_model_call','setup_model_call')",
        "NEW.resource_type NOT IN ('checker_run','checker_model_call','setup_model_call','checker_trial_evidence')",
    )
    _replace_function(
        signature,
        "receipt.model_call_attempt_id IS NOT DISTINCT FROM attempt.model_call_attempt_id\n"
        "              AND receipt.logical_role",
        "receipt.model_call_attempt_id IS NOT DISTINCT FROM attempt.model_call_attempt_id\n"
        "              AND receipt.checker_trial_evidence_id IS NOT DISTINCT FROM "
        "attempt.checker_trial_evidence_id\n              AND receipt.logical_role",
    )
    _replace_function(
        signature,
        "CASE WHEN NEW.resource_type IN ('checker_model_call','setup_model_call')\n"
        "                  THEN attempt.model_call_attempt_id::text ELSE "
        "attempt.checker_run_id::text END",
        "CASE WHEN NEW.resource_type IN ('checker_model_call','setup_model_call')\n"
        "                  THEN attempt.model_call_attempt_id::text\n"
        "                  WHEN NEW.resource_type='checker_trial_evidence'\n"
        "                  THEN attempt.checker_trial_evidence_id::text\n"
        "                  ELSE attempt.checker_run_id::text END",
    )
    _replace_function(
        signature,
        "OR replica.integrity_state <> 'valid'\n             OR write_receipt_matches <> 1",
        "OR replica.integrity_state <> 'valid'\n"
        "             OR (NEW.resource_type='checker_trial_evidence' AND NOT EXISTS (\n"
        "       SELECT 1 FROM public.checker_trial_evidence evidence\n"
        "       WHERE evidence.id=attempt.checker_trial_evidence_id\n"
        "         AND evidence.id::text=NEW.resource_id\n"
        "         AND evidence.project_id=NEW.project_id\n"
        "         AND evidence.task_id=attempt.task_id\n"
        "         AND evidence.submission_id=attempt.submission_id\n"
        "         AND evidence.submission_version=attempt.submission_version\n"
        "         AND evidence.content_sha256=attempt.sha256))\n"
        "             OR write_receipt_matches <> 1",
    )


def downgrade() -> None:
    """Refuse downgrade without weakening retained trial and ART custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
