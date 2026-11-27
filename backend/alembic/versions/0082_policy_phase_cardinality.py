"""Require one image per phase for new approvals; preserve retained policy custody."""
from alembic import op

revision = "0082_policy_phase_cardinality"
down_revision = "0081_operation_read_authority"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.project_guide_proposal_approvals IN SHARE ROW EXCLUSIVE MODE")
    # This existing trigger runs only BEFORE INSERT. Historical approvals, including
    # non-null zero/multiple requests, keep their original deferred custody checks.
    op.execute("""
CREATE OR REPLACE FUNCTION public.require_current_guide_proposal_approval()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF NEW.request_json IS NULL OR NEW.target_json->>'result_schema_version'
        IS DISTINCT FROM 'project_guide_check_specification.v1' THEN
        RAISE EXCEPTION 'current guide approval request required' USING ERRCODE='23514';
    END IF;
    IF jsonb_typeof(NEW.request_json->'pre_submit_attachments') IS DISTINCT FROM 'array'
       OR jsonb_typeof(NEW.request_json->'post_submit_attachments') IS DISTINCT FROM 'array'
       OR jsonb_typeof(NEW.effective_pre_submit_plan::jsonb #> '{pre_submit,entries}') IS DISTINCT FROM 'array'
       OR jsonb_typeof(NEW.effective_pre_submit_plan::jsonb #> '{post_submit,entries}') IS DISTINCT FROM 'array'
    THEN
        RAISE EXCEPTION 'guide approval requires one PRE and one POST image'
            USING ERRCODE='23514', CONSTRAINT='ck_guide_approval_phase_cardinality';
    END IF;
    IF jsonb_array_length(NEW.request_json->'pre_submit_attachments') <> 1
       OR jsonb_array_length(NEW.request_json->'post_submit_attachments') <> 1
       OR jsonb_array_length(NEW.effective_pre_submit_plan::jsonb #> '{pre_submit,entries}') <> 1
       OR jsonb_array_length(NEW.effective_pre_submit_plan::jsonb #> '{post_submit,entries}') <> 1
    THEN
        RAISE EXCEPTION 'guide approval requires one PRE and one POST image'
            USING ERRCODE='23514', CONSTRAINT='ck_guide_approval_phase_cardinality';
    END IF;
    RETURN NEW;
END $$
""")


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
