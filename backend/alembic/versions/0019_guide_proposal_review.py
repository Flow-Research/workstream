"""Bind unified proposal approvals and correction successors to immutable custody."""

from alembic import op
from sqlalchemy import text
from scripts.schema_baseline_sql import split_sql_statements

revision = "0019_guide_proposal_review"
down_revision = "0018_guide_document_creation"
branch_labels = None
depends_on = None


def _execute(sql: str) -> None:
    for statement in split_sql_statements(sql):
        op.execute(statement)


def upgrade() -> None:
    _execute(r"""

CREATE TABLE project_guide_proposal_approvals (
	operation_id UUID NOT NULL,
	project_id VARCHAR(36) NOT NULL,
	guide_id VARCHAR(36) NOT NULL,
	compilation_id UUID NOT NULL,
	finalization_id UUID NOT NULL,
	target_json JSON NOT NULL,
	target_digest VARCHAR(71) NOT NULL,
	request_digest VARCHAR(71) NOT NULL,
	resource_context_digest VARCHAR(71) NOT NULL,
	output_digest VARCHAR(71) NOT NULL,
	receipt_json JSON NOT NULL,
	artifact_policy_id VARCHAR(36) NOT NULL,
	effective_policy_id VARCHAR(36) NOT NULL,
	pre_submit_policy_id VARCHAR(36) NOT NULL,
	approved_policy_output_digest VARCHAR(71) NOT NULL,
	effective_pre_submit_plan JSON NOT NULL,
	effective_pre_submit_plan_hash VARCHAR(71) NOT NULL,
	prior_approval_operation_id UUID,
	actor_profile_id VARCHAR(36) NOT NULL,
	identity_link_id VARCHAR(36) NOT NULL,
	admin_role_grant_id UUID NOT NULL,
	authorization_decision_event_id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_project_guide_proposal_approvals PRIMARY KEY (operation_id),
	CONSTRAINT fk_proposal_approval_compilation_scope FOREIGN KEY(compilation_id, project_id, guide_id) REFERENCES project_guide_compilations (id, project_id, guide_id),
	CONSTRAINT fk_proposal_approval_actor_link FOREIGN KEY(identity_link_id, actor_profile_id) REFERENCES actor_identity_links (id, actor_profile_id),
	CONSTRAINT uq_proposal_approval_finalization UNIQUE (finalization_id),
	CONSTRAINT uq_proposal_approval_prior UNIQUE (prior_approval_operation_id),
	CONSTRAINT uq_proposal_approval_artifact UNIQUE (artifact_policy_id),
	CONSTRAINT uq_proposal_approval_effective UNIQUE (effective_policy_id),
	CONSTRAINT uq_proposal_approval_pre UNIQUE (pre_submit_policy_id),
	CONSTRAINT uq_proposal_approval_decision UNIQUE (authorization_decision_event_id),
	CONSTRAINT ck_project_guide_proposal_approvals_ck_proposal_approva_1f0e CHECK (target_digest ~ '^sha256:[0-9a-f]{64}$' and request_digest ~ '^sha256:[0-9a-f]{64}$' and resource_context_digest ~ '^sha256:[0-9a-f]{64}$' and output_digest ~ '^sha256:[0-9a-f]{64}$' and approved_policy_output_digest ~ '^sha256:[0-9a-f]{64}$' and effective_pre_submit_plan_hash ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_project_guide_proposal_approvals_ck_proposal_approval_sizes CHECK (octet_length(target_json::text) <= 16384 and octet_length(receipt_json::text) <= 32768 and octet_length(effective_pre_submit_plan::text) <= 4194304),
	CONSTRAINT fk_project_guide_proposal_approvals_operation_id_submis_cdf3 FOREIGN KEY(operation_id) REFERENCES submission_policy_mutation_idempotency_records (operation_id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT fk_project_guide_proposal_approvals_finalization_id_pro_a505 FOREIGN KEY(finalization_id) REFERENCES project_guide_setup_finalizations (id),
	CONSTRAINT fk_project_guide_proposal_approvals_artifact_policy_id__74ba FOREIGN KEY(artifact_policy_id) REFERENCES submission_artifact_policies (id),
	CONSTRAINT fk_project_guide_proposal_approvals_effective_policy_id_e004 FOREIGN KEY(effective_policy_id) REFERENCES effective_project_submission_artifact_policies (id),
	CONSTRAINT fk_project_guide_proposal_approvals_pre_submit_policy_i_020c FOREIGN KEY(pre_submit_policy_id) REFERENCES pre_submit_checker_policies (id),
	CONSTRAINT fk_project_guide_proposal_approvals_prior_approval_oper_464d FOREIGN KEY(prior_approval_operation_id) REFERENCES project_guide_proposal_approvals (operation_id),
	CONSTRAINT fk_project_guide_proposal_approvals_actor_profile_id_ac_138f FOREIGN KEY(actor_profile_id) REFERENCES actor_profiles (id),
	CONSTRAINT fk_project_guide_proposal_approvals_admin_role_grant_id_c2fe FOREIGN KEY(admin_role_grant_id) REFERENCES admin_role_grants (id),
	CONSTRAINT fk_project_guide_proposal_approvals_authorization_decis_0fd3 FOREIGN KEY(authorization_decision_event_id) REFERENCES audit_events (id)
)

;

CREATE TABLE project_guide_proposal_corrections (
	operation_id UUID NOT NULL,
	idempotency_key UUID NOT NULL,
	project_id VARCHAR(36) NOT NULL,
	guide_id VARCHAR(36) NOT NULL,
	compilation_id UUID NOT NULL,
	finalization_id UUID NOT NULL,
	target_json JSON NOT NULL,
	target_digest VARCHAR(71) NOT NULL,
	request_digest VARCHAR(71) NOT NULL,
	resource_context_digest VARCHAR(71) NOT NULL,
	resource_context_json JSON NOT NULL,
	output_digest VARCHAR(71) NOT NULL,
	receipt_json JSON NOT NULL,
	reason TEXT NOT NULL,
	feedback_hash VARCHAR(71) NOT NULL,
	successor_setup_run_id VARCHAR(36) NOT NULL,
	successor_setup_generation BIGINT NOT NULL,
	actor_profile_id VARCHAR(36) NOT NULL,
	identity_link_id VARCHAR(36) NOT NULL,
	admin_role_grant_id UUID NOT NULL,
	authorization_decision_event_id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_project_guide_proposal_corrections PRIMARY KEY (operation_id),
	CONSTRAINT fk_proposal_correction_compilation_scope FOREIGN KEY(compilation_id, project_id, guide_id) REFERENCES project_guide_compilations (id, project_id, guide_id),
	CONSTRAINT fk_proposal_correction_actor_link FOREIGN KEY(identity_link_id, actor_profile_id) REFERENCES actor_identity_links (id, actor_profile_id),
	CONSTRAINT uq_proposal_correction_key UNIQUE (actor_profile_id, idempotency_key),
	CONSTRAINT uq_proposal_correction_predecessor UNIQUE (finalization_id),
	CONSTRAINT uq_proposal_correction_successor UNIQUE (successor_setup_run_id),
	CONSTRAINT uq_proposal_correction_decision UNIQUE (authorization_decision_event_id),
	CONSTRAINT ck_project_guide_proposal_corrections_ck_proposal_corre_0b4a CHECK (successor_setup_generation > 1),
	CONSTRAINT ck_project_guide_proposal_corrections_ck_proposal_corre_c4cb CHECK (target_digest ~ '^sha256:[0-9a-f]{64}$' and request_digest ~ '^sha256:[0-9a-f]{64}$' and resource_context_digest ~ '^sha256:[0-9a-f]{64}$' and feedback_hash ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_project_guide_proposal_corrections_ck_proposal_corre_ac60 CHECK (length(btrim(reason)) between 1 and 4000 and octet_length(reason) <= 16000 and octet_length(target_json::text) <= 16384),
	CONSTRAINT fk_project_guide_proposal_corrections_finalization_id_p_7d0c FOREIGN KEY(finalization_id) REFERENCES project_guide_setup_finalizations (id),
	CONSTRAINT fk_project_guide_proposal_corrections_successor_setup_r_db10 FOREIGN KEY(successor_setup_run_id) REFERENCES project_setup_runs (id),
	CONSTRAINT fk_project_guide_proposal_corrections_actor_profile_id__0d74 FOREIGN KEY(actor_profile_id) REFERENCES actor_profiles (id),
	CONSTRAINT fk_project_guide_proposal_corrections_admin_role_grant__7dce FOREIGN KEY(admin_role_grant_id) REFERENCES admin_role_grants (id),
	CONSTRAINT fk_project_guide_proposal_corrections_authorization_dec_47af FOREIGN KEY(authorization_decision_event_id) REFERENCES audit_events (id)
)

;
CREATE UNIQUE INDEX uq_proposal_approval_root_guide
ON project_guide_proposal_approvals (guide_id)
WHERE prior_approval_operation_id IS NULL;
    """)
    _custody()
    _audit_vocabulary()
    _reservation_custody()
    _setup_authority_shape()


