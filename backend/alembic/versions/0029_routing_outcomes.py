"""Bind routing authority to its complete governed outcome in one root transaction."""

from alembic import op
import sqlalchemy as sa
from scripts.schema_baseline_sql import split_sql_statements

revision = "0029_routing_outcomes"
down_revision = "0028_lifecycle_transitions"
branch_labels = None
depends_on = None


def _execute_statements(source):
    for statement in split_sql_statements(source):
        op.execute(statement)


def _replace_function(signature, old, new):
    body = (
        op.get_bind()
        .execute(
            sa.text("SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"),
            {"signature": signature},
        )
        .scalar_one()
    )
    if body.count(old) != 1:
        raise RuntimeError("routing migration function shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute(
        "LOCK TABLE public.task_post_submit_routing_manifests, public.final_acceptances, "
        "public.checker_runs IN ACCESS EXCLUSIVE MODE"
    )
    _execute_statements("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.task_post_submit_routing_manifests)
        OR EXISTS(SELECT 1 FROM public.final_acceptances)
        OR EXISTS(SELECT 1 FROM public.checker_runs WHERE finalize_evidence_id IS NOT NULL)
      THEN RAISE EXCEPTION 'retained outcome or terminal material lacks required source authority'
        USING ERRCODE='23514'; END IF;
    END $$;
    ALTER TABLE public.checker_runs ADD COLUMN input_materialization_evidence_id uuid
      CONSTRAINT fk_checker_input_materialization_evidence REFERENCES public.audit_events(id);
    ALTER TABLE public.final_acceptances ADD COLUMN source_authorization_decision_id uuid NOT NULL UNIQUE
      REFERENCES public.audit_events(id) ON DELETE RESTRICT;
    ALTER TABLE public.task_post_submit_routing_manifests
      ADD COLUMN authorization_decision_id uuid NOT NULL UNIQUE REFERENCES public.audit_events(id) ON DELETE RESTRICT,
      ADD COLUMN router_actor_id uuid NOT NULL REFERENCES public.actor_profiles(id),
      ADD COLUMN router_identity_link_id uuid NOT NULL REFERENCES public.actor_identity_links(id),
      ADD COLUMN authority_context jsonb NOT NULL,
      ADD COLUMN final_acceptance_id uuid UNIQUE REFERENCES public.final_acceptances(id) DEFERRABLE INITIALLY DEFERRED,
      ADD COLUMN authorized_lifecycle_generation bigint,
      ADD COLUMN audit_event_id uuid NOT NULL UNIQUE REFERENCES public.audit_events(id) DEFERRABLE INITIALLY DEFERRED,
      ADD COLUMN outcome_event_id uuid NOT NULL UNIQUE REFERENCES public.outbox_events(event_id) DEFERRABLE INITIALLY DEFERRED;
    """)
    _replace_function(
        "public.protect_checker_run_custody()",
        "'result_json','result_digest','material_custody'",
        "'input_materialization_evidence_id','result_json','result_digest','material_custody'",
    )
    _replace_function(
        "public.checker_post_submit_authority_digest(public.checker_runs,text)",
        "'execute_evidence_id',r.execute_evidence_id::text,",
        "'execute_evidence_id',r.execute_evidence_id::text, "
        "'input_materialization_evidence_id',r.input_materialization_evidence_id::text,",
    )
    _audit_contract()
    _material_authority()
    _routing_authority()
    _closure()
    for old in (
        "NOT EXISTS (SELECT 1 FROM public.final_acceptances)",
        "EXISTS(SELECT 1 FROM public.final_acceptances)",
    ):
        replacement = old.replace(
            "SELECT 1 FROM public.final_acceptances",
            (
                "SELECT 1 FROM public.final_acceptances f LEFT JOIN public.task_post_submit_routing_manifests m "
                "ON m.id=f.source_routing_manifest_id WHERE m.id IS NULL OR NOT public.task_routing_receipt_valid(m)"
            ),
        )
        _replace_function(
            "public.joint_lifecycle_transition_valid(public.joint_lifecycle_transitions)",
            old,
            replacement,
        )


def _audit_contract():
    replacements = {
        "ck_audit_events_authorization_action_evidence": (
            "(((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text))",
            " OR (((action_id)::text = 'task.post_submit.route'::text) AND ((permission_id)::text = 'task.post_submit.route'::text))",
            2,
        ),
        "ck_audit_events_authority_registries": (
            "('outbox.dispatch'::character varying)::text",
            ", ('task.post_submit.route'::character varying)::text",
            1,
        ),
        "ck_audit_events_authority_privacy_bounds": (
            "('outbox_event'::character varying)::text",
            ", ('task_post_submit_routing_manifest'::character varying)::text",
            1,
        ),
    }
    for name, (anchor, addition, count) in replacements.items():
        definition = (
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
                    "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
                ),
                {"name": name},
            )
            .scalar_one()
        )
        if definition.count(anchor) != count:
            raise RuntimeError("routing audit constraint shape changed: " + name)
        op.execute(f"ALTER TABLE public.audit_events DROP CONSTRAINT {name}")
        op.execute(
            f"ALTER TABLE public.audit_events ADD CONSTRAINT {name} "
            + definition.replace(anchor, anchor + addition)
        )


def _material_authority():
    _execute_statements("""
    CREATE FUNCTION public.checker_input_authority_digest(r public.checker_runs) RETURNS text
    LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
      SELECT 'sha256:' || encode(sha256(convert_to(public.project_guide_projection_canonical_json(
        jsonb_build_object('domain','workstream.authorization.post_submit_materialization',
          'action_id','artifact.post_submit.checker_input.materialize',
          'permission_id','artifact.checker_input.materialize',
          'service_identity','workstream.artifact.materializer','resource_type','checker_run',
          'resource_id',r.id::text,'scope_project_id',r.project_id::text,
          'execution_digest',public.checker_post_submit_authority_digest(r,'execute'),
          'material',jsonb_build_object('material',r.material_custody::jsonb,
            'evidence_id',a.pre_submit_evidence_set_id::text,
            'verification_receipt_id',v.id::text,'verification_job_id',v.verification_job_id::text,
            'verification_generation',v.execution_generation,'namespace_fingerprint',n.namespace_fingerprint,
            'semantic_manifest_id',a.semantic_manifest_id::text))), 'UTF8')), 'hex')
      FROM public.submission_bundle_admissions a
      JOIN public.artifact_verification_receipts v ON v.id=a.verification_receipt_id
      JOIN public.artifact_replicas p ON p.id=a.verified_replica_id
      JOIN public.artifact_storage_namespaces n ON n.id=p.storage_namespace_id
      WHERE a.id=(r.material_custody->>'admission_id')::uuid
    $$;
    CREATE FUNCTION public.checker_input_receipt_valid(r public.checker_runs) RETURNS boolean
    LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
      SELECT EXISTS(SELECT 1 FROM public.audit_events a
        JOIN public.actor_profiles p ON p.id::text=a.actor_id
        JOIN public.actor_identity_links l ON l.actor_profile_id=p.id
        WHERE a.id=r.input_materialization_evidence_id
          AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
          AND a.actor_ref_kind='actor_profile' AND p.actor_kind='service'
          AND p.service_identity='workstream.artifact.materializer' AND l.subject_kind='service'
          AND a.action_id='artifact.post_submit.checker_input.materialize'
          AND a.permission_id='artifact.checker_input.materialize'
          AND a.denial_code IS NULL AND a.matched_grant_id IS NULL
          AND a.project_id=r.project_id AND a.resource_type='checker_run' AND a.resource_id=r.id::text
          AND a.target_ref_kind='project' AND a.target_ref_id=r.project_id::text
          AND a.request_id=r.evaluation_request_id AND a.correlation_id=r.evaluation_request_id
          AND a.after_facts::jsonb=jsonb_build_object('allowed',true,
            'resource_context_digest',public.checker_input_authority_digest(r)))
    $$;
    CREATE FUNCTION public.guard_checker_input_receipt() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE r public.checker_runs%ROWTYPE;
    BEGIN
      SELECT * INTO r FROM public.checker_runs WHERE id=NEW.id;
      IF NOT FOUND OR (r.material_custody IS NULL) <> (r.input_materialization_evidence_id IS NULL)
        OR (r.input_materialization_evidence_id IS NOT NULL AND (
          r.status NOT IN ('completed','infrastructure_failed')
          OR r.input_materialization_evidence_id IN (r.execute_evidence_id,r.finalize_evidence_id)
          OR NOT public.checker_input_receipt_valid(r)))
      THEN RAISE EXCEPTION 'checker input authorization custody mismatch' USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER checker_input_receipt_custody AFTER INSERT OR UPDATE ON public.checker_runs
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_checker_input_receipt();
    """)


def _routing_authority():
    _execute_statements("""
    CREATE FUNCTION public.task_routing_resource_digest(m public.task_post_submit_routing_manifests)
    RETURNS text LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE source jsonb := m.authority_context->'source'; commitment jsonb; source_digest text;
    BEGIN
      source_digest := 'sha256:' || encode(sha256(convert_to(public.project_guide_projection_canonical_json(
        jsonb_build_object('domain','workstream.task_post_submit_source.v0.1','source',source)), 'UTF8')), 'hex');
      SELECT jsonb_object_agg(key,value) INTO commitment FROM jsonb_each(source)
      WHERE key=ANY(ARRAY['project_id','task_id','assignment_id','submission_id','submission_version',
        'contributor_id','contribution_policy_version_id','checker_run_id','evaluation_request_id',
        'evaluation_generation','result_id','completion_event_id','human_review_required',
        'content_id','content_sha256','semantic_manifest_sha256']);
      commitment := commitment || jsonb_build_object('source','task_post_submit_route',
        'routing_manifest_id',m.id::text,'routing_source_digest',source_digest,
        'locked_review_policy_id',source#>'{locked_policy,locked_review_policy_id}',
        'locked_review_policy_generation',source#>'{locked_policy,locked_review_policy_generation}',
        'locked_review_policy_hash',source#>'{locked_policy,locked_review_policy_hash}',
        'route_operation_id',m.authority_context#>'{request,route_operation_id}',
        'route_request_digest',m.authority_context#>'{request,route_request_digest}');
      RETURN 'sha256:' || encode(sha256(convert_to(public.project_guide_projection_canonical_json(
        jsonb_build_object('domain','workstream.authorization.task_post_submit_route.v0.1',
          'resource_type','task_post_submit_routing_manifest','resource_id',m.id::text,
          'project_id',m.project_id::text,'router_actor_id',m.router_actor_id::text,
          'router_identity_link_id',m.router_identity_link_id::text,
          'request',jsonb_build_object('routing_request',m.authority_context->'request'),
          'source_commitment_digest','sha256:' || encode(sha256(convert_to(
            public.project_guide_projection_canonical_json(jsonb_build_object(
              'domain','workstream.authorization.acceptance_source.v0.1','source',commitment)), 'UTF8')), 'hex'),
          'claim',m.authority_context->'claim','consequence',m.authority_context->'consequence')), 'UTF8')), 'hex');
    END $$;

    CREATE FUNCTION public.task_routing_receipt_valid(m public.task_post_submit_routing_manifests)
    RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
      SELECT EXISTS(SELECT 1 FROM public.audit_events a
        JOIN public.actor_profiles p ON p.id=m.router_actor_id AND a.actor_id=p.id::text
        JOIN public.actor_identity_links l ON l.id=m.router_identity_link_id AND l.actor_profile_id=p.id
        WHERE a.id=m.authorization_decision_id AND p.actor_kind='service'
          AND p.service_identity='workstream.task.post_submit_router' AND l.subject_kind='service'
          AND a.actor_ref_kind='actor_profile' AND a.event_domain='authority'
          AND a.event_type='SensitiveAuthorizationAllowed'
          AND a.action_id='task.post_submit.route' AND a.permission_id=a.action_id
          AND a.denial_code IS NULL AND a.matched_grant_id IS NULL
          AND a.project_id=m.project_id AND a.resource_type='task_post_submit_routing_manifest'
          AND a.resource_id=m.id::text AND a.target_ref_kind='project' AND a.target_ref_id=m.project_id::text
          AND a.request_id::text=m.authority_context#>>'{request,route_operation_id}'
          AND a.correlation_id=a.request_id
          AND a.after_facts::jsonb=jsonb_build_object('allowed',true,
            'resource_context_digest',public.task_routing_resource_digest(m)))
    $$;

    CREATE FUNCTION public.task_routing_acceptance_matches(
      p_manifest uuid,p_acceptance uuid,p_decision uuid,p_actor uuid,p_project uuid,p_task uuid,
      p_submission uuid,p_policy uuid,p_generation bigint,p_is_new boolean)
    RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
      SELECT EXISTS(SELECT 1 FROM public.task_post_submit_routing_manifests m
        JOIN public.joint_lifecycle_release_control c ON c.singleton
        WHERE m.id=p_manifest AND m.final_acceptance_id=p_acceptance
          AND m.authorization_decision_id=p_decision AND m.router_actor_id=p_actor
          AND m.project_id=p_project AND m.task_id=p_task AND m.submission_id=p_submission
          AND m.authority_context#>>'{source,locked_policy,locked_review_policy_id}'=p_policy::text
          AND NOT m.human_review_required AND m.authorized_lifecycle_generation>0
          AND c.generation=p_generation
          AND (NOT p_is_new OR (c.phase='live' AND m.authorized_lifecycle_generation=c.generation))
          AND public.task_routing_receipt_valid(m))
    $$;
    """)


def _closure():
    _execute_statements("""
    CREATE FUNCTION public.task_routing_context_valid(m public.task_post_submit_routing_manifests)
    RETURNS boolean LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE s public.submissions%ROWTYPE; d public.submission_dispatches%ROWTYPE;
      r public.checker_runs%ROWTYPE; q public.task_post_submit_routing_requests%ROWTYPE;
      policy jsonb; source jsonb; consequence jsonb; context jsonb;
    BEGIN
      SELECT * INTO s FROM public.submissions WHERE id=m.submission_id AND task_id=m.task_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO d FROM public.submission_dispatches WHERE submission_id=s.id AND project_id=m.project_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO r FROM public.checker_runs WHERE id=m.checker_run_id AND submission_id=s.id;
      IF NOT FOUND OR NOT public.checker_input_receipt_valid(r) THEN RETURN false; END IF;
      SELECT * INTO q FROM public.task_post_submit_routing_requests WHERE routing_manifest_id=m.id;
      IF NOT FOUND OR q.project_id<>m.project_id OR q.task_id<>m.task_id
        OR q.submission_id<>m.submission_id OR q.submission_version<>m.submission_version
        OR q.checker_run_id<>m.checker_run_id OR q.evaluation_request_id<>m.evaluation_request_id
        OR q.evaluation_request_digest<>m.request_digest OR q.evaluation_generation<>m.evaluation_generation
        OR q.result_id<>m.result_id OR q.result_digest<>m.result_digest
        OR q.completion_event_id<>m.completion_event_id OR q.routing_recommendation<>'allow_review'
      THEN RETURN false; END IF;
      SELECT jsonb_object_agg(key,value) INTO policy FROM jsonb_each(to_jsonb(s))
      WHERE key=ANY(ARRAY['locked_guide_version','locked_guide_source_snapshot_id','locked_guide_source_snapshot_hash',
        'locked_effective_project_submission_artifact_policy_id','locked_effective_project_submission_artifact_policy_hash',
        'locked_pre_submit_checker_policy_id','locked_pre_submit_checker_bundle_hash',
        'locked_post_submit_checker_policy_id','locked_post_submit_checker_policy_version','locked_post_submit_checker_policy_hash',
        'locked_review_policy_id','locked_review_policy_generation','locked_review_policy_hash',
        'locked_revision_policy_id','locked_revision_policy_generation','locked_revision_policy_hash']);
      policy := policy || jsonb_build_object('locked_contribution_policy_version_id',s.contribution_policy_version_id::text);
      source := (to_jsonb(m)-ARRAY['created_at','authorization_decision_id','router_actor_id','router_identity_link_id',
        'authority_context','final_acceptance_id','authorized_lifecycle_generation','audit_event_id','outcome_event_id']) ||
        jsonb_build_object('predecessor_submission_id',s.supersedes_submission_id::text,
          'predecessor_submission_version',CASE WHEN s.supersedes_submission_id IS NOT NULL THEN s.version-1 ELSE NULL END,
          'admission_id',s.submission_bundle_admission_id::text,'binding_id',s.artifact_binding_id::text,
          'content_id',s.artifact_content_id::text,'locked_policy',policy,'routing_recommendation','allow_review',
          'creation_decision_id',d.creation_decision_id::text,'binding_decision_id',d.binding_decision_id::text,
          'input_materialization_evidence_id',r.input_materialization_evidence_id::text);
      IF m.human_review_required THEN
        IF m.final_acceptance_id IS NOT NULL OR m.authorized_lifecycle_generation IS NOT NULL THEN RETURN false; END IF;
        consequence := jsonb_build_object('kind','human_admission',
          'expected_task_status','evaluation_pending','target_task_status','review_pending');
      ELSE
        IF m.final_acceptance_id IS NULL OR m.authorized_lifecycle_generation IS NULL
          OR m.authorized_lifecycle_generation<=0 THEN RETURN false; END IF;
        consequence := jsonb_build_object('kind','final_acceptance',
          'authorized_lifecycle_generation',m.authorized_lifecycle_generation,
          'task_effects',jsonb_build_object('project_id',m.project_id::text,'task_id',m.task_id::text,
            'assignment_id',m.assignment_id::text,'submission_id',m.submission_id::text,
            'submission_version',m.submission_version,'contributor_id',m.contributor_id::text,
            'contribution_policy_version_id',m.contribution_policy_version_id::text,
            'content_id',s.artifact_content_id::text,'content_sha256',m.content_sha256,
            'final_acceptance_id',m.final_acceptance_id::text,'expected_task_status','evaluation_pending'));
      END IF;
      context := jsonb_build_object('resource_type','task_post_submit_routing_manifest','resource_id',m.id::text,
        'scope_project_id',m.project_id::text,'source',source,
        'router_actor_id',m.router_actor_id::text,'router_identity_link_id',m.router_identity_link_id::text,
        'request',(to_jsonb(q)-'created_at') || jsonb_build_object('created_at',replace(public.outbox_dispatch_utc(q.created_at),'+00:00','Z')),
        'claim',m.authority_context->'claim','consequence',consequence);
      RETURN m.authority_context=context AND public.task_routing_receipt_valid(m);
    END $$;

    CREATE FUNCTION public.guard_task_routing_authority() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE a public.outbox_delivery_attempts%ROWTYPE; e public.outbox_events%ROWTYPE; expected_claim jsonb;
    BEGIN
      -- Follow the same REV -> TASK -> Assignment -> Submission -> CHECKERS order
      -- as the owner. These locks retain currentness through the caller commit.
      IF NOT NEW.human_review_required THEN
        PERFORM 1 FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE;
      END IF;
      PERFORM 1 FROM public.workstream_tasks WHERE id=NEW.task_id AND project_id=NEW.project_id
        AND status='evaluation_pending' AND assigned_to=NEW.contributor_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing task is not current' USING ERRCODE='23514'; END IF;
      PERFORM 1 FROM public.task_assignments WHERE id=NEW.assignment_id AND task_id=NEW.task_id
        AND contributor_id=NEW.contributor_id AND status='active' AND accepted_at IS NOT NULL
        AND released_at IS NULL FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing assignment is not current' USING ERRCODE='23514'; END IF;
      PERFORM 1 FROM public.submissions s WHERE s.id=NEW.submission_id AND s.task_id=NEW.task_id
        AND NOT EXISTS(SELECT 1 FROM public.submissions successor
          WHERE successor.task_id=s.task_id AND successor.version>s.version) FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing submission is not current' USING ERRCODE='23514'; END IF;
      PERFORM 1 FROM public.checker_submission_fences
        WHERE submission_id=NEW.submission_id AND current_run_id=NEW.checker_run_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing evaluation is not current' USING ERRCODE='23514'; END IF;
      IF NOT public.task_routing_context_valid(NEW) THEN
        RAISE EXCEPTION 'routing source authority context mismatch' USING ERRCODE='23514'; END IF;
      IF NOT EXISTS(SELECT 1 FROM public.actor_profiles p JOIN public.actor_identity_links l ON l.actor_profile_id=p.id
        WHERE p.id=NEW.router_actor_id AND l.id=NEW.router_identity_link_id AND p.status='active' AND l.status='active')
      THEN RAISE EXCEPTION 'routing principal is not active' USING ERRCODE='23514'; END IF;
      SELECT * INTO e FROM public.outbox_events WHERE event_id=NEW.completion_event_id AND project_id=NEW.project_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      SELECT * INTO a FROM public.outbox_delivery_attempts
        WHERE event_id=e.event_id AND claim_generation=e.claim_generation FOR UPDATE;
      IF NOT FOUND OR a.stage<>'invoked' OR a.finalize_decision_event_id IS NOT NULL
        OR a.claim_expires_at<=clock_timestamp() OR a.project_id<>NEW.project_id
      THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      expected_claim := jsonb_build_object('event_id',a.event_id::text,'project_id',a.project_id::text,
        'payload_digest',a.payload_digest,'claim_generation',a.claim_generation,'claim_owner',a.claim_owner,
        'claimed_at',replace(public.outbox_dispatch_utc(a.claimed_at),'+00:00','Z'),'claim_expires_at',replace(public.outbox_dispatch_utc(a.claim_expires_at),'+00:00','Z'));
      IF NEW.authority_context->'claim' IS DISTINCT FROM expected_claim THEN
        RAISE EXCEPTION 'routing invocation differs' USING ERRCODE='23514'; END IF;
      IF NOT NEW.human_review_required AND NOT EXISTS(SELECT 1 FROM public.joint_lifecycle_release_control c
        WHERE c.singleton AND c.phase='live' AND c.generation=NEW.authorized_lifecycle_generation)
      THEN RAISE EXCEPTION 'routing acceptance generation unavailable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER task_routing_authority BEFORE INSERT ON public.task_post_submit_routing_manifests
      FOR EACH ROW EXECUTE FUNCTION public.guard_task_routing_authority();

    CREATE FUNCTION public.task_routing_outcome_complete(m public.task_post_submit_routing_manifests)
    RETURNS boolean LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE task_status text; assignment_status text; refs jsonb; notice jsonb; f public.final_acceptances%ROWTYPE;
      c public.contribution_records%ROWTYPE;
    BEGIN
      IF NOT public.task_routing_context_valid(m) THEN RETURN false; END IF;
      SELECT status INTO task_status FROM public.workstream_tasks WHERE id=m.task_id AND project_id=m.project_id;
      SELECT status INTO assignment_status FROM public.task_assignments WHERE id=m.assignment_id AND task_id=m.task_id;
      IF task_status IS DISTINCT FROM (CASE WHEN m.human_review_required THEN 'review_pending' ELSE 'accepted' END)
        OR assignment_status IS DISTINCT FROM (CASE WHEN m.human_review_required THEN 'active' ELSE 'completed' END)
      THEN RETURN false; END IF;
      refs := jsonb_build_object('project_id',m.project_id::text,'task_id',m.task_id::text,
        'submission_id',m.submission_id::text,'assignment_id',m.assignment_id::text,
        'authorization_decision_id',m.authorization_decision_id::text,'routing_manifest_id',m.id::text);
      IF NOT EXISTS(SELECT 1 FROM public.audit_events a WHERE a.id=m.audit_event_id
        AND a.entity_type='task' AND a.entity_id=m.task_id AND a.event_type='TaskPostSubmitRouted'
        AND a.actor_id=m.router_actor_id::text AND a.auth_source='local_lifecycle'
        AND a.from_status='evaluation_pending' AND a.to_status=task_status
        AND a.event_payload::jsonb=jsonb_build_object('references',refs)) THEN RETURN false; END IF;
      notice := jsonb_build_object('routing_manifest_id',m.id::text,'task_id',m.task_id::text,
        'submission_id',m.submission_id::text,'authorization_decision_id',m.authorization_decision_id::text,
        'human_review_required',m.human_review_required,'final_acceptance_id',m.final_acceptance_id::text);
      IF NOT EXISTS(SELECT 1 FROM public.outbox_events e WHERE e.event_id=m.outcome_event_id
        AND e.event_type='TaskPostSubmitRouted' AND e.event_version=1 AND e.aggregate_type='task'
        AND e.aggregate_id=m.task_id AND e.project_id=m.project_id AND e.payload::jsonb=notice
        AND e.causation_event_id=m.completion_event_id
        AND e.correlation_id=m.authority_context#>>'{request,route_operation_id}'
        AND e.idempotency_key='task-routed:' || m.id::text) THEN RETURN false; END IF;
      IF m.human_review_required THEN
        RETURN NOT EXISTS(SELECT 1 FROM public.final_acceptances WHERE source_routing_manifest_id=m.id);
      END IF;
      SELECT * INTO f FROM public.final_acceptances WHERE id=m.final_acceptance_id;
      IF NOT FOUND OR f.acceptance_source<>'task_post_submit_route' OR f.source_review_id IS NOT NULL
        OR f.source_routing_manifest_id IS DISTINCT FROM m.id OR f.project_id<>m.project_id
        OR f.task_id<>m.task_id OR f.submission_id<>m.submission_id OR f.accepted_submitter_id<>m.contributor_id
        OR f.recorded_by<>m.router_actor_id OR f.source_authorization_decision_id<>m.authorization_decision_id
        OR f.policy_context_ref::text IS DISTINCT FROM m.authority_context#>>'{source,locked_policy,locked_review_policy_id}'
      THEN RETURN false; END IF;
      SELECT * INTO c FROM public.contribution_records WHERE source_final_acceptance_id=f.id;
      IF NOT FOUND OR c.contribution_type<>'accepted_submission' OR c.project_id<>m.project_id
        OR c.task_id<>m.task_id OR c.submission_id<>m.submission_id OR c.contributor_id<>m.contributor_id
        OR c.source_task_assignment_id<>m.assignment_id OR c.artifact_hash<>m.content_sha256
        OR c.contribution_policy_version_id<>m.contribution_policy_version_id
      THEN RETURN false; END IF;
      refs := jsonb_build_object('project_id',m.project_id::text,'task_id',m.task_id::text,
        'submission_id',m.submission_id::text,'assignment_id',m.assignment_id::text,
        'final_acceptance_id',f.id::text,'contribution_record_id',c.id::text);
      IF NOT EXISTS(SELECT 1 FROM public.audit_events a WHERE a.entity_type='contribution'
        AND a.entity_id=c.id AND a.event_type='SubmitterContributionRecorded'
        AND a.actor_id=m.router_actor_id::text AND a.auth_source='local_lifecycle'
        AND a.from_status IS NULL AND a.to_status IS NULL
        AND a.event_payload::jsonb=jsonb_build_object('references',refs)) THEN RETURN false; END IF;
      -- CON's existing deferred guard proves the complete governed award set;
      -- every retained award must also have its shared audit evidence.
      IF EXISTS(SELECT 1 FROM public.compensation_awards w WHERE w.contribution_record_id=c.id
        AND NOT EXISTS(SELECT 1 FROM public.audit_events a WHERE a.entity_type='compensation_award'
          AND a.entity_id=w.id AND a.event_type='CompensationAwardCreated'
          AND a.actor_id=m.router_actor_id::text AND a.auth_source='local_lifecycle'
          AND a.from_status IS NULL AND a.to_status IS NULL
          AND a.event_payload::jsonb=jsonb_build_object('references',jsonb_build_object(
            'project_id',m.project_id::text,'compensation_award_id',w.id::text,
            'contribution_record_id',c.id::text)))) THEN RETURN false; END IF;
      RETURN true;
    END $$;

    CREATE FUNCTION public.guard_task_routing_closure() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE m public.task_post_submit_routing_manifests%ROWTYPE;
    BEGIN
      IF TG_TABLE_NAME='audit_events' THEN
        SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE authorization_decision_id=NEW.id;
      ELSIF TG_TABLE_NAME='final_acceptances' THEN
        SELECT * INTO m FROM public.task_post_submit_routing_manifests
          WHERE id=NEW.source_routing_manifest_id AND final_acceptance_id=NEW.id;
      ELSE
        SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=NEW.id;
      END IF;
      IF NOT FOUND OR NOT public.task_routing_outcome_complete(m) THEN
        RAISE EXCEPTION 'routing authority requires its complete governed outcome' USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$;
    CREATE FUNCTION public.guard_task_accepted_routing_state() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE m public.task_post_submit_routing_manifests%ROWTYPE;
    BEGIN
      FOR m IN SELECT * FROM public.task_post_submit_routing_manifests
        WHERE NOT human_review_required AND
          ((TG_TABLE_NAME='workstream_tasks' AND task_id=NEW.id)
           OR (TG_TABLE_NAME='task_assignments' AND assignment_id=NEW.id))
      LOOP
        IF NOT public.task_routing_outcome_complete(m) THEN
          RAISE EXCEPTION 'accepted routing outcome is immutable' USING ERRCODE='23514'; END IF;
      END LOOP;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER task_accepted_routing_state AFTER UPDATE ON public.workstream_tasks
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_task_accepted_routing_state();
    CREATE CONSTRAINT TRIGGER assignment_accepted_routing_state AFTER UPDATE ON public.task_assignments
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_task_accepted_routing_state();
    CREATE CONSTRAINT TRIGGER task_routing_complete_outcome AFTER INSERT ON public.task_post_submit_routing_manifests
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_task_routing_closure();
    CREATE CONSTRAINT TRIGGER task_routing_authority_closure AFTER INSERT ON public.audit_events
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
      WHEN (NEW.action_id='task.post_submit.route' AND NEW.event_type='SensitiveAuthorizationAllowed')
      EXECUTE FUNCTION public.guard_task_routing_closure();
    CREATE CONSTRAINT TRIGGER final_acceptance_source_authority AFTER INSERT ON public.final_acceptances
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_task_routing_closure();
    """)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
