"""Bind new selected PRE runs to live sealed intake; retain v1 evidence read-only."""
from alembic import op
from sqlalchemy import text

revision = "0071_source_first_pre"
down_revision = "0070_submission_intake_authority"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    """Preserve intervening lineage repairs and refuse an unexpected SQL shape."""
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("source-first PRE predecessor shape changed: " + signature)
    op.execute(body.replace(old, new))


def _source_guard():
    op.execute(r"""
CREATE FUNCTION public.require_selected_pre_source(r public.selected_pre_submit_runs)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE t public.workstream_tasks%ROWTYPE; o public.submission_intake_operations%ROWTYPE;
 source jsonb; request jsonb:=r.request_json; observed timestamptz;
 predecessor jsonb:='null'::jsonb; predecessor_rules text; policy_lineage jsonb;
 rules text; expected_context jsonb; predecessor_id uuid;
BEGIN
 SELECT * INTO t FROM public.workstream_tasks WHERE id=r.task_id FOR UPDATE;
 IF NOT FOUND OR t.active_submission_operation_id IS DISTINCT FROM r.source_operation_id
 THEN RAISE EXCEPTION 'selected PRE active source mismatch' USING ERRCODE='23514'; END IF;
 SELECT * INTO o FROM public.submission_intake_operations
 WHERE id=r.source_operation_id AND task_id=r.task_id FOR UPDATE;
 observed:=clock_timestamp();
 IF NOT FOUND OR o.state IS DISTINCT FROM 'pre_checking'
    OR o.lease_expires_at<=observed OR o.pre_deadline_at<=observed
    OR t.status IS DISTINCT FROM o.eligible_task_status
    OR o.project_id IS DISTINCT FROM r.project_id
    OR o.assignment_id IS DISTINCT FROM r.assignment_id
    OR o.actor_profile_id IS DISTINCT FROM r.actor_profile_id
    OR o.identity_link_id IS DISTINCT FROM r.identity_link_id
    OR o.idempotency_key IS DISTINCT FROM r.idempotency_key
    OR o.metadata_sha256 IS DISTINCT FROM request->>'metadata_sha256'
    OR o.locked_context_sha256 IS DISTINCT FROM request->>'locked_context_sha256'
    OR o.locked_task_context IS DISTINCT FROM public.submission_intake_task_snapshot(t)
    OR o.lease_id IS DISTINCT FROM (request->>'foreground_lease_id')::uuid
    OR o.lease_generation IS DISTINCT FROM (request->>'foreground_lease_generation')::bigint
    OR o.pre_deadline_at IS DISTINCT FROM (request->>'pre_deadline_at')::timestamptz
    OR (r.lease_expires_at IS NOT NULL AND r.lease_expires_at>o.pre_deadline_at)
 THEN RAISE EXCEPTION 'selected PRE source custody mismatch' USING ERRCODE='23514'; END IF;
 source:=jsonb_build_object(
   'location',jsonb_build_object('operation_id',o.id::text,'namespace_id',o.namespace_id,
     'namespace_fingerprint',o.namespace_fingerprint,'provider_profile',o.provider_profile),
   'provider_generation',o.provider_generation,'raw_sha256',o.raw_sha256,
   'raw_byte_count',o.raw_byte_count,'sealed_upload_fence',o.sealed_upload_fence,
   'media_type','application/zip');
 IF request->'source' IS DISTINCT FROM source
    OR request->>'source_sha256' IS DISTINCT FROM public.external_checker_registry_digest(
      source||jsonb_build_object('schema_version','workstream.sealed_submission_source.v1'))
    OR r.archive_sha256 IS DISTINCT FROM o.raw_sha256
    OR r.archive_byte_count IS DISTINCT FROM o.raw_byte_count
    OR request->'default_context'->'packet' IS DISTINCT FROM jsonb_build_object(
      'summary',o.command_metadata->>'summary',
      'contributor_attestation',o.command_metadata->>'contributor_attestation')
    OR request->'admission_lineage'->>'packet_sha256' IS DISTINCT FROM
       public.external_checker_registry_digest(request->'default_context'->'packet')
    OR request->'admission_lineage'->>'rules_sha256' IS DISTINCT FROM
       request->'default_context'->>'current_rules_sha256'
    OR request->'admission_lineage' ?| ARRAY['semantic_manifest_id','semantic_manifest_body']
 THEN RAISE EXCEPTION 'selected PRE source descriptor mismatch' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.pre_submit_checker_policies p
    WHERE p.id=t.locked_pre_submit_checker_policy_id AND p.project_id=r.project_id
      AND p.compiled_bundle::jsonb=request->'policy')
    OR NOT EXISTS(SELECT 1 FROM public.project_guide_proposal_approvals a
      WHERE a.pre_submit_policy_id=t.locked_pre_submit_checker_policy_id
        AND a.project_id=r.project_id
        AND a.effective_pre_submit_plan::jsonb->'post_submit'=
            request->'admission_lineage'->'post_submit_policy_body'
        AND a.effective_pre_submit_plan_hash=
            request->'admission_lineage'->>'external_checker_policies_sha256')
    OR jsonb_array_length(request->'policy'->'entries') IS DISTINCT FROM 1
    OR r.policy_sha256 IS DISTINCT FROM public.external_checker_registry_digest(
       (request->'policy')-'policy_sha256')
 THEN RAISE EXCEPTION 'selected PRE policy custody mismatch' USING ERRCODE='23514'; END IF;
 SELECT jsonb_object_agg(key,value) INTO policy_lineage FROM jsonb_each(to_jsonb(t))
 WHERE key=ANY(ARRAY[
   'locked_guide_version','locked_guide_source_snapshot_id','locked_guide_source_snapshot_hash',
   'locked_effective_project_submission_artifact_policy_id',
   'locked_effective_project_submission_artifact_policy_hash','locked_pre_submit_checker_policy_id',
   'locked_pre_submit_checker_bundle_hash','locked_post_submit_checker_policy_id',
   'locked_post_submit_checker_policy_version','locked_post_submit_checker_policy_hash',
   'locked_review_policy_id','locked_review_policy_generation','locked_review_policy_hash',
   'locked_revision_policy_id','locked_revision_policy_generation','locked_revision_policy_hash',
   'locked_contribution_policy_version_id']);
 rules:=public.external_checker_registry_digest(jsonb_build_object(
   'schema_version','workstream.task_checker_rules.v1','task_policy',policy_lineage,
   'external_checker_policies_sha256',request->'admission_lineage'->>'external_checker_policies_sha256'));
 predecessor_id:=(request->'admission_lineage'->>'predecessor_submission_id')::uuid;
 IF predecessor_id IS NOT NULL THEN
   SELECT jsonb_build_object('submission_id',s.id::text,'submission_version',s.version,
       'archive_sha256',a.archive_sha256,'semantic_manifest_sha256',a.semantic_manifest_sha256),
       a.selected_rules_sha256 INTO predecessor,predecessor_rules
   FROM public.submissions s JOIN public.submission_bundle_admissions a
     ON a.consumed_by_submission_id=s.id AND a.status='consumed'
   WHERE s.id=predecessor_id AND s.task_id=r.task_id AND a.project_id=r.project_id
     AND a.task_id=s.task_id AND a.assignment_id=r.assignment_id
     AND s.task_assignment_id=r.assignment_id AND s.contributor_id=r.actor_profile_id
     AND s.version=(request->'admission_lineage'->>'predecessor_submission_version')::integer
     AND a.selected_pre_submit_run_id IS NOT NULL AND a.pre_submit_evidence_set_id IS NULL
     AND a.selected_rules_sha256 IS NOT NULL
     AND NOT EXISTS(SELECT 1 FROM public.submissions later
       WHERE later.task_id=s.task_id AND later.version>s.version);
   IF NOT FOUND THEN
     RAISE EXCEPTION 'selected PRE predecessor custody mismatch' USING ERRCODE='23514';
   END IF;
 END IF;
 expected_context:=jsonb_build_object('predecessor',predecessor,
   'current_predecessor',predecessor,'predecessor_exists',predecessor_id IS NOT NULL,
   'predecessor_rules_sha256',predecessor_rules,'current_rules_sha256',rules,
   'packet',jsonb_build_object('summary',o.command_metadata->>'summary',
      'contributor_attestation',o.command_metadata->>'contributor_attestation'));
 IF request->'default_context' IS DISTINCT FROM expected_context THEN
   RAISE EXCEPTION 'selected PRE default context mismatch' USING ERRCODE='23514';
 END IF;
END $$
""")


