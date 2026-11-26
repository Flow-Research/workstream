"""Retain immutable POST identities while inspecting live background ownership."""

from alembic import op
from sqlalchemy import text

revision = "0096_post_renewable_lifetimes"
down_revision = "0095_post_infrastructure_retry"
branch_labels = None
depends_on = None


def _replace(signature: str, *changes: tuple[str, str, int]) -> None:
    """Change only the installed, identified owner routine's expected clauses."""
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    for old, new, count in changes:
        if body.count(old) != count:
            raise RuntimeError("POST lease predecessor shape changed: " + signature)
        body = body.replace(old, new)
    op.execute(body)


def upgrade() -> None:
    """Add bounded renewable liveness, retaining every original claim and receipt."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.checker_runs, public.outbox_events, "
               "public.outbox_delivery_attempts IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(text("""
        SELECT EXISTS(SELECT 1 FROM public.checker_runs
          WHERE status='running' AND worker_lease_expires_at>clock_timestamp())
          OR EXISTS(SELECT 1 FROM public.outbox_events
          WHERE delivery_state='claimed' AND claim_expires_at>clock_timestamp())
    """)).scalar_one():
        raise RuntimeError("drain live POST and OUTBOX claims before renewable-lease migration")

    op.execute("ALTER TABLE public.checker_runs ADD COLUMN worker_lease_live_until timestamptz")
    # Rewrite the newly added projection under the table lock. A row UPDATE
    # would queue old deferred custody checks for retained terminal history;
    # those checks intentionally need not validate against today's schema.
    # The DDL rewrite preserves row values without disabling any trigger.
    op.execute("ALTER TABLE public.checker_runs ALTER COLUMN worker_lease_live_until "
               "TYPE timestamptz USING worker_lease_expires_at")
    op.execute("ALTER TABLE public.checker_runs ADD CONSTRAINT ck_checker_runs_live_lease_shape "
               "CHECK ((worker_lease_id IS NULL AND worker_lease_live_until IS NULL) OR "
               "(worker_lease_id IS NOT NULL AND worker_lease_live_until IS NOT NULL "
               "AND worker_lease_live_until>=worker_lease_expires_at))")

    op.execute("ALTER TABLE public.outbox_events ADD COLUMN claim_live_until timestamptz")
    op.execute("ALTER TABLE public.outbox_events ALTER COLUMN claim_live_until "
               "TYPE timestamptz USING CASE WHEN delivery_state='claimed' "
               "THEN claim_expires_at ELSE NULL END")
    op.execute("ALTER TABLE public.outbox_events ADD CONSTRAINT ck_outbox_events_claim_live_shape "
               "CHECK ((delivery_state='claimed' AND claim_live_until IS NOT NULL "
               "AND claim_live_until>=claim_expires_at) OR "
               "(delivery_state<>'claimed' AND claim_live_until IS NULL))")
    op.execute("DROP INDEX public.ix_outbox_events_expired_claims")
    op.execute("CREATE INDEX ix_outbox_events_expired_claims ON public.outbox_events "
               "(claim_live_until,event_id) WHERE delivery_state='claimed'")

    op.execute("ALTER TABLE public.outbox_delivery_attempts ADD COLUMN claim_live_until timestamptz")
    op.execute("ALTER TABLE public.outbox_delivery_attempts ALTER COLUMN claim_live_until "
               "TYPE timestamptz USING claim_expires_at")
    op.execute("ALTER TABLE public.outbox_delivery_attempts ALTER COLUMN claim_live_until SET NOT NULL")
    op.execute("ALTER TABLE public.outbox_delivery_attempts ADD COLUMN renew_decision_event_id uuid "
               "REFERENCES public.audit_events(id)")
    op.execute("ALTER TABLE public.outbox_delivery_attempts ADD CONSTRAINT "
               "ck_outbox_delivery_attempts_renewed_lease CHECK "
               "((claim_live_until=claim_expires_at AND renew_decision_event_id IS NULL) OR "
               "(claim_live_until>claim_expires_at AND renew_decision_event_id IS NOT NULL))")
    op.execute("ALTER TABLE public.outbox_delivery_attempts DROP CONSTRAINT "
               "ck_outbox_delivery_attempts_outcome")
    op.execute("ALTER TABLE public.outbox_delivery_attempts ADD CONSTRAINT "
               "ck_outbox_delivery_attempts_outcome CHECK (outcome_json IS NULL OR "
               "coalesce(public.outbox_delivery_outcome_valid(outcome_json,outcome_digest,"
               "claimed_at,claim_live_until,invoked_at),false))")

    _replace("public.protect_checker_run_custody()",
        ("'worker_lease_generation','worker_lease_expires_at','execute_evidence_id'",
         "'worker_lease_generation','worker_lease_expires_at','worker_lease_live_until','execute_evidence_id'", 1),
        ("IF NEW.status='running' THEN", _CHECKER_RENEW + "\n        IF NEW.status='running' THEN", 1),
        ("OLD.worker_lease_expires_at > clock_timestamp()",
         "OLD.worker_lease_live_until > clock_timestamp()", 1),
        ("OR NEW.worker_lease_expires_at > clock_timestamp()+interval '1 hour'",
         "OR NEW.worker_lease_expires_at > clock_timestamp()+interval '1 hour'\n"
         "            OR NEW.worker_lease_live_until IS DISTINCT FROM NEW.worker_lease_expires_at", 1),
        ("OLD.worker_lease_expires_at <= clock_timestamp()",
         "OLD.worker_lease_live_until <= clock_timestamp()", 1),
        ("OR NEW.worker_lease_expires_at IS DISTINCT FROM OLD.worker_lease_expires_at",
         "OR NEW.worker_lease_expires_at IS DISTINCT FROM OLD.worker_lease_expires_at\n"
         "            OR NEW.worker_lease_live_until IS DISTINCT FROM OLD.worker_lease_live_until", 1),
        ("IF NEW.worker_lease_id IS NOT NULL OR NEW.worker_lease_expires_at IS NOT NULL",
         "IF NEW.worker_lease_id IS NOT NULL OR NEW.worker_lease_expires_at IS NOT NULL\n"
         "          OR NEW.worker_lease_live_until IS NOT NULL", 1),
        ("ELSIF NEW.worker_lease_id IS NULL OR NEW.worker_lease_expires_at IS NULL",
         "ELSIF NEW.worker_lease_id IS NULL OR NEW.worker_lease_expires_at IS NULL\n"
         "        OR NEW.worker_lease_live_until IS NULL", 1),
    )
    _replace("public.checker_post_submit_abandonment_valid(public.checker_runs,public.checker_runs)",
        ("source.worker_lease_expires_at<=clock_timestamp()",
         "source.worker_lease_live_until<=clock_timestamp()", 1),
        ("ca.claim_expires_at>clock_timestamp()",
         "ca.claim_live_until>clock_timestamp()", 1))
    _replace("public.guard_task_routing_authority()",
        ("OR a.stage IS DISTINCT FROM 'invoked'\n"
         "          OR a.finalize_decision_event_id IS NOT NULL\n"
         "          OR a.claim_expires_at<=clock_timestamp()\n"
         "          OR a.project_id IS DISTINCT FROM NEW.project_id",
         "OR a.stage IS DISTINCT FROM 'invoked'\n"
         "          OR a.finalize_decision_event_id IS NOT NULL\n"
         "          OR a.claim_live_until<=clock_timestamp()\n"
         "          OR a.project_id IS DISTINCT FROM NEW.project_id", 1))
    _replace("public.guard_checker_model_invocation_grant()",
        ("run.worker_lease_expires_at IS DISTINCT FROM NEW.expires_at",
         "run.worker_lease_live_until IS DISTINCT FROM NEW.expires_at", 1),
        ("run.status IS DISTINCT FROM 'running' OR run.phase IS DISTINCT FROM 'post_submission'",
         "run.worker_lease_live_until<=clock_timestamp() OR "
         "run.status IS DISTINCT FROM 'running' OR run.phase IS DISTINCT FROM 'post_submission'", 1))
    _replace("public.guard_checker_trial_evidence()",
        ("run.worker_lease_expires_at<=pg_catalog.clock_timestamp()",
         "run.worker_lease_live_until<=pg_catalog.clock_timestamp()", 2))
    _replace("public.guard_checker_trial_artifact_ancestry()",
        ("run.worker_lease_expires_at<=pg_catalog.clock_timestamp()",
         "run.worker_lease_live_until<=pg_catalog.clock_timestamp()", 1))

    _replace("public.guard_outbox_event()",
        ("new.claim_expires_at := null;", "new.claim_expires_at := null;\n            new.claim_live_until := null;", 1),
        ("or new.last_error_code is distinct from old.last_error_code then\n              raise exception 'outbox claim generation must increment once'",
         "or new.last_error_code is distinct from old.last_error_code\n"
         "               or new.claim_live_until is distinct from new.claim_expires_at then\n"
         "              raise exception 'outbox claim generation must increment once'", 1),
        ("elsif old.delivery_state = 'claimed'\n                and new.delivery_state in",
         _OUTBOX_RENEW + "\n          elsif old.delivery_state = 'claimed'\n                and new.delivery_state in", 1),
        ("or new.last_attempt_at is distinct from old.last_attempt_at then\n              raise exception 'outbox outcome cannot change claim generation'",
         "or new.last_attempt_at is distinct from old.last_attempt_at\n"
         "               or new.claim_live_until is not null then\n"
         "              raise exception 'outbox outcome cannot change claim generation'", 1))
    _replace("public.check_outbox_delivery_projection()",
        ("(e.claim_owner,e.claimed_at,e.claim_expires_at,e.last_attempt_at) is distinct from\n"
         "               (a.claim_owner,a.claimed_at,a.claim_expires_at,a.claimed_at)",
         "(e.claim_owner,e.claimed_at,e.claim_expires_at,e.claim_live_until,e.last_attempt_at) is distinct from\n"
         "               (a.claim_owner,a.claimed_at,a.claim_expires_at,a.claim_live_until,a.claimed_at)", 1))
    _replace("public.outbox_dispatch_authority_digest(public.outbox_delivery_attempts,text)",
        ("'outcome_digest',case when phase='finalize' then a.outcome_digest else null end\n              )",
         "'outcome_digest',case when phase='finalize' then a.outcome_digest else null end\n"
         "              ) || case when phase='renew' then\n"
         "                jsonb_build_object('live_until',outbox_dispatch_utc(a.claim_live_until))\n"
         "                else '{}'::jsonb end", 1))
    _replace("public.require_outbox_phase_authority()",
        ("array['claim','invoke','finalize']", "array['claim','invoke','renew','finalize']", 1),
        ("if previous_id is not null and decision_id is distinct from previous_id then",
         "if phase<>'renew' and previous_id is not null "
         "and decision_id is distinct from previous_id then", 1),
        ("if previous_id is null and (actor.status is distinct from 'active' or link.status is distinct from 'active') then",
         "if (previous_id is null or decision_id is distinct from previous_id) "
         "and (actor.status is distinct from 'active' or link.status is distinct from 'active') then", 1))
    op.execute(_OUTBOX_ATTEMPT_RENEW_GUARD)
    op.execute("CREATE TRIGGER outbox_attempt_renewal_guard BEFORE UPDATE OF "
               "claim_live_until,renew_decision_event_id ON public.outbox_delivery_attempts "
               "FOR EACH ROW EXECUTE FUNCTION public.guard_outbox_attempt_renewal()")


def downgrade() -> None:
    """Retained running lease history cannot be truncated by a downgrade."""
    raise RuntimeError("renewable POST custody is forward-only")


_CHECKER_RENEW = """
        IF OLD.status='running' AND NEW.status='running'
          AND NEW.worker_lease_live_until IS DISTINCT FROM OLD.worker_lease_live_until THEN
          IF (to_jsonb(NEW)-'worker_lease_live_until') IS DISTINCT FROM
             (to_jsonb(OLD)-'worker_lease_live_until')
            OR NEW.worker_lease_live_until IS NULL
            OR OLD.worker_lease_live_until<=clock_timestamp()
            OR NEW.worker_lease_live_until<=OLD.worker_lease_live_until
            OR NEW.worker_lease_live_until>clock_timestamp()+interval '3 hours'
            OR NOT public.checker_post_submit_receipt_valid(OLD,'execute',true)
            OR NOT EXISTS (SELECT 1 FROM public.checker_submission_fences f
              WHERE f.submission_id=OLD.submission_id AND f.current_run_id=OLD.id)
          THEN RAISE EXCEPTION 'checker renewal custody is invalid' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;"""


_OUTBOX_RENEW = """elsif old.delivery_state = 'claimed' and new.delivery_state = 'claimed' then
            if (to_jsonb(new)-'claim_live_until') is distinct from
               (to_jsonb(old)-'claim_live_until')
               or old.event_type not in ('PostSubmissionEvaluationRequested',
                 'PostSubmissionDeliveryReconciliationRequested')
               or old.event_version<>1
               or old.claim_live_until<=clock_timestamp()
               or new.claim_live_until<=old.claim_live_until
               or new.claim_live_until>clock_timestamp()+interval '3 hours' then
              raise exception 'outbox renewal custody is invalid' using errcode='23514';
            end if;"""


_OUTBOX_ATTEMPT_RENEW_GUARD = """
CREATE FUNCTION public.guard_outbox_attempt_renewal() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE event public.outbox_events%ROWTYPE;
BEGIN
  SELECT * INTO event FROM public.outbox_events WHERE event_id=OLD.event_id FOR UPDATE;
  IF OLD.stage IS DISTINCT FROM 'invoked' OR NEW.stage IS DISTINCT FROM 'invoked'
    OR (to_jsonb(NEW)-ARRAY['claim_live_until','renew_decision_event_id']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['claim_live_until','renew_decision_event_id'])
    OR OLD.claim_live_until<=clock_timestamp()
    OR NEW.claim_live_until<=OLD.claim_live_until
    OR NEW.claim_live_until>clock_timestamp()+interval '3 hours'
    OR NEW.renew_decision_event_id IS NULL
    OR NEW.renew_decision_event_id IS NOT DISTINCT FROM OLD.renew_decision_event_id
    OR event.delivery_state IS DISTINCT FROM 'claimed'
    OR event.claim_generation IS DISTINCT FROM OLD.claim_generation
    OR event.claim_live_until IS DISTINCT FROM NEW.claim_live_until
  THEN RAISE EXCEPTION 'outbox attempt renewal custody is invalid' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$
"""
