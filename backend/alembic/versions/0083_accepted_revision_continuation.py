"""Check revision eligibility at acceptance and immutable custody at finalization."""
from alembic import op
from sqlalchemy import text

revision = "0083_accepted_revision"
down_revision = "0082_policy_phase_cardinality"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("revision continuation predecessor changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.workstream_tasks, public.submission_intake_operations, "
               "public.submission_bundle_admissions, public.submissions "
               "IN ACCESS EXCLUSIVE MODE")
    _replace("public.require_submission_acceptance_current(public.submission_intake_operations)",
        "      OR p.blocked_reason IS NOT NULL OR p.outcome NOT IN ('kept','rebased')",
        """      OR p.project_id IS DISTINCT FROM o.project_id
      OR p.packet#>'{candidate,target,lineage}' IS DISTINCT FROM
         (SELECT public.revision_task_lineage(to_jsonb(t)) FROM public.workstream_tasks t WHERE t.id=o.task_id)
      OR NOT EXISTS (SELECT 1 FROM public.task_post_submit_routing_manifests m
         JOIN public.checker_submission_fences f ON f.submission_id=m.submission_id
         WHERE m.id=p.routing_manifest_id AND f.current_run_id=m.checker_run_id)
      OR p.blocked_reason IS NOT NULL OR p.outcome NOT IN ('kept','rebased')""")
    _replace("public.guard_revision_admission_context()", "BEGIN\n SELECT selected_request_json",
        """BEGIN
 IF NEW.source_operation_id IS NOT NULL THEN
   PERFORM public.require_source_submission_admission(NEW);
   RETURN NEW;
 END IF;
 SELECT selected_request_json""")
    op.execute(_SOURCE_REVISION)
    for name, result in (("guard_new_revision_submission", "NEW"),
                         ("guard_revision_submission_deadline", "NULL")):
        anchor = f" IF NEW.supersedes_submission_id IS NULL THEN RETURN {result}; END IF;"
        _replace(f"public.{name}()", anchor, anchor + f"""
 IF public.accepted_revision_submission_valid(NEW,{'true' if result == 'NULL' else 'false'}) THEN
   RETURN {result};
 END IF;""")


_SOURCE_REVISION = """
CREATE FUNCTION public.accepted_revision_submission_valid(s public.submissions, committed boolean)
RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE o public.submission_intake_operations%ROWTYPE;
 a public.submission_bundle_admissions%ROWTYPE; p public.task_revision_preparations%ROWTYPE;
BEGIN
 -- At INSERT the binding is not consumed yet. At deferred commit, use the
 -- finalized submission identity, since TASK may already have cleared its pointer.
 SELECT * INTO o FROM public.submission_intake_operations candidate
 WHERE candidate.task_id=s.task_id AND
   ((NOT committed AND candidate.id=(SELECT active_submission_operation_id
       FROM public.workstream_tasks WHERE id=s.task_id))
    OR (committed AND candidate.finalized_submission_id=s.id));
 IF o.id IS NULL THEN RETURN false; END IF;
 SELECT * INTO a FROM public.submission_bundle_admissions WHERE source_operation_id=o.id;
 SELECT * INTO p FROM public.task_revision_preparations
 WHERE id=(o.command_metadata->>'revision_preparation_id')::uuid;
 IF o.state NOT IN ('finalization_pending','finalized') OR a.id IS NULL OR p.id IS NULL
    OR NOT public.submission_finalization_authority_valid(o,'claim')
    OR s.task_assignment_id IS DISTINCT FROM o.assignment_id
    OR s.contributor_id IS DISTINCT FROM o.actor_profile_id
    OR s.supersedes_submission_id IS DISTINCT FROM a.predecessor_submission_id
    OR s.version IS DISTINCT FROM a.predecessor_submission_version+1
    OR p.id IS DISTINCT FROM a.revision_preparation_id
    OR p.preparation_sha256 IS DISTINCT FROM a.revision_preparation_sha256
    OR p.packet#>'{candidate,target,lineage}' IS DISTINCT FROM public.revision_submission_lineage(s)
 THEN RAISE EXCEPTION 'accepted revision submission custody mismatch' USING ERRCODE='23514'; END IF;
 PERFORM public.require_source_submission_admission(a);
 IF committed AND (o.state IS DISTINCT FROM 'finalized'
    OR o.finalized_admission_id IS DISTINCT FROM a.id
    OR a.status IS DISTINCT FROM 'consumed'
    OR a.consumed_by_submission_id IS DISTINCT FROM s.id
    OR NOT EXISTS (SELECT 1 FROM public.submissions retained WHERE retained.id=s.id
       AND retained.submission_bundle_admission_id=a.id)
    OR NOT public.submission_finalization_authority_valid(o,'commit')) THEN
   RAISE EXCEPTION 'accepted revision submission closure mismatch' USING ERRCODE='23514';
 END IF;
 RETURN true;
END $$;
"""


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
