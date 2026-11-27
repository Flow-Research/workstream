"""Bind one scheduled POST successor to a known service-finalized failure."""

from alembic import op
import sqlalchemy as sa

revision = "0095_post_infrastructure_retry"
down_revision = "0094_project_archive_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extend the failed-supersession guard with an exact automatic source."""
    op.add_column("checker_runs", sa.Column("retry_delivery_event_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_checker_runs_retry_delivery_event_id", "checker_runs", ["retry_delivery_event_id"],
    )
    op.create_foreign_key(
        "fk_checker_runs_retry_delivery_event", "checker_runs", "outbox_events",
        ["retry_delivery_event_id"], ["event_id"],
    )
    op.add_column("checker_runs", sa.Column("retry_abandonment_event_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_checker_runs_retry_abandonment_event_id", "checker_runs", ["retry_abandonment_event_id"],
    )
    op.create_foreign_key(
        "fk_checker_runs_retry_abandonment_event", "checker_runs", "outbox_events",
        ["retry_abandonment_event_id"], ["event_id"],
    )
    op.create_check_constraint(
        op.f("ck_checker_runs_service_retry_scope"), "checker_runs",
        "(retry_abandonment_event_id IS NULL OR retry_delivery_event_id IS NOT NULL) AND "
        "(retry_delivery_event_id IS NULL OR (supersedes_checker_run_id IS NOT NULL "
        "AND (retry_abandonment_event_id IS NOT NULL OR evaluation_generation BETWEEN 2 AND 5)))",
    )
    op.execute(_ABANDONMENT_GUARD)
    op.execute("""
    CREATE OR REPLACE FUNCTION public.require_checker_failed_supersession_receipt() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE prior public.checker_runs%ROWTYPE; successor public.checker_runs%ROWTYPE; receipt_id uuid;
    BEGIN
      IF TG_OP <> 'UPDATE' THEN RETURN NULL; END IF;
      SELECT * INTO prior FROM public.checker_runs WHERE id=OLD.current_run_id;
      SELECT * INTO successor FROM public.checker_runs WHERE id=NEW.current_run_id;
      IF successor.retry_abandonment_event_id IS NOT NULL THEN
        IF NOT public.checker_post_submit_abandonment_valid(prior,successor) THEN
          RAISE EXCEPTION 'checker abandonment requires the exact expired invocation and Operator cause' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
      IF successor.retry_delivery_event_id IS NOT NULL THEN
        IF prior.status IS DISTINCT FROM 'infrastructure_failed'
          OR prior.completed_at IS NULL OR prior.completion_event_id IS NOT NULL
          OR prior.routing_recommendation IS DISTINCT FROM 'not_evaluated'
          OR prior.failure_code IS NULL OR prior.failure_code NOT IN ('capacity_exceeded','deadline_exceeded',
              'material_unavailable','implementation_unavailable','invalid_output')
          OR prior.evaluation_generation NOT BETWEEN 1 AND 4
          OR successor.supersedes_checker_run_id IS DISTINCT FROM prior.id
          OR successor.evaluation_generation IS DISTINCT FROM prior.evaluation_generation+1
          OR successor.request_json::jsonb - ARRAY['evaluation_request_id','evaluation_generation']
               IS DISTINCT FROM prior.request_json::jsonb - ARRAY['evaluation_request_id','evaluation_generation']
          OR NOT public.checker_post_submit_receipt_valid(prior,'finalize',false)
          OR NOT EXISTS (
            SELECT 1 FROM public.outbox_events e
            WHERE e.event_id=successor.retry_delivery_event_id
              AND e.event_type='PostSubmissionEvaluationRequested' AND e.event_version=1
              AND e.producer='workstream' AND e.aggregate_type='submission'
              AND e.project_id=successor.project_id AND e.aggregate_id=successor.submission_id
              AND e.correlation_id=prior.id::text AND e.causation_event_id IS NULL
              AND e.idempotency_key='checker-auto-retry:'||prior.id::text
              AND e.delivery_state='pending'
              AND e.not_before_at=prior.completed_at + CASE prior.evaluation_generation
                WHEN 1 THEN interval '5 seconds' WHEN 2 THEN interval '10 seconds'
                WHEN 3 THEN interval '20 seconds' WHEN 4 THEN interval '40 seconds' END
              AND e.payload::jsonb=jsonb_build_object(
                'project_id',successor.project_id,'task_id',successor.task_id,
                'submission_id',successor.submission_id,'submission_version',successor.submission_version,
                'request_id',successor.evaluation_request_id,'request_digest',successor.request_digest,
                'evaluation_generation',successor.evaluation_generation,'attempt_id',successor.id,
                'result_id',successor.result_id,'source_run_id',prior.id,
                'source_result_digest',prior.result_digest,'source_finalize_evidence_id',prior.finalize_evidence_id
              )
          ) THEN
          RAISE EXCEPTION 'automatic checker retry requires exact terminal service custody' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
      IF prior.status IS DISTINCT FROM 'infrastructure_failed' THEN RETURN NULL; END IF;
      SELECT id INTO receipt_id FROM public.checker_retry_receipts
        WHERE source_run_id=OLD.current_run_id AND successor_run_id=NEW.current_run_id;
      IF receipt_id IS NULL OR NOT public.checker_retry_receipt_valid(receipt_id) THEN
        RAISE EXCEPTION 'terminal checker infrastructure retry requires Operator receipt' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$
    """)


def downgrade() -> None:
    """Keep scheduled successor references valid for their retained runs."""
    raise RuntimeError("POST infrastructure retry migration is forward-only")


_ABANDONMENT_GUARD = """
CREATE FUNCTION public.checker_post_submit_abandonment_valid(
  source public.checker_runs, successor public.checker_runs
) RETURNS boolean LANGUAGE sql SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT coalesce(source.status='running' AND source.result_json IS NULL
    AND source.worker_lease_id IS NOT NULL AND source.worker_lease_expires_at<=clock_timestamp()
    AND successor.supersedes_checker_run_id=source.id
    AND successor.evaluation_generation=source.evaluation_generation+1
    AND successor.request_json::jsonb - ARRAY['evaluation_request_id','evaluation_generation']
          = source.request_json::jsonb - ARRAY['evaluation_request_id','evaluation_generation']
    AND EXISTS (
      SELECT 1 FROM public.outbox_events c
      JOIN public.outbox_delivery_attempts ca ON ca.event_id=c.event_id AND ca.claim_generation=c.claim_generation
      JOIN public.outbox_events o ON o.event_id=c.causation_event_id
      JOIN public.outbox_delivery_attempts oa ON oa.event_id=o.event_id AND oa.claim_generation=o.claim_generation
      JOIN public.audit_events a ON a.id::text=c.payload->>'authorization_decision_id'
      JOIN public.actor_profiles actor ON actor.id::text=a.actor_id AND actor.actor_kind='human'
      JOIN public.admin_role_grants g ON g.id::text=a.matched_grant_id AND g.target_actor_profile_id=actor.id
      JOIN public.actor_identity_links l ON l.actor_profile_id=actor.id
        AND l.id::text=c.payload->>'operator_identity_link_id'
      JOIN public.outbox_events e ON e.event_id=successor.retry_delivery_event_id
      CROSS JOIN LATERAL (
        SELECT ((c.payload->>'authorization_resource_json')::jsonb)->'resource_context' AS data
      ) r
      WHERE c.event_id=successor.retry_abandonment_event_id
        AND o.event_type='PostSubmissionEvaluationRequested' AND o.event_version=1
        AND o.project_id=source.project_id AND o.aggregate_id=source.submission_id
        AND o.payload->>'request_id'=source.evaluation_request_id::text
        AND o.payload->>'request_digest'=source.request_digest
        AND o.payload->>'attempt_id'=source.id::text
        AND o.delivery_state='dead_letter' AND o.last_error_code='INVOKE_OUTCOME_UNKNOWN'
        AND oa.stage='completed' AND oa.finalize_decision_event_id IS NOT NULL
        AND oa.payload_digest=o.payload_digest AND oa.project_id=o.project_id
        AND oa.outcome_json::jsonb->>'invocation_unknown'='true'
        AND c.event_type='PostSubmissionDeliveryReconciliationRequested' AND c.event_version=1
        AND c.producer='workstream' AND c.project_id=o.project_id
        AND c.aggregate_type='outbox_delivery' AND c.aggregate_id=o.event_id
        AND c.idempotency_key='post-submit-reconcile:'||o.event_id::text
        AND c.delivery_state='claimed' AND ca.stage='invoked' AND ca.claim_expires_at>clock_timestamp()
        AND ca.project_id=c.project_id AND ca.payload_digest=c.payload_digest
        AND ca.finalize_decision_event_id IS NULL
        AND c.payload->>'classification'='unresolved'
        AND c.payload->>'checker_run_id'=source.id::text
        AND c.payload->>'evaluation_request_id'=source.evaluation_request_id::text
        AND c.payload->>'evaluation_generation'=source.evaluation_generation::text
        AND c.payload->>'original_event_id'=o.event_id::text
        AND c.payload->>'original_event_type'=o.event_type
        AND c.payload->>'original_event_version'=o.event_version::text
        AND c.payload->>'original_claim_generation'=oa.claim_generation::text
        AND c.payload->>'original_payload_digest'=o.payload_digest
        AND c.payload#>>'{abandonment,lease_id}'=source.worker_lease_id::text
        AND c.payload#>>'{abandonment,lease_generation}'=source.worker_lease_generation::text
        AND (c.payload#>>'{abandonment,expires_at}')::timestamptz=source.worker_lease_expires_at
        AND r.data#>'{preparation,abandonment}'=c.payload->'abandonment'
        AND r.data->>'resource_type'='outbox_delivery'
        AND r.data->>'resource_id'=o.event_id::text AND r.data->>'scope_project_id'=source.project_id::text
        AND r.data->>'identity_link_id'=l.id::text
        AND r.data#>>'{preparation,command,action}'='abandon_unknown'
        AND r.data#>>'{preparation,command,actor_profile_id}'=actor.id::text
        AND r.data#>>'{preparation,command,event_id}'=o.event_id::text
        AND r.data#>>'{preparation,command,project_id}'=source.project_id::text
        AND r.data#>>'{preparation,command,request_key}'=a.request_id::text
        AND r.data#>>'{preparation,source,event_id}'=o.event_id::text
        AND r.data#>>'{preparation,source,checker_run_id}'=source.id::text
        AND r.data#>>'{preparation,source,classification}'='unresolved'
        AND g.role='operator' AND g.scope_type='system' AND g.scope_project_id IS NULL
        AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
        AND a.actor_ref_kind='actor_profile' AND a.actor_id=c.payload->>'operator_actor_profile_id'
        AND a.project_id=source.project_id AND a.action_id='operations.post_submit_delivery.reconcile'
        AND a.permission_id='operations.reconcile.run' AND a.resource_type='outbox_delivery'
        AND a.resource_id=o.event_id::text AND a.request_id::text=c.payload->>'reconciliation_request_id'
        AND a.correlation_id=a.request_id AND a.denial_code IS NULL
        AND a.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',
          'sha256:'||encode(sha256(convert_to(public.project_guide_projection_canonical_json(
            jsonb_strip_nulls(jsonb_build_object('resource_context',r.data))), 'UTF8')), 'hex'))
        AND e.event_type='PostSubmissionEvaluationRequested' AND e.event_version=1
        AND e.producer='workstream' AND e.aggregate_type='submission'
        AND e.project_id=successor.project_id AND e.aggregate_id=successor.submission_id
        AND e.correlation_id=source.id::text AND e.causation_event_id=c.event_id
        AND e.idempotency_key='checker-abandonment-retry:'||source.id::text
        AND e.delivery_state='pending' AND e.not_before_at IS NULL
        AND e.payload::jsonb=jsonb_build_object(
          'project_id',successor.project_id,'task_id',successor.task_id,
          'submission_id',successor.submission_id,'submission_version',successor.submission_version,
          'request_id',successor.evaluation_request_id,'request_digest',successor.request_digest,
          'evaluation_generation',successor.evaluation_generation,'attempt_id',successor.id,
          'result_id',successor.result_id,'source_run_id',source.id,
          'source_worker_lease_id',source.worker_lease_id,'source_worker_lease_generation',source.worker_lease_generation
        )
    ),false)
$$
"""
