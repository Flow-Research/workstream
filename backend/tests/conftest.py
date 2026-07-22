from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
import asyncio
import fcntl
from functools import partial
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from alembic import command  # type: ignore[import-not-found,attr-defined]
from alembic.config import Config  # type: ignore[import-not-found]
import asyncpg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

from app.core.config import get_settings
from app.db import session as db_session

DDL_LOCK_DIRECTORY = Path("/tmp")
TEST_DATABASE_PATTERN = re.compile(r"workstream_test_([0-9a-f]{12})")
TEST_ROLE_PATTERN = re.compile(r"workstream_role_([0-9a-f]{12})")
PROTECTED_TEST_TABLES = (
    "actor_profile_migration_state",
    "alembic_version",
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
    "artifact_upload_items",
    "artifact_upload_sessions",
    "artifact_verification_jobs",
    "artifact_verification_receipts",
    "audit_events",
    "authority_control",
    "authority_idempotency_records",
    "checker_policies",
    "checker_results",
    "checker_runs",
    "effective_project_submission_artifact_policies",
    "evidence_items",
    "guide_source_snapshot_items",
    "guide_source_snapshots",
    "guide_sufficiency_reports",
    "legacy_actor_identities",
    "legacy_workflow_eligibility",
    "outbox_events",
    "payment_policies",
    "pre_submit_checker_policies",
    "project_guides",
    "project_role_grants",
    "project_role_qualification_snapshots",
    "project_setup_runs",
    "projects",
    "review_policies",
    "revision_policies",
    "submission_artifact_policies",
    "submissions",
    "task_assignments",
    "workstream_tasks",
)
TRUNCATE_GUARDED_TABLES = (
    "admin_role_grants",
    "audit_events",
    "authority_control",
    "authority_idempotency_records",
    "outbox_events",
    "project_role_grants",
    "project_role_qualification_snapshots",
)
TestDatabaseReset = Callable[..., Awaitable[None]]
DatabaseLock = Callable[[], AbstractContextManager[None]]
ResetHook = Callable[[], Awaitable[None]]


async def _assert_owned_test_database(
    connection: asyncpg.Connection,
    database_url: str,
) -> None:
    """Fail closed unless the live target is the runner-owned test database."""
    parsed = urlsplit(database_url)
    url_database = parsed.path.removeprefix("/")
    url_role = unquote(parsed.username or "")
    database_match = TEST_DATABASE_PATTERN.fullmatch(url_database)
    role_match = TEST_ROLE_PATTERN.fullmatch(url_role)
    if (
        parsed.scheme != "postgresql+asyncpg"
        or database_match is None
        or role_match is None
        or database_match.group(1) != role_match.group(1)
    ):
        raise RuntimeError("unsafe test database target")

    custody = await connection.fetchrow(
        "select current_database() as database_name, current_user as session_role, "
        "pg_get_userbyid(d.datdba) as owner_role, r.rolsuper, r.rolcreatedb, "
        "r.rolcreaterole, r.rolreplication, r.rolbypassrls "
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
        or custody["rolreplication"]
        or custody["rolbypassrls"]
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
    return {name: actual[name] for name in RESETTABLE_TEST_TABLES}


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


async def _drop_test_database_schema(database_url: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await _assert_owned_test_database(connection, database_url)
        await _assert_canonical_test_schema(connection)
        await connection.execute("drop schema if exists public cascade")
        await connection.execute("create schema public")
    finally:
        await connection.close()


def _rebuild_test_database_schema(database_url: str) -> None:
    with postgres_ddl_lock(database_url):
        asyncio.run(_drop_test_database_schema(database_url))
        command.upgrade(_alembic_config(), "head")


async def _reset_test_database_state(
    database_url: str,
    *,
    include_canonical_actors: bool = False,
    after_disable: ResetHook | None = None,
) -> None:
    """Restore the already-migrated isolated database to its empty baseline."""
    del include_canonical_actors
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
        if owns_schema:
            with postgres_ddl_lock(postgres_database_url):
                command.upgrade(_alembic_config(), "head")
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
