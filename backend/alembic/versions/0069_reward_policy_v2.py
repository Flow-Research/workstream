"""Replace new policy authoring with v2 tiers; retain exact v1 economic facts."""

import re

from alembic import op
from sqlalchemy import text

revision = "0069_reward_policy_v2"
down_revision = "0068_issuer_profile_email"
branch_labels = None
depends_on = None

# Frozen predecessor predicates, executed under the cutover fence before DDL.
# Do not import mutable application preflight logic into retained migrations.
BASELINE_BLOCKERS = {
    "live_v1_tasks": "\n    SELECT t.id FROM public.workstream_tasks t\n    JOIN public.contribution_policy_versions p ON p.id=t.locked_contribution_policy_version_id\n    WHERE t.status <> 'accepted'\n",
    "live_v1_assignments": "\n        SELECT a.id FROM public.task_assignments a\n        JOIN public.contribution_policy_versions p\n          ON p.id=a.submitter_contribution_policy_version_id\n        WHERE a.status='active'\n    ",
    "live_v1_submissions": "\n        SELECT s.id FROM public.submissions s\n        JOIN public.contribution_policy_versions p ON p.id=s.contribution_policy_version_id\n        WHERE s.attempt_status IN ('evaluation_pending','review_pending','needs_revision')\n    ",
    "live_v1_revision_preparations": "\n        SELECT r.id FROM public.task_revision_preparations r\n        WHERE r.task_id IN (\n    SELECT t.id FROM public.workstream_tasks t\n    JOIN public.contribution_policy_versions p ON p.id=t.locked_contribution_policy_version_id\n    WHERE t.status <> 'accepted'\n)\n    ",
    "acceptance_source_anomalies": "\n        SELECT f.id FROM public.final_acceptances f\n        LEFT JOIN public.submissions s ON s.id=f.submission_id\n        LEFT JOIN public.workstream_tasks t ON t.id=s.task_id\n        LEFT JOIN public.artifact_contents content ON content.id=s.artifact_content_id\n        LEFT JOIN public.audit_events audit ON audit.id=f.source_authorization_decision_id\n        LEFT JOIN public.task_post_submit_routing_manifests m ON m.id=f.source_routing_manifest_id\n        WHERE s.id IS NULL OR t.id IS NULL OR content.id IS NULL OR audit.id IS NULL\n           OR ROW(f.project_id,f.task_id,f.accepted_submitter_id,f.policy_context_ref)\n              IS DISTINCT FROM ROW(t.project_id,s.task_id,s.contributor_id,s.locked_review_policy_id)\n           OR (f.acceptance_source='task_post_submit_route' AND (\n                 m.id IS NULL OR m.human_review_required OR f.source_review_id IS NOT NULL\n              OR ROW(m.project_id,m.task_id,m.submission_id,m.contributor_id,m.content_sha256,\n                     m.router_actor_id,m.authorization_decision_id,m.final_acceptance_id)\n                 IS DISTINCT FROM\n                 ROW(f.project_id,f.task_id,f.submission_id,f.accepted_submitter_id,content.sha256,\n                     f.recorded_by,f.source_authorization_decision_id,f.id)\n              OR f.policy_context_ref::text IS DISTINCT FROM\n                 m.authority_context#>>'{source,locked_policy,locked_review_policy_id}'\n              OR NOT public.task_routing_receipt_valid(m)))\n           -- This supported baseline has no authorized human FinalAcceptance\n           -- writer or canonical human decision receipt. A Review and an AUDIT\n           -- row by the same actor cannot establish that missing authority.\n           OR f.acceptance_source='human_review'\n    ",
    "acceptance_contribution_gaps": "\n        SELECT f.id FROM public.final_acceptances f\n        WHERE NOT EXISTS (\n            SELECT 1 FROM public.contribution_records c\n            WHERE c.source_final_acceptance_id=f.id AND c.contribution_type='accepted_submission'\n              AND ROW(c.project_id,c.task_id,c.submission_id,c.contributor_id)\n                  IS NOT DISTINCT FROM\n                  ROW(f.project_id,f.task_id,f.submission_id,f.accepted_submitter_id))\n    ",
    "contribution_source_anomalies": "\n        SELECT c.id FROM public.contribution_records c\n        LEFT JOIN public.submissions s ON s.id=c.submission_id\n        LEFT JOIN public.workstream_tasks t ON t.id=s.task_id\n        LEFT JOIN public.task_assignments a ON a.id=s.task_assignment_id\n        LEFT JOIN public.artifact_contents content ON content.id=s.artifact_content_id\n        LEFT JOIN public.artifact_bindings binding ON binding.id=s.artifact_binding_id\n        LEFT JOIN public.contribution_policy_versions p ON p.id=c.contribution_policy_version_id\n        LEFT JOIN public.final_acceptances f ON f.id=c.source_final_acceptance_id\n        WHERE s.id IS NULL OR t.id IS NULL OR a.id IS NULL OR content.id IS NULL\n           OR binding.id IS NULL OR p.id IS NULL OR p.status NOT IN ('published','retired')\n           OR ROW(c.project_id,c.task_id,c.artifact_hash)\n              IS DISTINCT FROM ROW(t.project_id,s.task_id,content.sha256)\n           OR ROW(a.project_id,a.task_id,a.contributor_id)\n              IS DISTINCT FROM ROW(c.project_id,c.task_id,s.contributor_id)\n           OR ROW(binding.content_id,binding.project_id,binding.resource_id,\n                  binding.resource_type,binding.logical_role)\n              IS DISTINCT FROM ROW(content.id,c.project_id,s.id::text,\n                  'submission','submission_bundle_original')\n           OR p.project_id IS DISTINCT FROM c.project_id\n           OR NOT EXISTS (SELECT 1 FROM public.contribution_rules rule\n                WHERE rule.contribution_policy_version_id=p.id AND rule.project_id=c.project_id\n                  AND rule.contribution_type=c.contribution_type)\n           OR (c.contribution_type='accepted_submission' AND (\n                 f.id IS NULL OR c.source_review_id IS NOT NULL\n              OR ROW(f.project_id,f.task_id,f.submission_id,f.accepted_submitter_id,\n                     a.id,a.submitter_contribution_policy_version_id,s.contribution_policy_version_id)\n                 IS DISTINCT FROM ROW(c.project_id,c.task_id,c.submission_id,c.contributor_id,\n                     c.source_task_assignment_id,c.contribution_policy_version_id,\n                     c.contribution_policy_version_id)))\n           -- Review storage is not an authorized reviewer-contribution writer.\n           OR c.contribution_type='completed_review'\n    ",
    "award_source_anomalies": "\n        SELECT w.id FROM public.compensation_awards w\n        LEFT JOIN public.contribution_records c ON c.id=w.contribution_record_id\n        LEFT JOIN public.contribution_award_definitions d ON d.id=w.award_definition_id\n        LEFT JOIN public.project_compensation_adapter_bindings b ON b.id=w.adapter_binding_id\n        WHERE c.id IS NULL OR d.id IS NULL OR b.id IS NULL\n           OR ROW(w.project_id,w.contributor_id,w.contribution_policy_version_id)\n              IS DISTINCT FROM ROW(c.project_id,c.contributor_id,c.contribution_policy_version_id)\n           OR ROW(w.project_id,w.contribution_policy_version_id,c.contribution_type,\n                  w.instrument_type,w.unit_code,w.quantity,w.adapter_binding_id)\n              IS DISTINCT FROM ROW(d.project_id,d.contribution_policy_version_id,d.contribution_type,\n                  d.instrument_type,d.unit_code,d.quantity,d.adapter_binding_id)\n           OR ROW(b.project_id,b.instrument_type) IS DISTINCT FROM ROW(w.project_id,w.instrument_type)\n    ",
    "award_completeness_anomalies": "\n        SELECT c.id FROM public.contribution_records c\n        WHERE EXISTS (\n            SELECT 1 FROM public.contribution_rules r\n            JOIN public.contribution_award_definitions d ON d.contribution_rule_id=r.id\n            WHERE r.contribution_policy_version_id=c.contribution_policy_version_id\n              AND r.project_id=c.project_id AND r.contribution_type=c.contribution_type\n              AND NOT EXISTS (SELECT 1 FROM public.compensation_awards w\n                    WHERE w.contribution_record_id=c.id AND w.award_definition_id=d.id))\n           OR EXISTS (\n            SELECT 1 FROM public.compensation_awards w WHERE w.contribution_record_id=c.id\n              AND NOT EXISTS (SELECT 1 FROM public.contribution_rules r\n                JOIN public.contribution_award_definitions d ON d.contribution_rule_id=r.id\n                WHERE r.contribution_policy_version_id=c.contribution_policy_version_id\n                  AND r.project_id=c.project_id AND r.contribution_type=c.contribution_type\n                  AND d.id=w.award_definition_id))\n    ",
}


