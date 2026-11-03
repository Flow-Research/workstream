"""Current check-specification custody while preserving retained compilation bytes."""

from alembic import op
from sqlalchemy import text

revision = "0066_guide_check_specification"
down_revision = "0065_claim_starts_work"
branch_labels = None
depends_on = None

RESULT = "project_guide_check_specification.v1"
HASHES = "project_guide_check_specification_hashes.v1"
DIGEST = "~ '^sha256:[0-9a-f]{64}$'"
FIVE = ("sufficiency_hash", "artifact_policy_hash", "requirement_inventory_hash",
        "pre_submit_hash", "post_submit_hash")
SEVEN = FIVE + ("capability_suggestions_hash", "setup_notes_hash")


def hashes_check(column, current):
    keys = FIVE if current else SEVEN
    pairs = ",".join(f"'{key}',{column}->>'{key}'" for key in keys)
    if current:
        pairs = f"'schema_version',{column}->>'schema_version'," + pairs
    checks = " and ".join(
        f"coalesce(({column}->>'{key}') {DIGEST},false)" for key in keys
    )
    version = f"{column}->>'schema_version' IS NOT DISTINCT FROM '{HASHES}' and " if current else ""
    return (f"json_typeof({column})='object' and {version}"
            f"{column}::jsonb=jsonb_build_object({pairs}) and {checks}")


def replace_function(signature, *changes):
    body = op.get_bind().execute(
        text("select pg_catalog.pg_get_functiondef(cast(:signature as regprocedure))"),
        {"signature": signature},
    ).scalar_one()
    for old, new in changes:
        if body.count(old) != 1:
            raise RuntimeError("guide specification predecessor changed: " + signature)
        body = body.replace(old, new)
    op.execute(body)
    op.execute("ALTER FUNCTION " + signature + " SET search_path=pg_catalog,public,pg_temp")


def replace_request_digest():
    signature = ("public.project_guide_compilation_request_facts_digest("
                 "public.project_guide_compilation_request_operations,"
                 "public.project_guide_compilation_attempts)")
    old = op.get_bind().execute(
        text("select pg_catalog.pg_get_functiondef(cast(:signature as regprocedure))"),
        {"signature": signature},
    ).scalar_one()
    old_name = "public.project_guide_compilation_request_facts_digest("
    if old.count(old_name) != 1:
        raise RuntimeError("guide request digest predecessor changed")
    op.execute(old.replace(old_name, "public.retained_guide_compilation_request_facts_digest("))
    op.execute(
        "ALTER FUNCTION public.retained_guide_compilation_request_facts_digest("
        "public.project_guide_compilation_request_operations,"
        "public.project_guide_compilation_attempts) "
        "SET search_path=pg_catalog,public,pg_temp"
    )
    fields = (
        ("agent_identity", "attempt.agent_identity"),
        ("agent_version", "attempt.agent_version"),
        ("canonical_input_hash", "attempt.canonical_input_hash"),
        ("expected_predecessor_compilation_id", "op.expected_predecessor_compilation_id::text"),
        ("guide_id", "op.guide_id"),
        ("guide_material_hash", "attempt.guide_material_hash"),
        ("guide_version", "attempt.guide_version"),
        ("idempotency_key", "op.idempotency_key::text"),
        ("instruction_version", "attempt.instruction_version"),
        ("operation_id", "op.operation_id::text"),
        ("project_id", "op.project_id"),
        ("request_id", "op.request_id::text"),
        ("result_schema_version", "attempt.result_schema_version"),
        ("setup_generation", "attempt.setup_generation"),
        ("setup_run_id", "op.setup_run_id"),
        ("source_snapshot_hash", "attempt.source_snapshot_hash"),
        ("source_snapshot_id", "op.source_snapshot_id"),
    )
    parts = []
    for key, value in fields:
        encoded = value + "::text" if key == "setup_generation" else f"coalesce(to_json({value})::text,'null')"
        parts.append(f"""'"{key}":' || {encoded}""")
    current = """'{"domain":"workstream.project_guide_compilation.facts.v1","facts":{' || """ + " || ',' || ".join(parts) + """ || '}}'"""
    op.execute(
        "CREATE OR REPLACE FUNCTION public.project_guide_compilation_request_facts_digest("
        "op public.project_guide_compilation_request_operations,"
        "attempt public.project_guide_compilation_attempts) RETURNS text "
        "LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$ "
        "SELECT CASE WHEN attempt.result_schema_version IS NULL THEN "
        "public.retained_guide_compilation_request_facts_digest(op,attempt) ELSE "
        "'sha256:' || encode(sha256(convert_to(" + current + ",'UTF8')),'hex') END $$"
    )


