"""Bind post-submit execution and finalization to exact immutable AUTH receipts."""

from alembic import op
import sqlalchemy as sa

revision = "0010_post_submit_authority"
down_revision = "0009_checker_material_lineage"
branch_labels = None
depends_on = None


def _extend_constraint(table, name, anchor, replacement, count):
    definition = op.get_bind().execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
        "where conrelid=cast(:table as regclass) and conname=:name"
    ), {"table": "public." + table, "name": name}).scalar_one()
    if definition.count(anchor) != count:
        raise RuntimeError("post-submit authority constraint shape changed: " + name)
    op.execute(f"alter table public.{table} drop constraint {name}")
    op.execute(f"alter table public.{table} add constraint {name} " + definition.replace(anchor, replacement))


def upgrade():
    """Preserve provable custody and reject unprovable retained receipts without repair."""
    op.execute("set local search_path = pg_catalog, public, pg_temp")
    op.execute("lock table public.actor_profiles, public.actor_identity_links, public.checker_runs, public.audit_events in access exclusive mode")
    _extend_constraint(
        "actor_profiles", "ck_actor_profiles_kind_service_identity", "ARRAY[",
        "ARRAY[('workstream.checker.post_submit'::character varying)::text, ", 1,
    )
    _extend_constraint(
        "audit_events", "ck_audit_events_authority_registries",
        "('outbox.dispatch'::character varying)::text",
        "('outbox.dispatch'::character varying)::text, "
        "('checker.post_submit.execute'::character varying)::text, "
        "('checker.post_submit.finalize'::character varying)::text", 1,
    )
    _extend_constraint(
        "audit_events", "ck_audit_events_authority_privacy_bounds",
        "('outbox_event'::character varying)::text",
        "('outbox_event'::character varying)::text, ('checker_run'::character varying)::text", 1,
    )
    anchor = "(((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    addition = " OR ".join(
        f"(((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{action}'::text))"
        for action in ("checker.post_submit.execute", "checker.post_submit.finalize")
    )
    _extend_constraint("audit_events", "ck_audit_events_authorization_action_evidence", anchor, anchor + " OR " + addition, 2)
    _functions()
    op.execute("""
      DO $$ BEGIN
        IF EXISTS (
          SELECT 1 FROM public.checker_runs r
          WHERE (r.execute_evidence_id IS NOT NULL AND NOT public.checker_post_submit_receipt_valid(r,'execute',false))
             OR (r.finalize_evidence_id IS NOT NULL AND NOT public.checker_post_submit_receipt_valid(r,'finalize',false))
        ) THEN
          RAISE EXCEPTION 'retained checker authorization receipts are unprovable' USING ERRCODE='23514';
        END IF;
      END $$
    """)
    for phase in ("execute", "finalize"):
        op.create_foreign_key(
            f"fk_checker_runs_{phase}_evidence", "checker_runs", "audit_events",
            [f"{phase}_evidence_id"], ["id"], source_schema="public", referent_schema="public",
            deferrable=True, initially="DEFERRED",
        )
    op.execute("""
      CREATE CONSTRAINT TRIGGER checker_post_submit_receipt_custody
      AFTER INSERT OR UPDATE ON public.checker_runs
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
      EXECUTE FUNCTION public.guard_checker_post_submit_receipts()
    """)


