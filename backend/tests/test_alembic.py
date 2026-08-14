from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import asyncpg
import pytest

from adapter_binding_fixtures import seed_nonempty_0003_adapter_binding
from scripts.schema_baseline_manifest import (
    APPLICATION_ACL_PRINCIPALS,
    build_manifest,
    canonical_acl_principal,
    canonical_bytes,
)
from scripts.schema_baseline_sql import split_sql_statements

HEAD_REVISION = "0004_compensation_adapter_binding_lifecycle"
BASELINE_REVISION = "0001_v01_baseline"
RECREATE_GUIDANCE = "Workstream v0.1 requires a fresh database; recreate this database"
pytestmark = pytest.mark.postgres_schema_contract


def _alembic_config() -> Config:
    backend = Path(__file__).resolve().parents[1]
    return Config(backend / "alembic.ini")


def _manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "alembic/baseline/v01_baseline_manifest.json"


async def _database_snapshot(database_url: str) -> dict[str, object]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        objects = await connection.fetch(
            "select c.relkind::text,c.relname from pg_class c join pg_namespace n "
            "on n.oid=c.relnamespace where n.nspname='public' order by 1,2"
        )
        versions: list[str] = []
        if await connection.fetchval("select to_regclass('public.alembic_version') is not null"):
            versions = await connection.fetch("select version_num from alembic_version order by 1")
        reference_rows: dict[str, list[str]] = {}
        for table in (
            "actor_profile_migration_state",
            "authority_control",
            "iso_4217_currency_codes",
            "actor_profiles", "actor_identity_links", "projects",
            "project_compensation_adapter_bindings",
        ):
            if await connection.fetchval("select to_regclass($1) is not null", f"public.{table}"):
                rows = await connection.fetch(
                    f'SELECT row_to_json(t)::text value FROM public."{table}" t ORDER BY 1'
                )
                reference_rows[table] = [row["value"] for row in rows]
        return {
            "schema": canonical_bytes(await build_manifest(database_url)),
            "versions": [row["version_num"] for row in versions],
            "objects": [tuple(row.values()) for row in objects],
            "reference_rows": reference_rows,
        }
    finally:
        await connection.close()


async def _execute(database_url: str, statement: str, *arguments: object) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(statement, *arguments)
    finally:
        await connection.close()


def test_v01_graph_has_one_root_and_head() -> None:
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())

    assert [revision.revision for revision in revisions] == [
        HEAD_REVISION,
        "0003_submission_lineage",
        "0002_admission_version",
        BASELINE_REVISION,
    ]
    assert revisions[-1].down_revision is None
    assert script.get_heads() == [HEAD_REVISION]


def test_fresh_database_matches_committed_manifest(
    isolated_database_env: str, migration_lock
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, BASELINE_REVISION)
    expected = _manifest_path().read_bytes()
    actual = canonical_bytes(asyncio.run(build_manifest(isolated_database_env)))
    assert hashlib.sha256(actual).hexdigest() == hashlib.sha256(expected).hexdigest()
    assert actual == expected