def add_approval_attachment_validator() -> None:
    """Verify the exact human attachment arrays against immutable locked images."""
    op.execute("""
CREATE FUNCTION public.guide_approval_attachments_valid(request jsonb, plan jsonb)
RETURNS boolean LANGUAGE plpgsql STABLE STRICT
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE phase_name text; selected jsonb; entries jsonb; attachment jsonb; entry jsonb;
        prior_key text; key_name text; index_no integer; pre_budget bigint := 60000;
        post_budget bigint := 60000; registry_id uuid;
BEGIN
  IF jsonb_typeof(request) IS DISTINCT FROM 'object'
     OR (SELECT count(*) FROM jsonb_object_keys(request))<>7
     OR NOT request ?& ARRAY[
       'target','acknowledged_warning_hashes',
       'expected_previous_approval_operation_id',
       'expected_previous_approval_output_digest','idempotency_key',
       'pre_submit_attachments','post_submit_attachments']
  THEN RAISE EXCEPTION 'approval request shape invalid' USING ERRCODE='23514'; END IF;
  FOREACH phase_name IN ARRAY ARRAY['pre_submit','post_submit'] LOOP
    selected := request->(phase_name||'_attachments');
    entries := plan->phase_name->'entries';
    IF jsonb_typeof(selected) IS DISTINCT FROM 'array'
       OR jsonb_typeof(entries) IS DISTINCT FROM 'array'
       OR jsonb_array_length(selected)>200
       OR jsonb_array_length(selected)<>jsonb_array_length(entries)
    THEN RAISE EXCEPTION 'approval attachment phase mismatch' USING ERRCODE='23514'; END IF;
    prior_key := NULL; index_no := 0;
    FOR attachment IN SELECT value FROM jsonb_array_elements(selected) AS item(value) LOOP
      index_no := index_no+1;
      entry := entries->(index_no-1);
      key_name := attachment->>'requirement_id';
      IF jsonb_typeof(attachment) IS DISTINCT FROM 'object'
         OR (SELECT count(*) FROM jsonb_object_keys(attachment))<>4
         OR NOT attachment ?& ARRAY[
              'requirement_id','registry_entry_id','registry_entry_digest','configuration']
         OR jsonb_typeof(attachment->'requirement_id') IS DISTINCT FROM 'string'
         OR jsonb_typeof(attachment->'registry_entry_id') IS DISTINCT FROM 'string'
         OR jsonb_typeof(attachment->'registry_entry_digest') IS DISTINCT FROM 'string'
         OR (key_name ~ '^[a-z][a-z0-9_.-]{0,99}$') IS NOT TRUE
         OR key_name LIKE 'workstream.%'
         OR (prior_key IS NOT NULL AND key_name COLLATE "C" <= prior_key COLLATE "C")
         OR jsonb_typeof(attachment->'configuration') IS DISTINCT FROM 'object'
         OR octet_length((attachment->'configuration')::text)>65536
         OR (attachment->>'registry_entry_digest' ~ '^sha256:[0-9a-f]{64}$') IS NOT TRUE
      THEN RAISE EXCEPTION 'approval attachment invalid' USING ERRCODE='23514'; END IF;
      registry_id := (attachment->>'registry_entry_id')::uuid;
      IF (get_byte(uuid_send(registry_id),6) >> 4)<>7
         OR (get_byte(uuid_send(registry_id),8) & 192)<>128
         OR entry->>'requirement_id' IS DISTINCT FROM key_name
         OR entry->>'stage' IS DISTINCT FROM phase_name
         OR entry->'registry'->>'registry_entry_id' IS DISTINCT FROM registry_id::text
         OR entry->'registry'->>'entry_digest' IS DISTINCT FROM
              attachment->>'registry_entry_digest'
         OR entry->'configuration' IS DISTINCT FROM attachment->'configuration'
         OR entry->>'configuration_sha256' IS DISTINCT FROM
              public.external_checker_registry_digest(attachment->'configuration')
         OR jsonb_typeof(entry#>'{registry,resources,deadline_ms}') IS DISTINCT FROM 'number'
         OR (entry#>>'{registry,resources,deadline_ms}')::bigint<=0
      THEN RAISE EXCEPTION 'locked image differs from approval attachment' USING ERRCODE='23514'; END IF;
      IF phase_name='pre_submit' THEN
        pre_budget := pre_budget + (entry#>>'{registry,resources,deadline_ms}')::bigint + 60000;
      ELSE
        post_budget := post_budget + (entry#>>'{registry,resources,deadline_ms}')::bigint
          + 60000 + CASE WHEN attachment->'configuration'->>'workstream_forge_facts_version'='v1'
                         THEN 120000 ELSE 0 END;
      END IF;
      prior_key := key_name;
    END LOOP;
  END LOOP;
  IF pre_budget>7200000 OR post_budget>3400000 THEN
    RAISE EXCEPTION 'locked image budget exceeded' USING ERRCODE='23514';
  END IF;
  RETURN true;
EXCEPTION WHEN SQLSTATE '23514' THEN RAISE;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'approval attachment value invalid' USING ERRCODE='23514';
END $$
    """)