def _custody() -> None:
    """Install exact target, authority and bidirectional product guards."""
    _execute("""
      ALTER TABLE project_setup_runs DROP CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_status;
      ALTER TABLE project_setup_runs ADD CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_status
      CHECK (status in ('awaiting_documents','correction_requested','queued','dispatch_pending',
        'enqueue_failed','enqueue_identity_mismatch','running_sufficiency_agent','sufficiency_blocked',
        'running_policy_derivation_agent','policy_draft_ready','running_post_submit_derivation_agent',
        'post_submit_setup_blocked','post_submit_policy_compiled','setup_blocked','failed'));

      CREATE FUNCTION guide_proposal_hash(value jsonb) RETURNS text
      LANGUAGE sql IMMUTABLE STRICT AS $$
        SELECT 'sha256:' || encode(sha256(convert_to(
          project_guide_projection_canonical_json(value), 'UTF8')), 'hex')
      $$;

      CREATE FUNCTION guide_proposal_resource(target jsonb, operation uuid, actor text, link text,
        action text, request_digest text, output_digest text, prior_id uuid, prior_digest text)
      RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
        SELECT jsonb_build_object(
          'locator', jsonb_build_object('project_id',target->>'project_id','guide_id',target->>'guide_id',
            'compilation_id',target->>'compilation_id','actor_profile_id',actor,'identity_link_id',link,
            'action_id',action,'operation_id',operation),
          'finalization_id',target->>'finalization_id','artifact_policy_id',target->'artifact_policy_id',
          'setup_run_id',target->>'setup_run_id','setup_generation',target->'setup_generation',
          'target_digest',guide_proposal_hash(target),'request_digest',request_digest,
          'output_digest',output_digest,'current_approval_operation_id',prior_id,
          'current_approval_output_digest',prior_digest)
      $$;

      CREATE FUNCTION require_guide_proposal_target(target jsonb, digest text, final_id uuid)
      RETURNS void LANGUAGE plpgsql AS $$
      DECLARE expected jsonb;
      BEGIN
        SELECT jsonb_build_object(
          'project_id',f.project_id,'guide_id',f.guide_id,'guide_version',f.guide_version,
          'compilation_id',f.compilation_id,'source_snapshot_id',f.source_snapshot_id,
          'source_snapshot_hash',f.source_snapshot_hash,'setup_run_id',f.setup_run_id,
          'setup_generation',f.setup_generation,'finalization_id',f.id,
          'finalization_facts_digest',f.facts_digest,'result_hash',f.result_hash,
          'component_hashes',f.component_hashes::jsonb,
          'pre_catalogue_id',a.pre_catalogue_id,'pre_catalogue_version',a.pre_catalogue_version,
          'pre_catalogue_schema_version',a.pre_catalogue_schema_version,
          'pre_catalogue_manifest_hash',a.pre_catalogue_manifest_hash,
          'post_catalogue_id',a.post_catalogue_id,'post_catalogue_version',a.post_catalogue_version,
          'post_catalogue_schema_version',a.post_catalogue_schema_version,
          'post_catalogue_manifest_hash',a.post_catalogue_manifest_hash,
          'artifact_policy_id',f.artifact_policy_id,'artifact_policy_hash',p.policy_hash,
          'artifact_projection_operation_id',f.artifact_policy_operation_id,
          'artifact_projection_output_digest',f.artifact_policy_output_digest
        ) INTO expected FROM project_guide_setup_finalizations f
        JOIN project_guide_compilations c ON c.id=f.compilation_id AND c.attempt_id=f.attempt_id
        JOIN project_guide_compilation_attempts a ON a.id=c.attempt_id
        LEFT JOIN submission_artifact_policies p ON p.id=f.artifact_policy_id
        WHERE f.id=final_id;
        IF expected IS NULL OR target IS DISTINCT FROM expected
           OR digest IS DISTINCT FROM guide_proposal_hash(expected) THEN
          RAISE EXCEPTION 'guide proposal target custody mismatch' USING ERRCODE='23514';
        END IF;
      END $$;

      CREATE FUNCTION require_guide_proposal_authority(actor text, link text, role_grant uuid,
        project text, decision text, action text, permission text, resource_kind text,
        resource text, digest text) RETURNS void LANGUAGE plpgsql AS $$
      DECLARE evidence audit_events%rowtype;
      BEGIN
        PERFORM 1 FROM actor_profiles a JOIN actor_identity_links l ON l.actor_profile_id=a.id
          JOIN admin_role_grants g ON g.target_actor_profile_id=a.id
          WHERE a.id=actor AND a.status='active' AND a.actor_kind='human'
            AND l.id=link AND l.status='active' AND l.subject_kind='human'
            AND g.id=role_grant AND g.status='active' AND g.role='project_manager'
            AND g.scope_type='project' AND g.scope_project_id=project FOR SHARE OF a,l,g;
        IF NOT FOUND THEN
          RAISE EXCEPTION 'guide proposal current authority missing' USING ERRCODE='23514';
        END IF;
        SELECT * INTO evidence FROM audit_events WHERE id=decision;
        IF evidence.id IS NULL OR evidence.event_domain IS DISTINCT FROM 'authority'
           OR evidence.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed'
           OR evidence.denial_code IS NOT NULL OR evidence.actor_ref_kind IS DISTINCT FROM 'actor_profile'
           OR evidence.actor_id IS DISTINCT FROM actor OR evidence.matched_grant_id IS DISTINCT FROM role_grant::text
           OR evidence.project_id IS DISTINCT FROM project OR evidence.action_id IS DISTINCT FROM action
           OR evidence.permission_id IS DISTINCT FROM permission OR evidence.resource_type IS DISTINCT FROM resource_kind
           OR evidence.resource_id IS DISTINCT FROM resource OR evidence.target_ref_kind IS DISTINCT FROM 'project'
           OR evidence.target_ref_id IS DISTINCT FROM project
           OR evidence.after_facts->>'allowed' IS DISTINCT FROM 'true'
           OR evidence.after_facts->>'resource_context_digest' IS DISTINCT FROM digest THEN
          RAISE EXCEPTION 'guide proposal authority evidence mismatch' USING ERRCODE='23514';
        END IF;
      END $$;

      CREATE FUNCTION reject_guide_proposal_change() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'guide proposal operation is immutable' USING ERRCODE='55000'; END $$;
    """)
    _approval_guards()
    _approved_content_guards()
    _correction_guards()
    _source_custody()
    for table in ("project_guide_proposal_approvals", "project_guide_proposal_corrections"):
        _execute(f"""
          CREATE TRIGGER immutable_guide_proposal_operation BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_guide_proposal_change();
          CREATE TRIGGER immutable_guide_proposal_operation_truncate BEFORE TRUNCATE ON {table}
            EXECUTE FUNCTION reject_guide_proposal_change();
        """)