def _functions():
    op.execute("""
      CREATE FUNCTION public.checker_post_submit_authority_digest(r public.checker_runs, phase text)
      RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog, public, pg_temp AS $$
        SELECT CASE WHEN $2 IN ('execute','finalize') THEN
          'sha256:' || encode(sha256(convert_to(public.project_guide_projection_canonical_json(
            jsonb_build_object(
              'domain','workstream.authorization.checker_post_submit', 'phase',$2,
              'action_id','checker.post_submit.' || $2, 'permission_id','checker.post_submit.' || $2,
              'service_identity','workstream.checker.post_submit',
              'resource_type','checker_run', 'resource_id',r.id::text, 'scope_project_id',r.project_id::text,
              'facts',jsonb_build_object(
                'project_id',r.project_id::text, 'task_id',r.task_id::text,
                'submission_id',r.submission_id::text, 'submission_version',r.submission_version,
                'request_id',r.evaluation_request_id::text, 'request_digest',r.request_digest,
                'evaluation_generation',r.evaluation_generation,
                'attempt_id',r.id::text, 'result_id',r.result_id::text,
                'lease_id',r.worker_lease_id::text, 'lease_generation',r.worker_lease_generation,
                'lease_expires_at',public.outbox_dispatch_utc(r.worker_lease_expires_at)
              ) || CASE WHEN $2='finalize' THEN jsonb_build_object(
                'execute_evidence_id',r.execute_evidence_id::text,
                'result_digest',r.result_digest, 'outcome',r.status, 'failure_code',r.failure_code,
                'material',r.material_custody::jsonb, 'output_binding_ids','[]'::jsonb
              ) ELSE '{}'::jsonb END
            )), 'UTF8')), 'hex') ELSE NULL END
      $$
    """)
    op.execute("""
      CREATE FUNCTION public.checker_post_submit_receipt_valid(r public.checker_runs, phase text, require_active boolean)
      RETURNS boolean LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
        SELECT coalesce(EXISTS (
          SELECT 1 FROM public.audit_events a
          JOIN public.actor_profiles p ON p.id::text=a.actor_id
          JOIN public.actor_identity_links l ON l.actor_profile_id=p.id
          WHERE a.id=CASE WHEN $2='execute' THEN r.execute_evidence_id ELSE r.finalize_evidence_id END
            AND $2 IN ('execute','finalize')
            AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
            AND a.actor_ref_kind='actor_profile'
            AND p.actor_kind='service' AND p.service_identity='workstream.checker.post_submit'
            AND l.subject_kind='service'
            AND (NOT $3 OR (p.status='active' AND l.status='active'))
            AND a.action_id='checker.post_submit.' || $2 AND a.permission_id=a.action_id
            AND a.denial_code IS NULL AND a.matched_grant_id IS NULL
            AND a.project_id=r.project_id AND a.resource_type='checker_run' AND a.resource_id=r.id::text
            AND a.target_ref_kind='project' AND a.target_ref_id=r.project_id::text
            AND a.request_id=r.evaluation_request_id AND a.correlation_id=r.evaluation_request_id
            AND a.after_facts::jsonb=jsonb_build_object(
              'allowed',true,'resource_context_digest',public.checker_post_submit_authority_digest(r,$2)
            )
            AND ($2='execute' OR (r.execute_evidence_id IS NOT NULL
                                 AND r.finalize_evidence_id IS DISTINCT FROM r.execute_evidence_id
                                 AND r.status IN ('completed','infrastructure_failed')))
        ),false)
      $$
    """)
    op.execute("""
      CREATE FUNCTION public.guard_checker_post_submit_receipts() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
      DECLARE current_run public.checker_runs%ROWTYPE; new_execute boolean; new_finalize boolean;
      BEGIN
        SELECT r.* INTO current_run FROM public.checker_runs r WHERE r.id=NEW.id;
        IF NOT FOUND THEN
          RAISE EXCEPTION 'checker authorization receipt parent is missing' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          new_execute := current_run.execute_evidence_id IS NOT NULL;
          new_finalize := current_run.finalize_evidence_id IS NOT NULL;
        ELSE
          new_execute := current_run.execute_evidence_id IS DISTINCT FROM OLD.execute_evidence_id;
          new_finalize := current_run.finalize_evidence_id IS DISTINCT FROM OLD.finalize_evidence_id;
        END IF;
        IF (current_run.execute_evidence_id IS NOT NULL AND NOT
              public.checker_post_submit_receipt_valid(current_run,'execute',new_execute))
           OR (current_run.finalize_evidence_id IS NOT NULL AND NOT
              public.checker_post_submit_receipt_valid(current_run,'finalize',new_finalize)) THEN
          RAISE EXCEPTION 'checker authorization receipt custody mismatch' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END $$
    """)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