def replace_proposal_target() -> None:
    """Current target binds the result format while old targets stay verifiable."""
    signature = "public.require_guide_proposal_target(jsonb,text,uuid)"
    replace_function(
        signature,
        ("DECLARE expected jsonb;", "DECLARE expected jsonb; result_version text;"),
        (") INTO expected FROM project_guide_setup_finalizations f",
         "),c.result_schema_version INTO expected,result_version FROM project_guide_setup_finalizations f"),
        ("IF expected IS NULL OR target IS DISTINCT FROM expected",
         """IF result_version='project_guide_check_specification.v1' THEN
          expected := expected - ARRAY[
            'pre_catalogue_id','pre_catalogue_version','pre_catalogue_schema_version',
            'pre_catalogue_manifest_hash','post_catalogue_id','post_catalogue_version',
            'post_catalogue_schema_version','post_catalogue_manifest_hash'
          ] || jsonb_build_object('result_schema_version',result_version);
        ELSIF result_version IS NOT NULL THEN
          RAISE EXCEPTION 'guide proposal result format invalid' USING ERRCODE='23514';
        END IF;
        IF expected IS NULL OR target IS DISTINCT FROM expected"""),
    )


def replace_proposal_approval() -> None:
    """Enforce full current request custody without reinterpreting old approvals."""
    signature = "public.require_guide_proposal_approval()"
    old = """OR a.request_digest IS DISTINCT FROM guide_proposal_hash(jsonb_build_object(
             'target',a.target_json::jsonb,'idempotency_key',r.idempotency_key,
             'acknowledged_warning_hashes',warning_hashes,
             'expected_previous_approval_operation_id',prior.operation_id,
             'expected_previous_approval_output_digest',prior.output_digest))"""
    new = """OR (a.request_json IS NULL AND
             a.request_digest IS DISTINCT FROM guide_proposal_hash(jsonb_build_object(
               'target',a.target_json::jsonb,'idempotency_key',r.idempotency_key,
               'acknowledged_warning_hashes',warning_hashes,
               'expected_previous_approval_operation_id',prior.operation_id,
               'expected_previous_approval_output_digest',prior.output_digest)))
           OR (a.request_json IS NOT NULL AND (
               a.target_json->>'result_schema_version' IS DISTINCT FROM
                 'project_guide_check_specification.v1'
               OR a.request_json->'target' IS DISTINCT FROM a.target_json::jsonb
               OR a.request_json->>'idempotency_key' IS DISTINCT FROM r.idempotency_key::text
               OR a.request_json->'acknowledged_warning_hashes' IS DISTINCT FROM warning_hashes
               OR a.request_json->>'expected_previous_approval_operation_id'
                    IS DISTINCT FROM prior.operation_id::text
               OR a.request_json->>'expected_previous_approval_output_digest'
                    IS DISTINCT FROM prior.output_digest
               OR a.request_digest IS DISTINCT FROM public.guide_proposal_hash(a.request_json)
               OR NOT public.guide_approval_attachments_valid(
                    a.request_json,a.effective_pre_submit_plan::jsonb)))"""
    replace_function(signature, (old, new))