def _insert_guard():
    signature = "public.guard_selected_pre_submit_run_insert()"
    changes = [
        ("'workstream.selected_pre_submit_reservation.v1'", "'workstream.selected_pre_submit_reservation.v2'"),
        ("new.prepared_generation_id is distinct from\n       (new.request_json->>'prepared_generation_id')::uuid",
         "new.prepared_generation_id is not null\n    or new.source_operation_id is null"),
        ("new.request_json->>'policy_sha256'", "new.request_json->'policy'->>'policy_sha256'"),
        ("new.request_json->>'default_behavior_sha256'", "new.request_json->'policy'->'workstream_default'->>'behavior_sha256'"),
        ("new.default_input_sha256 is distinct from new.request_json->>'default_input_sha256'", "new.default_input_sha256 is not null"),
        ("new.request_json->>'archive_sha256'", "new.request_json->'source'->>'raw_sha256'"),
        ("new.request_json->>'archive_byte_count'", "new.request_json->'source'->>'raw_byte_count'"),
        ("new.semantic_manifest_sha256 is distinct from\n       new.request_json->>'semantic_manifest_sha256'", "new.semantic_manifest_sha256 is not null"),
        ("or jsonb_typeof(lineage) is distinct from 'object'", """or jsonb_typeof(lineage) is distinct from 'object'
    or not new.request_json ?& ARRAY['schema_version','actor_profile_id','identity_link_id',
       'project_id','task_id','assignment_id','attempt_id','idempotency_key','foreground_lease_id',
       'source','source_sha256','metadata_sha256','locked_context_sha256',
       'foreground_lease_generation','pre_deadline_at','policy','default_context',
       'runtime_profile','admission_lineage']
    or new.request_json-ARRAY['schema_version','actor_profile_id','identity_link_id',
       'project_id','task_id','assignment_id','attempt_id','idempotency_key','foreground_lease_id',
       'source','source_sha256','metadata_sha256','locked_context_sha256',
       'foreground_lease_generation','pre_deadline_at','policy','default_context',
       'runtime_profile','admission_lineage'] <> '{}'::jsonb"""),
        ("new.request_json->>'execution_budget_ms'", "new.request_json->'runtime_profile'->>'aggregate_deadline_ms'"),
        (" return new;", " perform public.require_selected_pre_source(new);\n return new;"),
    ]
    for old, new in changes:
        _replace(signature, old, new)


