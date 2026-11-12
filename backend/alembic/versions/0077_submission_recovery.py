"""Bind one finalization recovery child to accepted custody and Operator evidence."""

from alembic import op
from sqlalchemy import text

revision = "0077_submission_recovery"
down_revision = "0076_submission_delivery_retry"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.outbox_events IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""CREATE UNIQUE INDEX uq_submission_finalization_recovery_original
        ON public.outbox_events(causation_event_id)
        WHERE event_type='SubmissionFinalizationRecoveryRequested'""")
    op.execute(r"""
CREATE FUNCTION public.require_submission_recovery_child() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE o public.submission_intake_operations%ROWTYPE;
        e public.outbox_events%ROWTYPE;
        a public.outbox_delivery_attempts%ROWTYPE;
        d public.audit_events%ROWTYPE;
        p jsonb; c jsonb; s jsonb; authority jsonb; resource jsonb; expected_source jsonb;
        expected_command jsonb; expected_authority jsonb; digest text;
BEGIN
 IF NEW.event_type<>'SubmissionFinalizationRecoveryRequested' THEN RETURN NEW; END IF;
 p := NEW.payload; c := p->'command'; s := p->'source'; authority := p->'authority';
 SELECT * INTO o FROM public.submission_intake_operations WHERE id=(s->>'operation_id')::uuid;
 IF NOT FOUND OR o.state<>'finalization_pending' THEN
   RAISE EXCEPTION 'recovery requires accepted pending operation' USING ERRCODE='23514'; END IF;
 PERFORM public.require_submission_acceptance(o);
 SELECT * INTO e FROM public.outbox_events WHERE event_id=o.finalization_event_id;
 SELECT * INTO a FROM public.outbox_delivery_attempts
   WHERE event_id=e.event_id AND claim_generation=e.claim_generation;
 IF e.event_type IS DISTINCT FROM 'SubmissionFinalizationRequested' OR e.event_version<>1
   OR e.delivery_state IS DISTINCT FROM 'dead_letter'
   OR e.last_error_code IS DISTINCT FROM 'INVOKE_OUTCOME_UNKNOWN'
   OR a.stage IS DISTINCT FROM 'completed'
   OR (a.outcome_json::jsonb->>'invocation_unknown') IS DISTINCT FROM 'true'
   OR NEW.event_version<>1 OR NEW.aggregate_type<>'outbox_delivery'
   OR NEW.aggregate_id IS DISTINCT FROM e.event_id OR NEW.causation_event_id IS DISTINCT FROM e.event_id
   OR NEW.project_id IS DISTINCT FROM o.project_id
   OR NEW.idempotency_key IS DISTINCT FROM 'submission-finalization-recovery:'||e.event_id::text
   OR NEW.correlation_id IS DISTINCT FROM c->>'request_id' THEN
   RAISE EXCEPTION 'recovery original delivery differs' USING ERRCODE='23514'; END IF;
 expected_source := jsonb_build_object('operation_id',o.id::text,'project_id',o.project_id::text,
   'task_id',o.task_id::text,'original_event_id',e.event_id::text,
   'original_claim_generation',e.claim_generation,'original_payload_digest',e.payload_digest,
   'acceptance_receipt_sha256',o.acceptance_receipt_sha256);
 expected_command := jsonb_build_object('operation_id',o.id::text,'project_id',o.project_id::text,
   'actor_profile_id',(c->>'actor_profile_id')::uuid::text,
   'request_id',(c->>'request_id')::uuid::text,'reason',c->>'reason');
 IF s IS DISTINCT FROM expected_source OR c IS DISTINCT FROM expected_command
   OR c->>'reason' IS NULL OR length(c->>'reason') NOT BETWEEN 1 AND 500
   OR c->>'reason' IS DISTINCT FROM btrim(c->>'reason',
       U&'\0009\000a\000b\000c\000d\001c\001d\001e\001f\0020\0085\00a0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200a\2028\2029\202f\205f\3000')
   OR (c->>'reason') ~ ('['||chr(1)||'-'||chr(31)||chr(127)||']') THEN
   RAISE EXCEPTION 'recovery exact source or command differs' USING ERRCODE='23514'; END IF;
 resource := jsonb_build_object('resource_type','submission_operation','resource_id',o.id::text,
   'scope_project_id',o.project_id::text,'identity_link_id',(authority->>'identity_link_id')::uuid::text,
   'command',c,'source',s);
 digest := public.external_checker_registry_digest(jsonb_build_object('resource_context',resource));
 expected_authority := jsonb_build_object('decision_id',(authority->>'decision_id')::uuid::text,
   'identity_link_id',(authority->>'identity_link_id')::uuid::text,'resource_digest',digest);
 IF NEW.payload_digest IS DISTINCT FROM public.external_checker_registry_digest(p) THEN
   RAISE EXCEPTION 'recovery payload digest differs' USING ERRCODE='23514'; END IF;
 IF authority IS DISTINCT FROM expected_authority OR p IS DISTINCT FROM
   jsonb_build_object('command',c,'source',s,'authority',authority) THEN
   RAISE EXCEPTION 'recovery authority shape differs' USING ERRCODE='23514'; END IF;
 SELECT * INTO d FROM public.audit_events WHERE id=(authority->>'decision_id')::uuid;
 IF NOT FOUND OR d.event_domain IS DISTINCT FROM 'authority'
   OR d.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed'
   OR d.actor_ref_kind IS DISTINCT FROM 'actor_profile'
   OR d.action_id IS DISTINCT FROM 'operations.submission_gate.repair'
   OR d.permission_id IS DISTINCT FROM 'operations.submission_gate.repair'
   OR d.actor_id IS DISTINCT FROM c->>'actor_profile_id'
   OR d.project_id IS DISTINCT FROM o.project_id
   OR d.resource_type IS DISTINCT FROM 'submission_operation' OR d.resource_id IS DISTINCT FROM o.id::text
   OR d.target_ref_kind IS DISTINCT FROM 'submission_operation' OR d.target_ref_id IS DISTINCT FROM o.id::text
   OR d.request_id::text IS DISTINCT FROM c->>'request_id'
   OR d.correlation_id::text IS DISTINCT FROM c->>'request_id' OR d.denial_code IS NOT NULL
   OR d.after_facts::jsonb IS DISTINCT FROM jsonb_build_object('allowed',true,'resource_context_digest',digest)
   OR NOT EXISTS (SELECT 1 FROM public.actor_profiles actor
     WHERE actor.id=(c->>'actor_profile_id')::uuid AND actor.actor_kind='human' AND actor.status='active')
   OR NOT EXISTS (SELECT 1 FROM public.admin_role_grants g
     WHERE g.id::text=d.matched_grant_id AND g.target_actor_profile_id=(c->>'actor_profile_id')::uuid
       AND g.role='operator' AND g.scope_type='system' AND g.scope_project_id IS NULL AND g.status='active')
   OR NOT EXISTS (SELECT 1 FROM public.actor_identity_links link
     WHERE link.id=(authority->>'identity_link_id')::uuid
       AND link.actor_profile_id=(c->>'actor_profile_id')::uuid AND link.status='active') THEN
   RAISE EXCEPTION 'recovery retained Operator cause differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
""")
    op.execute("""CREATE TRIGGER submission_recovery_child_custody BEFORE INSERT ON public.outbox_events
 FOR EACH ROW EXECUTE FUNCTION public.require_submission_recovery_child();
""")
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef('public.check_outbox_delivery_projection()'::regprocedure)"
    )).scalar_one()
    old = "'TaskRevisionExpired','SubmissionFinalizationRequested')"
    new = "'TaskRevisionExpired','SubmissionFinalizationRequested','SubmissionFinalizationRecoveryRequested')"
    if body.count(old) != 1:
        raise RuntimeError("submission recovery retry predecessor shape changed")
    op.execute(body.replace(old, new))


def downgrade():
    raise RuntimeError("Retained finalization recovery cannot be downgraded")
