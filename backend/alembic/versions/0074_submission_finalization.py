"""Continue accepted custody into exact retained Submission and POST lineage."""
import re
from alembic import op
from sqlalchemy import text

revision = "0074_submission_finalization"
down_revision = "0073_submission_acceptance"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("finalization predecessor shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _extend_audit_action()
    op.execute("LOCK TABLE public.workstream_tasks, public.submission_intake_operations, "
               "public.submission_bundle_admissions, public.artifact_replicas, public.submissions, "
               "public.submission_dispatches IN ACCESS EXCLUSIVE MODE")
    for column, kind in {
        "continuation_lease_id": "uuid", "continuation_generation": "bigint",
        "continuation_expires_at": "timestamptz", "continuation_decision_id": "uuid",
        "finalized_at": "timestamptz", "finalization_decision_id": "uuid",
        "finalized_submission_id": "uuid", "finalized_admission_id": "uuid",
    }.items():
        op.execute(f"ALTER TABLE public.submission_intake_operations ADD COLUMN {column} {kind}")
    for table in ("submission_bundle_admissions", "artifact_replicas"):
        op.execute(f"ALTER TABLE public.{table} ADD COLUMN source_operation_id uuid")
    for column in ("durable_intent_id", "put_attempt_id", "verification_receipt_id"):
        op.execute(f"ALTER TABLE public.submission_bundle_admissions ALTER COLUMN {column} DROP NOT NULL")
    for table, name, ddl in _CONSTRAINTS:
        op.execute(f'ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS "{name}"')
        op.execute(ddl)
    for statement in re.split(r"\n(?=CREATE (?:FUNCTION|CONSTRAINT TRIGGER|TRIGGER))", _FUNCTIONS):
        if statement.strip():
            op.execute(statement)
    _extend_existing_guards()


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


def _extend_audit_action():
    """Allow only the fixed finalization action/permission evidence pair."""
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "(((action_id)::text = 'contribution.read_self'::text) AND ((permission_id)::text = 'contribution.read_self'::text))"
    if definition.count(anchor) != 2 or "artifact.submission.finalize" in definition:
        raise RuntimeError("finalization audit action constraint shape changed")
    addition = " OR (((action_id)::text = 'artifact.submission.finalize'::text) AND ((permission_id)::text = 'artifact.binding.create'::text))"
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " "
               + definition.replace(anchor, anchor + addition))