def replace_post_policy() -> None:
    """New POST is the approval's locked body; retained POST keeps old evidence."""
    signature = "public.require_post_policy_operation()"
    # The existing locked-body equality is authoritative for both retained and
    # current approvals. The old result-binding loops below are retired for
    # current approvals only; retained rows keep their historical guard.
    definition = op.get_bind().execute(
        text("select pg_catalog.pg_get_functiondef(cast(:signature as regprocedure))"),
        {"signature": signature},
    ).scalar_one()
    anchor = """      IF EXISTS(
        SELECT 1 FROM project_guide_compilations c,
          jsonb_array_elements(c.canonical_result::jsonb->'post_submit_bindings') binding"""
    if definition.count(anchor) != 1:
        raise RuntimeError("POST result-binding predecessor changed")
    definition = definition.replace(anchor, "      IF a.request_json IS NULL THEN\n" + anchor)
    tail = """      expected := jsonb_build_object(
        'locator'"""
    if definition.count(tail) != 1:
        raise RuntimeError("POST resource predecessor changed")
    definition = definition.replace(tail, "      END IF;\n" + tail)
    old_catalogue = """         OR p.policy_body->>'catalogue_manifest_sha256' IS DISTINCT FROM t->'proposal'->>'post_catalogue_manifest_hash'"""
    if definition.count(old_catalogue) != 0:
        raise RuntimeError("POST current locked-body predecessor changed")
    # Current resource JSON no longer carries catalogue_manifest_hash; retained
    # rows keep that key and continue to compare against the old target.
    resource = """        'catalogue_manifest_hash',t->'proposal'->>'post_catalogue_manifest_hash',"""
    if definition.count(resource) != 1:
        raise RuntimeError("POST resource catalogue predecessor changed")
    definition = definition.replace(resource, "")
    check = """IF NEW.resource_context_json::jsonb IS DISTINCT FROM expected"""
    if definition.count(check) != 1:
        raise RuntimeError("POST resource check predecessor changed")
    definition = definition.replace(
        check,
        """IF a.request_json IS NULL THEN
        expected := expected || jsonb_build_object(
          'catalogue_manifest_hash',t->'proposal'->>'post_catalogue_manifest_hash');
      END IF;
      IF NEW.resource_context_json::jsonb IS DISTINCT FROM expected""",
    )
    op.execute(definition)
    op.execute("ALTER FUNCTION " + signature + " SET search_path=pg_catalog,public,pg_temp")


