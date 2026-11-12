"""Close exhausted assignments and preserve paused revision allowances."""

from alembic import op
from scripts.schema_baseline_sql import split_sql_statements
import sqlalchemy as sa


revision = "0048_revision_exhaustion"
down_revision = "0047_revision_recovery"
branch_labels = None
depends_on = None


def _replace(signature: str, old: str, new: str) -> None:
    """Refuse migration against an unexpected predecessor function body."""
    body = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("revision exhaustion predecessor changed: " + signature)
    op.execute(body.replace(old, new))


def _execute_sql(sql: str) -> None:
    """Execute separately parsed SQL commands through the async PostgreSQL driver."""
    for statement in split_sql_statements(sql):
        op.execute(statement)


EXHAUSTION_TRANSITION_GUARDS = """
CREATE FUNCTION public.guard_task_revision_exhaustion_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_TABLE_NAME='task_assignments' THEN
  IF OLD.status='revision_exhausted' THEN
   RAISE EXCEPTION 'exhausted assignment is immutable'
    USING ERRCODE='23514', CONSTRAINT='ck_revision_exhausted_assignment_immutable';
  ELSIF OLD.status='revision_expired' THEN
   RAISE EXCEPTION 'expired assignment is immutable'
    USING ERRCODE='23514', CONSTRAINT='ck_revision_expired_assignment_immutable';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 END IF;
 IF TG_TABLE_NAME='workstream_tasks' AND OLD.status='evaluation_pending' AND NEW.status='ready' THEN
  IF NEW.assigned_to IS NOT NULL OR NOT EXISTS(SELECT 1 FROM public.task_revision_exhaustions e
    WHERE e.task_id=OLD.id AND e.project_id=OLD.project_id AND e.contributor_id=OLD.assigned_to
      AND e.creation_xid=pg_current_xact_id()::text)
  THEN RAISE EXCEPTION 'revision exhaustion receipt required' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='task_assignments' AND NEW.status='revision_exhausted' THEN
  IF OLD.status<>'active' OR OLD.released_at IS NOT NULL OR NEW.released_at IS NULL
    OR NOT EXISTS(SELECT 1 FROM public.task_revision_exhaustions e
      WHERE e.assignment_id=OLD.id AND e.task_id=OLD.task_id AND e.contributor_id=OLD.contributor_id
        AND e.exhausted_at=NEW.released_at AND e.creation_xid=pg_current_xact_id()::text)
  THEN RAISE EXCEPTION 'revision exhaustion receipt required' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER revision_exhaustion_task_transition BEFORE UPDATE ON public.workstream_tasks
 FOR EACH ROW EXECUTE FUNCTION public.guard_task_revision_exhaustion_transition();
CREATE TRIGGER a_revision_terminal_assignment_immutable BEFORE UPDATE OR DELETE ON public.task_assignments
 FOR EACH ROW EXECUTE FUNCTION public.guard_task_revision_exhaustion_transition();
    """

def upgrade() -> None:
    """Add new-write custody without changing retained business facts."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("ALTER TABLE public.revision_policies DROP CONSTRAINT "
               "ck_revision_policies_revision_policy_semantics_shape")
    _execute_sql("""ALTER TABLE public.revision_policies ADD CONSTRAINT
      ck_revision_policies_revision_policy_semantics_shape CHECK (
        semantics_status='legacy_incomplete' OR
        (max_revision_rounds >= 0 AND revision_deadline_hours > 0))""")
    _execute_sql("""
ALTER TABLE public.task_revision_preparations DROP CONSTRAINT ck_task_revision_preparations_positive_rounds;
ALTER TABLE public.task_revision_preparations ADD CONSTRAINT ck_task_revision_preparations_positive_rounds
 CHECK (sequence > 0 AND source_submission_version > 0 AND next_revision_round > 0 AND max_revision_rounds >= 0);
    """)
    _create_exhaustion_receipts()
    _route_exhaustion()
    _retained_exhaustion()
    _allow_reclaim()
    _paused_revision_clock()
    _retained_blocked_clock()


def _create_exhaustion_receipts() -> None:
    """Retain source, policy and routing authority without a phantom window."""
    _execute_sql("""
