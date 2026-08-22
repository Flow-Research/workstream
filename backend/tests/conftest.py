from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
import asyncio
import base64
import fcntl
from functools import partial
import hashlib
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from alembic import command  # type: ignore[import-not-found,attr-defined]
from alembic.config import Config  # type: ignore[import-not-found]
import asyncpg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

from app.core.config import get_settings
from app.db import session as db_session
from scripts.run_isolated_tests import LOOPBACK, NAME_RE, ROLE_RE

DDL_LOCK_DIRECTORY = Path("/tmp")
EXPECTED_PUBLIC_SCHEMA_SHA256 = "4b31005ee4e03fa5e67ce262ff67b2be2cfaeb09540441ef4798deae8bfd0ce1"
PROTECTED_TEST_TABLES = (
    "actor_profile_migration_state",
    "alembic_version",
    "iso_4217_currency_codes",
)
RESETTABLE_TEST_TABLES = (
    "actor_identity_links",
    "actor_profiles",
    "admin_role_grants",
    "api_rate_control_counters",
    "artifact_admission_charges",
    "artifact_admission_scopes",
    "artifact_bindings",
    "artifact_contents",
    "artifact_operation_receipts",
    "artifact_put_attempt_charges",
    "artifact_put_attempts",
    "artifact_put_observation_receipts",
    "artifact_recovery_attempts",
    "artifact_replicas",
    "artifact_storage_namespaces",
    "artifact_verification_jobs",
    "artifact_verification_receipts",
    "audit_events",
    "authority_control",
    "authority_idempotency_records",
    "checker_policies",
    "checker_results",
    "checker_runs",
    "compensation_adapter_binding_lifecycle_events",
    "contribution_policy_lifecycle_events",
    "contribution_policy_transition_custody",
    "contribution_award_definitions",
    "contribution_policies",
    "contribution_policy_versions",
    "contribution_rules",
    "effective_project_submission_artifact_policies",
    "evidence_items",
    "guide_source_artifact_ingests",
    "guide_source_artifact_incidents",
    "guide_source_artifact_bindings",
    "guide_source_extracted_contents",
    "guide_source_extraction_attempts",
    "guide_source_extraction_retry_budgets",
    "guide_source_extraction_usages",
    "guide_source_format_classifications",
    "guide_mutation_idempotency_records",
    "guide_source_snapshot_items",
    "guide_source_snapshots",
    "guide_sufficiency_reports",
    "guide_sufficiency_report_source_usages",
    "guide_sufficiency_mutation_idempotency_records",
    "legacy_actor_identities",
    "legacy_workflow_eligibility",
    "outbox_events",
    "payment_policies",
    "policy_mutation_idempotency_records",
    "pre_submit_checker_policies",
    "pre_submit_evidence_results",
    "pre_submit_evidence_sets",
    "project_compensation_adapter_bindings",
    "project_compensation_units",
    "project_create_idempotency_records",
    "project_guides",
    "project_guide_compilation_attempts",
    "project_guide_component_projection_operations",
    "project_guide_compilations",
    "project_guide_compilation_request_operations",
    "project_role_grants",
    "project_role_qualification_snapshots",
    "project_setup_runs",
    "projects",
    "review_policies",
    "revision_policies",
    "review_admission_idempotency_records",
    "review_leases",
    "review_queue_entries",
    "submission_policy_mutation_idempotency_records",
    "submission_artifact_policies",
    "submission_bundle_admissions",
    "submission_bundle_durable_intents",
    "submissions",
    "task_assignments",
    "workstream_tasks",
)
TRUNCATE_GUARDED_TABLES = (
    "admin_role_grants",
    "audit_events",
    "authority_control",
    "authority_idempotency_records",
    "compensation_adapter_binding_lifecycle_events",
    "contribution_policy_lifecycle_events",
    "contribution_policy_transition_custody",
    "guide_mutation_idempotency_records",
    "guide_sufficiency_reports",
    "guide_sufficiency_report_source_usages",
    "guide_sufficiency_mutation_idempotency_records",
    "guide_source_snapshot_items",
    "outbox_events",
    "policy_mutation_idempotency_records",
    "pre_submit_evidence_results",
    "pre_submit_evidence_sets",
    "contribution_award_definitions",
    "contribution_policies",
    "contribution_policy_versions",
    "contribution_rules",
    "project_compensation_units",
    "project_create_idempotency_records",
    "project_guide_compilation_attempts",
    "project_guide_component_projection_operations",
    "project_guide_compilations",
    "project_guide_compilation_request_operations",
    "project_role_grants",
    "project_role_qualification_snapshots",
    "review_admission_idempotency_records",
    "review_leases",
    "review_queue_entries",
    "review_policies",
    "revision_policies",
    "submission_bundle_admissions",
    "submission_artifact_policies",
    "submission_bundle_durable_intents",
    "submission_policy_mutation_idempotency_records",
)
TestDatabaseReset = Callable[..., Awaitable[None]]
DatabaseLock = Callable[[], AbstractContextManager[None]]
ResetHook = Callable[[], Awaitable[None]]
PAGINATION_CURSOR_HMAC_SECRET = base64.b64encode(bytes(range(32))).decode("ascii")