def test_current_head_installs_submission_lineage_contract(
    isolated_database_env: str, migration_lock
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, HEAD_REVISION)

    async def contract() -> tuple[bool, str, list[str], str, set[str], str]:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            exists = await connection.fetchval(
                "select exists(select 1 from information_schema.columns "
                "where table_schema='public' and table_name='submission_bundle_admissions' "
                "and column_name='consumed_by_submission_version' and data_type='integer')"
            )
            definition = await connection.fetchval(
                "select pg_get_constraintdef(c.oid) from pg_constraint c "
                "join pg_class t on t.oid=c.conrelid "
                "join pg_namespace n on n.oid=t.relnamespace "
                "where c.conname='ck_submission_bundle_admissions_terminal_shape' "
                "and n.nspname='public' and t.relname='submission_bundle_admissions'"
            )
            columns = await connection.fetch(
                "select column_name from information_schema.columns "
                "where table_schema='public' and table_name='submissions' and "
                "column_name=any($1::text[]) order by column_name",
                [
                    "artifact_binding_id",
                    "artifact_content_id",
                    "submission_bundle_admission_id",
                    "task_assignment_id",
                ],
            )
            lineage_shape = await connection.fetchval(
                "select pg_get_constraintdef(c.oid) from pg_constraint c "
                "join pg_class t on t.oid=c.conrelid "
                "join pg_namespace n on n.oid=t.relnamespace "
                "where c.conname='ck_submissions_artifact_lineage_shape' "
                "and t.relname='submissions' and n.nspname='public'"
            )
            objects = await connection.fetch(
                "select conname as name from pg_constraint c join pg_class t on t.oid=c.conrelid "
                "join pg_namespace n on n.oid=t.relnamespace "
                "where t.relname='submissions' and n.nspname='public' "
                "and conname=any($1::text[]) union all "
                "select indexname as name from pg_indexes where tablename='submissions' "
                "and schemaname='public' and indexname=any($1::text[])",
                ["fk_submissions_task_assignment_id_task_assignments",
                 "ix_submissions_submission_bundle_admission_id",
                 "uq_submissions_artifact_binding_id", "ix_submissions_artifact_content_id"],
            )
            package_nullable = await connection.fetchval(
                "select is_nullable from information_schema.columns where "
                "table_schema='public' and table_name='submissions' "
                "and column_name='package_hash'"
            )
            return (bool(exists), definition, [row["column_name"] for row in columns],
                    lineage_shape, {row["name"] for row in objects}, package_nullable)
        finally:
            await connection.close()

    exists, definition, columns, lineage_shape, objects, package_nullable = asyncio.run(contract())
    assert exists is True
    assert "consumed_by_submission_version > 0" in definition
    assert columns == [
        "artifact_binding_id",
        "artifact_content_id",
        "submission_bundle_admission_id",
        "task_assignment_id",
    ]
    assert "task_assignment_id IS NULL" in lineage_shape
    assert "artifact_content_id IS NOT NULL" in lineage_shape
    assert objects == {
        "fk_submissions_task_assignment_id_task_assignments",
        "ix_submissions_submission_bundle_admission_id",
        "uq_submissions_artifact_binding_id",
        "ix_submissions_artifact_content_id",
    }
    assert package_nullable == "YES"


def test_current_head_installs_compensation_binding_lifecycle(
    isolated_database_env: str, migration_lock
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, HEAD_REVISION)

    async def contract() -> tuple[bool, int, set[str], set[str], set[str]]:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            table_exists = await connection.fetchval(
                "select to_regclass('public.compensation_adapter_binding_lifecycle_events') "
                "is not null"
            )
            revision_length = await connection.fetchval(
                "select character_maximum_length from information_schema.columns "
                "where table_schema='public' and table_name='alembic_version' "
                "and column_name='version_num'"
            )
            triggers = await connection.fetch(
                "select tgname from pg_trigger t join pg_class c on c.oid=t.tgrelid "
                "where c.relname=any($1::text[]) and not t.tgisinternal",
                ["project_compensation_adapter_bindings",
                 "compensation_adapter_binding_lifecycle_events"],
            )
            functions = await connection.fetch(
                "select proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "where n.nspname='public' and proname=any($1::text[])",
                ["enforce_compensation_binding_lifecycle",
                 "guard_compensation_binding_lifecycle_event",
                 "reject_compensation_binding_lifecycle_event_change",
                 "require_compensation_binding_lifecycle_event"],
            )
            binding_checks = await connection.fetch(
                "select conname from pg_constraint c join pg_class t on t.oid=c.conrelid "
                "where t.relname='project_compensation_adapter_bindings' "
                "and c.contype='c' order by conname"
            )
            return (
                bool(table_exists),
                revision_length,
                {row["tgname"] for row in triggers},
                {row["proname"] for row in functions},
                {row["conname"] for row in binding_checks},
            )
        finally:
            await connection.close()

    exists, revision_length, triggers, functions, binding_checks = asyncio.run(contract())
    assert exists is True
    assert revision_length == 64
    assert triggers >= {
        "project_compensation_binding_update_guard",
        "compensation_binding_event_insert_guard",
        "compensation_binding_event_change_guard",
        "compensation_binding_event_truncate_guard",
        "compensation_binding_lifecycle_event_required",
    }
    assert len(functions) == 4
    assert {
        "ck_project_compensation_adapter_bindings_status",
        "ck_project_compensation_adapter_bindings_lifecycle_shape",
    } <= binding_checks
    assert not {
        "ck_project_compensation_adapter_bindings_ck_project_com_95ba",
        "ck_project_compensation_adapter_bindings_ck_project_com_da73",
    } & binding_checks


def test_0004_nonempty_binding_preflight_leaves_0003_unchanged(
    isolated_database_env: str, migration_lock
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, "0003_submission_lineage")
        asyncio.run(seed_nonempty_0003_adapter_binding(isolated_database_env))
        before = asyncio.run(_database_snapshot(isolated_database_env))
        with pytest.raises(RuntimeError, match="requires a fresh database"):
            command.upgrade(config, HEAD_REVISION)

    assert asyncio.run(_database_snapshot(isolated_database_env)) == before