def replace_false_review_activation() -> None:
    """Current specifications do not classify requirements by reviewer disposition."""
    old = """                        AND CASE
                          WHEN jsonb_typeof(c.canonical_result::jsonb->'requirements')='array'
                          THEN NOT EXISTS(
                            SELECT 1 FROM jsonb_array_elements(
                              c.canonical_result::jsonb->'requirements'
                            ) AS requirement(value)
                            WHERE jsonb_typeof(requirement.value) IS DISTINCT FROM 'object'
                               OR jsonb_typeof(requirement.value->'disposition') IS DISTINCT FROM 'string'
                               OR requirement.value->>'disposition'='human_review'
                          )
                          ELSE false
                        END"""
    new = """                        AND ((c.result_schema_version IS NULL
                              AND CASE
                                WHEN jsonb_typeof(c.canonical_result::jsonb->'requirements')='array'
                                THEN NOT EXISTS(
                                  SELECT 1 FROM jsonb_array_elements(
                                    c.canonical_result::jsonb->'requirements'
                                  ) AS requirement(value)
                                  WHERE jsonb_typeof(requirement.value) IS DISTINCT FROM 'object'
                                     OR jsonb_typeof(requirement.value->'disposition') IS DISTINCT FROM 'string'
                                     OR requirement.value->>'disposition'='human_review'
                                )
                                ELSE false
                              END)
                          OR (c.result_schema_version='project_guide_check_specification.v1'
                              AND target->'proposal'->>'result_schema_version'
                                  IS NOT DISTINCT FROM c.result_schema_version
                              AND c.canonical_result::jsonb->>'schema_version'
                                  IS NOT DISTINCT FROM c.result_schema_version
                              AND jsonb_typeof(c.canonical_result::jsonb->'requirements')='array'))"""
    replace_function("public.require_guide_activation_custody(uuid,boolean)", (old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute(
        "LOCK TABLE public.project_guide_compilation_attempts, "
        "public.project_guide_compilations, public.project_guide_setup_finalizations "
        "IN ACCESS EXCLUSIVE MODE"
    )
    attempt = "public.project_guide_compilation_attempts"
    compilation = "public.project_guide_compilations"
    finalization = "public.project_guide_setup_finalizations"
    for table in (attempt, compilation):
        op.execute(f"ALTER TABLE {table} ADD COLUMN result_schema_version varchar(100)")
    for column in (
        "pre_catalogue_id", "pre_catalogue_version", "pre_catalogue_schema_version",
        "pre_catalogue_manifest_hash", "post_catalogue_id", "post_catalogue_version",
        "post_catalogue_schema_version", "post_catalogue_manifest_hash",
    ):
        op.execute(f"ALTER TABLE {attempt} ALTER COLUMN {column} DROP NOT NULL")
    for column in ("pre_catalogue_manifest_hash", "post_catalogue_manifest_hash"):
        op.execute(f"ALTER TABLE {compilation} ALTER COLUMN {column} DROP NOT NULL")
    for table, names in (
        (attempt, (
            "ck_project_guide_compilation_attempts_ck_compilation_at_00d8",
            "ck_project_guide_compilation_attempts_ck_compilation_at_31c4",
        )),
        (compilation, (
            "ck_project_guide_compilations_ck_project_guide_compilat_9cd9",
            "ck_project_guide_compilations_ck_project_guide_compilat_dafe",
        )),
        (finalization, ("ck_project_guide_setup_finalizations_ck_finalization_components",)),
    ):
        for name in names:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    common = (f"source_snapshot_hash {DIGEST} and canonical_input_hash {DIGEST} "
              f"and guide_material_hash {DIGEST}")
    retained = f"pre_catalogue_manifest_hash {DIGEST} and post_catalogue_manifest_hash {DIGEST}"
    null_catalogue = " and ".join(f"{key} is null" for key in (
        "pre_catalogue_id", "pre_catalogue_version", "pre_catalogue_schema_version",
        "pre_catalogue_manifest_hash", "post_catalogue_id", "post_catalogue_version",
        "post_catalogue_schema_version", "post_catalogue_manifest_hash",
    ))
    op.execute(
        f"ALTER TABLE {attempt} ADD CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_00d8 "
        f"CHECK ({common} and ((result_schema_version is null and {retained}) or "
        f"(result_schema_version='{RESULT}' and {null_catalogue})))"
    )
    op.execute(
        f"ALTER TABLE {attempt} ADD CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_31c4 "
        f"CHECK (component_hashes is null or "
        f"((result_schema_version is null and ({hashes_check('component_hashes', False)})) "
        f"or (result_schema_version='{RESULT}' and "
        f"({hashes_check('component_hashes', True)}))))"
    )
    op.execute(
        f"ALTER TABLE {attempt} ADD CONSTRAINT ck_compilation_attempt_spec_result "
        "CHECK (result_schema_version is null or canonical_result is null or "
        "canonical_result->>'schema_version' IS NOT DISTINCT FROM result_schema_version)"
    )
    op.execute(
        f"ALTER TABLE {compilation} ADD CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_9cd9 "
        f"CHECK ({common} and result_hash {DIGEST} and "
        f"((result_schema_version is null and {retained}) or "
        f"(result_schema_version='{RESULT}' and pre_catalogue_manifest_hash is null "
        "and post_catalogue_manifest_hash is null)))"
    )
    op.execute(
        f"ALTER TABLE {compilation} ADD CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_dafe "
        "CHECK (octet_length(canonical_result::text)<=4194304 and "
        f"((result_schema_version is null and ({hashes_check('component_hashes', False)})) "
        f"or (result_schema_version='{RESULT}' and "
        f"({hashes_check('component_hashes', True)}) and "
        "canonical_result->>'schema_version' IS NOT DISTINCT FROM result_schema_version)))"
    )
    op.execute(
        f"ALTER TABLE {finalization} ADD CONSTRAINT ck_finalization_components "
        f"CHECK (((result_schema_version='{RESULT}' and "
        f"({hashes_check('component_hashes', True)})) or "
        f"(result_schema_version<>'{RESULT}' and "
        f"({hashes_check('component_hashes', False)}))))"
    )
    op.execute(
        "CREATE FUNCTION public.require_current_guide_specification_attempt() RETURNS trigger "
        "LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$ BEGIN "
        f"IF NEW.result_schema_version IS DISTINCT FROM '{RESULT}' THEN "
        "RAISE EXCEPTION 'current guide specification format required' USING ERRCODE='23514'; "
        "END IF; RETURN NEW; END $$"
    )
    op.execute(
        f"CREATE TRIGGER guide_specification_attempt_insert BEFORE INSERT ON {attempt} "
        "FOR EACH ROW EXECUTE FUNCTION public.require_current_guide_specification_attempt()"
    )
    replace_function(
        "public.guard_project_guide_compilation_attempt_update()",
        ("begin\n", "begin\n          if old.result_schema_version is null then\n"
         "            raise exception 'retained compilation attempt cannot execute' using errcode='23514';\n"
         "          end if;\n"),
        ("new.provider_idempotency_key)", "new.result_schema_version,new.provider_idempotency_key)"),
        ("old.provider_idempotency_key)", "old.result_schema_version,old.provider_idempotency_key)"),
    )
    replace_function(
        "public.guard_project_guide_compilation_insert()",
        ("new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb)",
         "new.result_schema_version,new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb)"),
        ("source_attempt.canonical_result::jsonb,source_attempt.result_hash,",
         "source_attempt.result_schema_version,source_attempt.canonical_result::jsonb,source_attempt.result_hash,"),
    )
    replace_request_digest()
    op.execute(
        "ALTER TABLE public.project_guide_proposal_approvals "
        "ADD COLUMN request_json jsonb"
    )
    op.execute(
        "ALTER TABLE public.project_guide_proposal_approvals "
        "DROP CONSTRAINT ck_project_guide_proposal_approvals_ck_proposal_approval_sizes"
    )
    op.execute(
        "ALTER TABLE public.project_guide_proposal_approvals "
        "ADD CONSTRAINT ck_project_guide_proposal_approvals_ck_proposal_approval_sizes "
        "CHECK (octet_length(target_json::text)<=16384 AND "
        "(request_json IS NULL OR octet_length(request_json::text)<=1048576) AND "
        "octet_length(receipt_json::text)<=32768 AND "
        "octet_length(effective_pre_submit_plan::text)<=4194304)"
    )
    op.execute(
        "CREATE FUNCTION public.require_current_guide_proposal_approval() "
        "RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp "
        "AS $$ BEGIN "
        "IF NEW.request_json IS NULL OR NEW.target_json->>'result_schema_version' "
        f"IS DISTINCT FROM '{RESULT}' THEN "
        "RAISE EXCEPTION 'current guide approval request required' USING ERRCODE='23514'; "
        "END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER current_guide_proposal_approval_insert BEFORE INSERT ON "
        "public.project_guide_proposal_approvals FOR EACH ROW EXECUTE FUNCTION "
        "public.require_current_guide_proposal_approval()"
    )
    op.execute(
        "CREATE TRIGGER current_guide_compilation_insert BEFORE INSERT ON "
        "public.project_guide_compilations FOR EACH ROW EXECUTE FUNCTION "
        "public.require_current_guide_specification_attempt()"
    )
    op.execute(
        "CREATE TRIGGER current_guide_finalization_insert BEFORE INSERT ON "
        "public.project_guide_setup_finalizations FOR EACH ROW EXECUTE FUNCTION "
        "public.require_current_guide_specification_attempt()"
    )
    add_approval_attachment_validator()
    replace_proposal_target()
    replace_proposal_approval()
    replace_post_policy()
    replace_false_review_activation()


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