CREATE TABLE public.task_revision_exhaustions (
 id uuid NOT NULL CONSTRAINT pk_task_revision_exhaustions PRIMARY KEY,
 project_id uuid NOT NULL, task_id uuid NOT NULL, assignment_id uuid NOT NULL,
 contributor_id uuid NOT NULL, source_submission_id uuid NOT NULL,
 routing_manifest_id uuid NOT NULL,
 revision_round integer NOT NULL, max_revision_rounds integer NOT NULL,
 revision_policy_id uuid NOT NULL, revision_policy_generation integer NOT NULL,
 revision_policy_hash varchar(71) NOT NULL,
 exhausted_at timestamptz NOT NULL,
 authorization_decision_id uuid NOT NULL, audit_event_id uuid NOT NULL,
 outcome_event_id uuid NOT NULL,
 recovery_authority_context jsonb,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 creation_xid varchar(20) NOT NULL DEFAULT pg_current_xact_id()::text,
 CONSTRAINT ck_task_revision_exhaustions_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_task_revision_exhaustions_rounds CHECK (
  revision_round>=0 AND max_revision_rounds>=0 AND revision_round=max_revision_rounds),
 CONSTRAINT ck_task_revision_exhaustions_policy CHECK (
  revision_policy_generation>0 AND revision_policy_hash ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_task_revision_exhaustions_recovery_authority_shape CHECK (
  recovery_authority_context IS NULL OR jsonb_typeof(recovery_authority_context)='object'),
 CONSTRAINT fk_revision_exhaustion_task_project FOREIGN KEY(task_id,project_id)
  REFERENCES public.workstream_tasks(id,project_id),
 CONSTRAINT fk_revision_exhaustion_assignment FOREIGN KEY(assignment_id,task_id,contributor_id)
  REFERENCES public.task_assignments(id,task_id,contributor_id),
 CONSTRAINT uq_revision_exhaustion_manifest UNIQUE(routing_manifest_id),
 CONSTRAINT uq_revision_exhaustion_assignment UNIQUE(assignment_id),
 CONSTRAINT uq_revision_exhaustion_submission UNIQUE(source_submission_id),
 CONSTRAINT uq_revision_exhaustion_audit UNIQUE(audit_event_id),
 CONSTRAINT uq_revision_exhaustion_outcome UNIQUE(outcome_event_id),
 CONSTRAINT fk_task_revision_exhaustions_source_submission_id_submissions
  FOREIGN KEY(source_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_exhaustions_routing_manifest_id_task_p_b41c
  FOREIGN KEY(routing_manifest_id) REFERENCES public.task_post_submit_routing_manifests(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_exhaustions_revision_policy_id_revisio_e046
  FOREIGN KEY(revision_policy_id) REFERENCES public.revision_policies(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_exhaustions_authorization_decision_id__58a8
  FOREIGN KEY(authorization_decision_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_exhaustions_audit_event_id_audit_events
  FOREIGN KEY(audit_event_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
 CONSTRAINT fk_task_revision_exhaustions_outcome_event_id_outbox_events
  FOREIGN KEY(outcome_event_id) REFERENCES public.outbox_events(event_id) ON DELETE RESTRICT
)
    """)
    _guard_exhaustion_receipt()


def _guard_exhaustion_receipt() -> None:
    """Prove immutable source custody and require the complete routing closure."""
    _execute_sql("""
CREATE FUNCTION public.guard_task_revision_exhaustion() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE m public.task_post_submit_routing_manifests%ROWTYPE;
 s public.submissions%ROWTYPE; p public.revision_policies%ROWTYPE;
 t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE; actual_round bigint;
 expected_status text;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'revision exhaustions are immutable' USING ERRCODE='55000'; END IF;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR UPDATE;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id FOR UPDATE;
 SELECT * INTO s FROM public.submissions WHERE id=NEW.source_submission_id FOR UPDATE;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=NEW.routing_manifest_id;
 SELECT * INTO p FROM public.revision_policies WHERE id=NEW.revision_policy_id;
 SELECT count(*)-1 INTO actual_round FROM public.submissions
  WHERE task_assignment_id=NEW.assignment_id AND version<=s.version;
 expected_status:=CASE WHEN NEW.recovery_authority_context IS NULL THEN 'evaluation_pending'
  ELSE 'needs_revision' END;
 IF t.id IS NULL OR a.id IS NULL OR s.id IS NULL OR m.id IS NULL OR p.id IS NULL
  OR NEW.creation_xid<>pg_current_xact_id()::text
  OR NEW.exhausted_at<m.created_at OR NEW.exhausted_at>clock_timestamp()
  OR t.status<>expected_status OR t.assigned_to IS DISTINCT FROM NEW.contributor_id
  OR a.status<>'active' OR a.released_at IS NOT NULL OR a.accepted_at IS NULL
  OR ROW(a.task_id,a.project_id,a.contributor_id) IS DISTINCT FROM
     ROW(NEW.task_id,NEW.project_id,NEW.contributor_id)
  OR ROW(s.task_id,s.task_assignment_id,s.contributor_id) IS DISTINCT FROM
     ROW(NEW.task_id,NEW.assignment_id,NEW.contributor_id)
  OR ROW(m.project_id,m.task_id,m.assignment_id,m.contributor_id,m.submission_id) IS DISTINCT FROM
     ROW(NEW.project_id,NEW.task_id,NEW.assignment_id,NEW.contributor_id,NEW.source_submission_id)
  OR ROW(NEW.revision_policy_id,NEW.revision_policy_generation,NEW.revision_policy_hash) IS DISTINCT FROM
     ROW(s.locked_revision_policy_id,s.locked_revision_policy_generation,s.locked_revision_policy_hash)
  OR p.project_id<>NEW.project_id OR p.guide_version<>s.locked_guide_version
  OR p.policy_generation<>NEW.revision_policy_generation OR p.policy_hash<>NEW.revision_policy_hash
  OR p.semantics_status<>'complete' OR p.max_revision_rounds<>actual_round
  OR NEW.revision_round<>actual_round OR NEW.max_revision_rounds<>p.max_revision_rounds
  OR m.routing_recommendation<>'needs_revision'
  OR (NEW.recovery_authority_context IS NULL AND (
   m.authorization_decision_id<>NEW.authorization_decision_id
   OR m.audit_event_id<>NEW.audit_event_id OR m.outcome_event_id<>NEW.outcome_event_id
   OR m.authority_context->'consequence' IS DISTINCT FROM jsonb_build_object(
    'kind','checker_exhaustion','expected_task_status','evaluation_pending',
    'target_task_status','ready','assignment_status','revision_exhausted',
    'exhaustion_receipt_id',NEW.id::text,'revision_round',NEW.revision_round,
    'max_revision_rounds',NEW.max_revision_rounds)))
  OR (NEW.recovery_authority_context IS NOT NULL AND
      NOT public.revision_exhaustion_recovery_authorized(NEW))
  OR NOT public.task_routing_context_valid(m)
  OR NOT public.revision_routing_source_current(m.id)
  OR (NEW.recovery_authority_context IS NULL AND
      EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id))
  OR EXISTS(SELECT 1 FROM public.task_revision_expirations WHERE routing_manifest_id=m.id)
  OR (NEW.recovery_authority_context IS NULL AND EXISTS(SELECT 1 FROM public.outbox_events WHERE
    idempotency_key='task.revision.expire:'||m.id::text))
 THEN RAISE EXCEPTION 'revision exhaustion source or authority differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)

    op.execute("CREATE TRIGGER revision_exhaustion_guard BEFORE INSERT OR UPDATE OR DELETE "
               "ON public.task_revision_exhaustions FOR EACH ROW "
               "EXECUTE FUNCTION public.guard_task_revision_exhaustion()")
    _execute_sql("""
CREATE FUNCTION public.guard_task_revision_exhaustion_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE m public.task_post_submit_routing_manifests%ROWTYPE;
 t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
BEGIN
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=NEW.routing_manifest_id;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id;
 IF NOT public.task_revision_exhaustion_complete(NEW.id)
  OR (NEW.recovery_authority_context IS NULL AND NOT public.task_routing_outcome_complete(m))
  OR t.status<>'ready' OR t.assigned_to IS NOT NULL
  OR a.status<>'revision_exhausted' OR a.released_at IS DISTINCT FROM NEW.exhausted_at
  OR (NEW.recovery_authority_context IS NULL AND
      EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id))
  OR EXISTS(SELECT 1 FROM public.task_revision_expirations WHERE routing_manifest_id=m.id)
  OR (NEW.recovery_authority_context IS NULL AND EXISTS(SELECT 1 FROM public.outbox_events WHERE
    idempotency_key='task.revision.expire:'||m.id::text))
 THEN RAISE EXCEPTION 'revision exhaustion closure unavailable' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
    """)
    op.execute("CREATE CONSTRAINT TRIGGER revision_exhaustion_closure AFTER INSERT "
               "ON public.task_revision_exhaustions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
               "EXECUTE FUNCTION public.guard_task_revision_exhaustion_closure()")
    _execute_sql("""
CREATE FUNCTION public.reject_task_revision_exhaustion_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN RAISE EXCEPTION 'revision exhaustions are immutable' USING ERRCODE='55000'; END $$;
CREATE TRIGGER revision_exhaustion_no_truncate BEFORE TRUNCATE ON public.task_revision_exhaustions
 FOR EACH STATEMENT EXECUTE FUNCTION public.reject_task_revision_exhaustion_truncate();
    """)


def _route_exhaustion() -> None:
    """Bind the terminal branch to the existing routing AUTH, audit and notice."""
    context = "public.task_routing_context_valid(public.task_post_submit_routing_manifests)"
    _replace(context,
        "consequence := jsonb_build_object('kind','checker_remediation',\n"
        "          'expected_task_status','evaluation_pending','target_task_status','needs_revision');",
        """IF m.authority_context#>>'{consequence,kind}'='checker_exhaustion' THEN
          consequence := jsonb_build_object('kind','checker_exhaustion',
            'expected_task_status','evaluation_pending','target_task_status','ready',
            'assignment_status','revision_exhausted',
            'exhaustion_receipt_id',m.authority_context#>>'{consequence,exhaustion_receipt_id}',
            'revision_round',(SELECT count(*)-1 FROM public.submissions counted
              WHERE counted.task_assignment_id=m.assignment_id AND counted.version<=s.version),
            'max_revision_rounds',(SELECT max_revision_rounds FROM public.revision_policies
              WHERE id=s.locked_revision_policy_id AND policy_generation=s.locked_revision_policy_generation
                AND policy_hash=s.locked_revision_policy_hash AND semantics_status='complete'));
          IF (consequence->>'revision_round')::bigint IS DISTINCT FROM
             (consequence->>'max_revision_rounds')::bigint
            OR (consequence->>'revision_round')::bigint<0
            OR consequence->>'exhaustion_receipt_id' IS NULL
            OR NOT ((get_byte(uuid_send((consequence->>'exhaustion_receipt_id')::uuid),6)>>4)=7
              AND (get_byte(uuid_send((consequence->>'exhaustion_receipt_id')::uuid),8)&192)=128)
          THEN RETURN false; END IF;
        ELSE
          consequence := jsonb_build_object('kind','checker_remediation',
            'expected_task_status','evaluation_pending','target_task_status','needs_revision');
        END IF;""")
    _replace("public.guard_task_routing_authority()",
        "IF NOT public.task_routing_context_valid(NEW) THEN",
        """IF NEW.routing_recommendation='needs_revision' AND EXISTS (
          SELECT 1 FROM public.submissions s JOIN public.revision_policies p
            ON p.id=s.locked_revision_policy_id AND p.policy_generation=s.locked_revision_policy_generation
              AND p.policy_hash=s.locked_revision_policy_hash
          WHERE s.id=NEW.submission_id AND p.semantics_status='complete'
            AND (SELECT count(*)-1 FROM public.submissions counted
              WHERE counted.task_assignment_id=NEW.assignment_id AND counted.version<=s.version)
              >=p.max_revision_rounds
        ) AND NEW.authority_context#>>'{consequence,kind}' IS DISTINCT FROM 'checker_exhaustion'
        THEN RAISE EXCEPTION 'revision exhaustion consequence required' USING ERRCODE='23514'; END IF;
      IF NOT public.task_routing_context_valid(NEW) THEN""")
    complete = "public.task_routing_outcome_complete(public.task_post_submit_routing_manifests)"
    _replace(complete,
        "CASE WHEN m.routing_recommendation='needs_revision' THEN 'needs_revision' ",
        "CASE WHEN m.authority_context#>>'{consequence,kind}'='checker_exhaustion' THEN 'ready' "
        "WHEN m.routing_recommendation='needs_revision' THEN 'needs_revision' ")
    _replace(complete,
        "CASE WHEN m.routing_recommendation='needs_revision' OR m.human_review_required ",
        "CASE WHEN m.authority_context#>>'{consequence,kind}'='checker_exhaustion' THEN 'revision_exhausted' "
        "WHEN m.routing_recommendation='needs_revision' OR m.human_review_required ")
    _replace(complete,
        "IF NOT EXISTS(SELECT 1 FROM public.outbox_events e WHERE e.event_id=m.outcome_event_id",
        """IF m.authority_context#>>'{consequence,kind}'='checker_exhaustion' THEN
        IF NOT EXISTS(SELECT 1 FROM public.task_revision_exhaustions exhausted
          JOIN public.task_assignments assignment ON assignment.id=exhausted.assignment_id
          JOIN public.workstream_tasks task ON task.id=exhausted.task_id
          WHERE exhausted.routing_manifest_id=m.id AND exhausted.source_submission_id=m.submission_id
            AND exhausted.id::text=m.authority_context#>>'{consequence,exhaustion_receipt_id}'
            AND exhausted.authorization_decision_id=m.authorization_decision_id
            AND exhausted.audit_event_id=m.audit_event_id AND exhausted.outcome_event_id=m.outcome_event_id
            AND assignment.status='revision_exhausted' AND assignment.released_at=exhausted.exhausted_at
            AND task.status='ready' AND task.assigned_to IS NULL)
          OR EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id)
          OR EXISTS(SELECT 1 FROM public.outbox_events
            WHERE idempotency_key='task.revision.expire:'||m.id::text)
        THEN RETURN false; END IF;
        notice:=notice||jsonb_build_object(
          'exhaustion_receipt_id',m.authority_context#>>'{consequence,exhaustion_receipt_id}',
          'assignment_status','revision_exhausted','status_reason','revision_limit_reached');
      END IF;
      IF NOT EXISTS(SELECT 1 FROM public.outbox_events e WHERE e.event_id=m.outcome_event_id""")
    _execute_sql(EXHAUSTION_TRANSITION_GUARDS)


def _allow_reclaim() -> None:
    """Accept only exact retained terminal evidence for another round-zero claim."""
    _execute_sql("""
CREATE FUNCTION public.task_revision_released_assignment_current(prior_assignment uuid, latest_submission uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT public.task_revision_expired_assignment_current(prior_assignment,latest_submission)
 OR EXISTS(SELECT 1 FROM public.task_revision_exhaustions e
   JOIN public.task_assignments a ON a.id=e.assignment_id
   JOIN public.submissions s ON s.id=e.source_submission_id
   JOIN public.task_post_submit_routing_manifests m ON m.id=e.routing_manifest_id
   WHERE e.assignment_id=prior_assignment AND e.source_submission_id=latest_submission
    AND a.status='revision_exhausted' AND a.released_at=e.exhausted_at
    AND a.task_id=e.task_id AND a.contributor_id=e.contributor_id
    AND s.task_id=e.task_id AND s.task_assignment_id=a.id AND s.contributor_id=e.contributor_id
    AND m.task_id=e.task_id AND m.assignment_id=a.id AND m.submission_id=s.id
    AND public.task_revision_exhaustion_complete(e.id)
    AND public.task_routing_context_valid(m)
    AND NOT EXISTS(SELECT 1 FROM public.submissions newer WHERE newer.task_id=s.task_id
      AND newer.version>s.version))
$$;
    """)
    _replace("public.guard_submission_revision_capacity()",
             "prior_assignment.status<>'revision_expired'",
             "prior_assignment.status NOT IN ('revision_expired','revision_exhausted')")
    for signature in ("public.guard_submission_revision_capacity()",
                      "public.guard_selected_pre_submit_run_insert()"):
        _replace(signature, "public.task_revision_expired_assignment_current(",
                 "public.task_revision_released_assignment_current(")


def _paused_revision_clock() -> None:
    """Make PostgreSQL the sole writer of allowance observations and packet hashes."""
    op.execute("ALTER TABLE public.task_revision_preparations ALTER COLUMN deadline_at DROP NOT NULL")
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN remaining_microseconds bigint")
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN clock_observed_at timestamptz")
    _execute_sql("""ALTER TABLE public.task_revision_preparations ADD CONSTRAINT
      ck_task_revision_preparations_clock_shape CHECK (
        (deadline_at IS NOT NULL AND remaining_microseconds IS NULL) OR
        (deadline_at IS NULL AND remaining_microseconds IS NOT NULL AND remaining_microseconds > 0))""")
    _execute_sql("""
CREATE FUNCTION public.revision_clock_interval(remaining_microseconds bigint)
RETURNS interval LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT make_interval(hours=>(remaining_microseconds/3600000000)::integer)
  +(remaining_microseconds%3600000000)*interval '1 microsecond'
$$;
CREATE FUNCTION public.project_revision_preparation_clock() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE prior public.task_revision_preparations%ROWTYPE;
 m public.task_post_submit_routing_manifests%ROWTYPE; policy public.revision_policies%ROWTYPE;
 source public.submissions%ROWTYPE; observed timestamptz; original_deadline timestamptz;
 blocked boolean;
BEGIN
 PERFORM 1 FROM public.workstream_tasks WHERE id=NEW.task_id FOR UPDATE;
 IF NEW.deadline_at IS NOT NULL OR NEW.remaining_microseconds IS NOT NULL
  OR NEW.clock_observed_at IS NOT NULL
  OR NEW.packet->'deadline_at' IS DISTINCT FROM 'null'::jsonb
  OR NEW.packet->'remaining_microseconds' IS DISTINCT FROM 'null'::jsonb
  OR NEW.packet->'clock_observed_at' IS DISTINCT FROM 'null'::jsonb
 THEN RAISE EXCEPTION 'revision clock is database owned' USING ERRCODE='23514'; END IF;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=NEW.routing_manifest_id;
 SELECT * INTO source FROM public.submissions WHERE id=m.submission_id;
 SELECT * INTO policy FROM public.revision_policies WHERE id=source.locked_revision_policy_id;
 IF policy.id IS NULL OR NEW.next_revision_round>policy.max_revision_rounds THEN
  RAISE EXCEPTION 'revision_limit_reached' USING ERRCODE='23514'; END IF;
 IF EXISTS(SELECT 1 FROM public.task_revision_exhaustions WHERE routing_manifest_id=m.id) THEN
  RAISE EXCEPTION 'revision source exhausted' USING ERRCODE='23514'; END IF;
 observed:=clock_timestamp();
 NEW.clock_observed_at:=observed;
 original_deadline:=m.created_at+make_interval(hours=>policy.revision_deadline_hours);
 blocked:=(NEW.packet#>'{candidate,target}'='null'::jsonb OR
  (NEW.packet#>>'{candidate,target_max_revision_rounds}')::integer<NEW.next_revision_round);
 IF NEW.predecessor_id IS NULL THEN
  IF original_deadline<=observed THEN
   NEW.deadline_at:=original_deadline;
   NEW.blocked_reason:='revision_deadline_expired';
  ELSIF blocked THEN
   NEW.remaining_microseconds:=CASE WHEN NEW.repair_actor_id IS NULL AND EXISTS(
    SELECT 1 FROM public.task_post_submit_routing_manifests original
    WHERE original.id=m.id AND original.xmin=pg_current_xact_id()::xid)
    THEN policy.revision_deadline_hours::bigint*3600000000
    ELSE floor(extract(epoch FROM (original_deadline-observed))*1000000)::bigint END;
   NEW.blocked_reason:='context_blocked';
  ELSE NEW.deadline_at:=original_deadline; NEW.blocked_reason:=NULL;
  END IF;
 ELSE
  SELECT * INTO prior FROM public.task_revision_preparations WHERE id=NEW.predecessor_id;
  IF prior.id IS NULL OR (prior.deadline_at IS NOT NULL AND prior.deadline_at<=observed) THEN
   RAISE EXCEPTION 'revision deadline expired'
    USING ERRCODE='23514', CONSTRAINT='ck_revision_preparation_deadline_expired'; END IF;
  IF blocked THEN
   NEW.remaining_microseconds:=CASE WHEN prior.deadline_at IS NULL THEN prior.remaining_microseconds
    ELSE floor(extract(epoch FROM (prior.deadline_at-observed))*1000000)::bigint END;
   NEW.blocked_reason:='context_blocked';
  ELSE
   NEW.deadline_at:=CASE WHEN prior.deadline_at IS NULL THEN
    observed+public.revision_clock_interval(prior.remaining_microseconds) ELSE prior.deadline_at END;
   NEW.blocked_reason:=NULL;
  END IF;
 END IF;
 NEW.outcome:=CASE WHEN NEW.blocked_reason IS NOT NULL THEN 'blocked'
  WHEN NEW.packet#>'{candidate,prior}'=NEW.packet#>'{candidate,target}' THEN 'kept' ELSE 'rebased' END;
 NEW.packet:=NEW.packet||jsonb_build_object(
  'deadline_at',CASE WHEN NEW.deadline_at IS NULL THEN NULL ELSE public.outbox_dispatch_utc(NEW.deadline_at) END,
  'remaining_microseconds',NEW.remaining_microseconds,
  'clock_observed_at',public.outbox_dispatch_utc(observed),
  'outcome',NEW.outcome,'blocked_reason',NEW.blocked_reason);
 NEW.preparation_sha256:='sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.project_guide_projection_canonical_json(NEW.packet),'UTF8')),'hex');
 RETURN NEW;
END $$;
CREATE TRIGGER a_revision_preparation_clock BEFORE INSERT ON public.task_revision_preparations
 FOR EACH ROW EXECUTE FUNCTION public.project_revision_preparation_clock();
    """)
    _guard_preparation_clock()
    _guard_effective_deadline()
    _guard_clock_events()
    _guard_preparation_closure()


def _guard_preparation_clock() -> None:
    """Keep the original source/authority guards while replacing fixed-wall-clock rules."""
    guard = "public.guard_revision_preparation()"
    _replace(guard,
        "OR NEW.deadline_at IS DISTINCT FROM m.created_at + make_interval(hours=>policy.revision_deadline_hours)",
        """OR (NEW.deadline_at IS NOT NULL AND NEW.deadline_at IS DISTINCT FROM
          m.created_at + make_interval(hours=>policy.revision_deadline_hours))
    OR (NEW.deadline_at IS NULL AND NEW.remaining_microseconds IS DISTINCT FROM
      CASE WHEN NEW.repair_actor_id IS NULL AND EXISTS(
       SELECT 1 FROM public.task_post_submit_routing_manifests original
       WHERE original.id=m.id AND original.xmin=pg_current_xact_id()::xid)
      THEN policy.revision_deadline_hours::bigint*3600000000
      ELSE floor(extract(epoch FROM (m.created_at
       +make_interval(hours=>policy.revision_deadline_hours)-NEW.clock_observed_at))*1000000)::bigint END)""")
    _replace(guard,
        "OR ROW(NEW.requested_at,NEW.deadline_at,NEW.max_revision_rounds)\n"
        "       IS DISTINCT FROM ROW(prior.requested_at,prior.deadline_at,prior.max_revision_rounds)",
        """OR ROW(NEW.requested_at,NEW.max_revision_rounds)
       IS DISTINCT FROM ROW(prior.requested_at,prior.max_revision_rounds)
    OR (NEW.deadline_at IS NOT NULL AND NEW.deadline_at IS DISTINCT FROM
      CASE WHEN prior.deadline_at IS NULL THEN
       NEW.clock_observed_at+public.revision_clock_interval(prior.remaining_microseconds) ELSE prior.deadline_at END)
    OR (NEW.deadline_at IS NULL AND NEW.remaining_microseconds IS DISTINCT FROM
      CASE WHEN prior.deadline_at IS NULL THEN prior.remaining_microseconds ELSE
       floor(extract(epoch FROM (prior.deadline_at-NEW.clock_observed_at))*1000000)::bigint END)""")
    _replace(guard,
        "reason:=CASE WHEN NEW.next_revision_round>NEW.max_revision_rounds OR NEW.next_revision_round>target_limit\n"
        "                 THEN 'revision_limit_reached'\n"
        "              WHEN clock_timestamp()>=NEW.deadline_at THEN 'revision_deadline_expired'\n"
        "              WHEN c->'target'='null'::jsonb THEN 'context_blocked' ELSE NULL END;",
        """IF NEW.next_revision_round>NEW.max_revision_rounds THEN
  RAISE EXCEPTION 'revision_limit_reached' USING ERRCODE='23514'; END IF;
 IF NEW.clock_observed_at IS NULL OR NEW.clock_observed_at>clock_timestamp()
  OR (NEW.packet->>'clock_observed_at')::timestamptz IS DISTINCT FROM NEW.clock_observed_at
  OR (NEW.packet->>'remaining_microseconds')::bigint IS DISTINCT FROM NEW.remaining_microseconds
 THEN RAISE EXCEPTION 'revision clock custody differs' USING ERRCODE='23514'; END IF;
 reason:=CASE WHEN NEW.deadline_at IS NOT NULL AND NEW.clock_observed_at>=NEW.deadline_at
                THEN 'revision_deadline_expired'
              WHEN c->'target'='null'::jsonb OR NEW.next_revision_round>target_limit
                THEN 'context_blocked' ELSE NULL END;""")
    _replace(guard,
        "'preparation_id',NULL,'preparation_sha256',NULL,\n                'candidate',NEW.packet->'candidate'",
        "'preparation_id',NULL,'preparation_sha256',NULL,\n"
        "                'head_preparation_id',NULL,'head_preparation_sha256',NULL,\n"
        "                'candidate',NEW.packet->'candidate'")
    _replace(guard,
        "(NEW.outcome='blocked' OR c->'target' IS NOT DISTINCT FROM (prior.packet#>'{candidate,target}'))",
        """(c IS NOT DISTINCT FROM prior.packet->'candidate'
      AND NOT (prior.clock_observed_at IS NULL AND prior.deadline_at IS NOT NULL
        AND prior.outcome='blocked' AND prior.blocked_reason IN ('context_blocked','revision_limit_reached')
        AND NEW.deadline_at IS NULL AND NEW.outcome='blocked'
        AND NEW.repair_actor_id IS NOT NULL AND EXISTS(SELECT 1 FROM public.audit_events decision
          WHERE decision.id=NEW.authorization_decision_id AND decision.action_id='task.revision.recover')))""")


def _guard_effective_deadline() -> None:
    """Apply one running clock to admission, insertion and the final commit boundary."""
    _replace("public.guard_new_revision_submission()", "OR p.outcome='blocked'",
             "OR p.outcome='blocked' OR p.deadline_at IS NULL")
    _replace("public.guard_revision_admission_context()", "OR p.outcome='blocked'",
             "OR p.outcome='blocked' OR p.deadline_at IS NULL")


def _guard_clock_events() -> None:
    """Bind immutable scheduling intents to the precise preparation clock."""
    _execute_sql("""
CREATE FUNCTION public.revision_expiry_event_matches(e public.outbox_events,
 root public.task_revision_preparations, scheduled public.task_revision_preparations)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(e.event_type='TaskRevisionExpiryRequested' AND e.event_version=1
  AND e.aggregate_type='task' AND e.aggregate_id=root.task_id AND e.project_id=root.project_id
  AND e.correlation_id=root.routing_manifest_id::text
  AND e.causation_event_id=m.outcome_event_id AND e.producer='workstream'
  AND root.sequence=1 AND root.predecessor_id IS NULL
  AND scheduled.routing_manifest_id=root.routing_manifest_id
  AND scheduled.deadline_at IS NOT NULL AND scheduled.remaining_microseconds IS NULL
  AND e.idempotency_key='task.revision.expire:'||root.routing_manifest_id::text||
    CASE WHEN scheduled.sequence=1 THEN '' ELSE ':'||scheduled.id::text END
  AND e.not_before_at=scheduled.deadline_at
  AND (e.payload->>'deadline_at')::timestamptz=scheduled.deadline_at
  AND e.payload-'deadline_at'=jsonb_build_object(
   'project_id',root.project_id::text,'task_id',root.task_id::text,
   'assignment_id',root.assignment_id::text,'contributor_id',root.contributor_id::text,
   'source_submission_id',root.submission_id::text,'routing_manifest_id',root.routing_manifest_id::text,
   'root_preparation_id',root.id::text,'root_preparation_sha256',root.preparation_sha256), false)
 FROM public.task_post_submit_routing_manifests m WHERE m.id=root.routing_manifest_id
$$;
    """)
    guard = "public.guard_task_revision_expiration()"
    _replace(guard,
        "SELECT * INTO source FROM public.submissions WHERE id=NEW.source_submission_id;",
        """SELECT * INTO source FROM public.submissions WHERE id=NEW.source_submission_id;
 IF EXISTS(SELECT 1 FROM public.revision_policies policy
   WHERE policy.id=source.locked_revision_policy_id AND policy.project_id=t.project_id
    AND policy.guide_version=source.locked_guide_version
    AND policy.policy_generation=source.locked_revision_policy_generation
    AND policy.policy_hash=source.locked_revision_policy_hash AND policy.semantics_status='complete'
    AND (SELECT count(*)-1 FROM public.submissions attempt
      WHERE attempt.task_assignment_id=source.task_assignment_id
       AND attempt.version<=source.version)>=policy.max_revision_rounds) THEN
  RAISE EXCEPTION 'revision source exhausted before expiry'
   USING ERRCODE='23514', CONSTRAINT='ck_revision_expiration_source_not_exhausted'; END IF;""")
    _replace(guard, "OR root.deadline_at<>NEW.deadline_at", "")
    _replace(guard, "OR head.deadline_at<>NEW.deadline_at",
             "OR head.deadline_at IS DISTINCT FROM NEW.deadline_at OR head.remaining_microseconds IS NOT NULL")
    _replace(guard, "OR event.idempotency_key<>'task.revision.expire:'||m.id::text",
        """OR NOT EXISTS(SELECT 1 FROM public.task_revision_preparations scheduled
     WHERE public.revision_expiry_event_matches(event,root,scheduled)
       AND scheduled.deadline_at=NEW.deadline_at)""")
    _replace("public.task_revision_expired_assignment_current(uuid,uuid)",
             "AND head.preparation_sha256=e.head_preparation_sha256",
             "AND head.preparation_sha256=e.head_preparation_sha256 "
             "AND head.deadline_at=e.deadline_at AND head.remaining_microseconds IS NULL")


def _guard_preparation_closure() -> None:
    """Require each clock head's exact timer or durable blocked-context notice."""
    _execute_sql("""
CREATE OR REPLACE FUNCTION public.guard_revision_preparation_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE p public.task_revision_preparations%ROWTYPE; root public.task_revision_preparations%ROWTYPE;
 t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
 m public.task_post_submit_routing_manifests%ROWTYPE; event public.outbox_events%ROWTYPE;
 decision public.audit_events%ROWTYPE; audit public.audit_events%ROWTYPE;
 expected jsonb; refs jsonb; intent_key text;
BEGIN
 SELECT * INTO p FROM public.task_revision_preparations WHERE id=NEW.id;
 SELECT * INTO root FROM public.task_revision_preparations
  WHERE routing_manifest_id=p.routing_manifest_id AND sequence=1;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=p.task_id;
 SELECT * INTO a FROM public.task_assignments WHERE id=p.assignment_id;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=p.routing_manifest_id;
 IF p.predecessor_id IS NOT NULL AND EXISTS(
  SELECT 1 FROM public.task_revision_preparations prior WHERE prior.id=p.predecessor_id
   AND prior.deadline_at IS NOT NULL AND prior.deadline_at<=clock_timestamp()) THEN
  RAISE EXCEPTION 'revision deadline expired before repair commit'
   USING ERRCODE='23514', CONSTRAINT='ck_revision_preparation_deadline_expired'; END IF;
 expected:=CASE WHEN p.outcome='blocked' THEN p.packet->'previous_task_lineage'
  ELSE p.packet#>'{candidate,target,lineage}' END;
 IF t.id IS NULL OR a.id IS NULL OR m.id IS NULL OR root.id IS NULL
  OR NOT public.task_routing_outcome_complete(m)
  OR t.status<>'needs_revision' OR t.assigned_to<>p.contributor_id
  OR a.status<>'active' OR a.released_at IS NOT NULL
  OR public.revision_task_lineage(to_jsonb(t)) IS DISTINCT FROM expected
  OR a.submitter_contribution_policy_version_id::text IS DISTINCT FROM
     expected->>'locked_contribution_policy_version_id'
  OR (p.outcome<>'blocked' AND t.locked_post_submit_checker_policy_body::jsonb IS DISTINCT FROM
     (p.packet#>>'{candidate,target_post_policy_json}')::jsonb)
 THEN RAISE EXCEPTION 'revision preparation has no complete task outcome' USING ERRCODE='23514'; END IF;
 intent_key:='task.revision.expire:'||p.routing_manifest_id::text||
  CASE WHEN p.sequence=1 THEN '' ELSE ':'||p.id::text END;
 IF p.deadline_at IS NULL THEN
  IF p.outcome<>'blocked' OR p.blocked_reason<>'context_blocked'
   OR EXISTS(SELECT 1 FROM public.outbox_events WHERE idempotency_key=intent_key)
   OR NOT EXISTS(SELECT 1 FROM public.outbox_events notice
     WHERE notice.idempotency_key='task.revision.context-blocked:'||p.routing_manifest_id::text||':'||p.id::text
      AND notice.event_type='TaskRevisionContextBlocked' AND notice.event_version=1
      AND notice.producer='workstream' AND notice.aggregate_type='task' AND notice.aggregate_id=p.task_id
      AND notice.project_id=p.project_id AND notice.correlation_id=p.routing_manifest_id::text
      AND notice.causation_event_id=m.outcome_event_id AND notice.not_before_at IS NULL
      AND notice.payload=jsonb_build_object(
        'project_id',p.project_id::text,'task_id',p.task_id::text,'assignment_id',p.assignment_id::text,
        'source_submission_id',p.submission_id::text,'routing_manifest_id',p.routing_manifest_id::text,
        'preparation_id',p.id::text,'preparation_sha256',p.preparation_sha256,
        'authorization_decision_id',p.authorization_decision_id::text,'audit_event_id',p.audit_event_id::text,
        'reason','context_blocked','remaining_microseconds',p.remaining_microseconds))
  THEN RAISE EXCEPTION 'revision paused notification unavailable' USING ERRCODE='23514'; END IF;
  SELECT * INTO event FROM public.outbox_events WHERE
   idempotency_key='task.revision.context-blocked:'||p.routing_manifest_id::text||':'||p.id::text;
 ELSE
  SELECT * INTO event FROM public.outbox_events WHERE idempotency_key=intent_key;
  IF event.event_id IS NULL OR NOT public.revision_expiry_event_matches(event,root,p)
  THEN RAISE EXCEPTION 'revision timer unavailable' USING ERRCODE='23514'; END IF;
 END IF;
 refs:=jsonb_build_object('project_id',p.project_id::text,'task_id',p.task_id::text,
  'assignment_id',p.assignment_id::text,'submission_id',p.submission_id::text,
  'routing_manifest_id',p.routing_manifest_id::text,'revision_preparation_id',p.id::text,
  'authorization_decision_id',p.authorization_decision_id::text);
 IF p.repair_actor_id IS NOT NULL THEN
  SELECT * INTO decision FROM public.audit_events WHERE id=p.authorization_decision_id;
  SELECT * INTO audit FROM public.audit_events WHERE id=p.audit_event_id;
  refs:=refs||jsonb_build_object('outbox_event_id',event.event_id::text);
  expected:=jsonb_build_object('references',refs);
  expected:=expected||jsonb_build_object('authorization_resource_digest',
   decision.after_facts::jsonb->>'resource_context_digest');
  IF audit.id IS NULL OR audit.event_domain<>'legacy_lifecycle'
   OR audit.event_type<>'TaskRevisionContextRepaired' OR audit.entity_type<>'task' OR audit.entity_id<>p.task_id
   OR audit.actor_id<>p.repair_actor_id::text OR audit.auth_source<>'local_lifecycle' OR audit.is_dev_auth
   OR audit.from_status IS NOT NULL OR audit.to_status IS NOT NULL OR audit.reason IS DISTINCT FROM p.repair_reason
   OR audit.event_payload::jsonb IS DISTINCT FROM expected
  THEN RAISE EXCEPTION 'revision repair audit unavailable' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NULL;
END $$;
    """)


def _retained_exhaustion() -> None:
    """Close old cap-blocked sources without changing original routing evidence."""
    _recovered_exhaustion_authority()
    _recovered_exhaustion_evidence()
    _exhaustion_complete()
    _replace("public.guard_task_revision_expiration_transition()",
        "AND e.contributor_id=OLD.assigned_to\n       AND e.creation_xid=pg_current_xact_id()::text)\n   THEN",
        """AND e.contributor_id=OLD.assigned_to
       AND e.creation_xid=pg_current_xact_id()::text)
      AND NOT EXISTS(SELECT 1 FROM public.task_revision_exhaustions exhausted
        WHERE exhausted.task_id=OLD.id AND exhausted.project_id=OLD.project_id
          AND exhausted.contributor_id=OLD.assigned_to
          AND exhausted.recovery_authority_context IS NOT NULL
          AND exhausted.creation_xid=pg_current_xact_id()::text)
   THEN""")


def _recovered_exhaustion_authority() -> None:
    """Validate fresh source/root/head-bound service authority at receipt INSERT."""
    _execute_sql("""
CREATE FUNCTION public.revision_exhaustion_recovery_authorized(e public.task_revision_exhaustions)
RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE t public.workstream_tasks%ROWTYPE; m public.task_post_submit_routing_manifests%ROWTYPE;
 root public.task_revision_preparations%ROWTYPE; head public.task_revision_preparations%ROWTYPE;
 decision public.audit_events%ROWTYPE; context jsonb; expected jsonb; request_hash text; digest text;
BEGIN
 context:=e.recovery_authority_context;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=e.task_id;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=e.routing_manifest_id;
 SELECT * INTO root FROM public.task_revision_preparations WHERE routing_manifest_id=m.id AND sequence=1;
 SELECT * INTO head FROM public.task_revision_preparations WHERE routing_manifest_id=m.id
  AND NOT EXISTS(SELECT 1 FROM public.task_revision_preparations child
    WHERE child.predecessor_id=task_revision_preparations.id);
 SELECT * INTO decision FROM public.audit_events WHERE id=e.authorization_decision_id;
 request_hash:='sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.project_guide_projection_canonical_json(jsonb_build_object(
   'routing_manifest_id',m.id::text,'preparation_id',root.id::text,
   'preparation_sha256',root.preparation_sha256,'head_preparation_id',head.id::text,
   'head_preparation_sha256',head.preparation_sha256,'exhaustion_receipt_id',e.id::text,
   'revision_round',e.revision_round,'max_revision_rounds',e.max_revision_rounds)),'UTF8')),'hex');
 expected:=jsonb_build_object('resource_type','task_authority','resource_id',e.task_id::text,
  'scope_project_id',e.project_id::text,'actor_profile_id',context->>'actor_profile_id',
  'identity_link_id',context->>'identity_link_id','task_status','needs_revision',
  'assigned_to',e.contributor_id::text,'assignment_id',e.assignment_id::text,
  'assignment_contributor_id',e.contributor_id::text,'locked_context_hash',public.revision_task_context_digest(t),
  'reason','Recover retained revision window','idempotency_key',coalesce(root.id,m.id)::text,
  'replay_assignment_id',NULL,'request_digest',request_hash,'replay_command_id',NULL,
  'revision_preparation_id',root.id::text,'revision_preparation_sha256',root.preparation_sha256,
  'revision_routing_manifest_id',m.id::text,'revision_replay_preparation_id',NULL);
 digest:='sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.project_guide_projection_canonical_json(jsonb_build_object(
   'resource_context',jsonb_strip_nulls(expected))),'UTF8')),'hex');
 RETURN coalesce(context=expected AND m.authority_context#>>'{consequence,kind}'='checker_remediation'
  AND decision.event_domain='authority' AND decision.event_type='SensitiveAuthorizationAllowed'
  AND decision.action_id='task.revision.recover' AND decision.permission_id='task.revision.recover'
  AND decision.actor_ref_kind='actor_profile' AND decision.actor_id=context->>'actor_profile_id'
  AND decision.resource_type='project' AND decision.resource_id=e.project_id::text
  AND decision.project_id=e.project_id AND decision.request_id=m.id AND decision.correlation_id=m.id
  AND decision.denial_code IS NULL AND decision.after_facts::jsonb=jsonb_build_object(
    'allowed',true,'resource_context_digest',digest)
  AND EXISTS(SELECT 1 FROM public.actor_profiles actor JOIN public.actor_identity_links link
    ON link.actor_profile_id=actor.id AND link.id::text=context->>'identity_link_id'
    WHERE actor.id::text=context->>'actor_profile_id' AND actor.actor_kind='service'
      AND actor.service_identity='workstream.task.revision_expirer' AND actor.status='active'
      AND link.status='active' AND link.subject_kind='service'),false);
END $$;
    """)


def _recovered_exhaustion_evidence() -> None:
    """Validate immutable recovery evidence even after a replacement claim starts."""
    _execute_sql("""
CREATE FUNCTION public.revision_recovered_exhaustion_evidence(e public.task_revision_exhaustions)
RETURNS boolean LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE m public.task_post_submit_routing_manifests%ROWTYPE; decision public.audit_events%ROWTYPE;
 audit public.audit_events%ROWTYPE; notice public.outbox_events%ROWTYPE;
 original_audit public.audit_events%ROWTYPE; original_notice public.outbox_events%ROWTYPE;
 refs jsonb; original_refs jsonb; digest text;
BEGIN
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=e.routing_manifest_id;
 SELECT * INTO decision FROM public.audit_events WHERE id=e.authorization_decision_id;
 SELECT * INTO audit FROM public.audit_events WHERE id=e.audit_event_id;
 SELECT * INTO notice FROM public.outbox_events WHERE event_id=e.outcome_event_id;
 SELECT * INTO original_audit FROM public.audit_events WHERE id=m.audit_event_id;
 SELECT * INTO original_notice FROM public.outbox_events WHERE event_id=m.outcome_event_id;
 digest:='sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.project_guide_projection_canonical_json(jsonb_build_object(
   'resource_context',jsonb_strip_nulls(e.recovery_authority_context))),'UTF8')),'hex');
 refs:=jsonb_build_object('project_id',e.project_id::text,'task_id',e.task_id::text,
  'assignment_id',e.assignment_id::text,'submission_id',e.source_submission_id::text,
  'routing_manifest_id',m.id::text,'revision_exhaustion_id',e.id::text,
  'authorization_decision_id',decision.id::text,'outbox_event_id',notice.event_id::text);
 original_refs:=jsonb_build_object('project_id',m.project_id::text,'task_id',m.task_id::text,
  'submission_id',m.submission_id::text,'assignment_id',m.assignment_id::text,
  'authorization_decision_id',m.authorization_decision_id::text,'routing_manifest_id',m.id::text);
 RETURN coalesce(e.recovery_authority_context IS NOT NULL AND public.task_routing_context_valid(m)
  AND m.authority_context#>>'{consequence,kind}'='checker_remediation'
  AND original_audit.event_type='TaskPostSubmitRouted' AND original_audit.entity_type='task'
  AND original_audit.entity_id=m.task_id AND original_audit.actor_id=m.router_actor_id::text
  AND original_audit.auth_source='local_lifecycle' AND original_audit.event_domain='legacy_lifecycle'
  AND NOT original_audit.is_dev_auth
  AND original_audit.from_status='evaluation_pending' AND original_audit.to_status='needs_revision'
  AND original_audit.reason='lifecycle_state_changed'
  AND original_audit.event_payload::jsonb=jsonb_build_object('references',original_refs)
  AND original_notice.event_type='TaskPostSubmitRouted' AND original_notice.event_version=1
  AND original_notice.aggregate_type='task' AND original_notice.aggregate_id=m.task_id
  AND original_notice.project_id=m.project_id AND original_notice.causation_event_id=m.completion_event_id
  AND original_notice.correlation_id=m.authority_context#>>'{request,route_operation_id}'
  AND original_notice.idempotency_key='task-routed:'||m.id::text
  AND original_notice.payload=jsonb_build_object('routing_manifest_id',m.id::text,'task_id',m.task_id::text,
    'submission_id',m.submission_id::text,'authorization_decision_id',m.authorization_decision_id::text,
    'human_review_required',m.human_review_required,'final_acceptance_id',NULL)
  AND decision.event_type='SensitiveAuthorizationAllowed' AND decision.action_id='task.revision.recover'
  AND decision.permission_id='task.revision.recover' AND decision.denial_code IS NULL
  AND decision.event_domain='authority' AND decision.actor_ref_kind='actor_profile'
  AND decision.actor_id=e.recovery_authority_context->>'actor_profile_id'
  AND decision.resource_type='project' AND decision.resource_id=e.project_id::text
  AND decision.project_id=e.project_id AND decision.request_id=m.id AND decision.correlation_id=m.id
  AND decision.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',digest)
  AND audit.event_domain='legacy_lifecycle' AND audit.event_type='TaskRevisionExhausted'
  AND audit.entity_type='task' AND audit.entity_id=e.task_id AND audit.actor_id=decision.actor_id
  AND audit.actor_id=e.recovery_authority_context->>'actor_profile_id'
  AND audit.auth_source='local_lifecycle' AND NOT audit.is_dev_auth
  AND audit.from_status='needs_revision' AND audit.to_status='ready' AND audit.reason='lifecycle_state_changed'
  AND audit.event_payload::jsonb=jsonb_build_object('references',refs,'authorization_resource_digest',digest)
  AND notice.event_type='TaskRevisionExhausted' AND notice.event_version=1 AND notice.producer='workstream'
  AND notice.aggregate_type='task' AND notice.aggregate_id=e.task_id AND notice.project_id=e.project_id
  AND notice.correlation_id=m.id::text AND notice.causation_event_id=m.outcome_event_id
  AND notice.idempotency_key='task.revision.exhausted:'||m.id::text AND notice.not_before_at IS NULL
  AND (notice.payload->>'exhausted_at')::timestamptz=e.exhausted_at
  AND notice.payload-'exhausted_at'=jsonb_build_object(
    'project_id',e.project_id::text,'task_id',e.task_id::text,'assignment_id',e.assignment_id::text,
    'contributor_id',e.contributor_id::text,'source_submission_id',e.source_submission_id::text,
    'routing_manifest_id',m.id::text,'exhaustion_receipt_id',e.id::text,
    'authorization_decision_id',decision.id::text,'audit_event_id',audit.id::text),false);
END $$;
    """)


def _exhaustion_complete() -> None:
    """Expose complete immutable terminal custody independently of current TASK state."""
    _execute_sql("""
CREATE FUNCTION public.task_revision_exhaustion_complete(receipt uuid)
RETURNS boolean LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE e public.task_revision_exhaustions%ROWTYPE; m public.task_post_submit_routing_manifests%ROWTYPE;
 a public.task_assignments%ROWTYPE; s public.submissions%ROWTYPE; p public.revision_policies%ROWTYPE;
 audit public.audit_events%ROWTYPE; notice public.outbox_events%ROWTYPE; refs jsonb;
BEGIN
 SELECT * INTO e FROM public.task_revision_exhaustions WHERE id=receipt;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=e.routing_manifest_id;
 SELECT * INTO s FROM public.submissions WHERE id=e.source_submission_id;
 SELECT * INTO a FROM public.task_assignments WHERE id=e.assignment_id;
 SELECT * INTO p FROM public.revision_policies WHERE id=e.revision_policy_id;
 IF m.id IS NULL OR s.id IS NULL OR a.id IS NULL OR p.id IS NULL
  OR ROW(m.project_id,m.task_id,m.assignment_id,m.contributor_id,m.submission_id) IS DISTINCT FROM
     ROW(e.project_id,e.task_id,e.assignment_id,e.contributor_id,e.source_submission_id)
  OR ROW(s.task_id,s.task_assignment_id,s.contributor_id) IS DISTINCT FROM
     ROW(e.task_id,e.assignment_id,e.contributor_id)
  OR ROW(a.project_id,a.task_id,a.contributor_id) IS DISTINCT FROM ROW(e.project_id,e.task_id,e.contributor_id)
  OR a.status<>'revision_exhausted' OR a.released_at IS DISTINCT FROM e.exhausted_at
  OR ROW(s.locked_revision_policy_id,s.locked_revision_policy_generation,s.locked_revision_policy_hash)
     IS DISTINCT FROM ROW(e.revision_policy_id,e.revision_policy_generation,e.revision_policy_hash)
  OR p.project_id<>e.project_id OR p.guide_version<>s.locked_guide_version OR p.semantics_status<>'complete'
  OR p.policy_generation<>e.revision_policy_generation OR p.policy_hash<>e.revision_policy_hash
  OR p.max_revision_rounds<>e.max_revision_rounds OR e.revision_round<>e.max_revision_rounds
  OR e.revision_round IS DISTINCT FROM (SELECT count(*)-1 FROM public.submissions counted
     WHERE counted.task_assignment_id=e.assignment_id AND counted.version<=s.version)
  OR NOT public.task_routing_context_valid(m)
 THEN RETURN false; END IF;
 IF e.recovery_authority_context IS NOT NULL THEN
  RETURN public.revision_recovered_exhaustion_evidence(e); END IF;
 SELECT * INTO audit FROM public.audit_events WHERE id=e.audit_event_id;
 SELECT * INTO notice FROM public.outbox_events WHERE event_id=e.outcome_event_id;
 refs:=jsonb_build_object('project_id',m.project_id::text,'task_id',m.task_id::text,
  'submission_id',m.submission_id::text,'assignment_id',m.assignment_id::text,
  'authorization_decision_id',m.authorization_decision_id::text,'routing_manifest_id',m.id::text);
 RETURN coalesce(e.authorization_decision_id=m.authorization_decision_id AND e.audit_event_id=m.audit_event_id
  AND e.outcome_event_id=m.outcome_event_id AND m.authority_context->'consequence'=jsonb_build_object(
    'kind','checker_exhaustion','expected_task_status','evaluation_pending','target_task_status','ready',
    'assignment_status','revision_exhausted','exhaustion_receipt_id',e.id::text,
    'revision_round',e.revision_round,'max_revision_rounds',e.max_revision_rounds)
  AND audit.event_type='TaskPostSubmitRouted' AND audit.event_domain='legacy_lifecycle'
  AND audit.entity_type='task' AND audit.entity_id=e.task_id AND audit.actor_id=m.router_actor_id::text
  AND audit.auth_source='local_lifecycle' AND NOT audit.is_dev_auth
  AND audit.from_status='evaluation_pending' AND audit.to_status='ready'
  AND audit.reason='lifecycle_state_changed'
  AND audit.event_payload::jsonb=jsonb_build_object('references',refs)
  AND notice.event_type='TaskPostSubmitRouted' AND notice.event_version=1 AND notice.producer='workstream'
  AND notice.aggregate_type='task' AND notice.aggregate_id=e.task_id AND notice.project_id=e.project_id
  AND notice.correlation_id=m.authority_context#>>'{request,route_operation_id}'
  AND notice.causation_event_id=m.completion_event_id AND notice.idempotency_key='task-routed:'||m.id::text
  AND notice.payload=jsonb_build_object('routing_manifest_id',m.id::text,'task_id',m.task_id::text,
    'submission_id',m.submission_id::text,'authorization_decision_id',m.authorization_decision_id::text,
    'human_review_required',m.human_review_required,'final_acceptance_id',NULL,
    'exhaustion_receipt_id',e.id::text,'assignment_status','revision_exhausted',
    'status_reason','revision_limit_reached'),false);
END $$;
    """)


def _retained_blocked_clock() -> None:
    """Allow one exact service pause of a retained running blocked head."""
    guard = "public.guard_revision_preparation()"
    _replace(guard, "NEW.predecessor_id IS NULL AND NEW.outcome IN ('kept','blocked')",
        """((NEW.predecessor_id IS NULL AND NEW.outcome IN ('kept','blocked'))
          OR (NEW.predecessor_id IS NOT NULL AND prior.clock_observed_at IS NULL
            AND prior.deadline_at IS NOT NULL AND prior.outcome='blocked'
            AND prior.blocked_reason IN ('context_blocked','revision_limit_reached')
            AND prior.next_revision_round<=prior.max_revision_rounds
            AND NEW.deadline_at IS NULL AND NEW.outcome='blocked'
            AND NEW.blocked_reason='context_blocked'
            AND NEW.packet#>'{candidate,target}'='null'::jsonb
            AND NEW.packet#>'{candidate,target_max_revision_rounds}'='null'::jsonb
            AND NEW.packet#>'{candidate,target_post_policy_json}'='null'::jsonb))""")
    _replace(guard, "NEW.repair_idempotency_key=NEW.routing_manifest_id",
             "NEW.repair_idempotency_key=coalesce(prior.id,NEW.routing_manifest_id)")
    _replace(guard,
        "'preparation_id',NULL,'preparation_sha256',NULL,\n"
        "                'head_preparation_id',NULL,'head_preparation_sha256',NULL,",
        """'preparation_id',(SELECT root.id::text FROM public.task_revision_preparations root
                  WHERE root.routing_manifest_id=NEW.routing_manifest_id AND root.sequence=1),
                'preparation_sha256',(SELECT root.preparation_sha256 FROM public.task_revision_preparations root
                  WHERE root.routing_manifest_id=NEW.routing_manifest_id AND root.sequence=1),
                'head_preparation_id',prior.id::text,'head_preparation_sha256',prior.preparation_sha256,""")


def downgrade() -> None:
    """Retained exhaustion and paused-clock evidence cannot be downgraded."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