def test_manifest_covers_every_required_object_class() -> None:
    manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    assert manifest["format"] == "workstream-v01-schema-manifest-1"
    assert len(manifest["tables"]) == 75
    assert len(manifest["columns"]) >= 1_200
    assert len(manifest["constraints"]) >= 850
    assert len(manifest["indexes"]) >= 400
    assert len(manifest["sequences"]) == 2
    assert len(manifest["routines"]) == 81
    assert len(manifest["triggers"]) == 113
    assert sum(row["principal"] == "PUBLIC" for row in manifest["acl"]) == 81
    assert set(manifest["reference_rows"]) == {
        "actor_profile_migration_state",
        "authority_control",
        "iso_4217_currency_codes",
    }
    assert all(row["principal"] in {"owner", "PUBLIC"} for row in manifest["acl"])
    assert manifest["types"] == []
    assert manifest["policies"] == []
    assert manifest["auxiliary_objects"] == []


@pytest.mark.parametrize(
    "name", ("v01_pre_reset_source_manifest.json", "v01_baseline_manifest.json")
)
def test_committed_schema_manifests_are_compact_canonical_json(name: str) -> None:
    path = _manifest_path().with_name(name)
    payload = path.read_bytes()
    assert payload == canonical_bytes(json.loads(payload))
    assert payload.count(b"\n") == 1


def test_source_to_baseline_delta_is_exactly_the_approved_sequence_repair() -> None:
    baseline_dir = _manifest_path().parent
    source = json.loads((baseline_dir / "v01_pre_reset_source_manifest.json").read_text())
    expected = json.loads(_manifest_path().read_text())
    delta = json.loads((baseline_dir / "v01_approved_manifest_delta.json").read_text())
    repaired = deepcopy(source)
    changes = {entry["name"]: entry for entry in delta["sequence_state_changes"]}
    assert set(changes) == {
        "actor_profile_migration_state_id_seq",
        "authority_control_id_seq",
    }
    for sequence in repaired["sequences"]:
        if sequence["name"] in changes:
            change = changes[sequence["name"]]
            assert sequence[change["field"]] == change["from"]
            sequence[change["field"]] = change["to"]
    assert canonical_bytes(repaired) == canonical_bytes(expected)


def test_acl_principals_are_closed_and_owner_mapping_is_role_name_independent() -> None:
    assert APPLICATION_ACL_PRINCIPALS == {}
    assert canonical_acl_principal("database_owner", "database_owner") == "owner"
    assert canonical_acl_principal("PUBLIC", "database_owner") == "PUBLIC"
    with pytest.raises(RuntimeError, match="unknown ACL principal"):
        canonical_acl_principal("unexpected_role", "database_owner")