def _extend_guard(signature: str, checks: str) -> None:
    """Extend an existing owner guard in place while preserving its prior checks."""
    definition = (
        op.get_bind()
        .execute(
            text("SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"),
            {"signature": signature},
        )
        .scalar_one()
    )
    begin = re.search(r"\bBEGIN\b", definition, re.IGNORECASE)
    if begin is None:
        raise RuntimeError("reward migration guard shape changed: " + signature)
    op.execute(definition[: begin.end()] + "\n" + checks + definition[begin.end() :])


def _cutover_fence() -> None:
    op.execute("SELECT id FROM public.authority_control WHERE id=1 FOR UPDATE")
    phase = (
        op.get_bind()
        .execute(
            text(
                "SELECT phase FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
            )
        )
        .scalar_one()
    )
    if phase != "disabled":
        raise RuntimeError("reward cutover requires the shared lifecycle disabled after drain")
    op.execute("""LOCK TABLE public.contribution_policies,
        public.contribution_policy_versions, public.contribution_rules,
        public.contribution_award_definitions, public.workstream_tasks,
        public.task_assignments, public.submissions, public.task_revision_preparations,
        public.final_acceptances, public.contribution_records, public.compensation_awards,
        public.task_command_receipts, public.task_import_batches,
        public.task_import_batch_members, public.task_import_batch_command_receipts
        IN ACCESS EXCLUSIVE MODE""")
    for category, query in BASELINE_BLOCKERS.items():
        if op.get_bind().execute(text("SELECT EXISTS (" + query + ")")).scalar_one():
            raise RuntimeError("reward cutover blocked: " + category)


