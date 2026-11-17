"""Bind task, admission, immutable Submission and award to one exact size selection."""

from alembic import op
from sqlalchemy import text

revision = "0071_selected_task_reward"
down_revision = "0070_task_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("SELECT id FROM public.authority_control WHERE id=1 FOR UPDATE")
    phase = op.get_bind().execute(text(
        "SELECT phase FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
    )).scalar_one()
    if phase != "disabled":
        raise RuntimeError("reward selection installation requires the lifecycle disabled")
    op.execute("""LOCK TABLE public.workstream_tasks, public.task_assignments,
        public.submissions, public.submission_bundle_admissions,
        public.submission_bundle_durable_intents, public.task_post_submit_routing_manifests,
        public.task_revision_preparations, public.task_revision_exhaustions IN ACCESS EXCLUSIVE MODE""")
    if op.get_bind().execute(text("""SELECT
        EXISTS(SELECT 1 FROM public.workstream_tasks WHERE status<>'draft'
          OR locked_contribution_policy_version_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM public.task_assignments)
        OR EXISTS(SELECT 1 FROM public.submissions)
        OR EXISTS(SELECT 1 FROM public.submission_bundle_durable_intents)
        OR EXISTS(SELECT 1 FROM public.submission_bundle_admissions)
        OR EXISTS(SELECT 1 FROM public.task_post_submit_routing_manifests)
        OR EXISTS(SELECT 1 FROM public.task_revision_preparations)
        OR EXISTS(SELECT 1 FROM public.task_revision_exhaustions)
    """)).scalar_one():
        raise RuntimeError("reward selection installation refuses work without immutable selection evidence")

    _remove_obsolete_recovery()

    op.execute("""ALTER TABLE public.task_revision_preparations
        DROP CONSTRAINT ck_task_revision_preparations_blocked_reason,
        ADD CONSTRAINT ck_task_revision_preparations_blocked_reason CHECK (
          blocked_reason IS NULL OR blocked_reason IN ('context_blocked','revision_deadline_expired')),
        DROP CONSTRAINT ck_task_revision_preparations_positive_rounds,
        ADD CONSTRAINT ck_task_revision_preparations_positive_rounds CHECK (
          sequence>0 AND source_submission_version>0 AND next_revision_round>=0
          AND max_revision_rounds>=0 AND next_revision_round<=max_revision_rounds)""")

    op.execute("""ALTER TABLE public.workstream_tasks
        ADD COLUMN locked_submission_award_definition_id uuid CONSTRAINT fk_task_selected_reward
        REFERENCES public.contribution_award_definitions(id)""")
    for table, size, definition, constraint in (
        ("task_assignments", "submitter_task_size", "submitter_award_definition_id", "fk_assignment_selected_reward"),
        ("submissions", "task_size", "contribution_award_definition_id", "fk_submission_selected_reward"),
        ("submission_bundle_admissions", "task_size", "contribution_award_definition_id", "fk_admission_selected_reward"),
        ("task_post_submit_routing_manifests", "task_size", "contribution_award_definition_id", "fk_routing_selected_reward"),
    ):
        op.execute(f"ALTER TABLE public.{table} ADD COLUMN {size} varchar(8) NOT NULL")
        op.execute(f"""ALTER TABLE public.{table} ADD CONSTRAINT ck_{table}_reward_size
            CHECK ({size} IN ('small','medium','large'))""")
        op.execute(f"""ALTER TABLE public.{table} ADD COLUMN {definition} uuid CONSTRAINT {constraint}
            REFERENCES public.contribution_award_definitions(id)""")
    op.execute("""ALTER TABLE public.submission_bundle_admissions
        ADD COLUMN contribution_policy_version_id uuid NOT NULL,
        ADD CONSTRAINT fk_submission_admission_contribution_project
          FOREIGN KEY (contribution_policy_version_id,project_id)
          REFERENCES public.contribution_policy_versions(id,project_id)""")

    op.execute("""
CREATE OR REPLACE FUNCTION public.revision_task_context_digest(t public.workstream_tasks) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT 'sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
   public.project_guide_projection_canonical_json(
     public.revision_task_lineage(to_jsonb(t)) || jsonb_build_object(
       'locked_post_submit_checker_policy_body',t.locked_post_submit_checker_policy_body::jsonb,
       'task_size',t.task_size,
       'locked_submission_award_definition_id',t.locked_submission_award_definition_id::text)),
   'UTF8')),'hex');
$$;
    """)

    op.execute("""
CREATE FUNCTION public.reward_selection_matches(project uuid, policy uuid, size text, definition uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS (
  SELECT 1 FROM public.contribution_rules r
  JOIN public.contribution_policy_versions p ON p.id=r.contribution_policy_version_id
    AND p.project_id=r.project_id
  WHERE r.project_id=project AND r.contribution_policy_version_id=policy
    AND r.contribution_type='accepted_submission' AND p.status IN ('published','retired')
    AND size IN ('small','medium','large')
    AND ((r.compensation_mode='unpaid' AND definition IS NULL)
      OR (r.compensation_mode='compensated' AND EXISTS (
        SELECT 1 FROM public.contribution_award_definitions d
        WHERE d.id=definition AND d.project_id=project AND d.contribution_rule_id=r.id
          AND d.contribution_policy_version_id=policy
          AND d.contribution_type='accepted_submission' AND d.task_size=size)))
 );
$$;
    """)
    op.execute("""
CREATE FUNCTION public.reward_selection_facts(project uuid, policy uuid, size text, definition uuid)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT jsonb_build_object('policy_version_id',policy::text,'task_size',size,
   'compensation_mode',r.compensation_mode,'award_definition_id',d.id::text,
   'instrument_type',d.instrument_type,'unit_code',d.unit_code,
   'quantity',CASE WHEN position('.' IN d.quantity::text)>0
      THEN rtrim(rtrim(d.quantity::text,'0'),'.') ELSE d.quantity::text END,
   'adapter_binding_id',d.adapter_binding_id::text)
 FROM public.contribution_rules r
 LEFT JOIN public.contribution_award_definitions d ON d.id=definition
 WHERE r.project_id=project AND r.contribution_policy_version_id=policy
   AND r.contribution_type='accepted_submission'
   AND public.reward_selection_matches(project,policy,size,definition);
$$;
    """)
    # Extend the existing authorization predicate: revision is the sole rebase owner.
    _replace_function(
        "public.revision_task_update_authorized(public.workstream_tasks,public.workstream_tasks)",
        "AND old_task.status='needs_revision'",
        """AND p.packet->'previous_task_reward_selection'=jsonb_build_object(
           'task_size',old_task.task_size,'award_definition_id',old_task.locked_submission_award_definition_id::text)
         AND p.packet#>>'{candidate,target_reward_selection,task_size}'=new_task.task_size
         AND (p.packet#>>'{candidate,target_reward_selection,award_definition_id}')::uuid
             IS NOT DISTINCT FROM new_task.locked_submission_award_definition_id
         AND old_task.status='needs_revision'""",
    )
    op.execute("""
CREATE FUNCTION public.guard_task_reward_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NEW.status='draft' AND NEW.locked_contribution_policy_version_id IS NULL
    AND NEW.locked_submission_award_definition_id IS NULL THEN RETURN NEW; END IF;
 IF NOT public.reward_selection_matches(NEW.project_id,NEW.locked_contribution_policy_version_id,
       NEW.task_size,NEW.locked_submission_award_definition_id) THEN
   RAISE EXCEPTION 'task reward selection differs' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND NEW.locked_submission_award_definition_id IS DISTINCT FROM OLD.locked_submission_award_definition_id
   AND NOT (OLD.status='draft' AND NEW.status='screening')
   AND NOT public.revision_task_update_authorized(OLD,NEW) THEN
   RAISE EXCEPTION 'task reward rebase lacks preparation' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER task_reward_selection BEFORE INSERT OR UPDATE ON public.workstream_tasks
 FOR EACH ROW EXECUTE FUNCTION public.guard_task_reward_selection();
    """)
    op.execute("""
CREATE FUNCTION public.guard_assignment_reward_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE t public.workstream_tasks%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' AND NEW.submitter_task_size IS DISTINCT FROM OLD.submitter_task_size THEN
   RAISE EXCEPTION 'assignment size is immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP='INSERT' OR ROW(NEW.submitter_contribution_policy_version_id,NEW.submitter_award_definition_id)
    IS DISTINCT FROM ROW(OLD.submitter_contribution_policy_version_id,OLD.submitter_award_definition_id) THEN
   SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id AND project_id=NEW.project_id FOR SHARE;
   IF t.id IS NULL OR ROW(NEW.submitter_task_size,NEW.submitter_contribution_policy_version_id,NEW.submitter_award_definition_id)
      IS DISTINCT FROM ROW(t.task_size,t.locked_contribution_policy_version_id,t.locked_submission_award_definition_id) THEN
     RAISE EXCEPTION 'assignment reward selection differs' USING ERRCODE='23514';
   END IF;
   IF TG_OP='UPDATE' AND NOT EXISTS (
     SELECT 1 FROM public.task_revision_preparations p
     WHERE p.assignment_id=OLD.id AND p.project_id=OLD.project_id AND p.task_id=OLD.task_id
       AND p.contributor_id=OLD.contributor_id AND p.creation_xid=pg_current_xact_id()::text
       AND p.outcome IN ('kept','rebased') AND OLD.status='active' AND NEW.status='active'
       AND OLD.released_at IS NULL AND NEW.released_at IS NULL
       AND p.packet->'previous_task_reward_selection'=jsonb_build_object(
         'task_size',OLD.submitter_task_size,'award_definition_id',OLD.submitter_award_definition_id::text)
       AND p.packet#>'{candidate,target_reward_selection}'=public.reward_selection_facts(
         NEW.project_id,NEW.submitter_contribution_policy_version_id,NEW.submitter_task_size,NEW.submitter_award_definition_id)
   ) THEN RAISE EXCEPTION 'assignment reward rebase lacks preparation' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER assignment_reward_selection BEFORE INSERT OR UPDATE ON public.task_assignments
 FOR EACH ROW EXECUTE FUNCTION public.guard_assignment_reward_selection();
    """)
    op.execute("""
CREATE FUNCTION public.guard_submission_reward_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE a public.task_assignments%ROWTYPE; t public.workstream_tasks%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' THEN
   IF ROW(NEW.task_size,NEW.contribution_award_definition_id) IS DISTINCT FROM
      ROW(OLD.task_size,OLD.contribution_award_definition_id) THEN
     RAISE EXCEPTION 'submission reward selection is immutable' USING ERRCODE='23514';
   END IF;
   RETURN NEW;
 END IF;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR SHARE;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.task_assignment_id FOR SHARE;
 IF a.id IS NULL OR t.id IS NULL
    OR ROW(NEW.task_size,NEW.contribution_policy_version_id,NEW.contribution_award_definition_id)
      IS DISTINCT FROM ROW(a.submitter_task_size,a.submitter_contribution_policy_version_id,a.submitter_award_definition_id)
    OR ROW(NEW.task_size,NEW.contribution_policy_version_id,NEW.contribution_award_definition_id)
      IS DISTINCT FROM ROW(t.task_size,t.locked_contribution_policy_version_id,t.locked_submission_award_definition_id)
    OR NOT public.reward_selection_matches(t.project_id,NEW.contribution_policy_version_id,NEW.task_size,NEW.contribution_award_definition_id)
 THEN RAISE EXCEPTION 'submission reward selection differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER submission_reward_selection BEFORE INSERT OR UPDATE ON public.submissions
 FOR EACH ROW EXECUTE FUNCTION public.guard_submission_reward_selection();
    """)
    op.execute("""
CREATE FUNCTION public.guard_admission_reward_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE a public.task_assignments%ROWTYPE; t public.workstream_tasks%ROWTYPE; request jsonb;
BEGIN
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR SHARE;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id FOR SHARE;
 SELECT selected_request_json INTO request FROM public.submission_bundle_durable_intents WHERE id=NEW.durable_intent_id;
 IF ROW(NEW.task_size,NEW.contribution_policy_version_id,NEW.contribution_award_definition_id)
      IS DISTINCT FROM ROW(a.submitter_task_size,a.submitter_contribution_policy_version_id,a.submitter_award_definition_id)
    OR ROW(NEW.task_size,NEW.contribution_policy_version_id,NEW.contribution_award_definition_id)
      IS DISTINCT FROM ROW(t.task_size,t.locked_contribution_policy_version_id,t.locked_submission_award_definition_id)
    OR NEW.task_size IS DISTINCT FROM request#>>'{admission_lineage,task_size}'
    OR NEW.contribution_policy_version_id::text IS DISTINCT FROM request#>>'{admission_lineage,contribution_policy_version_id}'
    OR to_jsonb(NEW.contribution_award_definition_id::text) IS DISTINCT FROM nullif(request#>'{admission_lineage,contribution_award_definition_id}','null'::jsonb)
    OR NOT (request->'admission_lineage' ? 'contribution_award_definition_id')
 THEN RAISE EXCEPTION 'admission reward selection differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER admission_reward_selection BEFORE INSERT ON public.submission_bundle_admissions
 FOR EACH ROW EXECUTE FUNCTION public.guard_admission_reward_selection();
    """)
    op.execute("""
CREATE FUNCTION public.guard_routing_reward_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.submissions%ROWTYPE;
BEGIN
 SELECT * INTO s FROM public.submissions WHERE id=NEW.submission_id;
 IF s.id IS NULL OR ROW(NEW.task_size,NEW.contribution_policy_version_id,NEW.contribution_award_definition_id)
    IS DISTINCT FROM ROW(s.task_size,s.contribution_policy_version_id,s.contribution_award_definition_id)
 THEN RAISE EXCEPTION 'routing reward selection differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER routing_reward_selection BEFORE INSERT ON public.task_post_submit_routing_manifests
 FOR EACH ROW EXECUTE FUNCTION public.guard_routing_reward_selection();
    """)
    op.execute("""
CREATE FUNCTION public.guard_revision_reward_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE s public.submissions%ROWTYPE; t public.workstream_tasks%ROWTYPE; c jsonb;
BEGIN
 SELECT * INTO s FROM public.submissions WHERE id=NEW.submission_id;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id;
 c:=NEW.packet->'candidate';
 IF c->'prior_reward_selection' IS DISTINCT FROM public.reward_selection_facts(
      NEW.project_id,s.contribution_policy_version_id,s.task_size,s.contribution_award_definition_id)
    OR NEW.packet->'previous_task_reward_selection' IS DISTINCT FROM jsonb_build_object(
      'task_size',t.task_size,'award_definition_id',t.locked_submission_award_definition_id::text)
    OR NOT (c ? 'target_reward_selection')
    OR (c->'target'='null'::jsonb AND c->'target_reward_selection'<>'null'::jsonb)
    OR (c->'target'<>'null'::jsonb AND c->'target_reward_selection' IS DISTINCT FROM
      public.reward_selection_facts(NEW.project_id,(c#>>'{target,lineage,locked_contribution_policy_version_id}')::uuid,
        s.task_size,(c#>>'{target_reward_selection,award_definition_id}')::uuid))
 THEN RAISE EXCEPTION 'revision reward packet differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER revision_reward_selection BEFORE INSERT ON public.task_revision_preparations
 FOR EACH ROW EXECUTE FUNCTION public.guard_revision_reward_selection();
    """)
    _replace_function(
        "public.guard_revision_preparation_closure()",
        "IF t.id IS NULL OR a.id IS NULL OR m.id IS NULL OR root.id IS NULL",
        """IF ROW(t.task_size,t.locked_submission_award_definition_id) IS DISTINCT FROM
           ROW(a.submitter_task_size,a.submitter_award_definition_id)
          OR jsonb_build_object('task_size',t.task_size,'award_definition_id',t.locked_submission_award_definition_id::text)
             IS DISTINCT FROM (CASE WHEN p.outcome='blocked' THEN p.packet->'previous_task_reward_selection'
             ELSE jsonb_build_object('task_size',p.packet#>>'{candidate,target_reward_selection,task_size}',
               'award_definition_id',p.packet#>>'{candidate,target_reward_selection,award_definition_id}') END)
          OR t.id IS NULL OR a.id IS NULL OR m.id IS NULL OR root.id IS NULL""",
    )
    # Keep the existing deferred closure owner and replace its policy-wide enumeration.
    op.execute("""
CREATE OR REPLACE FUNCTION public.accepted_submission_award_set_is_complete(record_uuid uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT NOT EXISTS (
   SELECT 1 FROM public.contribution_records r
   LEFT JOIN public.submissions s ON s.id=r.submission_id
   LEFT JOIN public.workstream_tasks t ON t.id=s.task_id
   WHERE r.id=record_uuid AND r.contribution_type='accepted_submission' AND (
     s.id IS NULL OR NOT public.reward_selection_matches(r.project_id,r.contribution_policy_version_id,
       s.task_size,s.contribution_award_definition_id)
     OR (SELECT count(*) FROM public.compensation_awards w WHERE w.contribution_record_id=r.id)
        <> CASE WHEN s.contribution_award_definition_id IS NULL THEN 0 ELSE 1 END
     OR EXISTS(SELECT 1 FROM public.compensation_awards w WHERE w.contribution_record_id=r.id
       AND w.award_definition_id IS DISTINCT FROM s.contribution_award_definition_id)
   )
 );
$$;
    """)
    _replace_function(
        "public.task_routing_context_valid(public.task_post_submit_routing_manifests)",
        "'contribution_policy_version_id',m.contribution_policy_version_id::text,",
        """'contribution_policy_version_id',m.contribution_policy_version_id::text,
            'task_size',m.task_size,'contribution_award_definition_id',m.contribution_award_definition_id::text,""",
    )
    # A wrong but valid policy tier must fail immediately, not only at commit.
    _replace_function("public.guard_compensation_award()", "    RETURN NEW;", """
    IF source_type='accepted_submission' AND NOT EXISTS (
      SELECT 1 FROM public.contribution_records r JOIN public.submissions s ON s.id=r.submission_id
      WHERE r.id=NEW.contribution_record_id AND s.contribution_award_definition_id=NEW.award_definition_id
    ) THEN RAISE EXCEPTION 'award differs from submission selection' USING ERRCODE='23514'; END IF;
    RETURN NEW;""")