def _update_guard():
    signature = "public.guard_selected_pre_submit_run()"
    _replace(signature, " if row(old.id,", """ if old.request_json->>'schema_version' is distinct from
    'workstream.selected_pre_submit_reservation.v2' then
  raise exception 'historical selected PRE runs are read-only' using errcode='55000';
 end if;
 if old.source_operation_id is distinct from new.source_operation_id then
  raise exception 'selected PRE source is immutable' using errcode='55000';
 end if;
 if row(old.id,""")
    _replace(signature, " return new;", """
 if old.status='running' then
  if row(old.lease_id,old.lease_generation,old.lease_expires_at,old.started_at,old.execute_evidence_id)
     is distinct from
     row(new.lease_id,new.lease_generation,new.lease_expires_at,new.started_at,new.execute_evidence_id)
  then raise exception 'selected PRE committed claim is immutable' using errcode='55000'; end if;
  if new.terminal_json-ARRAY['schema_version','reservation','request_digest','lease_id',
       'lease_generation','lease_expires_at','outcome','execution','infrastructure_failure_code',
       'queued_at','started_at','completed_at','queue_latency_ms','execution_latency_ms'] <> '{}'::jsonb
     or new.terminal_json->>'schema_version' is distinct from 'workstream.selected_pre_submit_terminal.v2'
     or new.terminal_digest is distinct from public.external_checker_registry_digest(new.terminal_json)
     or new.terminal_json->'reservation' is distinct from new.request_json
     or new.terminal_json->>'request_digest' is distinct from new.request_digest
     or new.terminal_json->>'outcome' is distinct from new.status
     or (new.terminal_json->>'lease_id')::uuid is distinct from new.lease_id
     or (new.terminal_json->>'lease_generation')::bigint is distinct from new.lease_generation
     or (new.terminal_json->>'lease_expires_at')::timestamptz is distinct from new.lease_expires_at
     or (new.terminal_json->>'queued_at')::timestamptz is distinct from new.queued_at
     or (new.terminal_json->>'started_at')::timestamptz is distinct from new.started_at
     or (new.terminal_json->>'completed_at')::timestamptz is distinct from new.completed_at
     or new.completed_at<new.started_at or new.started_at<new.queued_at
     or (new.terminal_json->>'queue_latency_ms')::bigint is distinct from
        trunc(extract(epoch from new.started_at-new.queued_at)*1000)::bigint
     or (new.terminal_json->>'execution_latency_ms')::bigint is distinct from
        trunc(extract(epoch from new.completed_at-new.started_at)*1000)::bigint
  then raise exception 'selected PRE terminal binding mismatch' using errcode='23514'; end if;
  if new.status='completed' then
    if jsonb_typeof(new.terminal_json->'execution') is distinct from 'object'
       or new.terminal_json->'infrastructure_failure_code' is distinct from 'null'::jsonb
       or new.terminal_json->'execution'->>'policy_sha256' is distinct from new.policy_sha256
       or (new.terminal_json->'execution'->>'eligible')::boolean is distinct from new.eligible
       or new.completed_at>new.lease_expires_at
    then raise exception 'selected PRE terminal result mismatch' using errcode='23514'; end if;
  elsif new.terminal_json->'execution' is distinct from 'null'::jsonb
     or coalesce(new.terminal_json->>'infrastructure_failure_code','') not in
        ('capacity_exceeded','deadline_exceeded','material_unavailable','implementation_unavailable','invalid_output')
  then raise exception 'selected PRE terminal result mismatch' using errcode='23514'; end if;
 end if;
 perform public.require_selected_pre_source(new);
 return new;""")
    signature = "public.selected_pre_submit_facts_digest(public.selected_pre_submit_runs,text)"
    for phase in ("execute", "finalize"):
        old = f"'workstream.selected_pre_submit_{phase}.v1'"
        new = ("case when r.request_json->>'schema_version'="
               "'workstream.selected_pre_submit_reservation.v2' then "
               f"'workstream.selected_pre_submit_{phase}.v2' else {old} end")
        _replace(signature, old, new)
    for signature in (
        "public.guard_submission_bundle_durable_intent_put_attempt()",
        "public.guard_submission_bundle_admission_verified_lineage()",
    ):
        _replace(signature, "r.status='completed' and r.eligible",
                 "r.status='completed' and r.eligible and r.request_json->>'schema_version'="
                 "'workstream.selected_pre_submit_reservation.v1'")


def upgrade():
    """Retain historical bytes while restricting new writes to source-bound runs."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("ALTER TABLE public.selected_pre_submit_runs ADD COLUMN source_operation_id uuid")
    for column in ("prepared_generation_id", "default_input_sha256", "semantic_manifest_sha256"):
        op.execute(f"ALTER TABLE public.selected_pre_submit_runs ALTER COLUMN {column} DROP NOT NULL")
    op.execute("""ALTER TABLE public.selected_pre_submit_runs
      ADD CONSTRAINT fk_selected_pre_run_source_operation FOREIGN KEY(source_operation_id,task_id)
        REFERENCES public.submission_intake_operations(id,task_id),
      ADD CONSTRAINT uq_selected_pre_run_source_operation UNIQUE(source_operation_id)""")
    _source_guard()
    _insert_guard()
    _update_guard()


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