@pytest.fixture(autouse=True)
def pagination_cursor_hmac_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provision the required cursor key explicitly for isolated test apps."""
    monkeypatch.setenv(
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET",
        PAGINATION_CURSOR_HMAC_SECRET,
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _assert_owned_test_database(
    connection: asyncpg.Connection,
    database_url: str,
) -> None:
    """Fail closed unless the live target is the runner-owned test database."""
    parsed = urlsplit(database_url)
    url_database = parsed.path.removeprefix("/")
    url_role = unquote(parsed.username or "")
    database_match = NAME_RE.fullmatch(url_database)
    role_match = ROLE_RE.fullmatch(url_role)
    if (
        parsed.scheme != "postgresql+asyncpg"
        or parsed.hostname not in LOOPBACK
        or not parsed.password
        or bool(parsed.query)
        or bool(parsed.fragment)
        or database_match is None
        or role_match is None
        or url_database.removeprefix("workstream_test_")
        != url_role.removeprefix("workstream_role_")
    ):
        raise RuntimeError("unsafe test database target")

    custody = await connection.fetchrow(
        "select current_database() as database_name, current_user as session_role, "
        "pg_get_userbyid(d.datdba) as owner_role, r.rolsuper, r.rolcreatedb, "
        "r.rolcreaterole, r.rolinherit, r.rolreplication, r.rolbypassrls, "
        "(select count(*) from pg_auth_members m where m.member = r.oid) "
        "as membership_count "
        "from pg_database d join pg_roles r on r.rolname = current_user "
        "where d.datname = current_database()"
    )
    if custody is None or (
        custody["database_name"] != url_database
        or custody["session_role"] != url_role
        or custody["owner_role"] != url_role
        or custody["rolsuper"]
        or custody["rolcreatedb"]
        or custody["rolcreaterole"]
        or custody["rolinherit"]
        or custody["rolreplication"]
        or custody["rolbypassrls"]
        or custody["membership_count"] != 0
    ):
        raise RuntimeError("test database custody check failed")


async def _assert_canonical_test_schema(
    connection: asyncpg.Connection,
) -> dict[str, str]:
    """Return quoted resettable tables only for the exact reviewed schema."""
    rows = await connection.fetch(
        "select tablename, quote_ident(tablename) as identifier "
        "from pg_tables where schemaname = 'public' order by tablename"
    )
    actual = {row["tablename"]: row["identifier"] for row in rows}
    expected = set(PROTECTED_TEST_TABLES) | set(RESETTABLE_TEST_TABLES)
    if set(actual) != expected:
        missing = ",".join(sorted(expected - set(actual))) or "none"
        unexpected = ",".join(sorted(set(actual) - expected)) or "none"
        raise RuntimeError(
            f"unexpected test database schema: missing={missing}; unexpected={unexpected}"
        )
    object_rows = await connection.fetch(
        "with namespace_objects(kind,name) as ("
        "select 'namespace-object',concat_ws('|',x.type,x.schema,x.name,x.identity) "
        "from (select (pg_identify_object(d.classid,d.objid,d.objsubid)).* "
        "from pg_depend d join pg_namespace n on n.oid=d.refobjid "
        "where d.refclassid='pg_namespace'::regclass and n.nspname='public' "
        "and d.deptype='n') x), parts(kind,name) as ("
        "select kind,name from namespace_objects union all "
        "select 'relation',c.relname||'|'||concat_ws('|',c.relkind::text,"
        "c.relpersistence::text,c.relreplident::text,c.relrowsecurity::text,"
        "c.relforcerowsecurity::text,coalesce(c.reloptions::text,''),"
        "coalesce(c.relacl::text,'')) from pg_class c join pg_namespace n "
        "on n.oid=c.relnamespace where n.nspname='public' "
        "union all select 'column',c.relname||'.'||a.attname||'|'||concat_ws('|',"
        "a.attnum::text,format_type(a.atttypid,a.atttypmod),a.attnotnull::text,"
        "a.attidentity,a.attgenerated,coalesce(pg_get_expr(d.adbin,d.adrelid),'')) "
        "from pg_attribute a join pg_class c on c.oid=a.attrelid "
        "join pg_namespace n on n.oid=c.relnamespace left join pg_attrdef d "
        "on d.adrelid=a.attrelid and d.adnum=a.attnum where n.nspname='public' "
        "and a.attnum>0 and not a.attisdropped "
        "union all select 'constraint',coalesce(c.relname,'')||'.'||q.conname||'|'||"
        "q.contype::text||'|'||pg_get_constraintdef(q.oid,true) from pg_constraint q "
        "left join pg_class c on c.oid=q.conrelid join pg_namespace n "
        "on n.oid=q.connamespace where n.nspname='public' "
        "union all select 'index',tablename||'.'||indexname||'|'||indexdef "
        "from pg_indexes where schemaname='public' "
        "union all select 'trigger',c.relname||'.'||t.tgname||'|'||t.tgenabled::text||'|'||"
        "pg_get_triggerdef(t.oid,true) from pg_trigger t join pg_class c "
        "on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and not t.tgisinternal "
        "union all select 'policy',c.relname||'.'||p.polname||'|'||concat_ws('|',"
        "p.polpermissive::text,p.polcmd,p.polroles::text,"
        "coalesce(pg_get_expr(p.polqual,p.polrelid),''),"
        "coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'')) from pg_policy p "
        "join pg_class c on c.oid=p.polrelid join pg_namespace n "
        "on n.oid=c.relnamespace where n.nspname='public' "
        "union all select 'rule',schemaname||'.'||tablename||'.'||rulename||'|'||"
        "definition from pg_rules where schemaname='public' "
        "union all select 'view',schemaname||'.'||viewname||'|'||definition "
        "from pg_views where schemaname='public' "
        "union all select 'matview',schemaname||'.'||matviewname||'|'||definition "
        "from pg_matviews where schemaname='public' "
        "union all select 'function',p.proname||'('||"
        "pg_get_function_identity_arguments(p.oid)||')|'||pg_get_functiondef(p.oid) "
        "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
        "where n.nspname='public' "
        "union all select 'sequence',c.relname||'|'||concat_ws('|',s.seqtypid::regtype::text,"
        "s.seqstart::text,s.seqincrement::text,s.seqmax::text,s.seqmin::text,"
        "s.seqcache::text,s.seqcycle::text) from pg_sequence s join pg_class c "
        "on c.oid=s.seqrelid join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' "
        "union all select 'enum',t.typname||'|'||e.enumsortorder::text||'|'||e.enumlabel "
        "from pg_enum e join pg_type t on t.oid=e.enumtypid join pg_namespace n "
        "on n.oid=t.typnamespace where n.nspname='public' "
        "union all select 'type',t.typname||'|'||concat_ws('|',t.typtype::text,"
        "t.typcategory::text,t.typispreferred::text,t.typnotnull::text,"
        "case when t.typelem=0 then '' else t.typelem::regtype::text end,"
        "coalesce(pg_get_expr(t.typdefaultbin,0),t.typdefault,'')) "
        "from pg_type t join pg_namespace n on n.oid=t.typnamespace "
        "where n.nspname='public') "
        "select kind,name from parts order by kind,name"
    )
    serialized_objects = "".join(f"{row['kind']}|{row['name']}\n" for row in object_rows).encode(
        "utf-8"
    )
    schema_sha256 = hashlib.sha256(serialized_objects).hexdigest()
    if schema_sha256 != EXPECTED_PUBLIC_SCHEMA_SHA256:
        raise RuntimeError(f"unexpected public schema object fingerprint: {schema_sha256}")
    return {name: actual[name] for name in RESETTABLE_TEST_TABLES}


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


async def _drop_test_database_schema(database_url: str) -> None:
    """Clear schema state owned by an explicitly marked migration-contract test."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await _assert_owned_test_database(connection, database_url)
        await connection.execute("drop schema if exists public cascade")
        await connection.execute("create schema public")
    finally:
        await connection.close()


