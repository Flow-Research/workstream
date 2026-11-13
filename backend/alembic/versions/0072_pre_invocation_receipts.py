"""Retain provider invocation receipts in source PRE finalization evidence."""
from alembic import op
from sqlalchemy import text

revision = "0072_pre_invocation_receipts"
down_revision = "0071_source_first_pre"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("PRE receipt predecessor shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.selected_pre_submit_runs IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.selected_pre_submit_runs
        WHERE request_json->>'schema_version'='workstream.selected_pre_submit_reservation.v2'
          AND status IN ('queued','running')) THEN
        RAISE EXCEPTION 'drain source PRE runs before migrating invocation receipts'
          USING ERRCODE='55000';
      END IF;
    END $$""")
    op.execute(r"""
CREATE FUNCTION public.require_selected_pre_invocation(r public.selected_pre_submit_runs)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE receipt jsonb:=r.terminal_json->'invocation_receipt'; identity jsonb;
 runtime jsonb; cleanup jsonb; timings jsonb; field text; stage_total bigint:=0;
 member jsonb; native boolean;
BEGIN
 IF receipt='null'::jsonb AND r.status='infrastructure_failed' THEN RETURN; END IF;
 IF jsonb_typeof(receipt) IS DISTINCT FROM 'object'
    OR NOT receipt ?& ARRAY['schema_version','adapter_provider_key','operation','phase',
      'invocation','provider_invocation_id','outcome','reason','runtime','timings_ms','cleanup']
    OR receipt-ARRAY['schema_version','adapter_provider_key','operation','phase',
      'invocation','provider_invocation_id','outcome','reason','runtime','timings_ms','cleanup']<>'{}'::jsonb
    OR receipt->>'schema_version' IS DISTINCT FROM 'workstream.pre_submit_invocation.v1'
    OR receipt->>'operation' IS DISTINCT FROM 'execute_pre'
    OR receipt->>'phase' IS DISTINCT FROM 'pre_submit'
    OR coalesce(receipt->>'adapter_provider_key','') !~ '^[a-z][a-z0-9_]{0,63}$'
    OR jsonb_typeof(receipt->'provider_invocation_id') IS DISTINCT FROM 'string'
    OR coalesce(receipt->>'provider_invocation_id','') !~ '^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,254}$'
 THEN RAISE EXCEPTION 'selected PRE invocation shape mismatch' USING ERRCODE='23514'; END IF;
 identity:=receipt->'invocation'; runtime:=receipt->'runtime';
 cleanup:=receipt->'cleanup'; timings:=receipt->'timings_ms';
 IF jsonb_typeof(identity) IS DISTINCT FROM 'object'
    OR identity IS DISTINCT FROM jsonb_build_object(
      'operation','execute_pre','run_id',r.id::text,'source_operation_id',r.source_operation_id::text,
      'request_digest',r.request_digest,'source_sha256',r.request_json->>'source_sha256',
      'profile_sha256',public.external_checker_registry_digest(r.request_json->'runtime_profile'),
      'image_digest',r.request_json->'policy'->'entries'->0->'registry'->>'image_digest',
      'config_image_id',identity->>'config_image_id','lease_id',r.lease_id::text,
      'lease_generation',r.lease_generation)
    OR coalesce(identity->>'config_image_id','') !~ '^sha256:[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'selected PRE invocation identity mismatch' USING ERRCODE='23514'; END IF;
 IF (r.status='completed' AND (receipt->>'outcome' IS DISTINCT FROM 'completed'
       OR receipt->'reason' IS DISTINCT FROM 'null'::jsonb))
    OR (r.status='infrastructure_failed' AND (
      coalesce(receipt->>'outcome','') NOT IN ('infrastructure_failure','deadline_exceeded')
      OR receipt->>'reason' IS DISTINCT FROM r.terminal_json->>'infrastructure_failure_code'
      OR NOT ((receipt->>'outcome'='deadline_exceeded' AND receipt->>'reason'='deadline_exceeded')
        OR (receipt->>'outcome'='infrastructure_failure' AND receipt->>'reason' IN
          ('capacity_exceeded','material_unavailable','implementation_unavailable','invalid_output')))))
 THEN RAISE EXCEPTION 'selected PRE invocation outcome mismatch' USING ERRCODE='23514'; END IF;
 native:=runtime->>'provider'='smolvm';
 IF jsonb_typeof(runtime) IS DISTINCT FROM 'object'
    OR coalesce(runtime->>'provider','') NOT IN ('smolvm','managed')
    OR jsonb_typeof(runtime->'version') IS DISTINCT FROM 'string'
    OR length(runtime->>'version') NOT BETWEEN 1 AND 100
    OR runtime->'profile' IS DISTINCT FROM r.request_json->'runtime_profile'
    OR (native AND (runtime-ARRAY['provider','version','binary_sha256','guest_sha256','profile']<>'{}'::jsonb
      OR coalesce(runtime->>'binary_sha256','') !~ '^sha256:[0-9a-f]{64}$'
      OR coalesce(runtime->>'guest_sha256','') !~ '^sha256:[0-9a-f]{64}$'))
    OR (NOT native AND (runtime-ARRAY['provider','version','deployment_sha256','profile']<>'{}'::jsonb
      OR coalesce(runtime->>'deployment_sha256','') !~ '^sha256:[0-9a-f]{64}$'))
    OR jsonb_typeof(cleanup) IS DISTINCT FROM 'object'
    OR coalesce(cleanup->>'disposition','') NOT IN ('destroyed','pending')
    OR jsonb_typeof(cleanup->'obligation_id') IS DISTINCT FROM 'string'
    OR coalesce(cleanup->>'obligation_id','') !~ '^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,254}$'
    OR (native AND (cleanup-ARRAY['obligation_id','journal_sha256','disposition']<>'{}'::jsonb
      OR cleanup->>'obligation_id' IS DISTINCT FROM receipt->>'provider_invocation_id'
      OR coalesce(cleanup->>'journal_sha256','') !~ '^sha256:[0-9a-f]{64}$'))
    OR (NOT native AND (cleanup-ARRAY['obligation_id','provider_receipt_sha256','disposition']<>'{}'::jsonb
      OR coalesce(cleanup->>'provider_receipt_sha256','') !~ '^sha256:[0-9a-f]{64}$'))
 THEN RAISE EXCEPTION 'selected PRE invocation runtime mismatch' USING ERRCODE='23514'; END IF;
 IF jsonb_typeof(timings) IS DISTINCT FROM 'object'
    OR timings-ARRAY['admission','preparation','execution','cleanup','total']<>'{}'::jsonb
 THEN RAISE EXCEPTION 'selected PRE invocation timings mismatch' USING ERRCODE='23514'; END IF;
 FOREACH field IN ARRAY ARRAY['admission','preparation','execution','cleanup','total'] LOOP
   IF jsonb_typeof(timings->field) IS DISTINCT FROM 'number'
      OR coalesce(timings->>field,'') !~ '^[0-9]+$'
      OR (timings->>field)::numeric>14400000
   THEN RAISE EXCEPTION 'selected PRE invocation timing bound mismatch' USING ERRCODE='23514'; END IF;
   IF field<>'total' THEN stage_total:=stage_total+(timings->>field)::bigint; END IF;
 END LOOP;
 IF stage_total>(timings->>'total')::bigint OR (timings->>'total')::bigint>
    (r.request_json->'runtime_profile'->>'aggregate_deadline_ms')::bigint
 THEN RAISE EXCEPTION 'selected PRE invocation deadline mismatch' USING ERRCODE='23514'; END IF;
 IF r.status='completed' THEN
   IF r.terminal_json->'execution'->>'request_digest' IS DISTINCT FROM r.request_digest
      OR r.terminal_json->'execution'->>'lease_id' IS DISTINCT FROM r.lease_id::text
      OR r.terminal_json->'execution'->'lease_generation' IS DISTINCT FROM to_jsonb(r.lease_generation)
   THEN RAISE EXCEPTION 'selected PRE invocation worker fence mismatch' USING ERRCODE='23514'; END IF;
   FOR member IN SELECT value FROM jsonb_array_elements(r.terminal_json->'execution'->'external_members') LOOP
     IF member->'isolation'->>'config_image_id' IS DISTINCT FROM identity->>'config_image_id'
        OR member->'isolation'->>'platform_manifest_digest' IS DISTINCT FROM identity->>'image_digest'
        OR (native AND (member->'isolation'->>'runtime' IS DISTINCT FROM 'smolvm'
          OR member->'isolation'->>'isolation_mode' IS DISTINCT FROM 'smol-microvm'))
        OR (NOT native AND (member->'isolation'->>'provider' IS DISTINCT FROM 'managed'
          OR member->'isolation'->>'deployment_sha256' IS DISTINCT FROM runtime->>'deployment_sha256'))
     THEN RAISE EXCEPTION 'selected PRE invocation worker runtime mismatch' USING ERRCODE='23514'; END IF;
   END LOOP;
 END IF;
