"""Retain source-backed predecessor custody in revision POST evidence."""
from alembic import op
from sqlalchemy import text

revision = "0075_source_post_custody"
down_revision = "0074_submission_finalization"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.checker_runs IN SHARE ROW EXCLUSIVE MODE")
    op.execute(_CUSTODY)
    _extend_input_authority_digest()
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef('public.checker_input_context_valid(public.checker_runs)'::regprocedure)"
    )).scalar_one()
    if body.count(_OLD_QUERY) != 1 or body.count("'verification_generation','namespace_fingerprint',") != 2:
        raise RuntimeError("revision POST custody predecessor shape changed")
    body = body.replace(_OLD_QUERY, "       OR NOT public.post_submission_material_custody_valid(prior_custody)")
    body = body.replace("'verification_generation','namespace_fingerprint',",
        "'verification_generation','source_operation_id','accepted_source_sha256','acceptance_receipt_sha256','namespace_fingerprint',")
    op.execute(body)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_OLD_QUERY = """       OR NOT EXISTS(
         SELECT 1 FROM public.submission_bundle_admissions a
         JOIN public.artifact_verification_receipts receipt
           ON receipt.id=a.verification_receipt_id
         JOIN public.artifact_replicas replica ON replica.id=a.verified_replica_id
         JOIN public.artifact_storage_namespaces namespace
           ON namespace.id=replica.storage_namespace_id
         WHERE a.id=(prior_custody->>'admission_id')::uuid
           AND prior_custody->>'evidence_id'=
             coalesce(a.pre_submit_evidence_set_id,a.selected_pre_submit_run_id)::text
           AND prior_custody->>'verification_receipt_id'=receipt.id::text
           AND prior_custody->>'verification_job_id'=receipt.verification_job_id::text
           AND prior_custody->>'verification_generation'=receipt.execution_generation::text
           AND prior_custody->>'namespace_fingerprint'=namespace.namespace_fingerprint
           AND prior_custody->>'semantic_manifest_id'=a.semantic_manifest_id::text)"""

_CUSTODY = r"""
CREATE FUNCTION public.post_submission_material_custody_valid(custody jsonb)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(EXISTS (
   SELECT 1 FROM public.submission_bundle_admissions a
   JOIN public.artifact_replicas replica ON replica.id=a.verified_replica_id
   JOIN public.artifact_storage_namespaces namespace ON namespace.id=replica.storage_namespace_id
   LEFT JOIN public.artifact_verification_receipts receipt ON receipt.id=a.verification_receipt_id
   LEFT JOIN public.submission_intake_operations o ON o.id=a.source_operation_id
   WHERE a.id=(custody->>'admission_id')::uuid
     AND custody->>'evidence_id'=coalesce(a.pre_submit_evidence_set_id,a.selected_pre_submit_run_id)::text
     AND custody->>'namespace_fingerprint'=namespace.namespace_fingerprint
     AND custody->>'semantic_manifest_id'=a.semantic_manifest_id::text
     AND ((a.source_operation_id IS NULL
           AND NOT custody ?| ARRAY['source_operation_id','accepted_source_sha256','acceptance_receipt_sha256']
           AND custody->>'verification_receipt_id'=receipt.id::text
           AND custody->>'verification_job_id'=receipt.verification_job_id::text
           AND custody->>'verification_generation'=receipt.execution_generation::text)
       OR (a.source_operation_id IS NOT NULL AND a.verification_receipt_id IS NULL
           AND NOT custody ?| ARRAY['verification_receipt_id','verification_job_id','verification_generation']
           AND o.state='finalized' AND o.finalized_admission_id=a.id
           AND o.finalized_submission_id=a.consumed_by_submission_id
           AND replica.source_operation_id=o.id
           AND custody->>'source_operation_id'=o.id::text
           AND custody->>'accepted_source_sha256'=o.accepted_source_sha256
           AND custody->>'acceptance_receipt_sha256'=o.acceptance_receipt_sha256))
 ),false)
$$;
"""


def _extend_input_authority_digest():
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef('public.checker_input_authority_digest(public.checker_runs)'::regprocedure)"
    )).scalar_one()
    changes = (
        ("jsonb_build_object('material',r.material_custody::jsonb,",
         "(CASE WHEN a.source_operation_id IS NULL THEN jsonb_build_object('material',r.material_custody::jsonb,"),
        ("'semantic_manifest_id',a.semantic_manifest_id::text)",
         "'semantic_manifest_id',a.semantic_manifest_id::text) ELSE jsonb_build_object("
         "'material',r.material_custody::jsonb,'evidence_id',a.selected_pre_submit_run_id::text,"
         "'source_operation_id',o.id::text,'accepted_source_sha256',o.accepted_source_sha256,"
         "'acceptance_receipt_sha256',o.acceptance_receipt_sha256,"
         "'namespace_fingerprint',n.namespace_fingerprint,'semantic_manifest_id',a.semantic_manifest_id::text) END)"),
        ("JOIN public.artifact_verification_receipts v ON v.id=a.verification_receipt_id",
         "LEFT JOIN public.artifact_verification_receipts v ON v.id=a.verification_receipt_id "
         "LEFT JOIN public.submission_intake_operations o ON o.id=a.source_operation_id"),
    )
    for old, new in changes:
        if body.count(old) != 1:
            raise RuntimeError("POST materialization digest predecessor shape changed")
        body = body.replace(old, new)
    op.execute(body)