def _rebuild_test_database_schema(database_url: str) -> None:
    with postgres_ddl_lock(database_url):
        asyncio.run(_drop_test_database_schema(database_url))
        command.upgrade(_alembic_config(), "head")


async def _verify_test_database_schema(database_url: str) -> None:
    """Verify that an ordinary test returned its owned database schema unchanged."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await _assert_owned_test_database(connection, database_url)
        await _assert_canonical_test_schema(connection)
    finally:
        await connection.close()


async def _reset_test_database_state(
    database_url: str,
    *,
    after_disable: ResetHook | None = None,
) -> None:
    """Restore the already-migrated isolated database to its empty baseline."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await _assert_owned_test_database(connection, database_url)
        tables = await _assert_canonical_test_schema(connection)
        async with connection.transaction():
            for name in TRUNCATE_GUARDED_TABLES:
                await connection.execute(f"alter table {tables[name]} disable trigger user")
            if after_disable is not None:
                await after_disable()
            await connection.execute(
                f"truncate table {', '.join(tables.values())} restart identity cascade"
            )
            await connection.execute(
                "insert into authority_control"
                "(id, bootstrap_completed, bootstrap_grant_id, version) "
                "values (1, false, null, 0)"
            )
            for name in TRUNCATE_GUARDED_TABLES:
                await connection.execute(f"alter table {tables[name]} enable trigger user")
    finally:
        await connection.close()