def _approval_guards() -> None:
    _execute("""
      CREATE FUNCTION require_guide_proposal_approval() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE a project_guide_proposal_approvals%rowtype;
        r submission_policy_mutation_idempotency_records%rowtype;
        p submission_artifact_policies%rowtype;
        e effective_project_submission_artifact_policies%rowtype;
        pre pre_submit_checker_policies%rowtype;
        projection project_guide_component_projection_operations%rowtype;
        expected_receipt jsonb; warning_hashes jsonb;
        successor project_guide_proposal_approvals%rowtype;
        prior project_guide_proposal_approvals%rowtype;
      BEGIN
        IF tg_table_name='project_guide_proposal_approvals' THEN a:=new;
        ELSIF tg_table_name='submission_artifact_policies' THEN
          IF new.lifecycle_status NOT IN ('approved','superseded') THEN
            IF EXISTS(SELECT 1 FROM project_guide_proposal_approvals WHERE artifact_policy_id=new.id) THEN
              RAISE EXCEPTION 'approved proposal lifecycle cannot revert' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
          END IF;
          IF new.derivation_source IS DISTINCT FROM 'unified_compilation' THEN
            IF tg_op='UPDATE' AND old.lifecycle_status='draft' AND new.lifecycle_status='superseded'
               AND old.approved_at IS NULL AND new.approved_at IS NULL
               AND NOT EXISTS(SELECT 1 FROM project_guide_proposal_approvals WHERE artifact_policy_id=new.id) THEN
              RETURN NULL; -- Existing mutation custody must prove the exact draft replacement.
            END IF;
            IF tg_op='INSERT' OR old.lifecycle_status IS DISTINCT FROM new.lifecycle_status THEN
              RAISE EXCEPTION 'approval requires a unified proposal' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
          END IF;
          SELECT * INTO a FROM project_guide_proposal_approvals WHERE artifact_policy_id=new.id;
        ELSIF tg_table_name='submission_policy_mutation_idempotency_records' THEN
          IF new.action_id<>'project.submission_artifact_policy.approve' OR new.status<>'committed' THEN RETURN NULL; END IF;
          SELECT * INTO a FROM project_guide_proposal_approvals WHERE operation_id=new.operation_id;
        ELSE
          IF new.creation_action_id IS DISTINCT FROM 'project.submission_artifact_policy.approve' THEN RETURN NULL; END IF;
          IF tg_table_name='effective_project_submission_artifact_policies' THEN
            SELECT * INTO a FROM project_guide_proposal_approvals WHERE effective_policy_id=new.id;
          ELSE
            SELECT * INTO a FROM project_guide_proposal_approvals WHERE pre_submit_policy_id=new.id;
          END IF;
        END IF;
        IF a.operation_id IS NULL THEN
          RAISE EXCEPTION 'immutable proposal approval operation missing' USING ERRCODE='23514';
        END IF;
        PERFORM require_guide_proposal_target(a.target_json::jsonb,a.target_digest,a.finalization_id);
        SELECT * INTO r FROM submission_policy_mutation_idempotency_records WHERE operation_id=a.operation_id;
        SELECT * INTO p FROM submission_artifact_policies WHERE id=a.artifact_policy_id;
        SELECT * INTO e FROM effective_project_submission_artifact_policies WHERE id=a.effective_policy_id;
        SELECT * INTO pre FROM pre_submit_checker_policies WHERE id=a.pre_submit_policy_id;
        SELECT * INTO projection FROM project_guide_component_projection_operations WHERE policy_id=p.id;
        IF r.id IS NULL OR r.status IS DISTINCT FROM 'committed'
           OR r.action_id IS DISTINCT FROM 'project.submission_artifact_policy.approve'
           OR r.actor_profile_id IS DISTINCT FROM a.actor_profile_id
           OR r.identity_link_id IS DISTINCT FROM a.identity_link_id
           OR r.project_id IS DISTINCT FROM a.project_id OR r.guide_id IS DISTINCT FROM a.guide_id
           OR r.source_snapshot_id IS DISTINCT FROM a.target_json->>'source_snapshot_id'
           OR r.setup_generation IS DISTINCT FROM (a.target_json->>'setup_generation')::bigint
           OR r.request_digest IS DISTINCT FROM a.request_digest
           OR r.resource_context_digest IS DISTINCT FROM a.resource_context_digest
           OR guide_proposal_hash(r.resource_context_json::jsonb) IS DISTINCT FROM a.resource_context_digest
           OR r.resource_context_json->>'target_digest' IS DISTINCT FROM a.target_digest
           OR r.resource_context_json->>'output_digest' IS DISTINCT FROM a.output_digest
           OR r.resource_context_json->>'request_digest' IS DISTINCT FROM a.request_digest
           OR r.committed_policy_id IS DISTINCT FROM p.id
           OR r.committed_effective_policy_id IS DISTINCT FROM e.id
           OR r.committed_pre_submit_policy_id IS DISTINCT FROM pre.id
           OR p.id IS NULL OR e.id IS NULL OR pre.id IS NULL OR projection.operation_id IS NULL
           OR (p.project_id,p.guide_id,e.project_id,e.guide_id,pre.project_id,pre.guide_id)
              IS DISTINCT FROM (a.project_id,a.guide_id,a.project_id,a.guide_id,a.project_id,a.guide_id)
           OR p.id IS DISTINCT FROM a.target_json->>'artifact_policy_id'
           OR p.policy_hash IS DISTINCT FROM a.target_json->>'artifact_policy_hash'
           OR a.compilation_id::text IS DISTINCT FROM a.target_json->>'compilation_id'
           OR projection.operation_id::text IS DISTINCT FROM a.target_json->>'artifact_projection_operation_id'
           OR projection.output_digest IS DISTINCT FROM a.target_json->>'artifact_projection_output_digest'
           OR p.derivation_source IS DISTINCT FROM 'unified_compilation'
           OR e.submission_artifact_policy_id IS DISTINCT FROM p.id
           OR e.submission_artifact_policy_hash IS DISTINCT FROM p.policy_hash
           OR pre.effective_policy_id IS DISTINCT FROM e.id
           OR pre.effective_policy_hash IS DISTINCT FROM e.effective_policy_hash
           OR guide_proposal_hash(e.effective_policy::jsonb) IS DISTINCT FROM e.effective_policy_hash
           OR guide_proposal_hash(pre.compiled_bundle::jsonb) IS DISTINCT FROM pre.compiled_bundle_hash
           OR guide_proposal_hash(a.effective_pre_submit_plan::jsonb) IS DISTINCT FROM a.effective_pre_submit_plan_hash
           OR guide_proposal_hash(a.receipt_json::jsonb) IS DISTINCT FROM a.output_digest
           OR r.response_json::jsonb IS DISTINCT FROM a.receipt_json::jsonb THEN
          RAISE EXCEPTION 'proposal approval reservation or output custody mismatch' USING ERRCODE='23514';
        END IF;
        SELECT coalesce(jsonb_agg(digest ORDER BY digest),'[]'::jsonb) INTO warning_hashes
          FROM (SELECT guide_proposal_hash(finding) AS digest FROM project_guide_compilations c,
                jsonb_array_elements(c.canonical_result::jsonb->'findings') AS finding
                WHERE c.id=a.compilation_id AND finding->>'severity'='warning') warnings;
        expected_receipt:=jsonb_build_object('operation_id',a.operation_id,'target_digest',a.target_digest,
          'artifact_policy_id',p.id,'effective_policy_id',e.id,'effective_policy_hash',e.effective_policy_hash,
          'pre_submit_policy_id',pre.id,'pre_submit_bundle_hash',pre.compiled_bundle_hash,
          'effective_pre_submit_plan_hash',a.effective_pre_submit_plan_hash,
          'acknowledged_warning_hashes',warning_hashes);
        IF a.receipt_json::jsonb IS DISTINCT FROM expected_receipt THEN
          RAISE EXCEPTION 'proposal approval receipt mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO prior FROM project_guide_proposal_approvals WHERE operation_id=a.prior_approval_operation_id;
        IF r.resource_context_json::jsonb IS DISTINCT FROM guide_proposal_resource(
             a.target_json::jsonb,a.operation_id,a.actor_profile_id,a.identity_link_id,
             'project.submission_artifact_policy.approve',a.request_digest,a.output_digest,
             prior.operation_id,prior.output_digest)
           OR a.request_digest IS DISTINCT FROM guide_proposal_hash(jsonb_build_object(
             'target',a.target_json::jsonb,'idempotency_key',r.idempotency_key,
             'acknowledged_warning_hashes',warning_hashes,
             'expected_previous_approval_operation_id',prior.operation_id,
             'expected_previous_approval_output_digest',prior.output_digest))
           OR a.effective_pre_submit_plan::jsonb->'lineage' IS DISTINCT FROM jsonb_build_object(
             'project_id',a.project_id,'guide_id',a.guide_id,
             'guide_version',a.target_json->>'guide_version',
             'source_snapshot_id',a.target_json->>'source_snapshot_id',
             'source_snapshot_hash',a.target_json->>'source_snapshot_hash',
             'effective_policy_id',e.id,'effective_policy_hash',e.effective_policy_hash,
             'pre_submit_policy_id',pre.id,'pre_submit_policy_bundle_hash',pre.compiled_bundle_hash)
           OR a.effective_pre_submit_plan::jsonb->'catalogue' IS DISTINCT FROM jsonb_build_object(
             'id',a.target_json->>'pre_catalogue_id','version',a.target_json->>'pre_catalogue_version',
             'schema_version',a.target_json->>'pre_catalogue_schema_version',
             'manifest_sha256',a.target_json->>'pre_catalogue_manifest_hash') THEN
          RAISE EXCEPTION 'proposal approval request or plan binding mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO successor FROM project_guide_proposal_approvals WHERE prior_approval_operation_id=a.operation_id;
        IF p.lifecycle_status='superseded' THEN
          IF successor.operation_id IS NULL OR successor.project_id<>a.project_id OR successor.guide_id<>a.guide_id
             OR e.lifecycle_status IS DISTINCT FROM 'superseded' OR pre.lifecycle_status IS DISTINCT FROM 'superseded'
             OR p.superseded_at IS NULL OR e.superseded_at IS DISTINCT FROM p.superseded_at
             OR pre.superseded_at IS DISTINCT FROM p.superseded_at
             OR NOT EXISTS(SELECT 1 FROM submission_artifact_policies next WHERE next.id=successor.artifact_policy_id
                           AND next.supersedes_policy_id=p.id)
             OR NOT EXISTS(SELECT 1 FROM effective_project_submission_artifact_policies next WHERE next.id=successor.effective_policy_id
                           AND next.supersedes_effective_policy_id=e.id)
             OR NOT EXISTS(SELECT 1 FROM pre_submit_checker_policies next WHERE next.id=successor.pre_submit_policy_id
                           AND next.supersedes_pre_submit_checker_policy_id=pre.id) THEN
            RAISE EXCEPTION 'proposal supersession requires exact successor approval' USING ERRCODE='23514';
          END IF;
        ELSIF p.lifecycle_status IS DISTINCT FROM 'approved' OR e.lifecycle_status IS DISTINCT FROM 'approved'
           OR pre.lifecycle_status IS DISTINCT FROM 'compiled' OR successor.operation_id IS NOT NULL THEN
          RAISE EXCEPTION 'proposal approval lifecycle mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO prior FROM project_guide_proposal_approvals WHERE operation_id=a.prior_approval_operation_id;
        IF (a.prior_approval_operation_id IS NOT NULL AND
            (prior.operation_id IS NULL OR prior.project_id<>a.project_id OR prior.guide_id<>a.guide_id
             OR (prior.target_json->>'setup_generation')::bigint >= (a.target_json->>'setup_generation')::bigint))
           OR p.supersedes_policy_id IS DISTINCT FROM prior.artifact_policy_id
           OR e.supersedes_effective_policy_id IS DISTINCT FROM prior.effective_policy_id
           OR pre.supersedes_pre_submit_checker_policy_id IS DISTINCT FROM prior.pre_submit_policy_id THEN
          RAISE EXCEPTION 'proposal prior approval mismatch' USING ERRCODE='23514';
        END IF;
        IF a.prior_approval_operation_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM submission_artifact_policies prior_policy
          JOIN effective_project_submission_artifact_policies prior_effective
            ON prior_effective.id=prior.effective_policy_id
          JOIN pre_submit_checker_policies prior_pre ON prior_pre.id=prior.pre_submit_policy_id
          WHERE prior_policy.id=prior.artifact_policy_id
            AND prior_policy.lifecycle_status='superseded'
            AND prior_effective.lifecycle_status='superseded'
            AND prior_pre.lifecycle_status='superseded'
            AND prior_policy.superseded_at IS NOT NULL
            AND prior_effective.superseded_at=prior_policy.superseded_at
            AND prior_pre.superseded_at=prior_policy.superseded_at
        ) THEN
          RAISE EXCEPTION 'proposal prior approval is not superseded' USING ERRCODE='23514';
        END IF;
        IF tg_table_name='project_guide_proposal_approvals' THEN
          IF NOT EXISTS(SELECT 1 FROM project_guides g WHERE g.id=a.guide_id AND g.status='draft')
             OR (SELECT max(setup_generation) FROM project_setup_runs WHERE guide_id=a.guide_id)
                IS DISTINCT FROM (a.target_json->>'setup_generation')::bigint THEN
            RAISE EXCEPTION 'proposal approval target is no longer current' USING ERRCODE='23514';
          END IF;
          IF p.lifecycle_status IS DISTINCT FROM 'approved' OR e.lifecycle_status IS DISTINCT FROM 'approved'
             OR pre.lifecycle_status IS DISTINCT FROM 'compiled'
             OR project_guide_projection_business_digest(projection) IS DISTINCT FROM a.approved_policy_output_digest THEN
            RAISE EXCEPTION 'proposal approval lifecycle mismatch' USING ERRCODE='23514';
          END IF;
          PERFORM require_guide_proposal_authority(a.actor_profile_id,a.identity_link_id,a.admin_role_grant_id,
            a.project_id,a.authorization_decision_event_id,'project.submission_artifact_policy.approve',
            'project.effective_policy.manage','project_submission_artifact_policy_mutation',p.id,a.resource_context_digest);
        END IF;
        RETURN NULL;
      END $$;
    """)
    for table in (
        "project_guide_proposal_approvals",
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
        "submission_policy_mutation_idempotency_records",
    ):
        _execute(f"""
          CREATE CONSTRAINT TRIGGER guide_proposal_approval_custody AFTER INSERT OR UPDATE ON {table}
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_guide_proposal_approval();
        """)