END $$
""")
    signature = "public.guard_selected_pre_submit_run()"
    _replace(signature, "'workstream.selected_pre_submit_terminal.v2'",
             "'workstream.selected_pre_submit_terminal.v3'")
    _replace(signature, "'outcome','execution','infrastructure_failure_code',",
             "'outcome','execution','invocation_receipt','infrastructure_failure_code',")
    _replace(signature, " perform public.require_selected_pre_source(new);",
             " IF old.status='running' THEN PERFORM public.require_selected_pre_invocation(new); END IF;\n"
             " perform public.require_selected_pre_source(new);")
    signature = "public.selected_pre_submit_facts_digest(public.selected_pre_submit_runs,text)"
    _replace(signature, "then 'workstream.selected_pre_submit_finalize.v2'",
             "then CASE WHEN r.terminal_json->>'schema_version'='workstream.selected_pre_submit_terminal.v3' "
             "THEN 'workstream.selected_pre_submit_finalize.v3' ELSE 'workstream.selected_pre_submit_finalize.v2' END")
    _replace(signature,
             "'infrastructure_failure_code',r.terminal_json->'infrastructure_failure_code'))",
             "'infrastructure_failure_code',r.terminal_json->'infrastructure_failure_code') || "
             "CASE WHEN r.terminal_json->>'schema_version'='workstream.selected_pre_submit_terminal.v3' "
             "THEN jsonb_build_object('invocation_receipt',r.terminal_json->'invocation_receipt') "
             "ELSE '{}'::jsonb END)")


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