@contextmanager
def postgres_ddl_lock(database_url: str) -> Iterator[None]:
    """Serialize Alembic resets only for processes sharing one database."""
    database_key = hashlib.sha256(database_url.encode("utf-8")).hexdigest()[:16]
    lock_path = DDL_LOCK_DIRECTORY / f"workstream-postgres-ddl-{database_key}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@pytest.fixture
def migration_lock(postgres_database_url: str) -> DatabaseLock:
    """Return a database-scoped PostgreSQL DDL lock context manager."""
    return partial(postgres_ddl_lock, postgres_database_url)


@pytest.fixture
def reset_test_database_state() -> TestDatabaseReset:
    """Return the shared privileged reset used by isolated database suites."""
    return _reset_test_database_state


@pytest.fixture
def clean_postgres_database(
    postgres_database_url: str,
    request: pytest.FixtureRequest,
) -> Iterator[str]:
    """Provide an isolated migrated database baseline per test."""
    owns_schema = request.node.get_closest_marker("postgres_schema_contract") is not None
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())
    if owns_schema:
        _rebuild_test_database_schema(postgres_database_url)
    else:
        asyncio.run(_reset_test_database_state(postgres_database_url))
    try:
        yield postgres_database_url
    finally:
        asyncio.run(db_session.dispose_engine())
        try:
            if owns_schema:
                _rebuild_test_database_schema(postgres_database_url)
            else:
                try:
                    asyncio.run(_verify_test_database_schema(postgres_database_url))
                except BaseException as verification_error:
                    try:
                        _rebuild_test_database_schema(postgres_database_url)
                    except BaseException as rebuild_error:
                        raise BaseExceptionGroup(
                            "schema verification and recovery both failed",
                            [verification_error, rebuild_error],
                        ) from verification_error
                    raise
        finally:
            get_settings.cache_clear()


@pytest.fixture
def postgres_database_url() -> str:
    value = os.environ.get("WORKSTREAM_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("WORKSTREAM_TEST_DATABASE_URL is required for database-backed tests")
    return value


@pytest.fixture
def isolated_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    yield clean_postgres_database
    get_settings.cache_clear()