def _approved_content_guards() -> None:
    """Content cannot drift after projection or approval; only governed lifecycle changes remain."""
    _execute("""
      CREATE FUNCTION protect_guide_proposal_content() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE permitted text[];
      BEGIN
        IF tg_table_name='submission_artifact_policies' THEN
          IF old.derivation_source IS DISTINCT FROM 'unified_compilation' THEN RETURN new; END IF;
          permitted:=ARRAY['lifecycle_status','approved_by_role','approved_by_actor','approved_at',
            'approved_by_actor_profile_id','approved_via_identity_link_id','approved_by_admin_role_grant_id',
            'approval_scope_type','approval_scope_project_id','approval_action_id','approval_decision_event_id',
            'supersedes_policy_id','superseded_at','updated_at'];
          IF old.approval_action_id IS NOT NULL THEN
            permitted:=ARRAY['lifecycle_status','superseded_at','updated_at'];
          END IF;
        ELSE
          IF old.creation_action_id IS DISTINCT FROM 'project.submission_artifact_policy.approve' THEN RETURN new; END IF;
          permitted:=ARRAY['lifecycle_status','superseded_at','updated_at'];
        END IF;
        IF (to_jsonb(new)-permitted) IS DISTINCT FROM (to_jsonb(old)-permitted) THEN
          RAISE EXCEPTION 'unified proposal content is immutable' USING ERRCODE='23514';
        END IF;
        RETURN new;
      END $$;
    """)
    for table in (
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
    ):
        _execute(f"""
          CREATE TRIGGER guide_proposal_content_immutable BEFORE UPDATE ON {table}
          FOR EACH ROW EXECUTE FUNCTION protect_guide_proposal_content();
        """)