_CONSTRAINTS = [('submission_intake_operations',
  'ck_submission_intake_operations_pre_requires_source',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT '
  'ck_submission_intake_operations_pre_requires_source CHECK (state not in '
  "('pre_checking','finalization_pending','finalized') or sealed_at is not null)"),
 ('submission_intake_operations',
  'ck_submission_intake_operations_terminal_shape',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT ck_submission_intake_operations_terminal_shape '
  "CHECK ((state in ('receiving','pre_checking','finalization_pending') and terminal_at is null and "
  "failure_code is null) or (state='finalized' and terminal_at is not null and failure_code is null) or "
  "(state in ('rejected','failed','abandoned','cancelled') and terminal_at is not null and failure_code is "
  'not null))'),
 ('submission_intake_operations',
  'ck_submission_intake_operations_foreground_state',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT ck_submission_intake_operations_foreground_state '
  'CHECK (state in '
  "('receiving','pre_checking','finalization_pending','finalized','rejected','failed','abandoned','cancelled'))"),
 ('submission_intake_operations',
  'ck_submission_intake_operations_acceptance_shape',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT ck_submission_intake_operations_acceptance_shape '
  "CHECK ((state in ('finalization_pending','finalized') and accepted_at is not null and "
  'acceptance_decision_id is not null and selected_pre_submit_run_id is not null and '
  'selected_pre_submit_request_sha256 is not null and selected_pre_submit_terminal_sha256 is not null and '
  'accepted_source_sha256 is not null and accepted_manifest_sha256 is not null and accepted_context is not '
  'null and accepted_context_sha256 is not null and acceptance_receipt is not null and '
  'acceptance_receipt_sha256 is not null and finalization_event_id is not null) or (state not in '
  "('finalization_pending','finalized') and accepted_at is null and acceptance_decision_id is null and "
  'selected_pre_submit_run_id is null and selected_pre_submit_request_sha256 is null and '
  'selected_pre_submit_terminal_sha256 is null and accepted_source_sha256 is null and '
  'accepted_manifest_sha256 is null and accepted_context is null and accepted_context_sha256 is null and '
  'acceptance_receipt is null and acceptance_receipt_sha256 is null and finalization_event_id is null))'),
 ('submission_intake_operations',
  'fk_intake_finalization_decision',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT fk_intake_finalization_decision FOREIGN '
  'KEY(finalization_decision_id) REFERENCES audit_events (id) DEFERRABLE INITIALLY DEFERRED'),
 ('submission_intake_operations',
  'fk_intake_continuation_decision',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT fk_intake_continuation_decision FOREIGN '
  'KEY(continuation_decision_id) REFERENCES audit_events (id) DEFERRABLE INITIALLY DEFERRED'),
 ('submission_intake_operations',
  'fk_intake_finalized_submission',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT fk_intake_finalized_submission FOREIGN '
  'KEY(finalized_submission_id) REFERENCES submissions (id) DEFERRABLE INITIALLY DEFERRED'),
 ('submission_intake_operations',
  'fk_intake_finalized_admission',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT fk_intake_finalized_admission FOREIGN '
  'KEY(finalized_admission_id) REFERENCES submission_bundle_admissions (id) DEFERRABLE INITIALLY DEFERRED'),
 ('submission_intake_operations',
  'uq_intake_finalized_submission',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT uq_intake_finalized_submission UNIQUE '
  '(finalized_submission_id)'),
 ('submission_intake_operations',
  'uq_intake_finalized_admission',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT uq_intake_finalized_admission UNIQUE '
  '(finalized_admission_id)'),
 ('submission_intake_operations',
  'ck_submission_intake_operations_continuation_shape',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT '
  'ck_submission_intake_operations_continuation_shape CHECK ((continuation_lease_id is null and '
  'continuation_generation is null and continuation_expires_at is null and continuation_decision_id is null) '
  "or (state in ('finalization_pending','finalized') and continuation_lease_id is not null and "
  'continuation_generation is not null and continuation_generation>0 and continuation_expires_at is not null '
  'and continuation_decision_id is not null))'),
 ('submission_intake_operations',
  'ck_submission_intake_operations_finalization_shape',
  'ALTER TABLE submission_intake_operations ADD CONSTRAINT '
  "ck_submission_intake_operations_finalization_shape CHECK ((state='finalized' and finalized_at is not null "
  'and finalized_at=terminal_at and finalization_decision_id is not null and finalized_submission_id is not '
  "null and finalized_admission_id is not null and continuation_lease_id is not null) or (state<>'finalized' "
  'and finalized_at is null and finalization_decision_id is null and finalized_submission_id is null and '
  'finalized_admission_id is null))'),
 ('submission_bundle_admissions',
  'fk_submission_bundle_admissions_source_operation_id_submission_intake_operations',
  'ALTER TABLE submission_bundle_admissions ADD CONSTRAINT '
  'fk_submission_bundle_admissions_source_operation_id_sub_3f5f FOREIGN KEY(source_operation_id) REFERENCES '
  'submission_intake_operations (id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED'),
 ('submission_bundle_admissions',
  'uq_submission_bundle_admissions_source_operation_id',
  'ALTER TABLE submission_bundle_admissions ADD CONSTRAINT '
  'uq_submission_bundle_admissions_source_operation_id UNIQUE (source_operation_id)'),
 ('submission_bundle_admissions',
  'ck_submission_bundle_admissions_write_receipt_shape',
  'ALTER TABLE submission_bundle_admissions ADD CONSTRAINT '
  'ck_submission_bundle_admissions_write_receipt_shape CHECK ((source_operation_id is null and '
  'durable_intent_id is not null and put_attempt_id is not null and verification_receipt_id is not null and '
  '((put_operation_receipt_id is not null)::int + (put_observation_receipt_id is not null)::int) = 1) or '
  '(source_operation_id is not null and durable_intent_id is null and put_attempt_id is null and '
  'verification_receipt_id is null and put_operation_receipt_id is null and put_observation_receipt_id is '
  'null))'),
 ('artifact_replicas',
  'uq_artifact_replicas_source_operation_id',
  'ALTER TABLE artifact_replicas ADD CONSTRAINT uq_artifact_replicas_source_operation_id UNIQUE '
  '(source_operation_id)'),
 ('artifact_replicas',
  'fk_artifact_replicas_source_operation_id_submission_intake_operations',
  'ALTER TABLE artifact_replicas ADD CONSTRAINT fk_artifact_replicas_source_operation_id_submission_int_1e83 '
  'FOREIGN KEY(source_operation_id) REFERENCES submission_intake_operations (id) ON DELETE RESTRICT '
  'DEFERRABLE INITIALLY DEFERRED')]


