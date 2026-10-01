"""Bind retained checker material facts to the canonical consumed ART admission."""

from alembic import op

revision = "0009_checker_material_lineage"
down_revision = "0008_checker_execution"
branch_labels = None
depends_on = None


def upgrade():
    # Exclude writers throughout preflight and installation, including writers
    # that began before this migration. No feature-row locks enter the validator.
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.execute("LOCK TABLE public.checker_runs IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""
CREATE FUNCTION public.art_submission_material_matches(
    project uuid, task uuid, submission uuid, version integer, material jsonb
) RETURNS boolean LANGUAGE sql STABLE
SET search_path = pg_catalog, pg_temp AS $$
    -- ART owns this scalar seam. Admission insertion already proves verified
    -- ancestry and freezes its identity. Current replica state is deliberately
    -- absent: later loss/quarantine must not invalidate retained evidence.
    SELECT CASE WHEN pg_catalog.jsonb_typeof(material)='object' THEN
        material - ARRAY['submission_id','submission_version','admission_id','binding_id',
                         'content_id','replica_id','content_sha256','byte_count',
                         'semantic_manifest_sha256'] = '{}'::jsonb
        AND pg_catalog.jsonb_typeof(material->'submission_version')='number'
        AND pg_catalog.jsonb_typeof(material->'byte_count')='number'
        AND EXISTS (
        SELECT 1 FROM public.submissions s
        JOIN public.workstream_tasks t ON t.id=s.task_id
        JOIN public.submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id
        JOIN public.artifact_bindings b ON b.id=s.artifact_binding_id
        JOIN public.artifact_contents c ON c.id=s.artifact_content_id
        WHERE s.id=submission AND s.task_id=task AND t.project_id=project
          -- Bind the argument explicitly; an unqualified version names s.version.
          AND s.version=$4
          AND a.status='consumed' AND a.consumed_by_submission_id=s.id
          AND a.consumed_by_submission_version=s.version
          AND a.project_id=project AND a.task_id=s.task_id
          AND a.assignment_id=s.task_assignment_id AND a.actor_profile_id=s.contributor_id
          AND a.predecessor_submission_id IS NOT DISTINCT FROM s.supersedes_submission_id
          AND b.project_id=project AND b.resource_type='submission' AND b.resource_id=s.id::text
          AND b.logical_role='submission_bundle_original' AND b.scope_version=1
          AND b.content_id=c.id AND a.artifact_content_id=c.id
          AND c.media_type='application/zip' AND c.sha256=a.archive_sha256
          AND c.byte_count=a.archive_byte_count
          AND material->'submission_id'=pg_catalog.to_jsonb(s.id)
          AND material->>'submission_version'=s.version::text
          AND material->'admission_id'=pg_catalog.to_jsonb(a.id)
          AND material->'binding_id'=pg_catalog.to_jsonb(b.id)
          AND material->'content_id'=pg_catalog.to_jsonb(c.id)
          AND material->'replica_id'=pg_catalog.to_jsonb(a.verified_replica_id)
          AND material->'content_sha256'=pg_catalog.to_jsonb(c.sha256)
          AND material->>'byte_count'=c.byte_count::text
          AND material->'semantic_manifest_sha256'=pg_catalog.to_jsonb(a.semantic_manifest_sha256)
    ) ELSE false END
$$;
""")
    op.execute("""
COMMENT ON FUNCTION public.art_submission_material_matches(uuid,uuid,uuid,integer,jsonb)
IS 'ART-owned immutable consumed Submission material identity; no current availability or authority decision';
""")
    op.execute("""
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM public.checker_runs r
        WHERE r.status IN ('completed','infrastructure_failed')
          AND r.material_custody::jsonb IS NOT NULL
          AND r.material_custody::jsonb <> 'null'::jsonb
          AND NOT public.art_submission_material_matches(
              r.project_id,r.task_id,r.submission_id,r.submission_version,r.material_custody::jsonb)
    ) THEN
        RAISE EXCEPTION 'retained checker material lacks canonical ART lineage' USING ERRCODE='23514';
    END IF;
END $$;
""")
    op.execute("""
CREATE FUNCTION public.guard_checker_material_lineage() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp AS $$
DECLARE current_run public.checker_runs%rowtype;
BEGIN
    -- A deferred trigger must validate the final row, not an earlier queued image.
    SELECT * INTO current_run FROM public.checker_runs WHERE id=NEW.id;
    IF current_run.status IN ('completed','infrastructure_failed')
       AND current_run.material_custody::jsonb IS NOT NULL
       AND current_run.material_custody::jsonb <> 'null'::jsonb
       AND NOT public.art_submission_material_matches(
           current_run.project_id,current_run.task_id,current_run.submission_id,
           current_run.submission_version,current_run.material_custody::jsonb)
    THEN
        RAISE EXCEPTION 'checker material canonical ART lineage mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER checker_material_lineage
AFTER INSERT OR UPDATE ON public.checker_runs DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION public.guard_checker_material_lineage();
""")


def downgrade() -> None:
    """Refuse downgrade without weakening retained evidence custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