def _correction_guards() -> None:
    _execute("""
      CREATE FUNCTION require_guide_proposal_correction() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE c project_guide_proposal_corrections%rowtype;
        source project_setup_runs%rowtype; successor project_setup_runs%rowtype; expected jsonb;
        prior project_guide_proposal_approvals%rowtype;
      BEGIN
        IF tg_table_name='project_guide_proposal_corrections' THEN c:=new;
        ELSE
          SELECT * INTO c FROM project_guide_proposal_corrections WHERE successor_setup_run_id=new.id;
          IF c.operation_id IS NULL AND new.status<>'correction_requested' THEN RETURN NULL; END IF;
        END IF;
        IF c.operation_id IS NULL THEN
          RAISE EXCEPTION 'guide correction operation missing' USING ERRCODE='23514';
        END IF;
        PERFORM require_guide_proposal_target(c.target_json::jsonb,c.target_digest,c.finalization_id);
        SELECT * INTO source FROM project_setup_runs WHERE id=c.target_json->>'setup_run_id';
        SELECT * INTO successor FROM project_setup_runs WHERE id=c.successor_setup_run_id;
        IF source.id IS NULL OR successor.id IS NULL
           OR (successor.project_id,successor.guide_id,successor.guide_version,successor.source_snapshot_id,successor.source_snapshot_hash)
              IS DISTINCT FROM (source.project_id,source.guide_id,source.guide_version,source.source_snapshot_id,source.source_snapshot_hash)
           OR (c.project_id,c.guide_id,c.compilation_id::text) IS DISTINCT FROM
              (source.project_id,source.guide_id,c.target_json->>'compilation_id')
           OR successor.setup_generation IS DISTINCT FROM source.setup_generation+1
           OR c.successor_setup_generation IS DISTINCT FROM successor.setup_generation
           OR source.documents_ready_at IS NULL OR successor.documents_ready_at IS DISTINCT FROM source.documents_ready_at
           OR guide_proposal_hash(c.resource_context_json::jsonb) IS DISTINCT FROM c.resource_context_digest
           OR c.resource_context_json->>'target_digest' IS DISTINCT FROM c.target_digest
           OR c.resource_context_json->>'request_digest' IS DISTINCT FROM c.request_digest
           OR c.resource_context_json->>'output_digest' IS DISTINCT FROM c.output_digest
           OR guide_proposal_hash(c.receipt_json::jsonb) IS DISTINCT FROM c.output_digest
           OR guide_proposal_hash(jsonb_build_object('target',c.target_json::jsonb,
               'idempotency_key',c.idempotency_key,'reason',c.reason)) IS DISTINCT FROM c.request_digest
           OR guide_proposal_hash(jsonb_build_object('operation_id',c.operation_id,
               'predecessor_compilation_id',c.compilation_id,'predecessor_result_hash',c.target_json->>'result_hash',
               'target_digest',c.target_digest,'reason',c.reason)) IS DISTINCT FROM c.feedback_hash THEN
          RAISE EXCEPTION 'guide correction successor custody mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO prior FROM project_guide_proposal_approvals
          WHERE operation_id=(c.resource_context_json->>'current_approval_operation_id')::uuid;
        IF (prior.operation_id IS NOT NULL AND (prior.project_id<>c.project_id OR prior.guide_id<>c.guide_id))
           OR c.resource_context_json::jsonb IS DISTINCT FROM guide_proposal_resource(
             c.target_json::jsonb,c.operation_id,c.actor_profile_id,c.identity_link_id,
             'project.guide_compilation.correction.request',c.request_digest,c.output_digest,
             prior.operation_id,prior.output_digest) THEN
          RAISE EXCEPTION 'guide correction resource binding mismatch' USING ERRCODE='23514';
        END IF;
        expected:=jsonb_build_object('operation_id',c.operation_id,'target_digest',c.target_digest,
          'successor_setup_run_id',successor.id,'successor_setup_generation',successor.setup_generation,
          'feedback_hash',c.feedback_hash,'status','correction_requested');
        IF c.receipt_json::jsonb IS DISTINCT FROM expected THEN
          RAISE EXCEPTION 'guide correction receipt mismatch' USING ERRCODE='23514';
        END IF;
        IF tg_table_name='project_guide_proposal_corrections' THEN
          IF NOT EXISTS(SELECT 1 FROM project_guides g WHERE g.id=c.guide_id AND g.status='draft')
             OR (SELECT max(setup_generation) FROM project_setup_runs WHERE guide_id=c.guide_id)
                IS DISTINCT FROM successor.setup_generation THEN
            RAISE EXCEPTION 'guide correction target is no longer current' USING ERRCODE='23514';
          END IF;
          IF successor.error_code IS NOT NULL OR successor.error_artifact_incident_id IS NOT NULL
             OR successor.status IS DISTINCT FROM 'correction_requested'
             OR successor.current_step IS DISTINCT FROM 'correction_requested'
             OR successor.celery_task_id IS NOT NULL OR successor.started_at IS NOT NULL
             OR successor.finished_at IS NOT NULL OR successor.output_sufficiency_report_id IS NOT NULL
             OR successor.output_submission_artifact_policy_id IS NOT NULL
             OR successor.output_post_submit_checker_policy_id IS NOT NULL THEN
            RAISE EXCEPTION 'guide correction initial successor shape mismatch' USING ERRCODE='23514';
          END IF;
          PERFORM require_guide_proposal_authority(c.actor_profile_id,c.identity_link_id,c.admin_role_grant_id,
            c.project_id,c.authorization_decision_event_id,'project.guide_compilation.correction.request',
            'project.guide_compilation.request','project_guide_compilation_correction',c.operation_id::text,c.resource_context_digest);
        END IF;
        IF successor.status<>'correction_requested' AND NOT EXISTS(
          SELECT 1 FROM project_guide_compilation_request_operations r
          JOIN project_guide_compilation_attempts a ON a.id=r.attempt_id
          WHERE r.setup_run_id=successor.id AND r.setup_generation=successor.setup_generation
            AND r.project_id=c.project_id AND r.guide_id=c.guide_id
            AND r.request_trigger='project_manager'
            AND r.expected_predecessor_compilation_id=c.compilation_id
            AND a.setup_run_id=successor.id AND a.runtime_configuration IS NOT NULL
        ) THEN
          RAISE EXCEPTION 'correction successor requires human compilation request' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END $$;
      CREATE CONSTRAINT TRIGGER guide_proposal_correction_custody
      AFTER INSERT ON project_guide_proposal_corrections DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION require_guide_proposal_correction();
      CREATE CONSTRAINT TRIGGER guide_proposal_correction_custody
      AFTER INSERT OR UPDATE ON project_setup_runs DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION require_guide_proposal_correction();
    """)


