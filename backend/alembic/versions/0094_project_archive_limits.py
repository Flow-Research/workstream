"""Require approved project archive limits in the source-first PRE SQL guard."""

from alembic import op
from sqlalchemy import text

revision = "0094_project_archive_limits"
down_revision = "0093_verified_email_observation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute(
        "LOCK TABLE public.submission_intake_operations, public.selected_pre_submit_runs "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM public.submission_intake_operations
                     WHERE state IN ('receiving', 'pre_checking')) THEN
            RAISE EXCEPTION 'wait for active submission uploads and PRE checks to end before upgrading';
          END IF;
        END $$;
    """)
    signature = "public.require_selected_pre_source(public.selected_pre_submit_runs)"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    declaration = " rules text; expected_context jsonb; predecessor_id uuid;"
    comparison = " IF request->'default_context' IS DISTINCT FROM expected_context THEN"
    if definition.count(declaration) != 1 or definition.count(comparison) != 1:
        raise RuntimeError("project archive limits predecessor guard changed")
    definition = definition.replace(
        declaration, declaration + "\n locked_policy jsonb; project_caps jsonb;",
    )
    definition = definition.replace(comparison, """
 SELECT p.effective_policy::jsonb INTO locked_policy
 FROM public.effective_project_submission_artifact_policies p
 WHERE p.id=t.locked_effective_project_submission_artifact_policy_id
   AND p.effective_policy_hash=t.locked_effective_project_submission_artifact_policy_hash
   AND p.project_id=r.project_id AND p.guide_version=t.locked_guide_version
   AND p.source_snapshot_id=t.locked_guide_source_snapshot_id
   AND p.source_snapshot_hash=t.locked_guide_source_snapshot_hash
   AND p.lifecycle_status IN ('approved','superseded');
 IF NOT FOUND OR jsonb_typeof(locked_policy) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'selected PRE locked artifact policy mismatch' USING ERRCODE='23514';
 END IF;
 SELECT jsonb_object_agg(key,value) INTO project_caps FROM jsonb_each(locked_policy)
 WHERE key IN ('maximum_archive_size_bytes','maximum_file_size_bytes',
               'maximum_package_size_bytes','maximum_archive_entries')
   AND value IS DISTINCT FROM 'null'::jsonb;
 IF project_caps IS NOT NULL THEN
   IF EXISTS(SELECT 1 FROM jsonb_each(project_caps)
             WHERE jsonb_typeof(value) IS DISTINCT FROM 'number'
                OR value::text !~ '^[1-9][0-9]*$') THEN
     RAISE EXCEPTION 'selected PRE locked artifact limits invalid' USING ERRCODE='23514';
   END IF;
   IF project_caps ? 'maximum_archive_size_bytes'
      AND o.maximum_raw_bytes>(project_caps->>'maximum_archive_size_bytes')::numeric THEN
     RAISE EXCEPTION 'selected PRE locked raw archive limit mismatch' USING ERRCODE='23514';
   END IF;
   expected_context:=expected_context||jsonb_build_object('project_archive_limits',project_caps);
 END IF;
""" + comparison)
    op.execute(definition)


def downgrade() -> None:
    raise RuntimeError("project archive limits migration is forward-only")
