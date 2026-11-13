"""Require exact audited service decisions for cleanup claim and confirmation."""
from alembic import op
from sqlalchemy import text

revision = "0080_cleanup_decisions"
down_revision = "0079_cleanup_authority"
branch_labels = None
depends_on = None


def upgrade():
    """Add audit references without inventing authority for historical claims."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submission_source_cleanup_claims IN ACCESS EXCLUSIVE MODE")
    for column, constraint in (
        ("claim_decision_id", "fk_source_cleanup_claim_decision"),
        ("confirmation_decision_id", "fk_source_cleanup_confirmation_decision"),
    ):
        op.execute(f"ALTER TABLE public.submission_source_cleanup_claims ADD COLUMN {column} uuid")
        op.execute(f"ALTER TABLE public.submission_source_cleanup_claims ADD CONSTRAINT {constraint} "
                   f"FOREIGN KEY ({column}) REFERENCES public.audit_events(id)")
    op.execute(_AUTHORITY)
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef('public.guard_submission_source_cleanup()'::regprocedure)"
    )).scalar_one()
    replacements = {
        "IF NEW.generation<>1 OR NEW.confirmed_at IS NOT NULL THEN":
            "IF NEW.generation<>1 OR NEW.confirmed_at IS NOT NULL OR NEW.confirmation_decision_id IS NOT NULL THEN",
        "IF (to_jsonb(NEW)-'confirmed_at') IS DISTINCT FROM (to_jsonb(OLD)-'confirmed_at')":
            "IF (to_jsonb(NEW)-ARRAY['confirmed_at','confirmation_decision_id']) IS DISTINCT FROM "
            "(to_jsonb(OLD)-ARRAY['confirmed_at','confirmation_decision_id'])",
        "IF OLD.lease_expires_at>clock_timestamp() OR NEW.generation<>OLD.generation+1 OR NEW.confirmed_at IS NOT NULL THEN":
            "IF OLD.lease_expires_at>clock_timestamp() OR NEW.generation<>OLD.generation+1 "
            "OR NEW.confirmed_at IS NOT NULL OR NEW.confirmation_decision_id IS NOT NULL THEN",
        " IF NEW.lease_expires_at<=clock_timestamp() THEN":
            " IF NOT public.source_cleanup_authority_valid(NEW,'claim') OR "
            "(NEW.confirmed_at IS NOT NULL AND NOT public.source_cleanup_authority_valid(NEW,'confirm')) THEN\n"
            "   RAISE EXCEPTION 'source cleanup authority differs' USING ERRCODE='23514'; END IF;\n"
            " IF NEW.lease_expires_at<=clock_timestamp() THEN",
    }
    for old, new in replacements.items():
        if body.count(old) != 1:
            raise RuntimeError("cleanup decision predecessor guard changed")
        body = body.replace(old, new)
    op.execute(body)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_AUTHORITY = """
CREATE FUNCTION public.source_cleanup_authority_valid(c public.submission_source_cleanup_claims, phase text)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(EXISTS (
  SELECT 1 FROM public.audit_events a JOIN public.actor_profiles p ON p.id::text=a.actor_id
  JOIN public.submission_intake_operations o ON o.id=c.operation_id
  WHERE a.id=(CASE WHEN phase='claim' THEN c.claim_decision_id ELSE c.confirmation_decision_id END)
    AND phase IN ('claim','confirm') AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
    AND a.actor_ref_kind='actor_profile' AND p.actor_kind='service' AND p.service_identity='workstream.artifact.source_cleanup'
    AND a.action_id='artifact.submission_source.cleanup' AND a.permission_id='artifact.submission_source.cleanup'
    AND a.project_id=o.project_id AND a.resource_type='submission_operation' AND a.resource_id=o.id::text
    AND a.target_ref_kind='project' AND a.target_ref_id=o.project_id::text AND a.matched_grant_id IS NULL
    AND a.denial_code IS NULL AND a.request_id IS NOT NULL AND a.correlation_id IS NOT NULL
    AND a.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',
      public.external_checker_registry_digest(jsonb_build_object('resource_context',jsonb_build_object(
        'resource_type','submission_source_cleanup','resource_id',o.id::text,'operation_id',o.id::text,
        'project_id',o.project_id::text,'task_id',o.task_id::text,
        'source_sha256',public.external_checker_registry_digest(
          c.source || jsonb_build_object('schema_version','workstream.sealed_submission_source.v1')),
        'claim_id',c.claim_id::text,'claim_generation',c.generation,'phase',phase))))
 ),false)
$$
"""