def _source_custody(*, reverse: bool = False) -> None:
    """The same setup owner validates each real source of authorized creation."""
    definition = op.get_bind().scalar(
        text("SELECT pg_get_functiondef('validate_guide_mutation_custody()'::regprocedure)")
    )
    marker = "if tg_table_name='guide_mutation_idempotency_records' then"
    if definition.count(marker) != 1:
        raise RuntimeError("guide mutation custody owner changed")
    branch = """
          if tg_table_name='project_setup_runs' then
            if new.authorization_action_id='project.guide_compilation.correction.request' then
              if not exists(select 1 from project_guide_proposal_corrections c
                 where c.successor_setup_run_id=new.id and c.project_id=new.project_id
                   and c.guide_id=new.guide_id and c.successor_setup_generation=new.setup_generation
                   and c.actor_profile_id=new.authorized_by_actor_profile_id
                   and c.identity_link_id=new.authorized_via_identity_link_id
                   and c.admin_role_grant_id=new.authorized_by_admin_role_grant_id
                   and c.authorization_decision_event_id=new.authorization_decision_event_id
                   and new.authorization_scope_type='project'
                   and new.authorization_scope_project_id=new.project_id) then
                raise exception 'correction setup source custody mismatch' using errcode='23514';
              end if;
              return null;
            end if;
          end if;
          """
    if reverse:
        if definition.count(branch) != 1:
            raise RuntimeError("correction source custody owner changed")
        _execute(definition.replace(branch, ""))
    else:
        _execute(definition.replace(marker, branch + marker))