def upgrade() -> None:
    """Label retained facts without rewriting them; allow only v2 new economics."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _cutover_fence()
    for table in (
        "contribution_policy_versions",
        "contribution_award_definitions",
        "compensation_awards",
    ):
        # Fast constant population does not run UPDATE on immutable historical rows.
        op.execute(
            f"ALTER TABLE public.{table} ADD COLUMN reward_model_version integer NOT NULL DEFAULT 1"
        )
        op.execute(f"ALTER TABLE public.{table} ALTER COLUMN reward_model_version SET DEFAULT 2")
        op.execute(
            f"ALTER TABLE public.{table} ADD CONSTRAINT ck_{table}_reward_model_version CHECK (reward_model_version IN (1,2))"
        )
    op.execute(
        "ALTER TABLE public.contribution_policy_versions ADD COLUMN instrument_type varchar(32)"
    )
    op.execute("ALTER TABLE public.contribution_policy_versions ADD COLUMN unit_code varchar(32)")
    op.execute("ALTER TABLE public.contribution_policy_versions ADD COLUMN adapter_binding_id uuid")
    op.execute("""ALTER TABLE public.contribution_policy_versions
        ADD CONSTRAINT ck_contribution_policy_versions_common_reward_header CHECK (
          (instrument_type IS NULL AND unit_code IS NULL AND adapter_binding_id IS NULL) OR
          (reward_model_version=2 AND instrument_type IS NOT NULL AND instrument_type IN ('money','project_points')
            AND unit_code IS NOT NULL AND adapter_binding_id IS NOT NULL))""")
    op.execute("""ALTER TABLE public.contribution_policy_versions
        ADD CONSTRAINT uq_contribution_policy_reward_version UNIQUE(id,project_id,reward_model_version)""")
    op.execute("ALTER TABLE public.contribution_award_definitions ADD COLUMN task_size varchar(8)")
    op.execute("""ALTER TABLE public.contribution_award_definitions
        ADD CONSTRAINT fk_award_definition_reward_version
        FOREIGN KEY(contribution_policy_version_id,project_id,reward_model_version)
        REFERENCES public.contribution_policy_versions(id,project_id,reward_model_version)
        DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""ALTER TABLE public.compensation_awards ADD CONSTRAINT fk_compensation_award_reward_version
        FOREIGN KEY(contribution_policy_version_id,project_id,reward_model_version)
        REFERENCES public.contribution_policy_versions(id,project_id,reward_model_version)
        DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""ALTER TABLE public.contribution_award_definitions
        ADD CONSTRAINT ck_contribution_award_definitions_reward_definition_size CHECK (
          (reward_model_version=1 AND task_size IS NULL) OR
          (reward_model_version=2 AND ((contribution_type='accepted_submission'
             AND task_size IN ('small','medium','large') AND task_size IS NOT NULL) OR
            (contribution_type='completed_review' AND task_size IS NULL))))""")
    op.execute(
        "ALTER TABLE public.contribution_award_definitions DROP CONSTRAINT uq_contribution_award_definition_instrument"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_award_definition_v1_instrument ON public.contribution_award_definitions(contribution_rule_id,instrument_type) WHERE reward_model_version=1"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_award_definition_v2_size ON public.contribution_award_definitions(contribution_rule_id,task_size) WHERE reward_model_version=2 AND task_size IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_award_definition_v2_fixed ON public.contribution_award_definitions(contribution_rule_id) WHERE reward_model_version=2 AND task_size IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_compensation_award_v2_contribution ON public.compensation_awards(contribution_record_id) WHERE reward_model_version=2"
    )
    _policy_guards()
    _new_economic_guards()


def _policy_guards() -> None:
    # Publication custody independently checks the graph at commit. Preserve
    # its actor/event/selector checks and replace only the old cardinality.
    custody = (
        op.get_bind()
        .execute(
            text(
                "SELECT pg_get_functiondef('public.guard_contribution_policy_transition_custody()'::regprocedure)"
            )
        )
        .scalar_one()
    )
    old_cardinality = ") not between 1 and 2"
    if custody.count(old_cardinality) != 1:
        raise RuntimeError("reward publication custody cardinality shape changed")
    op.execute(
        custody.replace(
            old_cardinality,
            """
        ) NOT BETWEEN
          CASE WHEN target.reward_model_version=2 AND r.contribution_type='accepted_submission'
            THEN 3 ELSE 1 END
          AND CASE WHEN target.reward_model_version=1 THEN 2
            WHEN r.contribution_type='accepted_submission' THEN 3 ELSE 1 END
    """,
        )
    )
    _extend_guard(
        "public.guard_contribution_policy_version_content()",
        """
      IF TG_OP='INSERT' THEN
        IF NEW.reward_model_version<>2 THEN
          RAISE EXCEPTION 'new reward policies require v2' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      IF TG_OP='UPDATE' THEN
        IF (OLD.reward_model_version IS DISTINCT FROM NEW.reward_model_version
              AND NOT (OLD.status='draft' AND NEW.status='draft'
                AND OLD.reward_model_version=1 AND NEW.reward_model_version=2))
           OR (NEW.status='published' AND NEW.reward_model_version<>2 AND OLD.status='draft')
           OR (OLD.status IN ('published','retired') AND
             ROW(NEW.reward_model_version,NEW.instrument_type,NEW.unit_code,NEW.adapter_binding_id)
               IS DISTINCT FROM ROW(OLD.reward_model_version,OLD.instrument_type,OLD.unit_code,OLD.adapter_binding_id))
        THEN RAISE EXCEPTION 'immutable reward policy terms changed' USING ERRCODE='23514'; END IF;
      END IF;
    """,
    )
    op.execute(
        "DROP TRIGGER contribution_policy_versions_content_guard ON public.contribution_policy_versions"
    )
    op.execute("""CREATE TRIGGER contribution_policy_versions_content_guard
        BEFORE INSERT OR UPDATE OR DELETE ON public.contribution_policy_versions
        FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_version_content()""")
    _extend_guard(
        "public.guard_contribution_policy_children()",
        """
      IF TG_OP='INSERT' AND TG_TABLE_NAME='contribution_award_definitions' THEN
        IF NEW.reward_model_version<>2 OR NOT EXISTS (
          SELECT 1 FROM public.contribution_policy_versions p
          WHERE p.id=NEW.contribution_policy_version_id AND p.project_id=NEW.project_id
            AND p.reward_model_version=2)
        THEN RAISE EXCEPTION 'new reward definitions require exact v2 policy' USING ERRCODE='23514'; END IF;
      END IF;
    """,
    )
    op.execute("""
