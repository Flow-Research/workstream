"""Replace reward policy development behavior with the current sized model."""

import re

from alembic import op
from sqlalchemy import text

revision = "0069_sized_reward_policy"
down_revision = "0068_issuer_profile_email"
branch_labels = None
depends_on = None


def _admit_transition() -> None:
    """Protect data under the existing authority/lifecycle and owner table fences."""
    op.execute("SELECT id FROM public.authority_control WHERE id=1 FOR UPDATE")
    phase = op.get_bind().execute(text(
        "SELECT phase FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
    )).scalar_one()
    if phase != "disabled":
        raise RuntimeError("reward transition requires the shared lifecycle disabled after drain")
    op.execute("""LOCK TABLE public.contribution_policies,
        public.contribution_policy_versions, public.contribution_rules,
        public.contribution_award_definitions, public.workstream_tasks,
        public.task_assignments, public.submissions, public.task_revision_preparations,
        public.final_acceptances, public.contribution_records, public.compensation_awards,
        public.task_command_receipts, public.task_import_batches,
        public.task_import_batch_members, public.task_import_batch_command_receipts
        IN ACCESS EXCLUSIVE MODE""")
    # No amounts, immutable published digests or recorded command bodies can be
    # inferred/replaced by this migration. Refusal leaves every source intact.
    checks = {
        "published_policy_evidence": "SELECT id FROM public.contribution_policy_versions WHERE status<>'draft'",
        "economic_definitions": "SELECT id FROM public.contribution_award_definitions",
        "earned_awards": "SELECT id FROM public.compensation_awards",
        "contribution_evidence": "SELECT id FROM public.contribution_records",
        "command_evidence": "SELECT id FROM public.task_command_receipts",
        "import_evidence": "SELECT id FROM public.task_import_batches",
        "screened_work": "SELECT id FROM public.workstream_tasks WHERE status<>'draft' OR locked_contribution_policy_version_id IS NOT NULL",
    }
    incompatible = {}
    for category, query in checks.items():
        rows = op.get_bind().execute(text(
            "SELECT id FROM (" + query + ") AS incompatible ORDER BY id LIMIT 21"
        )).scalars().all()
        if rows:
            incompatible[category] = {
                "sample_ids": [str(value) for value in rows[:20]],
                "truncated": len(rows) > 20,
            }
    if incompatible:
        raise RuntimeError("reward transition requires explicit data resolution: " + str(incompatible))


def _extend_guard(signature: str, checks: str) -> None:
    definition = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    begin = re.search(r"\bBEGIN\b", definition, re.IGNORECASE)
    if begin is None:
        raise RuntimeError("reward guard shape changed: " + signature)
    op.execute(definition[:begin.end()] + "\n" + checks + definition[begin.end():])


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _admit_transition()
    op.execute("ALTER TABLE public.contribution_policy_versions ADD COLUMN instrument_type varchar(32)")
    op.execute("ALTER TABLE public.contribution_policy_versions ADD COLUMN unit_code varchar(32)")
    op.execute("ALTER TABLE public.contribution_policy_versions ADD COLUMN adapter_binding_id uuid")
    op.execute("""ALTER TABLE public.contribution_policy_versions
        ADD CONSTRAINT ck_contribution_policy_versions_common_reward_header CHECK (
          (instrument_type IS NULL AND unit_code IS NULL AND adapter_binding_id IS NULL) OR
          (instrument_type IS NOT NULL AND instrument_type IN ('money','project_points')
            AND unit_code IS NOT NULL AND adapter_binding_id IS NOT NULL))""")
    op.execute("ALTER TABLE public.contribution_award_definitions ADD COLUMN task_size varchar(8)")
    op.execute("""ALTER TABLE public.contribution_award_definitions
        ADD CONSTRAINT ck_contribution_award_definitions_reward_definition_size CHECK (
          (contribution_type='accepted_submission' AND task_size IS NOT NULL
            AND task_size IN ('small','medium','large')) OR
          (contribution_type='completed_review' AND task_size IS NULL))""")
    op.execute("ALTER TABLE public.contribution_award_definitions DROP CONSTRAINT uq_contribution_award_definition_instrument")
    op.execute("CREATE UNIQUE INDEX uq_award_definition_size ON public.contribution_award_definitions(contribution_rule_id,task_size) WHERE task_size IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_award_definition_fixed ON public.contribution_award_definitions(contribution_rule_id) WHERE task_size IS NULL")
    op.execute("ALTER TABLE public.compensation_awards DROP CONSTRAINT uq_compensation_awards_contribution_record_id")
    op.execute("ALTER TABLE public.compensation_awards ADD CONSTRAINT uq_compensation_award_contribution UNIQUE(contribution_record_id)")
    op.execute("""ALTER TABLE public.compensation_awards ADD CONSTRAINT fk_compensation_award_policy_project
        FOREIGN KEY(contribution_policy_version_id,project_id)
        REFERENCES public.contribution_policy_versions(id,project_id)
        DEFERRABLE INITIALLY DEFERRED""")
    _policy_guards()