def _audit_vocabulary(*, reverse: bool = False) -> None:
    """Declare bounded evidence names; the AUTH catalogue keeps both actions planned."""
    connection = op.get_bind()
    connection.execute(text("LOCK TABLE audit_events IN ACCESS EXCLUSIVE MODE"))
    for name in (
        "ck_audit_events_authority_privacy_bounds",
        "ck_audit_events_authorization_action_evidence",
    ):
        definition = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='audit_events'::regclass AND conname=:name"
            ),
            {"name": name},
        ).scalar_one()
        if name.endswith("privacy_bounds"):
            anchor = "('project_guide_setup_finalization'::character varying)::text"
            addition = (
                ", ('project_guide_compilation_review_package'::character varying)::text"
                ", ('project_guide_compilation_correction'::character varying)::text"
            )
            if definition.count(anchor) != 1:
                raise RuntimeError("proposal audit resource vocabulary changed")
            if reverse:
                if definition.count(anchor + addition) != definition.count(anchor):
                    raise RuntimeError("proposal audit vocabulary changed")
                definition = definition.replace(anchor + addition, anchor)
            else:
                definition = definition.replace(anchor, anchor + addition)
        else:
            anchor = (
                "(((action_id)::text = 'project.guide_compilation.request'::text) "
                "AND ((permission_id)::text = 'project.guide_compilation.request'::text))"
            )
            if definition.count(anchor) != 2:
                raise RuntimeError("proposal action evidence vocabulary changed")
            addition = (
                " OR (((action_id)::text = 'project.guide_compilation.correction.request'::text) "
                "AND ((permission_id)::text = 'project.guide_compilation.request'::text))"
                " OR (((action_id)::text = 'project.guide_compilation.review_package.read'::text) "
                "AND ((permission_id)::text = 'project.guide.manage'::text))"
            )
            if reverse:
                if definition.count(anchor + addition) != definition.count(anchor):
                    raise RuntimeError("proposal audit vocabulary changed")
                definition = definition.replace(anchor + addition, anchor)
            else:
                definition = definition.replace(anchor, anchor + addition)
        _execute("ALTER TABLE audit_events DROP CONSTRAINT " + name)
        _execute("ALTER TABLE audit_events ADD CONSTRAINT " + name + " " + definition)


