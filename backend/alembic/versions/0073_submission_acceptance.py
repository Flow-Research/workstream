"""Bind accepted source custody to TASK, immutable PRE, AUTH and finalization outbox."""
import re

from alembic import op
from sqlalchemy import text

revision = "0073_submission_acceptance"
down_revision = "0072_pre_invocation_receipts"
branch_labels = None
depends_on = None

_ACCEPTED = {
    "accepted_at": "timestamptz", "acceptance_decision_id": "uuid",
    "selected_pre_submit_run_id": "uuid", "selected_pre_submit_request_sha256": "varchar(71)",
    "selected_pre_submit_terminal_sha256": "varchar(71)", "accepted_source_sha256": "varchar(71)",
    "accepted_manifest_sha256": "varchar(71)", "accepted_context": "jsonb",
    "accepted_context_sha256": "varchar(71)", "acceptance_receipt": "jsonb",
    "acceptance_receipt_sha256": "varchar(71)", "finalization_event_id": "uuid",
}


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("acceptance predecessor shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.workstream_tasks, public.submission_intake_operations, "
               "public.selected_pre_submit_runs, public.outbox_events IN ACCESS EXCLUSIVE MODE")
    for name, sql_type in _ACCEPTED.items():
        op.execute(f"ALTER TABLE public.submission_intake_operations ADD COLUMN {name} {sql_type}")
    for name, target, label in (
        ("acceptance_decision_id", "audit_events(id)", "acceptance_decision"),
        ("selected_pre_submit_run_id", "selected_pre_submit_runs(id)", "accepted_pre_run"),
        ("finalization_event_id", "outbox_events(event_id)", "finalization_event"),
    ):
        op.execute(f"ALTER TABLE public.submission_intake_operations ADD CONSTRAINT fk_intake_{label} "
                   f"FOREIGN KEY ({name}) REFERENCES public.{target} DEFERRABLE INITIALLY DEFERRED")
        op.execute(f"ALTER TABLE public.submission_intake_operations ADD CONSTRAINT uq_intake_{label} UNIQUE ({name})")
    conditions = {
        "foreground_state": "state in ('receiving','pre_checking','finalization_pending','rejected','failed','abandoned','cancelled')",
        "pre_requires_source": "state not in ('pre_checking','finalization_pending') or sealed_at is not null",
        "terminal_shape": "(state in ('receiving','pre_checking','finalization_pending') and terminal_at is null and failure_code is null) or "
                          "(state in ('rejected','failed','abandoned','cancelled') and terminal_at is not null and failure_code is not null)",
    }
    for name, condition in conditions.items():
        op.execute(f"ALTER TABLE public.submission_intake_operations DROP CONSTRAINT ck_submission_intake_operations_{name}")
        op.execute(f"ALTER TABLE public.submission_intake_operations ADD CONSTRAINT ck_submission_intake_operations_{name} CHECK ({condition})")
    present = " AND ".join(f"{name} IS NOT NULL" for name in _ACCEPTED)
    absent = " AND ".join(f"{name} IS NULL" for name in _ACCEPTED)
    op.execute("ALTER TABLE public.submission_intake_operations ADD CONSTRAINT "
               "ck_submission_intake_operations_acceptance_shape CHECK "
               f"((state='finalization_pending' AND {present}) OR (state<>'finalization_pending' AND {absent}))")
    op.execute("DROP INDEX public.uq_submission_intake_active_task")
    op.execute("CREATE UNIQUE INDEX uq_submission_intake_active_task ON public.submission_intake_operations(task_id) "
               "WHERE state IN ('receiving','pre_checking','finalization_pending')")
    excluded = ",".join("'" + name + "'" for name in ("state", *_ACCEPTED))
    anchor = "  IF (to_jsonb(NEW)-ARRAY['state','lease_generation','lease_expires_at','raw_sha256',"
    handoff = f"""  IF OLD.state='pre_checking' AND NEW.state='finalization_pending' THEN
    IF (to_jsonb(NEW)-ARRAY[{excluded}]) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY[{excluded}])
       OR OLD.lease_expires_at<=clock_timestamp() OR OLD.pre_deadline_at<=clock_timestamp()
       OR NOT isfinite(NEW.accepted_at) OR NEW.accepted_at<OLD.sealed_at
       OR NEW.accepted_at>clock_timestamp() THEN
      RAISE EXCEPTION 'invalid accepted intake transition' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
"""
    _replace("public.guard_submission_intake_mutation()", anchor, handoff + anchor)
    _replace("public.check_submission_intake_custody()",
             "WHERE task_id=task_key AND state IN ('receiving','pre_checking');",
             "WHERE task_id=task_key AND state IN ('receiving','pre_checking','finalization_pending');")
    _replace("public.check_submission_intake_custody()",
             "OR t.status IS DISTINCT FROM o.eligible_task_status",
             "OR t.status IS DISTINCT FROM (CASE WHEN o.state='finalization_pending' THEN 'evaluation_pending' ELSE o.eligible_task_status END)")
    for statement in re.split(r"\n(?=CREATE (?:FUNCTION|CONSTRAINT TRIGGER))", _CLOSURE):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_CLOSURE = r"""
CREATE FUNCTION public.submission_acceptance_context(o public.submission_intake_operations, r public.selected_pre_submit_runs)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT jsonb_build_object(
   'schema_version','workstream.submission_acceptance_context.v1','operation_id',o.id::text,
   'metadata_sha256',o.metadata_sha256,'locked_context_sha256',o.locked_context_sha256,
   'selected_pre_submit_run_id',r.id::text,'selected_pre_submit_request_sha256',r.request_digest,
   'selected_pre_submit_terminal_sha256',r.terminal_digest,'source_sha256',r.request_json->>'source_sha256',
   'semantic_manifest_sha256',r.terminal_json->'execution'->>'manifest_sha256',
   'predecessor_submission_id',r.request_json->'admission_lineage'->'predecessor_submission_id',
   'predecessor_submission_version',r.request_json->'admission_lineage'->'predecessor_submission_version',
   'checker_remediation_manifest_id',r.request_json->'admission_lineage'->'checker_remediation_manifest_id')
$$;

CREATE FUNCTION public.submission_acceptance_results(execution jsonb)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(jsonb_agg(value ORDER BY section, ordinality),'[]'::jsonb) FROM (
  SELECT 1 AS section, ordinality, jsonb_build_object('source','workstream_default',
    'check_id',value->'check_id','status',value->'status','failure_code',value->'failure_code',
    'finding_count',value->'finding_count') AS value
  FROM jsonb_array_elements(execution->'workstream_default'->'checks') WITH ORDINALITY
  UNION ALL
  SELECT 2, ordinality, jsonb_build_object('source','workstream_default','status','warning','warning_code',value->'code')
  FROM jsonb_array_elements(execution->'workstream_default'->'warnings') WITH ORDINALITY
  UNION ALL
  SELECT 3, ordinality, jsonb_build_object('source','project_external_checker',
    'requirement_id',value->'requirement_id','registry_entry_id',value->'registry_entry_id',
    'registry_entry_digest',value->'registry_entry_digest','status',value->'result'->'verdict',
    'findings',value->'result'->'findings')
  FROM jsonb_array_elements(execution->'external_members') WITH ORDINALITY
 ) projected
$$;

CREATE FUNCTION public.require_submission_acceptance(o public.submission_intake_operations)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r public.selected_pre_submit_runs%ROWTYPE; a public.audit_events%ROWTYPE;
 e public.outbox_events%ROWTYPE; context jsonb; resource jsonb; receipt jsonb; payload jsonb;
BEGIN
 SELECT * INTO r FROM public.selected_pre_submit_runs WHERE id=o.selected_pre_submit_run_id;
 IF r.id IS NULL OR r.source_operation_id IS DISTINCT FROM o.id OR r.status<>'completed' OR r.eligible IS DISTINCT FROM true
    OR r.execute_evidence_id IS NULL OR r.finalize_evidence_id IS NULL
    OR r.request_json->>'schema_version' IS DISTINCT FROM 'workstream.selected_pre_submit_reservation.v2'
    OR r.terminal_json->>'schema_version' IS DISTINCT FROM 'workstream.selected_pre_submit_terminal.v3'
    OR r.request_digest IS DISTINCT FROM o.selected_pre_submit_request_sha256
    OR r.terminal_digest IS DISTINCT FROM o.selected_pre_submit_terminal_sha256
    OR r.request_json->>'source_sha256' IS DISTINCT FROM o.accepted_source_sha256
    OR r.terminal_json->'execution'->>'manifest_sha256' IS DISTINCT FROM o.accepted_manifest_sha256
    OR r.actor_profile_id IS DISTINCT FROM o.actor_profile_id OR r.identity_link_id IS DISTINCT FROM o.identity_link_id
    OR r.task_id IS DISTINCT FROM o.task_id OR r.project_id IS DISTINCT FROM o.project_id
    OR r.assignment_id IS DISTINCT FROM o.assignment_id OR r.idempotency_key IS DISTINCT FROM o.idempotency_key
    OR r.request_json->>'foreground_lease_id' IS DISTINCT FROM o.lease_id::text
    OR r.request_json->'foreground_lease_generation' IS DISTINCT FROM to_jsonb(o.lease_generation)
    OR r.request_json->>'metadata_sha256' IS DISTINCT FROM o.metadata_sha256
    OR r.request_json->>'locked_context_sha256' IS DISTINCT FROM o.locked_context_sha256
    OR r.completed_at>o.accepted_at OR o.accepted_at>=o.lease_expires_at OR o.accepted_at>=o.pre_deadline_at
 THEN RAISE EXCEPTION 'accepted PRE custody mismatch' USING ERRCODE='23514'; END IF;
 PERFORM public.require_selected_pre_invocation(r);
 context:=public.submission_acceptance_context(o,r);
 IF o.accepted_context IS DISTINCT FROM context
    OR o.accepted_context_sha256 IS DISTINCT FROM public.external_checker_registry_digest(context)
 THEN RAISE EXCEPTION 'accepted context mismatch' USING ERRCODE='23514'; END IF;
 receipt:=jsonb_build_object('operation_id',o.id::text,'task_id',o.task_id::text,'assignment_id',o.assignment_id::text,
   'status','accepted','accepted_at',replace(public.outbox_dispatch_utc(o.accepted_at),'+00:00','Z'),
   'task_status_at_acceptance','evaluation_pending','processing_stage_at_acceptance','finalization_pending',
   'replayed',false,'pre_submission_results',public.submission_acceptance_results(r.terminal_json->'execution'));
 IF o.acceptance_receipt IS DISTINCT FROM receipt
    OR o.acceptance_receipt_sha256 IS DISTINCT FROM public.external_checker_registry_digest(receipt)
 THEN RAISE EXCEPTION 'accepted receipt mismatch' USING ERRCODE='23514'; END IF;
 resource:=jsonb_strip_nulls(jsonb_build_object(
   'resource_type','submission_intake_acceptance','resource_id',o.id::text,'operation_id',o.id::text,
   'scope_project_id',o.project_id::text,'task_id',o.task_id::text,'assignment_id',o.assignment_id::text,
   'actor_profile_id',o.actor_profile_id::text,'identity_link_id',o.identity_link_id::text,
   'idempotency_key',o.idempotency_key::text,'metadata_sha256',o.metadata_sha256,
   'locked_context_sha256',o.locked_context_sha256,'task_status',o.eligible_task_status,
   'foreground_lease_id',o.lease_id::text,'foreground_lease_generation',o.lease_generation,
   'selected_pre_submit_run_id',r.id::text,'selected_pre_submit_request_sha256',r.request_digest,
   'selected_pre_submit_terminal_sha256',r.terminal_digest,'source_sha256',o.accepted_source_sha256,
   'semantic_manifest_sha256',o.accepted_manifest_sha256,'accepted_context_sha256',o.accepted_context_sha256,
   'receipt_sha256',o.acceptance_receipt_sha256,'accepted_at',receipt->'accepted_at',
   'predecessor_submission_id',context->'predecessor_submission_id',
   'predecessor_submission_version',context->'predecessor_submission_version',
   'checker_remediation_manifest_id',context->'checker_remediation_manifest_id'));
 SELECT * INTO a FROM public.audit_events WHERE id=o.acceptance_decision_id;
 IF a.id IS NULL OR a.event_domain IS DISTINCT FROM 'authority' OR a.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed'
    OR a.actor_ref_kind IS DISTINCT FROM 'actor_profile' OR a.actor_id IS DISTINCT FROM o.actor_profile_id::text
    OR a.action_id IS DISTINCT FROM 'submission.create' OR a.permission_id IS DISTINCT FROM 'submission.create'
    OR a.project_id IS DISTINCT FROM o.project_id OR a.resource_type IS DISTINCT FROM 'submission_operation'
    OR a.resource_id IS DISTINCT FROM o.id::text OR a.target_ref_kind IS DISTINCT FROM 'project'
    OR a.target_ref_id IS DISTINCT FROM o.project_id::text OR a.denial_code IS NOT NULL
    OR a.matched_grant_id IS NULL OR a.request_id IS NULL OR a.correlation_id IS NULL
    OR a.after_facts::jsonb IS DISTINCT FROM jsonb_build_object('allowed',true,'resource_context_digest',
       public.external_checker_registry_digest(jsonb_build_object('resource_context',resource)))
 THEN RAISE EXCEPTION 'accepted authority mismatch' USING ERRCODE='23514'; END IF;
 payload:=jsonb_build_object('operation_id',o.id::text,'project_id',o.project_id::text,'task_id',o.task_id::text,
   'acceptance_decision_id',o.acceptance_decision_id::text,'accepted_context_sha256',o.accepted_context_sha256,
   'receipt_sha256',o.acceptance_receipt_sha256);
 SELECT * INTO e FROM public.outbox_events WHERE event_id=o.finalization_event_id;
 IF e.event_id IS NULL OR e.event_type<>'SubmissionFinalizationRequested' OR e.event_version<>1
    OR e.aggregate_type<>'submission_operation' OR e.aggregate_id IS DISTINCT FROM o.id
    OR e.project_id IS DISTINCT FROM o.project_id OR e.idempotency_key IS DISTINCT FROM 'submission-finalization:'||o.id::text
    OR e.payload IS DISTINCT FROM payload OR e.correlation_id IS DISTINCT FROM o.id::text
    OR e.causation_event_id IS NOT NULL
 THEN RAISE EXCEPTION 'accepted finalization event mismatch' USING ERRCODE='23514'; END IF;
END $$;

CREATE FUNCTION public.require_submission_acceptance_current(o public.submission_intake_operations)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE p public.task_revision_preparations%ROWTYPE;
BEGIN
 IF o.eligible_task_status='in_progress' THEN
   IF o.accepted_context->'predecessor_submission_id' IS DISTINCT FROM 'null'::jsonb
      OR o.accepted_context->'predecessor_submission_version' IS DISTINCT FROM 'null'::jsonb
      OR o.accepted_context->'checker_remediation_manifest_id' IS DISTINCT FROM 'null'::jsonb
      OR EXISTS(SELECT 1 FROM public.submissions WHERE task_assignment_id=o.assignment_id) THEN
     RAISE EXCEPTION 'initial acceptance predecessor mismatch' USING ERRCODE='23514';
   END IF;
 ELSE
   SELECT * INTO p FROM public.task_revision_preparations
     WHERE id=(o.command_metadata->>'revision_preparation_id')::uuid;
   IF p.id IS NULL OR p.task_id IS DISTINCT FROM o.task_id OR p.assignment_id IS DISTINCT FROM o.assignment_id
      OR p.contributor_id IS DISTINCT FROM o.actor_profile_id
      OR p.preparation_sha256 IS DISTINCT FROM o.command_metadata->>'revision_preparation_sha256'
      OR p.submission_id::text IS DISTINCT FROM o.accepted_context->>'predecessor_submission_id'
      OR to_jsonb(p.source_submission_version) IS DISTINCT FROM o.accepted_context->'predecessor_submission_version'
      OR p.routing_manifest_id::text IS DISTINCT FROM o.accepted_context->>'checker_remediation_manifest_id'
      OR p.blocked_reason IS NOT NULL OR p.outcome NOT IN ('kept','rebased')
      OR p.deadline_at IS NULL OR p.deadline_at<=clock_timestamp()
      OR p.next_revision_round>p.max_revision_rounds
      OR EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE predecessor_id=p.id)
      OR EXISTS(SELECT 1 FROM public.submissions WHERE task_id=o.task_id AND version>p.source_submission_version) THEN
     RAISE EXCEPTION 'revision acceptance is no longer eligible' USING ERRCODE='23514';
   END IF;
 END IF;
END $$;

CREATE FUNCTION public.check_submission_acceptance()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE o public.submission_intake_operations%ROWTYPE;
BEGIN
 IF TG_TABLE_NAME='outbox_events' THEN
   IF NEW.event_type<>'SubmissionFinalizationRequested' THEN RETURN NULL; END IF;
   SELECT * INTO o FROM public.submission_intake_operations WHERE finalization_event_id=NEW.event_id;
   IF o.id IS NULL OR o.state<>'finalization_pending' THEN
     RAISE EXCEPTION 'finalization event has no accepted owner' USING ERRCODE='23514';
   END IF;
 ELSE
   IF NEW.state<>'finalization_pending' THEN RETURN NULL; END IF;
   SELECT * INTO o FROM public.submission_intake_operations WHERE id=NEW.id;
   IF TG_OP='UPDATE' AND OLD.state<>'finalization_pending'
      AND (o.lease_expires_at<=clock_timestamp() OR o.pre_deadline_at<=clock_timestamp()) THEN
     RAISE EXCEPTION 'acceptance expired before commit' USING ERRCODE='23514';
   END IF;
   IF TG_OP='UPDATE' AND OLD.state<>'finalization_pending' THEN
     PERFORM public.require_submission_acceptance_current(o);
   END IF;
 END IF;
 PERFORM public.require_submission_acceptance(o);
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER submission_acceptance_closure AFTER INSERT OR UPDATE ON public.submission_intake_operations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_acceptance();
CREATE CONSTRAINT TRIGGER submission_finalization_event_closure AFTER INSERT OR UPDATE ON public.outbox_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_submission_acceptance();
"""
