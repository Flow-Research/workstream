from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import asyncpg
import pytest

from scripts.schema_baseline_manifest import (
    APPLICATION_ACL_PRINCIPALS,
    build_manifest,
    canonical_acl_principal,
    canonical_bytes,
)
from scripts.schema_baseline_sql import split_sql_statements

from tests.migration_fixtures import current_schema_revision

HEAD_REVISION = current_schema_revision()
BASELINE_REVISION = "0001_uuid7_v01"
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
        ):
            if await connection.fetchval("select to_regclass($1) is not null", f"public.{table}"):
                rows = await connection.fetch(
                    f'SELECT row_to_json(t)::text value FROM public."{table}" t ORDER BY 1'
                )
                reference_rows[table] = [row["value"] for row in rows]
        return {
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


async def _seed_export_resume_rows(database_url: str):
    """Retain real main-owned export membership and its required identity custody."""
    from app.core.identifiers import new_record_id

    actor, link, snapshot = new_record_id(), new_record_id(), new_record_id()
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            await connection.execute("""
                INSERT INTO public.actor_profiles
                  (id,actor_kind,status,provisioning_method,created_by)
                VALUES ($1,'human','active','automatic_first_access','migration-resume-test')
            """, actor)
            await connection.execute("""
                INSERT INTO public.actor_identity_links
                  (id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,last_verified_at)
                VALUES ($1,$2,'https://identity.flowresearch.tech',$3,'human','active',
                        'migration-resume-test',clock_timestamp())
            """, link, actor, str(actor))
            await connection.execute("""
                INSERT INTO public.contribution_export_snapshots
                  (id,actor_profile_id,allocation_slot,query_digest,member_ids,created_at,expires_at)
                VALUES ($1,$2,1,$3,$4,statement_timestamp(),statement_timestamp()+interval '1 hour')
            """, snapshot, actor, "sha256:" + "a" * 64, [new_record_id(), new_record_id()])
        return snapshot
    finally:
        await connection.close()


async def _migration_resume_custody(database_url: str, snapshot_id) -> dict[str, object]:
    """Compare retained row bytes and table identities, including the sentinel."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        sentinel = await connection.fetchrow(
            "select value,tableoid::bigint,xmin::text from migration_resume_sentinel where id=1"
        )
        assert sentinel is not None
        export = None
        if snapshot_id is not None:
            export = await connection.fetchrow("""
                SELECT to_jsonb(s)::text,to_jsonb(a)::text,to_jsonb(l)::text,
                       s.tableoid::bigint,a.tableoid::bigint,l.tableoid::bigint,
                       s.xmin::text,a.xmin::text,l.xmin::text
                FROM public.contribution_export_snapshots s
                JOIN public.actor_profiles a ON a.id=s.actor_profile_id
                JOIN public.actor_identity_links l ON l.actor_profile_id=a.id
                WHERE s.id=$1
            """, snapshot_id)
            assert export is not None
        return {"sentinel": tuple(sentinel.values()),
                "export": tuple(export.values()) if export is not None else None}
    finally:
        await connection.close()


def test_v01_graph_has_one_root_and_head() -> None:
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())

    assert [revision.revision for revision in revisions] == [
        HEAD_REVISION,
        "0050_contributor_reads",
        "0049_attempt_outcome_findings",
        "0048_revision_exhaustion",
        "0047_revision_recovery",
        "0046_revision_expiry_retry",
        "0045_task_revision_expiry",
        "0044_outbox_not_before",
        "0043_revision_preparation",
        "0042_revision_lineage",
        "0041_checker_revision_cap",
        "0040_contribution_export_page",
        "0039_false_guide_activation",
        "0038_task_batch_transitions",
        "0037_task_import_batches",
        "0036_selected_checker_flow",
        "0035_checker_retry",
        "0034_checker_replacement",
        "0033_contribution_reads",
        "0032_checker_remediation",
        "0031_task_import_source",
        "0030_routing_outcomes",
        "0029_external_checker_registry",
        "0028_lifecycle_transitions",
        "0027_markdown_guide_media",
        "0026_task_guide_read",
        "0025_submission_dispatch",
        "0024_require_second_review_false",
        "0023_remove_task_payment_policy",
        "0022_submission_packet_custody",
        "0021_submission_manifest",
        "0020_review_admission_lock_order",
        "0019_submitter_awards",
        "0018_task_routing_request",
        "0017_acceptance_source_contracts",
        "0016_review_lifecycle_fence",
        "0015_contribution_awards",
        "0014_final_acceptance",
        "0013_review_source",
        "0012_review_packet",
        "0011_task_routing_source",
        "0010_post_submit_authority",
        "0009_checker_material_lineage",
        "0008_checker_execution",
        "0007_checker_output_custody",
        "0006_history_read_authority",
        "0005_task_evidence_authority",
        "0004_task_context_authority",
        "0003_task_read_authority",
        "0002_task_queue_authority",
        BASELINE_REVISION,
    ]
    assert revisions[-1].down_revision is None
    assert script.get_heads() == [HEAD_REVISION]


async def test_guide_read_upgrade_targets_public_audit_with_shadow_search_path(
    isolated_database_env, migration_lock,
):
    """Successful stamping must update public custody, not a visible namesake."""
    from app.db import session as db_session
    from scripts.run_isolated_tests import NAME_RE, ROLE_RE
    from tests.conftest import _drop_test_database_schema

    shadow = "pilot13_migration_shadow"
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0025_submission_dispatch")
        connection = await asyncpg.connect(url)
        role, database = await connection.fetchrow("select current_user, current_database()")
        assert ROLE_RE.fullmatch(role) and NAME_RE.fullmatch(database)
        try:
            assert await connection.fetchval(
                "select setconfig from pg_db_role_setting "
                "where setrole=(select oid from pg_roles where rolname=current_user) "
                "and setdatabase=(select oid from pg_database where datname=current_database())"
            ) is None
            await connection.execute(f"create schema {shadow}")
            await connection.execute(
                f"create table {shadow}.audit_events (like public.audit_events including all)"
            )

            async def definition(schema):
                return await connection.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid=to_regclass($1) "
                    "and conname='ck_audit_events_authorization_action_evidence'",
                    f"{schema}.audit_events",
                )

            before = await definition("public")
            assert "task.guide.read" not in before
            assert await definition(shadow) == before
            await connection.execute(
                f'alter role "{role}" in database "{database}" set search_path = {shadow}, public'
            )
            probe = await asyncpg.connect(url)
            try:
                assert await probe.fetchval("select current_schema()") == shadow
                assert await probe.fetchval("select 'audit_events'::regclass::oid") == (
                    await probe.fetchval("select to_regclass($1)::oid", f"{shadow}.audit_events")
                )
            finally:
                await probe.close()
            await asyncio.to_thread(command.upgrade, _alembic_config(), HEAD_REVISION)
            after = await definition("public")
            assert after.count("task.guide.read") == 2
            assert await definition(shadow) == before
            assert await connection.fetchval(
                "select version_num from public.alembic_version"
            ) == HEAD_REVISION
            assert await connection.fetchval(
                "select to_regclass($1)", f"{shadow}.alembic_version"
            ) is None
        finally:
            await connection.execute(
                f'alter role "{role}" in database "{database}" reset search_path'
            )
            await connection.execute(f"drop schema if exists {shadow} cascade")
            await connection.close()
            await _drop_test_database_schema(isolated_database_env)
            await asyncio.to_thread(command.upgrade, _alembic_config(), HEAD_REVISION)


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

    async def validate_installed_bodies() -> None:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute("set local check_function_bodies = true")
            definitions = await connection.fetch(
                "select pg_get_functiondef(p.oid) as definition from pg_proc p "
                "join pg_namespace n on n.oid=p.pronamespace "
                "where n.nspname='public' and p.prokind in ('f','p') order by p.oid"
            )
            assert definitions
            for definition in definitions:
                await connection.execute(definition["definition"])
        finally:
            # Recompile against the complete schema without retaining DDL changes.
            await transaction.rollback()
            await connection.close()

    asyncio.run(validate_installed_bodies())


def test_repeated_upgrade_head_preserves_current_database(
    isolated_database_env: str, migration_lock
) -> None:
    """An already-current database stays usable without recreation or data loss."""
    config = _alembic_config()
    with migration_lock():
        before = asyncio.run(_database_snapshot(isolated_database_env))
        assert before["versions"] == [HEAD_REVISION]
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        after = asyncio.run(_database_snapshot(isolated_database_env))
    assert after == before


@pytest.mark.parametrize("installed_revision", [
    "0038_task_batch_transitions",
    "0040_contribution_export_page",
    "0041_checker_revision_cap",
    "0042_revision_lineage",
    "0043_revision_preparation",
    "0044_outbox_not_before",
    "0045_task_revision_expiry",
    "0046_revision_expiry_retry",
    "0047_revision_recovery",
    "0048_revision_exhaustion",
    "0049_attempt_outcome_findings",
    "0050_contributor_reads",
])
def test_preceding_head_upgrades_to_current_without_recreation(
    isolated_database_env: str, migration_lock, installed_revision: str,
) -> None:
    """Each supported installed predecessor resumes without recreation or data loss."""
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, installed_revision)
        asyncio.run(_execute(
            isolated_database_env,
            "create table migration_resume_sentinel(id integer primary key, value text not null); "
            "insert into migration_resume_sentinel values (1,'preserve-me')",
        ))
        snapshot_id = (
            asyncio.run(_seed_export_resume_rows(isolated_database_env))
            if installed_revision != "0038_task_batch_transitions" else None
        )
        retained = asyncio.run(_migration_resume_custody(isolated_database_env, snapshot_id))
        assert retained["sentinel"][0] == "preserve-me"
        before = asyncio.run(_database_snapshot(isolated_database_env))
        assert before["versions"] == [installed_revision]
        command.upgrade(config, HEAD_REVISION)
        after = asyncio.run(_database_snapshot(isolated_database_env))
        command.upgrade(config, "head")
        repeated = asyncio.run(_database_snapshot(isolated_database_env))
        assert asyncio.run(
            _migration_resume_custody(isolated_database_env, snapshot_id)
        ) == retained
        asyncio.run(_execute(isolated_database_env, "drop table migration_resume_sentinel"))
    assert after["versions"] == [HEAD_REVISION]
    assert after["reference_rows"] == before["reference_rows"]
    assert repeated == after


async def test_revision_upgrade_retains_policy_source_and_running_window(
    tmp_path, isolated_database_env, migration_lock, monkeypatch,
):
    """A genuine guarded 0047 window survives and remains usable on the new head."""
    from sqlalchemy import select, text
    from app.adapters.tasks import task_post_submit_outcome
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from app.modules.tasks.revision.service import project_current_revision
    from tests.migration_revision_fixtures import (
        enter_predecessor_owner_shape, insert_0047_preparation, leave_predecessor_owner_shape,
        retained_revision_rows,
    )
    from tests.tasks.post_submit_routing.remediation_support import remediation_source
    from tests.tasks.post_submit_routing.support import revision_archive
    from tests.tasks.submission_dispatch.test_replacement_creation import (
        _create, _creation_request, _ready_replacement,
    )

    with migration_lock():
        await _execute(isolated_database_env, "drop schema public cascade; create schema public")
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0047_revision_recovery")
        shape = pytest.MonkeyPatch()
        await enter_predecessor_owner_shape(_execute, isolated_database_env, shape)
        async with remediation_source(tmp_path, isolated_database_env) as h:
            with monkeypatch.context() as patch:
                patch.setattr("app.modules.tasks.post_submit_routing.outcome.prepare_revision", insert_0047_preparation)
                async with h.factory() as session, session.begin():
                    outcome = await task_post_submit_outcome(session, h.factory).apply(
                        h.envelope, current_generation=None,
                    )
            async with h.factory() as session:
                assert await session.scalar(text(
                    "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
                    "AND NOT t.tgisinternal AND t.tgenabled='D'"
                )) == 0
                before = await retained_revision_rows(session, outcome.routing_manifest_id)
                source = before["task_revision_preparations"][0][0]
                assert "remaining_microseconds" not in source
            shape.undo()
            await leave_predecessor_owner_shape(_execute, isolated_database_env)
            await asyncio.to_thread(command.upgrade, _alembic_config(), HEAD_REVISION)
            async with h.factory() as session:
                assert await retained_revision_rows(session, outcome.routing_manifest_id) == before
                preparation = await session.scalar(select(TaskRevisionPreparation))
                assert preparation.clock_observed_at is None
                assert preparation.remaining_microseconds is None and preparation.deadline_at is not None
                view = await project_current_revision(session, preparation)
                assert view.disposition == "ready" and view.outcome == "kept"
                assert view.preparation_sha256 == json.loads(source)["preparation_sha256"]
                assert view.deadline_at == preparation.deadline_at
                h.revision_preparation_id = preparation.id
                h.revision_preparation_sha256 = preparation.preparation_sha256
            prepared, admission_id = await _ready_replacement(h, revision_archive(h.data))
            creation = _creation_request(h, prepared, admission_id)
            successor = await _create(h, creation)
            assert successor.submission_version == 2
            assert successor.submission_id != h.created.submission_id
            async with h.factory() as session:
                retained = await retained_revision_rows(session, outcome.routing_manifest_id)
                for owner in ("revision_policies", "submissions", "task_revision_preparations", "outbox_events"):
                    assert retained[owner] == before[owner], owner


def test_current_head_installs_selected_only_checker_custody(
    isolated_database_env: str, migration_lock
) -> None:
    """Current writers reject missing schemas and contain no executable catalogue tail."""
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, HEAD_REVISION)

    async def installed_functions() -> dict[str, str]:
        from tests.conftest import _assert_canonical_test_schema

        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute("set local check_function_bodies = true")
            installed = await connection.fetch(
                "select p.oid,p.oid::regprocedure::text as identity "
                "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "join pg_language l on l.oid=p.prolang "
                "where n.nspname='public' and l.lanname='plpgsql' order by p.oid"
            )
            assert installed
            for row in installed:
                try:
                    await connection.fetchval(
                        "select pg_catalog.plpgsql_validator($1::oid)", row["oid"]
                    )
                except asyncpg.PostgresError as error:
                    raise AssertionError(
                        f"installed function does not compile: {row['identity']}"
                    ) from error
            rows = await connection.fetch(
                "select p.proname,pg_get_functiondef(p.oid) as definition "
                "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "where n.nspname='public' and p.proname=any($1::text[])",
                [
                    "protect_checker_run_custody",
                    "protect_checker_result_custody",
                    "validate_checker_terminal_custody",
                    "submission_dispatch_valid",
                    "external_checker_locked_policies_valid",
                    "require_guide_proposal_approval",
                    "require_post_policy_operation",
                    "guard_pre_submit_attempt",
                    "guard_pre_submit_evidence_set_creation",
                    "guard_pre_submit_evidence_result_membership",
                    "require_pre_submit_attempt_evidence",
                    "require_pre_submit_result_reconstruction",
                ],
            )
            await _assert_canonical_test_schema(connection)
            return {row["proname"]: row["definition"] for row in rows}
        finally:
            await transaction.rollback()
            await connection.close()

    definitions = asyncio.run(installed_functions())
    assert set(definitions) == {
        "protect_checker_run_custody",
        "protect_checker_result_custody",
        "validate_checker_terminal_custody",
        "submission_dispatch_valid",
        "external_checker_locked_policies_valid",
        "require_guide_proposal_approval",
        "require_post_policy_operation",
        "guard_pre_submit_attempt",
        "guard_pre_submit_evidence_set_creation",
        "guard_pre_submit_evidence_result_membership",
        "require_pre_submit_attempt_evidence",
        "require_pre_submit_result_reconstruction",
    }
    for name in (
        "protect_checker_run_custody",
        "protect_checker_result_custody",
        "validate_checker_terminal_custody",
    ):
        assert "schema_version' IS DISTINCT FROM" in definitions[name]
    assert "check_submission_packet" not in definitions["protect_checker_result_custody"]
    assert "member_results' IS DISTINCT FROM members" not in definitions[
        "validate_checker_terminal_custody"
    ]
    assert "workstream.selected_post_submit_request.v1" in definitions[
        "submission_dispatch_valid"
    ]
    assert "selected_pre_submit_run_id IS NOT NULL" in definitions[
        "submission_dispatch_valid"
    ]
    assert "external_plan" not in definitions["require_guide_proposal_approval"]
    assert "->'catalogue'" not in definitions["require_guide_proposal_approval"]
    assert "catalogue_manifest_sha256" not in definitions["require_post_policy_operation"]
    assert "external_post_submit_policy.v1" in definitions[
        "require_post_policy_operation"
    ]
    assert "checker terminal selected policy differs" in definitions[
        "validate_checker_terminal_custody"
    ]
    assert "result_registry_entry_id" in definitions[
        "validate_checker_terminal_custody"
    ]
    assert "platform_manifest_digest" in definitions[
        "validate_checker_terminal_custody"
    ]
    assert "is distinct from 'external_checker_policies.v1'" in definitions[
        "external_checker_locked_policies_valid"
    ].lower()
    retired = {
        "guard_pre_submit_attempt": "retained pre-submit attempts are immutable",
        "guard_pre_submit_evidence_set_creation": (
            "retained pre-submit evidence is immutable"
        ),
        "guard_pre_submit_evidence_result_membership": (
            "retained pre-submit evidence results are immutable"
        ),
        "require_pre_submit_attempt_evidence": (
            "retained pre-submit evidence is immutable"
        ),
        "require_pre_submit_result_reconstruction": (
            "retained pre-submit evidence results are immutable"
        ),
    }
    for name, message in retired.items():
        assert message in definitions[name]
        assert " select " not in definitions[name].lower()


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
            for required in ("task_assignment_id", "contribution_policy_version_id"):
                assert await connection.fetchval(
                    "select is_nullable from information_schema.columns where "
                    "table_schema='public' and table_name='submissions' and column_name=$1", required,
                ) == "NO"
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
                [
                    "fk_submissions_task_assignment_id_task_assignments",
                    "ix_submissions_submission_bundle_admission_id",
                    "uq_submissions_artifact_binding_id",
                    "ix_submissions_artifact_content_id",
                ],
            )
            package_nullable = await connection.fetchval(
                "select is_nullable from information_schema.columns where "
                "table_schema='public' and table_name='submissions' "
                "and column_name='package_hash'"
            )
            return (
                bool(exists),
                definition,
                [row["column_name"] for row in columns],
                lineage_shape,
                {row["name"] for row in objects},
                package_nullable,
            )
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
    assert "task_assignment_id" not in lineage_shape
    for reference in ("submission_bundle_admission_id", "artifact_binding_id", "artifact_content_id"):
        assert f"{reference} IS NULL" in lineage_shape
        assert f"{reference} IS NOT NULL" in lineage_shape
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
            assert await connection.fetchval(
                "select version_num from alembic_version"
            ) == HEAD_REVISION
            triggers = await connection.fetch(
                "select tgname from pg_trigger t join pg_class c on c.oid=t.tgrelid "
                "where c.relname=any($1::text[]) and not t.tgisinternal",
                [
                    "project_compensation_adapter_bindings",
                    "compensation_adapter_binding_lifecycle_events",
                ],
            )
            functions = await connection.fetch(
                "select proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "where n.nspname='public' and proname=any($1::text[])",
                [
                    "enforce_compensation_binding_lifecycle",
                    "guard_compensation_binding_lifecycle_event",
                    "reject_compensation_binding_lifecycle_event_change",
                    "require_compensation_binding_lifecycle_event",
                ],
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
    # Historical long revision names are gone; the fresh root must fit and be stamped.
    assert revision_length >= len(HEAD_REVISION)
    assert triggers >= {
        "project_compensation_binding_update_guard",
        "compensation_binding_event_insert_guard",
        "compensation_binding_event_change_guard",
        "compensation_binding_event_truncate_guard",
        "compensation_binding_lifecycle_event_required",
    }
    assert functions == {
        "enforce_compensation_binding_lifecycle",
        "guard_compensation_binding_lifecycle_event",
        "reject_compensation_binding_lifecycle_event_change",
        "require_compensation_binding_lifecycle_event",
    }
    assert {
        "ck_project_compensation_adapter_bindings_status",
        "ck_project_compensation_adapter_bindings_lifecycle_shape",
        "ck_project_compensation_adapter_bindings_lifecycle_timestamps",
    } <= binding_checks
    assert (
        not {
            "ck_project_compensation_adapter_bindings_ck_project_com_95ba",
            "ck_project_compensation_adapter_bindings_ck_project_com_da73",
            "ck_project_compensation_adapter_bindings_ck_project_com_ade1",
        }
        & binding_checks
    )


def test_current_head_installs_compensation_adapter_identity(
    isolated_database_env: str, migration_lock
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(isolated_database_env, "drop schema public cascade; create schema public")
        )
        command.upgrade(config, HEAD_REVISION)

    async def identity_constraint() -> str:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            return await connection.fetchval(
                "select pg_get_constraintdef(c.oid) from pg_constraint c "
                "join pg_class t on t.oid=c.conrelid where "
                "t.relname='actor_profiles' and "
                "c.conname='ck_actor_profiles_kind_service_identity'"
            )
        finally:
            await connection.close()

    assert "workstream.compensation.adapter" in asyncio.run(identity_constraint())




def test_manifest_covers_every_required_object_class() -> None:
    manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    assert manifest["format"] == "workstream-v01-schema-manifest-1"
    assert len(manifest["tables"]) == 89
    assert len(manifest["columns"]) >= 1_200
    assert len(manifest["constraints"]) >= 850
    assert len(manifest["indexes"]) >= 400
    assert len(manifest["sequences"]) == 2
    assert len(manifest["routines"]) == 155
    assert len(manifest["triggers"]) == 211
    assert sum(row["principal"] == "PUBLIC" for row in manifest["acl"]) == 155
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
    "name", ("v01_baseline_manifest.json",)
)
def test_committed_schema_manifests_are_compact_canonical_json(name: str) -> None:
    path = _manifest_path().with_name(name)
    payload = path.read_bytes()
    assert payload == canonical_bytes(json.loads(payload))
    assert payload.count(b"\n") == 1




def test_acl_principals_are_closed_and_owner_mapping_is_role_name_independent() -> None:
    assert APPLICATION_ACL_PRINCIPALS == {}
    assert canonical_acl_principal("database_owner", "database_owner") == "owner"
    assert canonical_acl_principal("PUBLIC", "database_owner") == "PUBLIC"
    with pytest.raises(RuntimeError, match="unknown ACL principal"):
        canonical_acl_principal("unexpected_role", "database_owner")


def test_every_acl_principal_is_effective_on_the_installed_head(
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
    manifest = asyncio.run(build_manifest(isolated_database_env))
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


@pytest.mark.parametrize("old_revision", [
    "0001_v01_baseline", "0030_task_management", "0031_task_queue_authority",
    "0063_compilation_authority",
])
def test_unknown_old_stamp_refuses_before_mutation(
    isolated_database_env: str,
    migration_lock,
    old_revision: str,
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(
            _execute(
                isolated_database_env,
                "drop schema public cascade; create schema public; "
                "create table sentinel(id integer primary key, value text not null); "
                "insert into sentinel values (1,'preserve-me'); "
                "create table alembic_version(version_num varchar(128) primary key)",
            )
        )
        asyncio.run(_execute(
            isolated_database_env, "insert into alembic_version values ($1)", old_revision,
        ))
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


@pytest.mark.parametrize("revision,message", [
    (BASELINE_REVISION, "0001_uuid7_v01 cannot be downgraded; recreate the database"),
    ("0002_task_queue_authority", "Workstream v0.1 migrations cannot be downgraded; recreate the database"),
    ("0003_task_read_authority", "Workstream v0.1 migrations cannot be downgraded; recreate the database"),
    ("0004_task_context_authority", "Workstream v0.1 migrations cannot be downgraded; recreate the database"),
    (HEAD_REVISION, "Workstream v0.1 migrations cannot be downgraded; recreate the database"),
])
def test_downgrade_refuses_without_mutation(
    isolated_database_env: str,
    migration_lock,
    revision: str,
    message: str,
) -> None:
    config = _alembic_config()
    with migration_lock():
        asyncio.run(_execute(isolated_database_env, "drop schema public cascade; create schema public"))
        command.upgrade(config, revision)
        command.upgrade(config, revision)  # Current installed revision remains a valid no-op target.
    before = asyncio.run(_database_snapshot(isolated_database_env))
    assert before["versions"] == [revision]
    with migration_lock(), pytest.raises(RuntimeError, match=message):
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


def test_fresh_head_installs_guide_creation_custody(
    isolated_database_env: str,
) -> None:
    async def creation_guards() -> int:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            return await connection.fetchval(
                "select count(*) from pg_trigger where tgname='require_document_creation_pair' "
                "and not tgisinternal and tgdeferrable and tginitdeferred"
            )
        finally:
            await connection.close()

    assert asyncio.run(creation_guards()) == 3
