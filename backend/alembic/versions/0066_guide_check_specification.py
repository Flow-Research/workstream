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
    version = f"{column}->>'schema_version'='{HASHES}' and " if current else ""
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
        "canonical_result->>'schema_version'=result_schema_version)"
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
        "canonical_result->>'schema_version'=result_schema_version)))"
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


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
