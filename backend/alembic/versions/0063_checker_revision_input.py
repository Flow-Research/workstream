"""Retain selected checker revision input and its exact historical custody."""

from alembic import op
import sqlalchemy as sa


revision = "0063_checker_revision_input"
down_revision = "0062_model_usage"
branch_labels = None
depends_on = None


def _replace_function(signature: str, old: str, new: str) -> None:
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
    if definition.count(old) != 1:
        raise RuntimeError("checker revision input function shape changed: " + signature)
    op.execute(definition.replace(old, new))


def upgrade() -> None:
    """Add revision input without changing retained current-only receipt digests."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute("lock table public.checker_runs in access exclusive mode")
    op.execute("alter table public.checker_runs add column input_context_custody jsonb")
    op.execute(
        "alter table public.checker_runs add constraint "
        "ck_checker_runs_input_context_custody_object check ("
        "input_context_custody is null or "
        "pg_catalog.jsonb_typeof(input_context_custody)='object')"
    )
    _replace_run_custody()
    _replace_authority_digests()
    _create_context_guard()
    op.execute(
        "do $$ begin if exists(select 1 from public.checker_runs r where "
        "public.checker_input_context_valid(r) is not true) then raise exception "
        "'retained checker revision input lacks exact custody' using errcode='23514'; "
        "end if; end $$"
    )
    op.execute(
        "create constraint trigger checker_input_context_custody "
        "after insert or update on public.checker_runs "
        "deferrable initially deferred for each row "
        "execute function public.guard_checker_input_context_custody()"
    )


def _replace_run_custody() -> None:
    _replace_function(
        "public.protect_checker_run_custody()",
        "'input_materialization_evidence_id','result_json','result_digest',"
        "'material_custody','completion_event_id'",
        "'input_materialization_evidence_id','result_json','result_digest',"
        "'material_custody','input_context_custody','completion_event_id'",
    )
    _replace_function(
        "public.protect_checker_run_custody()",
        "NEW.material_custody IS NOT NULL OR NEW.completion_event_id IS NOT NULL",
        "NEW.material_custody IS NOT NULL OR NEW.input_context_custody IS NOT NULL "
        "OR NEW.completion_event_id IS NOT NULL",
    )


def _replace_authority_digests() -> None:
    _replace_function(
        "public.checker_input_authority_digest(public.checker_runs)",
        "'semantic_manifest_id',a.semantic_manifest_id::text)",
        "'semantic_manifest_id',a.semantic_manifest_id::text) || "
        "CASE WHEN r.input_context_custody IS NOT NULL THEN "
        "jsonb_build_object('input_context_custody',r.input_context_custody) "
        "ELSE '{}'::jsonb END",
    )
    _replace_function(
        "public.checker_post_submit_authority_digest(public.checker_runs,text)",
        "'material',r.material_custody::jsonb, 'output_binding_ids','[]'::jsonb\n"
        "              ) ELSE '{}'::jsonb END",
        "'material',r.material_custody::jsonb, 'output_binding_ids','[]'::jsonb\n"
        "              ) || CASE WHEN r.input_context_custody IS NOT NULL THEN\n"
        "                jsonb_build_object('input_context_custody',r.input_context_custody)\n"
        "              ELSE '{}'::jsonb END ELSE '{}'::jsonb END",
    )


def _create_context_guard() -> None:
    op.execute(r"""
CREATE FUNCTION public.checker_input_context_valid(r public.checker_runs) RETURNS boolean
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  entry jsonb;
  configuration jsonb;
  roles jsonb;
  selected boolean := false;
  wants_feedback boolean := false;
  wants_archive boolean := false;
  custody jsonb := r.input_context_custody;
  context jsonb;
  source jsonb;
  evaluation jsonb;
  predecessor jsonb;
  feedback jsonb;
  prior_custody jsonb;
  current_submission public.submissions%ROWTYPE;
  prior_submission public.submissions%ROWTYPE;
  current_admission public.submission_bundle_admissions%ROWTYPE;
  prior_admission public.submission_bundle_admissions%ROWTYPE;
  dispatch public.submission_dispatches%ROWTYPE;
  preparation public.task_revision_preparations%ROWTYPE;
  manifest public.task_post_submit_routing_manifests%ROWTYPE;
  prior_run public.checker_runs%ROWTYPE;
  expected_evaluation jsonb;
  expected_source jsonb;
  expected_predecessor jsonb;
  expected_feedback_source jsonb;
  expected_feedback_members jsonb;