def _policy_guards() -> None:
    custody = op.get_bind().execute(text(
        "SELECT pg_get_functiondef('public.guard_contribution_policy_transition_custody()'::regprocedure)"
    )).scalar_one()
    anchor = ") not between 1 and 2"
    if custody.count(anchor) != 1:
        raise RuntimeError("reward publication custody cardinality shape changed")
    op.execute(custody.replace(anchor,
        ") <> CASE WHEN r.contribution_type='accepted_submission' THEN 3 ELSE 1 END"))
    _extend_guard("public.guard_contribution_policy_version_content()", """
      IF TG_OP='UPDATE' AND OLD.status IN ('published','retired') AND
         ROW(NEW.instrument_type,NEW.unit_code,NEW.adapter_binding_id)
           IS DISTINCT FROM ROW(OLD.instrument_type,OLD.unit_code,OLD.adapter_binding_id)
      THEN RAISE EXCEPTION 'immutable reward policy terms changed' USING ERRCODE='23514'; END IF;
    """)
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
      (EXISTS(SELECT 1 FROM public.contribution_rules r WHERE r.contribution_policy_version_id=v.id
          AND r.compensation_mode='compensated') IS DISTINCT FROM (v.instrument_type IS NOT NULL)) OR
      EXISTS (SELECT 1 FROM public.contribution_rules r WHERE r.contribution_policy_version_id=v.id AND (
        (r.compensation_mode='unpaid' AND EXISTS(SELECT 1 FROM public.contribution_award_definitions d
          WHERE d.contribution_rule_id=r.id)) OR
        (r.compensation_mode='compensated' AND
          (SELECT count(*) FROM public.contribution_award_definitions d WHERE d.contribution_rule_id=r.id)
            <> CASE WHEN r.contribution_type='accepted_submission' THEN 3 ELSE 1 END) OR
        EXISTS (SELECT 1 FROM public.contribution_award_definitions d WHERE d.contribution_rule_id=r.id AND
          ROW(d.instrument_type,d.unit_code,d.adapter_binding_id)
            IS DISTINCT FROM ROW(v.instrument_type,v.unit_code,v.adapter_binding_id)))))
  ) THEN RAISE EXCEPTION 'published contribution policy graph is incomplete' USING ERRCODE='23514'; END IF;
  IF EXISTS(SELECT 1 FROM public.contribution_policies p LEFT JOIN public.contribution_policy_versions v
      ON v.id=p.current_published_version_id AND v.contribution_policy_id=p.id AND v.project_id=p.project_id
      WHERE p.status='active' AND (v.id IS NULL OR v.status<>'published'))
  THEN RAISE EXCEPTION 'active contribution policy selector is invalid' USING ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Reward schema replacement requires a matched application/database restore")