def _extend_existing_guards():
    anchor = "  IF OLD.state='pre_checking' AND NEW.state='finalization_pending' THEN"
    _replace("public.guard_submission_intake_mutation()", anchor, _CONTINUATION_MUTATION + anchor)
    _replace("public.check_submission_acceptance()", "o.state<>'finalization_pending'",
             "o.state NOT IN ('finalization_pending','finalized')")
    _replace("public.check_submission_acceptance()", "NEW.state<>'finalization_pending'",
             "NEW.state NOT IN ('finalization_pending','finalized')")
    _replace("public.guard_submission_bundle_admission_verified_lineage()",
             "begin\n if new.pre_submit_evidence_set_id is not null",
             "begin\n if new.source_operation_id is not null then\n"
             "  perform public.require_source_submission_admission(new); return new;\n end if;\n"
             " if new.pre_submit_evidence_set_id is not null")
    original = "public.submission_authority_receipt_valid(d.creation_decision_id,public.submission_creation_resource(s.id),true)"
    _replace("public.submission_dispatch_valid(public.submission_dispatches)", original,
             "(CASE WHEN a.source_operation_id IS NULL THEN " + original + " ELSE EXISTS ("
             "SELECT 1 FROM public.submission_intake_operations o WHERE o.id=a.source_operation_id "
             "AND o.state='finalized' AND o.finalized_submission_id=s.id "
             "AND o.finalized_admission_id=a.id AND o.acceptance_decision_id=d.creation_decision_id) END)")


_CONTINUATION_MUTATION = """  IF OLD.state='finalization_pending' AND NEW.state='finalization_pending'
     AND ROW(NEW.continuation_lease_id,NEW.continuation_generation,NEW.continuation_expires_at,NEW.continuation_decision_id)
         IS DISTINCT FROM ROW(OLD.continuation_lease_id,OLD.continuation_generation,OLD.continuation_expires_at,OLD.continuation_decision_id) THEN
    IF (to_jsonb(NEW)-ARRAY['continuation_lease_id','continuation_generation','continuation_expires_at','continuation_decision_id'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['continuation_lease_id','continuation_generation','continuation_expires_at','continuation_decision_id'])
       OR NEW.continuation_generation IS DISTINCT FROM coalesce(OLD.continuation_generation,0)+1
       OR NEW.continuation_lease_id IS NOT DISTINCT FROM OLD.continuation_lease_id
       OR (OLD.continuation_expires_at IS NOT NULL AND OLD.continuation_expires_at>clock_timestamp())
       OR NOT isfinite(NEW.continuation_expires_at) OR NEW.continuation_expires_at<=clock_timestamp()
       OR NEW.continuation_expires_at>clock_timestamp()+interval '1 hour' THEN
      RAISE EXCEPTION 'invalid submission continuation claim' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.state='finalization_pending' AND NEW.state='finalized' THEN
    IF (to_jsonb(NEW)-ARRAY['state','terminal_at','finalized_at','finalization_decision_id','finalized_submission_id','finalized_admission_id'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','terminal_at','finalized_at','finalization_decision_id','finalized_submission_id','finalized_admission_id'])
       OR OLD.continuation_expires_at IS NULL OR OLD.continuation_expires_at<=clock_timestamp()
       OR NOT isfinite(NEW.finalized_at) OR NEW.finalized_at<OLD.accepted_at OR NEW.finalized_at>clock_timestamp() THEN
      RAISE EXCEPTION 'invalid submission finalization transition' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
"""