BEGIN
  IF pg_catalog.jsonb_typeof(r.request_json::jsonb#>'{policy,entries}') IS DISTINCT FROM 'array'
  THEN RETURN false; END IF;
  FOR entry IN SELECT value FROM pg_catalog.jsonb_array_elements(
    r.request_json::jsonb#>'{policy,entries}')
  LOOP
    configuration := entry->'configuration';
    IF pg_catalog.jsonb_typeof(configuration) IS DISTINCT FROM 'object' THEN
      RETURN false;
    END IF;
    IF configuration ? 'workstream_evaluation_context_version'
       OR configuration ? 'workstream_evaluation_context_roles' THEN
      IF NOT (configuration ? 'workstream_evaluation_context_version')
         OR NOT (configuration ? 'workstream_evaluation_context_roles')
         OR configuration->>'workstream_evaluation_context_version' IS DISTINCT FROM 'v1'
      THEN RETURN false; END IF;
      roles := configuration->'workstream_evaluation_context_roles';
      IF roles IS DISTINCT FROM '[]'::jsonb
         AND roles IS DISTINCT FROM '["predecessor_findings"]'::jsonb
         AND roles IS DISTINCT FROM '["predecessor_submission_archive"]'::jsonb
         AND roles IS DISTINCT FROM
           '["predecessor_findings","predecessor_submission_archive"]'::jsonb
      THEN RETURN false; END IF;
      selected := true;
      wants_feedback := wants_feedback OR roles @> '["predecessor_findings"]'::jsonb;
      wants_archive := wants_archive OR roles @> '["predecessor_submission_archive"]'::jsonb;
    END IF;
  END LOOP;

  IF (custody IS NOT NULL) IS DISTINCT FROM
     (selected AND r.material_custody IS NOT NULL) THEN
    RETURN false;
  END IF;
  IF custody IS NULL THEN RETURN true; END IF;
  IF custody - ARRAY['evaluation_context','predecessor'] <> '{}'::jsonb
     OR pg_catalog.jsonb_typeof(custody->'evaluation_context') IS DISTINCT FROM 'object'
     OR NOT custody ? 'predecessor' THEN
    RETURN false;
  END IF;
  context := custody->'evaluation_context';
  prior_custody := custody->'predecessor';
  IF context - ARRAY['schema_version','kind','source','predecessor','feedback'] <> '{}'::jsonb
     OR context->>'schema_version' IS DISTINCT FROM
        'workstream.post_submit_evaluation_context.v1'
     OR NOT context ?& ARRAY['source','predecessor','feedback'] THEN
    RETURN false;
  END IF;

  SELECT * INTO current_submission FROM public.submissions s
   WHERE s.id=r.submission_id AND s.task_id=r.task_id AND s.version=r.submission_version
     AND s.task_assignment_id=(r.request_json::jsonb->>'assignment_id')::uuid;
  SELECT * INTO current_admission FROM public.submission_bundle_admissions a
   WHERE a.id=(r.material_custody::jsonb->>'admission_id')::uuid
     AND a.status='consumed' AND a.consumed_by_submission_id=r.submission_id
     AND a.consumed_by_submission_version=r.submission_version
     AND a.project_id=r.project_id AND a.task_id=r.task_id
     AND a.assignment_id=current_submission.task_assignment_id;
  SELECT * INTO dispatch FROM public.submission_dispatches d
   WHERE d.submission_id=r.submission_id AND d.submission_version=r.submission_version
     AND d.project_id=r.project_id AND d.task_id=r.task_id
     AND d.assignment_id=current_submission.task_assignment_id
     AND d.admission_id=current_admission.id;
  IF current_submission.id IS NULL OR current_admission.id IS NULL OR dispatch.submission_id IS NULL
  THEN RETURN false; END IF;

  IF context->>'kind'='initial' THEN
    RETURN context=jsonb_build_object(
      'schema_version','workstream.post_submit_evaluation_context.v1',
      'kind','initial','source',NULL,'predecessor',NULL,'feedback',NULL)
      AND prior_custody='null'::jsonb
      AND dispatch.creation_kind='initial' AND dispatch.creation_status='in_progress'
      AND dispatch.checker_remediation_manifest_id IS NULL
      AND current_submission.supersedes_submission_id IS NULL
      AND current_admission.revision_preparation_id IS NULL
      AND current_admission.revision_preparation_sha256 IS NULL;
  END IF;
  IF context->>'kind' IS DISTINCT FROM 'checker_remediation' THEN RETURN false; END IF;
  source := context->'source';
  evaluation := source->'evaluation';
  predecessor := context->'predecessor';
  feedback := context->'feedback';
  IF pg_catalog.jsonb_typeof(source) IS DISTINCT FROM 'object'
     OR source - ARRAY['preparation_id','preparation_sha256','routing_manifest_id',
                       'revision_round','evaluation'] <> '{}'::jsonb
     OR pg_catalog.jsonb_typeof(evaluation) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(predecessor) IS DISTINCT FROM 'object'
     OR (feedback IS NOT NULL AND feedback<>'null'::jsonb AND
         pg_catalog.jsonb_typeof(feedback) IS DISTINCT FROM 'object')
  THEN RETURN false; END IF;

  SELECT * INTO prior_submission FROM public.submissions s
   WHERE s.id=current_submission.supersedes_submission_id AND s.task_id=r.task_id
     AND s.task_assignment_id=current_submission.task_assignment_id
     AND s.contributor_id=current_submission.contributor_id
     AND s.version=r.submission_version-1;
  SELECT * INTO preparation FROM public.task_revision_preparations p
   WHERE p.id=(source->>'preparation_id')::uuid
     AND p.preparation_sha256=source->>'preparation_sha256'
     AND p.project_id=r.project_id AND p.task_id=r.task_id
     AND p.assignment_id=current_submission.task_assignment_id
     AND p.contributor_id=current_submission.contributor_id
     AND p.submission_id=prior_submission.id
     AND p.source_submission_version=prior_submission.version
     AND p.routing_manifest_id=(source->>'routing_manifest_id')::uuid
     AND p.next_revision_round=(source->>'revision_round')::integer
     AND p.next_revision_round<=p.max_revision_rounds
     AND p.outcome IN ('kept','rebased') AND p.blocked_reason IS NULL;
  SELECT * INTO manifest FROM public.task_post_submit_routing_manifests m
   WHERE m.id=preparation.routing_manifest_id AND m.project_id=r.project_id
     AND m.task_id=r.task_id AND m.assignment_id=current_submission.task_assignment_id
     AND m.contributor_id=current_submission.contributor_id
     AND m.submission_id=prior_submission.id
     AND m.submission_version=prior_submission.version
     AND m.routing_recommendation='needs_revision';
  SELECT * INTO prior_admission FROM public.submission_bundle_admissions a
   WHERE a.id=prior_submission.submission_bundle_admission_id
     AND a.status='consumed'
     AND a.consumed_by_submission_id=prior_submission.id
     AND a.consumed_by_submission_version=prior_submission.version
     AND a.project_id=r.project_id AND a.task_id=r.task_id
     AND a.assignment_id=current_submission.task_assignment_id;
  IF prior_submission.id IS NULL OR prior_admission.id IS NULL
     OR preparation.id IS NULL OR manifest.id IS NULL
     OR dispatch.creation_kind<>'checker_remediation'
     OR dispatch.creation_status<>'needs_revision'
     OR dispatch.checker_remediation_manifest_id IS DISTINCT FROM manifest.id
     OR current_admission.revision_preparation_id IS DISTINCT FROM preparation.id
     OR current_admission.revision_preparation_sha256 IS DISTINCT FROM preparation.preparation_sha256
  THEN RETURN false; END IF;

  expected_evaluation := jsonb_build_object(
    'project_id',manifest.project_id,'task_id',manifest.task_id,
    'submission_id',manifest.submission_id,'submission_version',manifest.submission_version,
    'checker_run_id',manifest.checker_run_id,
    'evaluation_request_id',manifest.evaluation_request_id,
    'evaluation_request_digest',manifest.request_digest,
    'evaluation_generation',manifest.evaluation_generation,
    'result_id',manifest.result_id,'result_digest',manifest.result_digest,
    'completion_event_id',manifest.completion_event_id,
    'routing_recommendation','needs_revision');
  expected_source := jsonb_build_object(
    'preparation_id',preparation.id,'preparation_sha256',preparation.preparation_sha256,
    'routing_manifest_id',manifest.id,'revision_round',preparation.next_revision_round,
    'evaluation',expected_evaluation);
  IF source IS DISTINCT FROM expected_source THEN RETURN false; END IF;

  SELECT * INTO prior_run FROM public.checker_runs cr
   WHERE cr.id=manifest.checker_run_id AND cr.project_id=manifest.project_id
     AND cr.task_id=manifest.task_id AND cr.submission_id=manifest.submission_id
     AND cr.submission_version=manifest.submission_version
     AND cr.evaluation_request_id=manifest.evaluation_request_id
     AND cr.request_digest=manifest.request_digest
     AND cr.evaluation_generation=manifest.evaluation_generation
     AND cr.result_id=manifest.result_id AND cr.result_digest=manifest.result_digest
     AND cr.completion_event_id=manifest.completion_event_id
     AND cr.status='completed' AND cr.routing_recommendation='needs_revision';
  IF prior_run.id IS NULL OR prior_run.request_json::jsonb->>'assignment_id'
     IS DISTINCT FROM current_submission.task_assignment_id::text THEN
    RETURN false;
  END IF;

  expected_predecessor := jsonb_build_object(
    'submission_id',prior_submission.id,'submission_version',prior_submission.version,
    'content_sha256',prior_admission.archive_sha256,
    'byte_count',prior_admission.archive_byte_count,
    'semantic_manifest_sha256',prior_admission.semantic_manifest_sha256);
  IF predecessor IS DISTINCT FROM expected_predecessor THEN RETURN false; END IF;

  IF wants_feedback THEN
    IF pg_catalog.jsonb_typeof(prior_run.request_json::jsonb#>'{policy,entries}')
         IS DISTINCT FROM 'array'
       OR pg_catalog.jsonb_typeof(prior_run.result_json::jsonb#>'{execution,external_members}')
         IS DISTINCT FROM 'array'
       OR pg_catalog.jsonb_array_length(prior_run.request_json::jsonb#>'{policy,entries}')
         IS DISTINCT FROM pg_catalog.jsonb_array_length(
           prior_run.result_json::jsonb#>'{execution,external_members}')
    THEN RETURN false; END IF;
    SELECT coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
      'order',(result_member.value->>'order')::integer,
      'requirement_id',result_member.value->>'requirement_id',
      'registry_entry_id',result_member.value->'registry_entry_id',
      'registry_entry_digest',result_member.value->'registry_entry_digest',
      'configuration_sha256',request_member.value->'configuration_sha256',
      'request_digest',result_member.value->'request_digest',
      'result_digest',result_member.value#>'{result,result_digest}',
      'verdict',result_member.value#>'{result,verdict}',
      'findings',result_member.value#>'{result,findings}'
    ) ORDER BY result_member.ordinality),'[]'::jsonb)
    INTO expected_feedback_members
    FROM pg_catalog.jsonb_array_elements(
      prior_run.result_json::jsonb#>'{execution,external_members}') WITH ORDINALITY
      AS result_member(value,ordinality)
    JOIN pg_catalog.jsonb_array_elements(
      prior_run.request_json::jsonb#>'{policy,entries}') WITH ORDINALITY
      AS request_member(value,ordinality)
      ON request_member.ordinality=result_member.ordinality;
    expected_feedback_source := jsonb_build_object(
      'project_id',manifest.project_id,'task_id',manifest.task_id,
      'assignment_id',manifest.assignment_id,'submission_id',manifest.submission_id,
      'submission_version',manifest.submission_version,
      'completion_event_id',manifest.completion_event_id,
      'result',jsonb_build_object(
        'schema_version','post_submit_current_result_reference',
        'attempt_id',manifest.checker_run_id,'request_id',manifest.evaluation_request_id,
        'request_digest',manifest.request_digest,
        'evaluation_generation',manifest.evaluation_generation,
        'result_id',manifest.result_id,'result_digest',manifest.result_digest));
    IF pg_catalog.jsonb_typeof(feedback) IS DISTINCT FROM 'object'
       OR feedback - ARRAY['source','policy_sha256','members'] <> '{}'::jsonb
       OR feedback->'source' IS DISTINCT FROM expected_feedback_source
       OR feedback->>'policy_sha256' IS DISTINCT FROM prior_run.selected_post_submit_policy_sha256
       OR feedback->'members' IS DISTINCT FROM expected_feedback_members
    THEN RETURN false; END IF;
  ELSIF feedback<>'null'::jsonb THEN
    RETURN false;
  END IF;

  IF wants_archive THEN
    IF pg_catalog.jsonb_typeof(prior_custody) IS DISTINCT FROM 'object'
       OR prior_custody - ARRAY[
         'submission_id','submission_version','content_sha256','byte_count',
         'semantic_manifest_sha256','admission_id','binding_id','content_id','replica_id',
         'evidence_id','verification_receipt_id','verification_job_id',
         'verification_generation','namespace_fingerprint','semantic_manifest_id'] <> '{}'::jsonb
       OR prior_custody->'submission_id' IS DISTINCT FROM predecessor->'submission_id'
       OR prior_custody->'submission_version' IS DISTINCT FROM predecessor->'submission_version'
       OR prior_custody->'content_sha256' IS DISTINCT FROM predecessor->'content_sha256'
       OR prior_custody->'byte_count' IS DISTINCT FROM predecessor->'byte_count'
       OR prior_custody->'semantic_manifest_sha256' IS DISTINCT FROM
          predecessor->'semantic_manifest_sha256'
       OR public.art_submission_material_matches(
         r.project_id,r.task_id,prior_submission.id,prior_submission.version,
         prior_custody - ARRAY['evidence_id','verification_receipt_id','verification_job_id',
                               'verification_generation','namespace_fingerprint',
                               'semantic_manifest_id']) IS NOT TRUE
       OR NOT EXISTS(
         SELECT 1 FROM public.submission_bundle_admissions a
         JOIN public.artifact_verification_receipts receipt
           ON receipt.id=a.verification_receipt_id
         JOIN public.artifact_replicas replica ON replica.id=a.verified_replica_id
         JOIN public.artifact_storage_namespaces namespace
           ON namespace.id=replica.storage_namespace_id
         WHERE a.id=(prior_custody->>'admission_id')::uuid
           AND prior_custody->>'evidence_id'=
             coalesce(a.pre_submit_evidence_set_id,a.selected_pre_submit_run_id)::text
           AND prior_custody->>'verification_receipt_id'=receipt.id::text
           AND prior_custody->>'verification_job_id'=receipt.verification_job_id::text
           AND prior_custody->>'verification_generation'=receipt.execution_generation::text
           AND prior_custody->>'namespace_fingerprint'=namespace.namespace_fingerprint
           AND prior_custody->>'semantic_manifest_id'=a.semantic_manifest_id::text)
    THEN RETURN false; END IF;
  ELSIF prior_custody<>'null'::jsonb THEN
    RETURN false;
  END IF;
  RETURN true;
EXCEPTION WHEN data_exception THEN
  RETURN false;
END $$
    """)
    op.execute(r"""
CREATE FUNCTION public.guard_checker_input_context_custody() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE current_run public.checker_runs%ROWTYPE;
BEGIN
  SELECT * INTO current_run FROM public.checker_runs WHERE id=NEW.id;
  IF NOT FOUND OR public.checker_input_context_valid(current_run) IS NOT TRUE THEN
    RAISE EXCEPTION 'checker revision input custody mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$
    """)


def downgrade() -> None:
    """Refuse downgrade without weakening retained revision input custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