def _reservation_custody(*, reverse: bool = False) -> None:
    """Keep the reservation owner and bind its approval output to canonical provenance."""
    definition = op.get_bind().scalar(
        text(
            "SELECT pg_get_functiondef('validate_submission_policy_authority_custody()'::regprocedure)"
        )
    )
    replacements = {
        "from submission_artifact_policies s": """from submission_artifact_policies s
                  join project_guide_proposal_approvals approval
                    on approval.operation_id=reservation.operation_id and approval.artifact_policy_id=s.id""",
        "reservation.resource_context_json->>'guide_version'": "approval.target_json->>'guide_version'",
        "reservation.resource_context_json->>'policy_digest'": "approval.target_json->>'artifact_policy_hash'",
        "reservation.resource_context_json->>'effective_output_digest'": "approval.receipt_json->>'effective_policy_hash'",
        "reservation.resource_context_json->>'compiled_pre_submit_output_digest'": "approval.receipt_json->>'pre_submit_bundle_hash'",
    }
    for before, after in replacements.items():
        if reverse:
            before, after = after, before
        if definition.count(before) != 1:
            raise RuntimeError("submission policy reservation custody owner changed")
        definition = definition.replace(before, after)
    _execute(definition)


def _setup_authority_shape(*, reverse: bool = False) -> None:
    """The successor has exact correction authority, distinct from upload consent."""
    name = "ck_project_setup_runs_setup_run_authority_shape"
    definition = op.get_bind().scalar(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='project_setup_runs'::regclass AND conname=:name"
        ),
        {"name": name},
    )
    old = "((authorization_action_id)::text = 'project.guide_source_snapshot.create'::text)"
    new = (
        "("
        + old
        + " OR ((authorization_action_id)::text = 'project.guide_compilation.correction.request'::text))"
    )
    before, after = (new, old) if reverse else (old, new)
    if definition.count(before) != 1:
        raise RuntimeError("setup source authority shape changed")
    _execute("ALTER TABLE project_setup_runs DROP CONSTRAINT " + name)
    _execute(
        "ALTER TABLE project_setup_runs ADD CONSTRAINT "
        + name
        + " "
        + definition.replace(before, after)
    )


def downgrade() -> None:
    connection = op.get_bind()
    retained = connection.scalar(
        text("""
        SELECT EXISTS(SELECT 1 FROM project_guide_proposal_approvals)
            OR EXISTS(SELECT 1 FROM project_guide_proposal_corrections)
            OR EXISTS(SELECT 1 FROM audit_events WHERE action_id IN (
                'project.guide_compilation.review_package.read',
                'project.guide_compilation.correction.request'))
    """)
    )
    if retained:
        raise RuntimeError("retained guide proposal evidence prevents downgrade")
    _setup_authority_shape(reverse=True)
    _reservation_custody(reverse=True)
    _source_custody(reverse=True)
    _audit_vocabulary(reverse=True)
    for table in (
        "project_guide_proposal_approvals",
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
        "submission_policy_mutation_idempotency_records",
    ):
        _execute(f"DROP TRIGGER guide_proposal_approval_custody ON {table}")
    for table in ("project_guide_proposal_corrections", "project_setup_runs"):
        _execute(f"DROP TRIGGER guide_proposal_correction_custody ON {table}")
    for table in (
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
    ):
        _execute(f"DROP TRIGGER guide_proposal_content_immutable ON {table}")
    _execute("""
      DROP FUNCTION protect_guide_proposal_content();
      DROP FUNCTION require_guide_proposal_approval();
      DROP FUNCTION require_guide_proposal_correction();
      DROP FUNCTION require_guide_proposal_target(jsonb,text,uuid);
      DROP FUNCTION require_guide_proposal_authority(text,text,uuid,text,text,text,text,text,text,text);
      DROP TABLE project_guide_proposal_corrections;
      DROP TABLE project_guide_proposal_approvals;
      DROP FUNCTION reject_guide_proposal_change();
      DROP FUNCTION guide_proposal_resource(jsonb,uuid,text,text,text,text,text,uuid,text);
      DROP FUNCTION guide_proposal_hash(jsonb);
      ALTER TABLE project_setup_runs DROP CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_status;
      ALTER TABLE project_setup_runs ADD CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_status
      CHECK (status in ('awaiting_documents','queued','dispatch_pending',
        'enqueue_failed','enqueue_identity_mismatch','running_sufficiency_agent','sufficiency_blocked',
        'running_policy_derivation_agent','policy_draft_ready','running_post_submit_derivation_agent',
        'post_submit_setup_blocked','post_submit_policy_compiled','setup_blocked','failed'));
    """)