CREATE OR REPLACE FUNCTION public.validate_contribution_policy_graph() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.contribution_policy_versions v WHERE v.status IN ('published','retired') AND (
      (SELECT count(*) FROM public.contribution_rules r WHERE r.contribution_policy_version_id=v.id
        AND r.contribution_type='accepted_submission')<>1 OR
      (SELECT count(*) FROM public.contribution_rules r WHERE r.contribution_policy_version_id=v.id
        AND r.contribution_type='completed_review')<>1 OR
      (v.reward_model_version=2 AND (
        EXISTS(SELECT 1 FROM public.contribution_rules r WHERE r.contribution_policy_version_id=v.id
          AND r.compensation_mode='compensated') IS DISTINCT FROM (v.instrument_type IS NOT NULL))) OR
      EXISTS (SELECT 1 FROM public.contribution_rules r WHERE r.contribution_policy_version_id=v.id AND (
        (r.compensation_mode='unpaid' AND EXISTS(SELECT 1 FROM public.contribution_award_definitions d
          WHERE d.contribution_rule_id=r.id)) OR
        (r.compensation_mode='compensated' AND (
          (v.reward_model_version=1 AND (SELECT count(*) FROM public.contribution_award_definitions d
             WHERE d.contribution_rule_id=r.id) NOT BETWEEN 1 AND 2) OR
          (v.reward_model_version=2 AND (SELECT count(*) FROM public.contribution_award_definitions d
             WHERE d.contribution_rule_id=r.id) <> CASE WHEN r.contribution_type='accepted_submission' THEN 3 ELSE 1 END))) OR
        EXISTS (SELECT 1 FROM public.contribution_award_definitions d WHERE d.contribution_rule_id=r.id AND (
          d.reward_model_version<>v.reward_model_version OR
          (v.reward_model_version=2 AND ROW(d.instrument_type,d.unit_code,d.adapter_binding_id)
             IS DISTINCT FROM ROW(v.instrument_type,v.unit_code,v.adapter_binding_id)))))))
  ) THEN RAISE EXCEPTION 'published contribution policy graph is incomplete' USING ERRCODE='23514'; END IF;
  IF EXISTS(SELECT 1 FROM public.contribution_policies p LEFT JOIN public.contribution_policy_versions v
      ON v.id=p.current_published_version_id AND v.contribution_policy_id=p.id AND v.project_id=p.project_id
      WHERE p.status='active' AND (v.id IS NULL OR v.status<>'published'))
  THEN RAISE EXCEPTION 'active contribution policy selector is invalid' USING ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;
    """)


def _new_economic_guards() -> None:
    for signature in ("public.guard_contribution_source()", "public.guard_compensation_award()"):
        marker = (
            "NEW.reward_model_version<>2 OR "
            if signature.endswith("guard_compensation_award()")
            else ""
        )
        _extend_guard(
            signature,
            """
          IF """
            + marker
            + """NOT EXISTS(SELECT 1 FROM public.contribution_policy_versions p
              WHERE p.id=NEW.contribution_policy_version_id AND p.project_id=NEW.project_id
                AND p.reward_model_version=2)
          THEN RAISE EXCEPTION 'new contribution and award effects require v2' USING ERRCODE='23514'; END IF;
        """,
        )
    op.execute("""