def test_every_acl_principal_is_effective_on_the_installed_baseline(
    isolated_database_env: str,
) -> None:
    async def acl_results() -> tuple[int, int]:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            row = await connection.fetchrow(
                "with checks(ok) as ("
                "select has_table_privilege(c.relowner,c.oid,x.privilege_type) "
                "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "cross join lateral aclexplode(coalesce(c.relacl,acldefault("
                "case when c.relkind='S' then 'S'::\"char\" else 'r'::\"char\" end,c.relowner))) x "
                "where n.nspname='public' and c.relname <> 'alembic_version' "
                "and c.relkind in ('r','p','v','m','f') and x.grantee=c.relowner "
                "union all select has_sequence_privilege(c.relowner,c.oid,x.privilege_type) "
                "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "cross join lateral aclexplode(coalesce(c.relacl,acldefault('S',c.relowner))) x "
                "where n.nspname='public' and c.relkind='S' and x.grantee=c.relowner "
                "union all select has_function_privilege(p.proowner,p.oid,x.privilege_type) "
                "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x "
                "where n.nspname='public' and x.grantee=p.proowner "
                "union all select has_type_privilege(t.typowner,t.oid,x.privilege_type) "
                "from pg_type t join pg_namespace n on n.oid=t.typnamespace "
                "cross join lateral aclexplode(coalesce(t.typacl,acldefault('T',t.typowner))) x "
                "where n.nspname='public' and t.typrelid=0 and t.typcategory <> 'A' "
                "and x.grantee=t.typowner union all "
                "select has_table_privilege('pg_monitor',c.oid,x.privilege_type) "
                "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "cross join lateral aclexplode(coalesce(c.relacl,acldefault("
                "case when c.relkind='S' then 'S'::\"char\" else 'r'::\"char\" end,c.relowner))) x "
                "where n.nspname='public' and c.relname <> 'alembic_version' "
                "and c.relkind in ('r','p','v','m','f') and x.grantee=0 "
                "union all select has_sequence_privilege('pg_monitor',c.oid,x.privilege_type) "
                "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "cross join lateral aclexplode(coalesce(c.relacl,acldefault('S',c.relowner))) x "
                "where n.nspname='public' and c.relkind='S' and x.grantee=0 "
                "union all select has_function_privilege('pg_monitor',p.oid,x.privilege_type) "
                "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x "
                "where n.nspname='public' and x.grantee=0 "
                "union all select has_type_privilege('pg_monitor',t.oid,x.privilege_type) "
                "from pg_type t join pg_namespace n on n.oid=t.typnamespace "
                "cross join lateral aclexplode(coalesce(t.typacl,acldefault('T',t.typowner))) x "
                "where n.nspname='public' and t.typrelid=0 and t.typcategory <> 'A' "
                "and x.grantee=0) select count(*) filter (where not ok) ineffective,"
                "count(*) total from checks"
            )
            return row["ineffective"], row["total"]
        finally:
            await connection.close()

    ineffective, total = asyncio.run(acl_results())
    manifest = json.loads(_manifest_path().read_text())
    assert ineffective == 0
    assert total == len(manifest["acl"])


def test_baseline_resources_are_deterministic_and_environment_free() -> None:
    baseline = Path(__file__).resolve().parents[1] / "alembic/baseline"
    schema = (baseline / "v01_schema.sql").read_text(encoding="utf-8")
    references = (baseline / "v01_reference_data.sql").read_text(encoding="utf-8")
    combined = schema + references

    prohibited = (
        "ALTER OWNER",
        "SESSION AUTHORIZATION",
        "CREATE DATABASE",
        "\\connect",
        "SET ROLE",
        "workstream_baseline_source",
        "workstream_baseline_target",
    )
    assert not any(token in combined for token in prohibited)
    assert "CREATE TABLE public.alembic_version" not in schema
    assert "$workstream_baseline_batch$" not in combined
    assert "CREATE TRIGGER" in schema
    assert "INSERT INTO public.iso_4217_currency_codes" in references


def test_baseline_sql_splitter_preserves_function_bodies() -> None:
    source = "CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM ';'; END $$ LANGUAGE plpgsql; SELECT 'a;''b';"
    assert split_sql_statements(source) == (
        "CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM ';'; END $$ LANGUAGE plpgsql",
        "SELECT 'a;''b'",
    )
    with pytest.raises(ValueError, match="unterminated"):
        split_sql_statements("SELECT $$broken")


def test_unknown_old_stamp_refuses_before_mutation(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(
                isolated_database_env,
                "drop schema public cascade; create schema public; "
                "create table sentinel(id integer primary key, value text not null); "
                "insert into sentinel values (1,'preserve-me'); "
                "create table alembic_version(version_num varchar(32) primary key); "
                "insert into alembic_version values ('0063_compilation_authority')",
            )
        )
        before = asyncio.run(_database_snapshot(isolated_database_env))
        with pytest.raises(RuntimeError, match=RECREATE_GUIDANCE):
            command.upgrade(config, "head")
        after = asyncio.run(_database_snapshot(isolated_database_env))

    assert before == after


def test_root_upgrade_refuses_nonempty_unstamped_schema_before_product_ddl(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = _alembic_config()
    asyncio.run(
        _execute(
            isolated_database_env,
            "drop schema public cascade; create schema public; create table sentinel(id integer)",
        )
    )

    with migration_lock(), pytest.raises(RuntimeError, match=RECREATE_GUIDANCE):
        command.upgrade(config, "head")

    snapshot = asyncio.run(_database_snapshot(isolated_database_env))
    assert snapshot["versions"] == []
    assert ("r", "sentinel") in snapshot["objects"]
    assert ("r", "projects") not in snapshot["objects"]


def test_root_downgrade_refuses_without_mutation(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = _alembic_config()
    before = asyncio.run(_database_snapshot(isolated_database_env))
    with migration_lock(), pytest.raises(RuntimeError, match="cannot be downgraded"):
        command.downgrade(config, "base")
    after = asyncio.run(_database_snapshot(isolated_database_env))
    assert before == after


def test_seeded_sequences_advance_past_singleton_rows(isolated_database_env: str) -> None:
    async def read_next_values() -> tuple[int, int]:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            return (
                await connection.fetchval("select nextval('actor_profile_migration_state_id_seq')"),
                await connection.fetchval("select nextval('authority_control_id_seq')"),
            )
        finally:
            await connection.close()

    assert asyncio.run(read_next_values()) == (2, 2)