def _remove_obsolete_recovery() -> None:
    """Remove excluded development recovery while preserving current installed guards."""
    # Install only complete definitions: actual upgrades compile every CREATE.
    replacements = (
        ('public.guard_task_revision_exhaustion()', ' expected_status text;\n', ''),
        ('public.guard_task_revision_exhaustion()', " expected_status:=CASE WHEN NEW.recovery_authority_context IS NULL THEN 'evaluation_pending'\n  ELSE 'needs_revision' END;\n", ''),
        ('public.guard_task_revision_exhaustion()', 't.status<>expected_status', "t.status<>'evaluation_pending'"),
        ('public.guard_task_revision_exhaustion()', 'OR (NEW.recovery_authority_context IS NULL AND (', 'OR ('),
        ('public.guard_task_revision_exhaustion()', "'max_revision_rounds',NEW.max_revision_rounds)))", "'max_revision_rounds',NEW.max_revision_rounds))"),
        ('public.guard_task_revision_exhaustion()', '  OR (NEW.recovery_authority_context IS NOT NULL AND\n      NOT public.revision_exhaustion_recovery_authorized(NEW))\n', ''),
        ('public.guard_task_revision_exhaustion()', '(NEW.recovery_authority_context IS NULL AND\n      EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id))', 'EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id)'),
        ('public.guard_task_revision_exhaustion()', "(NEW.recovery_authority_context IS NULL AND EXISTS(SELECT 1 FROM public.outbox_events WHERE\n    idempotency_key='task.revision.expire:'||m.id::text))", "EXISTS(SELECT 1 FROM public.outbox_events WHERE\n    idempotency_key='task.revision.expire:'||m.id::text)"),
        ('public.guard_task_revision_exhaustion_closure()', '(NEW.recovery_authority_context IS NULL AND\n      EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id))', 'EXISTS(SELECT 1 FROM public.task_revision_preparations WHERE routing_manifest_id=m.id)'),
        ('public.guard_task_revision_exhaustion_closure()', "(NEW.recovery_authority_context IS NULL AND EXISTS(SELECT 1 FROM public.outbox_events WHERE\n    idempotency_key='task.revision.expire:'||m.id::text))", "EXISTS(SELECT 1 FROM public.outbox_events WHERE\n    idempotency_key='task.revision.expire:'||m.id::text)"),
        ('public.guard_task_revision_exhaustion_closure()', '(NEW.recovery_authority_context IS NULL AND NOT public.task_routing_outcome_complete(m))', 'NOT public.task_routing_outcome_complete(m)'),
        ('public.task_revision_exhaustion_complete(uuid)', ' IF e.recovery_authority_context IS NOT NULL THEN\n  RETURN public.revision_recovered_exhaustion_evidence(e); END IF;\n', ''),
        ('public.guard_task_revision_expiration_transition()', '\n      AND NOT EXISTS(SELECT 1 FROM public.task_revision_exhaustions exhausted\n        WHERE exhausted.task_id=OLD.id AND exhausted.project_id=OLD.project_id\n          AND exhausted.contributor_id=OLD.assigned_to\n          AND exhausted.recovery_authority_context IS NOT NULL\n          AND exhausted.creation_xid=pg_current_xact_id()::text)', ''),
        ('public.guard_revision_preparation()', "(c IS NOT DISTINCT FROM prior.packet->'candidate'\n      AND NOT (prior.clock_observed_at IS NULL AND prior.deadline_at IS NOT NULL\n        AND prior.outcome='blocked' AND prior.blocked_reason IN ('context_blocked','revision_limit_reached')\n        AND NEW.deadline_at IS NULL AND NEW.outcome='blocked'\n        AND NEW.repair_actor_id IS NOT NULL AND EXISTS(SELECT 1 FROM public.audit_events decision\n          WHERE decision.id=NEW.authorization_decision_id AND decision.action_id='task.revision.recover')))", "(c IS NOT DISTINCT FROM prior.packet->'candidate')"),
        ('public.guard_revision_preparation()', "((NEW.predecessor_id IS NULL AND NEW.outcome IN ('kept','blocked'))\n          OR (NEW.predecessor_id IS NOT NULL AND prior.clock_observed_at IS NULL\n            AND prior.deadline_at IS NOT NULL AND prior.outcome='blocked'\n            AND prior.blocked_reason IN ('context_blocked','revision_limit_reached')\n            AND prior.next_revision_round<=prior.max_revision_rounds\n            AND NEW.deadline_at IS NULL AND NEW.outcome='blocked'\n            AND NEW.blocked_reason='context_blocked'\n            AND NEW.packet#>'{candidate,target}'='null'::jsonb\n            AND NEW.packet#>'{candidate,target_max_revision_rounds}'='null'::jsonb\n            AND NEW.packet#>'{candidate,target_post_policy_json}'='null'::jsonb))", "NEW.predecessor_id IS NULL AND NEW.outcome IN ('kept','blocked')"),
        ('public.guard_revision_preparation()', 'NEW.repair_idempotency_key=coalesce(prior.id,NEW.routing_manifest_id)', 'NEW.repair_idempotency_key=NEW.routing_manifest_id'),
        ('public.guard_revision_preparation()', "'preparation_id',(SELECT root.id::text FROM public.task_revision_preparations root\n                  WHERE root.routing_manifest_id=NEW.routing_manifest_id AND root.sequence=1),\n                'preparation_sha256',(SELECT root.preparation_sha256 FROM public.task_revision_preparations root\n                  WHERE root.routing_manifest_id=NEW.routing_manifest_id AND root.sequence=1),\n                'head_preparation_id',prior.id::text,'head_preparation_sha256',prior.preparation_sha256,", "'preparation_id',NULL,'preparation_sha256',NULL,\n                'head_preparation_id',NULL,'head_preparation_sha256',NULL,"),
    )
    bodies = {}
    for signature, old, new in replacements:
        if signature not in bodies:
            bodies[signature] = op.get_bind().execute(text(
                "SELECT pg_get_functiondef(to_regprocedure(:signature))"
            ), {"signature": signature}).scalar_one()
        if bodies[signature].count(old) != 1:
            raise RuntimeError(f"selected reward guard owner changed: {signature}")
        bodies[signature] = bodies[signature].replace(old, new)
    for body in bodies.values():
        op.execute(body)
    op.execute("DROP FUNCTION public.revision_exhaustion_recovery_authorized(public.task_revision_exhaustions)")
    op.execute("DROP FUNCTION public.revision_recovered_exhaustion_evidence(public.task_revision_exhaustions)")
    op.execute("ALTER TABLE public.task_revision_exhaustions DROP CONSTRAINT ck_task_revision_exhaustions_recovery_authority_shape, DROP COLUMN recovery_authority_context")


def _replace_function(signature: str, old: str, new: str) -> None:
    body = op.get_bind().execute(text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
                                 {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError(f"selected reward guard owner changed: {signature}")
    op.execute(body.replace(old, new))


def downgrade() -> None:
    raise RuntimeError("Immutable selected rewards require a matched backup to restore")