CREATE FUNCTION public.guard_new_work_reward_version() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE policy_id uuid;
BEGIN
  IF TG_TABLE_NAME='workstream_tasks' THEN
    policy_id := NEW.locked_contribution_policy_version_id;
    IF TG_OP='UPDATE' AND policy_id IS NOT DISTINCT FROM OLD.locked_contribution_policy_version_id THEN RETURN NEW; END IF;
  ELSIF TG_TABLE_NAME='task_assignments' THEN
    policy_id := NEW.submitter_contribution_policy_version_id;
    IF TG_OP='UPDATE' AND policy_id IS NOT DISTINCT FROM OLD.submitter_contribution_policy_version_id THEN RETURN NEW; END IF;
  ELSE policy_id := NEW.contribution_policy_version_id;
  END IF;
  IF policy_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.contribution_policy_versions p
       WHERE p.id=policy_id AND p.reward_model_version=2)
  THEN RAISE EXCEPTION 'new work cannot adopt a v1 reward policy' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
    """)
    for table, events in (
        ("workstream_tasks", "INSERT OR UPDATE"),
        ("task_assignments", "INSERT OR UPDATE"),
        ("submissions", "INSERT"),
    ):
        op.execute(
            f"CREATE TRIGGER new_work_reward_version BEFORE {events} ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.guard_new_work_reward_version()"
        )


def downgrade() -> None:
    raise RuntimeError("Reward history cannot be downgraded; restore a matched pre-effect backup")