_FUNCTIONS = r"""
CREATE FUNCTION public.submission_finalization_authority_valid(o public.submission_intake_operations, phase text)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(EXISTS (
  SELECT 1 FROM public.audit_events a JOIN public.actor_profiles p ON p.id::text=a.actor_id
  WHERE a.id=(CASE WHEN phase='claim' THEN o.continuation_decision_id ELSE o.finalization_decision_id END)
    AND phase IN ('claim','commit') AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
    AND a.actor_ref_kind='actor_profile' AND p.actor_kind='service' AND p.service_identity='workstream.artifact.binding'
    AND a.action_id='artifact.submission.finalize' AND a.permission_id='artifact.binding.create'
    AND a.project_id=o.project_id AND a.resource_type='submission_operation' AND a.resource_id=o.id::text
    AND a.target_ref_kind='project' AND a.target_ref_id=o.project_id::text AND a.matched_grant_id IS NULL
    AND a.denial_code IS NULL AND a.request_id IS NOT NULL AND a.correlation_id IS NOT NULL
    AND a.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',
      public.external_checker_registry_digest(jsonb_build_object('resource_context',jsonb_strip_nulls(jsonb_build_object(
        'resource_type','submission_finalization','resource_id',o.id::text,'operation_id',o.id::text,
        'project_id',o.project_id::text,'task_id',o.task_id::text,'assignment_id',o.assignment_id::text,
        'contributor_id',o.actor_profile_id::text,'acceptance_decision_id',o.acceptance_decision_id::text,
        'accepted_context_sha256',o.accepted_context_sha256,'acceptance_receipt_sha256',o.acceptance_receipt_sha256,
        'source_sha256',o.accepted_source_sha256,'continuation_lease_id',o.continuation_lease_id::text,
        'continuation_generation',o.continuation_generation,'phase',phase,
        'submission_id',CASE WHEN phase='commit' THEN o.finalized_submission_id::text ELSE NULL END,
        'submission_version',CASE WHEN phase='commit' THEN
          (SELECT version FROM public.submissions WHERE id=o.finalized_submission_id) ELSE NULL END)))))
 ),false)
$$;

CREATE FUNCTION public.require_source_submission_admission(a public.submission_bundle_admissions)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE o public.submission_intake_operations%ROWTYPE; r public.selected_pre_submit_runs%ROWTYPE;
 v public.artifact_replicas%ROWTYPE; c public.artifact_contents%ROWTYPE; expected jsonb; actual jsonb;
BEGIN
 SELECT * INTO o FROM public.submission_intake_operations WHERE id=a.source_operation_id;
 IF o.id IS NULL OR o.state NOT IN ('finalization_pending','finalized') THEN
   RAISE EXCEPTION 'source admission has no accepted owner' USING ERRCODE='23514';
 END IF;
 PERFORM public.require_submission_acceptance(o);
 SELECT * INTO r FROM public.selected_pre_submit_runs WHERE id=o.selected_pre_submit_run_id;
 SELECT * INTO v FROM public.artifact_replicas WHERE id=a.verified_replica_id;
 SELECT * INTO c FROM public.artifact_contents WHERE id=a.artifact_content_id FOR SHARE;
 IF a.selected_pre_submit_run_id IS DISTINCT FROM r.id OR a.pre_submit_evidence_set_id IS NOT NULL
    OR v.id IS NULL OR c.id IS NULL OR v.source_operation_id IS DISTINCT FROM o.id
    OR v.content_id IS DISTINCT FROM c.id OR v.storage_namespace_id IS DISTINCT FROM o.namespace_id
    OR v.namespace_fingerprint IS DISTINCT FROM o.namespace_fingerprint OR v.provider_profile IS DISTINCT FROM o.provider_profile
    OR v.adapter IS DISTINCT FROM (SELECT adapter FROM public.artifact_storage_namespaces WHERE id=o.namespace_id)
    OR v.provider_object_ref IS DISTINCT FROM o.object_ref OR c.sha256 IS DISTINCT FROM o.raw_sha256
    OR c.byte_count IS DISTINCT FROM o.raw_byte_count OR c.media_type IS DISTINCT FROM 'application/zip'
    OR v.verification_state IS DISTINCT FROM 'verified' OR v.integrity_state IS DISTINCT FROM 'valid'
    OR a.actor_profile_id IS DISTINCT FROM o.actor_profile_id OR a.identity_link_id IS DISTINCT FROM o.identity_link_id
    OR a.project_id IS DISTINCT FROM o.project_id OR a.task_id IS DISTINCT FROM o.task_id
    OR a.assignment_id IS DISTINCT FROM o.assignment_id OR a.archive_sha256 IS DISTINCT FROM o.raw_sha256
    OR a.archive_byte_count IS DISTINCT FROM o.raw_byte_count
    OR a.semantic_manifest_body IS DISTINCT FROM r.terminal_json#>'{execution,manifest_body}'
    OR a.semantic_manifest_sha256 IS DISTINCT FROM o.accepted_manifest_sha256
    OR a.semantic_manifest_id IS NULL OR a.ready_at IS NULL OR a.ready_at<o.accepted_at
    OR a.revision_preparation_id::text IS DISTINCT FROM o.command_metadata->>'revision_preparation_id'
    OR a.revision_preparation_sha256 IS DISTINCT FROM o.command_metadata->>'revision_preparation_sha256' THEN
   RAISE EXCEPTION 'source admission provenance mismatch' USING ERRCODE='23514';
 END IF;
 expected:=r.request_json->'admission_lineage';
 actual:=jsonb_build_object(
   'predecessor_submission_id',a.predecessor_submission_id,'predecessor_submission_version',a.predecessor_submission_version,
   'checker_remediation_manifest_id',a.checker_remediation_manifest_id,
   'guide_id',a.guide_id,'guide_version',a.guide_version,'source_snapshot_id',a.source_snapshot_id,
   'source_snapshot_sha256',a.source_snapshot_sha256,'effective_policy_id',a.effective_policy_id,
   'effective_policy_sha256',a.effective_policy_sha256,'pre_submit_policy_id',a.pre_submit_policy_id,
   'pre_submit_policy_sha256',a.pre_submit_policy_sha256,'effective_plan_sha256',a.effective_plan_sha256,
   'rules_sha256',a.selected_rules_sha256,'post_submit_policy_sha256',a.selected_post_submit_policy_sha256,
   'post_submit_policy_body',a.selected_post_submit_policy_body,'locked_policy_context_hash',a.locked_policy_context_hash,
   'packet_sha256',a.packet_sha256);
 IF EXISTS(SELECT 1 FROM jsonb_each(actual) WHERE value IS DISTINCT FROM expected->key) THEN
   RAISE EXCEPTION 'source admission locked lineage mismatch' USING ERRCODE='23514';
 END IF;
END $$;

CREATE FUNCTION public.guard_accepted_source_content()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF ROW(OLD.sha256,OLD.byte_count,OLD.media_type) IS DISTINCT FROM ROW(NEW.sha256,NEW.byte_count,NEW.media_type)
    AND EXISTS(SELECT 1 FROM public.artifact_replicas WHERE content_id=OLD.id AND source_operation_id IS NOT NULL) THEN
   RAISE EXCEPTION 'accepted source content is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER accepted_source_content_immutable BEFORE UPDATE ON public.artifact_contents
 FOR EACH ROW EXECUTE FUNCTION public.guard_accepted_source_content();

CREATE FUNCTION public.check_submission_finalization()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE o public.submission_intake_operations%ROWTYPE; a public.submission_bundle_admissions%ROWTYPE;
 d public.submission_dispatches%ROWTYPE; source_id uuid;
BEGIN
 IF TG_TABLE_NAME='submission_intake_operations' THEN
   source_id:=NEW.id;
 ELSE
   IF TG_OP='UPDATE' AND OLD.source_operation_id IS DISTINCT FROM NEW.source_operation_id THEN
     RAISE EXCEPTION 'retained source ownership is immutable' USING ERRCODE='23514';
   END IF;
   source_id:=CASE WHEN TG_OP='DELETE' THEN OLD.source_operation_id ELSE NEW.source_operation_id END;
 END IF;
 IF source_id IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO o FROM public.submission_intake_operations WHERE id=source_id;
 IF o.continuation_lease_id IS NULL THEN
   IF TG_TABLE_NAME<>'submission_intake_operations' THEN
     RAISE EXCEPTION 'retained source has no continuation' USING ERRCODE='23514';
   END IF;
   RETURN NULL;
 END IF;
 PERFORM public.require_submission_acceptance(o);
 IF NOT public.submission_finalization_authority_valid(o,'claim') THEN
   RAISE EXCEPTION 'submission continuation authority mismatch' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='submission_intake_operations' THEN
   IF TG_OP='UPDATE' THEN
     IF (OLD.continuation_generation IS DISTINCT FROM NEW.continuation_generation OR OLD.state IS DISTINCT FROM NEW.state)
        AND o.continuation_expires_at<=clock_timestamp() THEN
       RAISE EXCEPTION 'submission continuation expired before commit' USING ERRCODE='23514';
     END IF;
   END IF;
 END IF;
 IF o.state='finalized' THEN
   SELECT * INTO a FROM public.submission_bundle_admissions WHERE id=o.finalized_admission_id;
   SELECT * INTO d FROM public.submission_dispatches WHERE submission_id=o.finalized_submission_id;
   IF a.id IS NULL OR a.source_operation_id IS DISTINCT FROM o.id OR a.status<>'consumed'
      OR a.consumed_by_submission_id IS DISTINCT FROM o.finalized_submission_id
      OR d.submission_id IS NULL OR d.admission_id IS DISTINCT FROM a.id
      OR d.creation_decision_id IS DISTINCT FROM o.acceptance_decision_id
      OR NOT public.submission_dispatch_valid(d)
      OR NOT public.submission_finalization_authority_valid(o,'commit') THEN
     RAISE EXCEPTION 'submission finalization closure mismatch' USING ERRCODE='23514';
   END IF;
   PERFORM public.require_source_submission_admission(a);
 ELSIF TG_TABLE_NAME<>'submission_intake_operations' THEN
   RAISE EXCEPTION 'retained source requires finalized owner' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER submission_finalization_closure AFTER INSERT OR UPDATE ON public.submission_intake_operations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_finalization();
CREATE CONSTRAINT TRIGGER source_admission_finalization_closure AFTER INSERT OR UPDATE OR DELETE ON public.submission_bundle_admissions
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_finalization();
CREATE CONSTRAINT TRIGGER source_replica_finalization_closure AFTER INSERT OR UPDATE OR DELETE ON public.artifact_replicas
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_finalization();
"""
