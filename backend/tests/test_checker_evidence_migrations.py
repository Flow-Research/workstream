"""Retain real checker and model ART lineages across the 0062-to-head upgrade."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from alembic import command
import asyncpg
import pytest

from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.preparation import ArtifactScratchManager
from tests.checkers.execution.support import provision_post_submit_service
from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests import conftest as suite_fixtures
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import signed_access as signed_access
from tests.authorization.admin_access.support import AdminAccess
from tests.checker_output_custody_helpers import output_custody_harness
from tests.checkers_model_calls.test_setup_model_handler_postgresql import (
    _Journey,
    _StorageCase,
    _setup_output_preparation_limits,
    _journey,
    _state,
)
from tests.projects.guide_compilation.helpers import seed_database
from tests.test_artifact_admission import _namespace, _settings
from tests.test_alembic import HEAD_REVISION, _alembic_config
from tests.test_checker_output_storage import (
    _INSERT_BINDING,
    _arrange_historical_checker_run_output,
    _historical_checker_run_binding_values,
    _store_verified_output,
)


pytestmark = pytest.mark.postgres_schema_contract

_SCHEMA_0062_SHA256 = "d14a06c088aae0e8876bebb637a7b3fb0c19344f8cc4fdfd31aa2c1a47348593"
_PROJECTION_SHIMS = (
    "alter table checker_runs add column input_context_custody jsonb",
    "alter table artifact_put_attempts add column checker_trial_evidence_id uuid",
    "alter table artifact_operation_receipts add column checker_trial_evidence_id uuid",
)
_DROP_PROJECTION_SHIMS = tuple(
    statement.replace(" add column ", " drop column ").rsplit(" ", 1)[0]
    for statement in _PROJECTION_SHIMS
)
_RETAINED_TABLES = (
    "checker_runs",
    "checker_model_usage_envelopes",
    "checker_model_usage_slots",
    "setup_model_usage_envelopes",
    "setup_model_usage_slots",
    "model_usage_effects",
    "artifact_contents",
    "artifact_replicas",
    "artifact_put_attempts",
    "artifact_operation_receipts",
    "artifact_verification_jobs",
    "artifact_verification_receipts",
    "artifact_bindings",
)


async def _execute(database_url: str, *statements: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            for statement in statements:
                await connection.execute(statement)
    finally:
        await connection.close()


async def _assert_exact_0062_schema(database_url: str, monkeypatch) -> None:
    tables = tuple(
        table
        for table in suite_fixtures.RESETTABLE_TEST_TABLES
        if table != "checker_trial_evidence"
    )
    with monkeypatch.context() as patch:
        patch.setattr(suite_fixtures, "RESETTABLE_TEST_TABLES", tables)
        patch.setattr(
            suite_fixtures,
            "EXPECTED_PUBLIC_SCHEMA_SHA256",
            _SCHEMA_0062_SHA256,
        )
        connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await suite_fixtures._assert_canonical_test_schema(connection)
            assert await connection.fetchval("select version_num from alembic_version") == (
                "0062_model_usage"
            )
        finally:
            await connection.close()


async def _fresh_admin_access(signed) -> AdminAccess:
    admin = await signed.actor("migration-administrator", roles=("viewer",))
    target = await signed.actor("migration-target", roles=("admin",))
    code, result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, result
    assert result["result_code"] == "bootstrapped"
    return AdminAccess(signed, admin, target, result["grant_id"])


async def _assert_projection_shims_null(database_url: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        assert (
            await connection.fetchval(
                "select count(*) from checker_runs where input_context_custody is not null"
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "select count(*) from artifact_put_attempts "
                "where checker_trial_evidence_id is not null"
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "select count(*) from artifact_operation_receipts "
                "where checker_trial_evidence_id is not null"
            )
            == 0
        )
    finally:
        await connection.close()


async def _retained_rows(database_url: str) -> dict[str, str]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        result = {}
        for table in _RETAINED_TABLES:
            excluded = {
                "checker_runs": "input_context_custody",
                "artifact_put_attempts": "checker_trial_evidence_id",
                "artifact_operation_receipts": "checker_trial_evidence_id",
            }.get(table)
            projection = "to_jsonb(value)" + (f" - '{excluded}'" if excluded else "")
            result[table] = await connection.fetchval(
                f"select coalesce(jsonb_agg({projection} order by value.id),'[]')::text "
                f"from {table} value"
            )
        return result
    finally:
        await connection.close()


async def _arrange_retained_lineages(
    tmp_path: Path,
    database_url: str,
    admin_access,
) -> tuple[str, str, str]:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    setup_values = await seed_database(
        database_url,
        namespace=namespace,
        provider_object_ref="fixture/retained-guide-source",
    )
    async with output_custody_harness(
        tmp_path,
        database_url,
        admin_access=admin_access,
        storage_settings=_settings(tmp_path, maximum_bytes=64 * 1024),
    ) as harness:
        model_stored = await harness.service.store(harness.request(b'{"result":"retained"}'))
        model_bound = await harness.bind(harness.selector, model_stored)

        legacy = await _store_verified_output(
            factory=harness.factory,
            settings=harness.settings,
            namespace=harness.namespace,
            store=harness.store,
            policy_bundle=harness.policy_bundle,
            source_path=tmp_path / "legacy-checker-output",
            payload=b'{"result":"retained historical checker output"}',
        )
        legacy_values = _historical_checker_run_binding_values(legacy)
        async with harness.factory() as session, session.begin():
            # Arrange the historical row shape explicitly; this is retained-data
            # proof, not a second production writer for pre-model evidence.
            await _arrange_historical_checker_run_output(session, legacy)
            await session.execute(_INSERT_BINDING, legacy_values)

        setup_effect_id = await _arrange_retained_setup(
            tmp_path, database_url, harness, setup_values, admin_access
        )
        return str(legacy_values["id"]), str(model_bound.binding_id), setup_effect_id


async def _arrange_retained_setup(tmp_path, database_url, harness, values, access) -> str:
    """Retain a real setup effect using its admitted actors and source bounds."""
    for identity in (
        ServiceIdentity.ARTIFACT_CHECKER_OUTPUT,
        ServiceIdentity.ARTIFACT_BINDING,
        ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        ServiceIdentity.ARTIFACT_VERIFIER,
    ):
        await provision_post_submit_service(harness.factory, identity)
    manager = ArtifactScratchManager(
        root=tmp_path / "retained-setup-scratch",
        limits=_setup_output_preparation_limits(),
    )
    try:
        storage = _StorageCase(
            database_url, harness.factory, harness.engine, harness.bootstrap,
            manager, harness.settings, harness.namespace, harness.store, values,
        )
        setup_access = replace(
            access, target=await access.signed.actor("retained-setup-operator"),
        )
        setup: _Journey = await _journey(storage, setup_access)
        assert (await setup.handler().handle(setup.request)).outcome == "unavailable"
        replay = await setup.handler().handle(setup.request)
        assert replay.outcome == "completed", (replay, setup.stages, setup.failures)
        setup_effect = await _state(setup)
        return str(setup_effect.id)
    finally:
        manager.close()


async def _assert_head_lineage_projection(
    database_url: str,
    legacy_binding_id: str,
    model_binding_id: str,
    setup_effect_id: str,
) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        assert (
            await connection.fetchval(
                "select resource_type from artifact_bindings where id=$1", legacy_binding_id
            )
            == "checker_run"
        )
        assert (
            await connection.fetchval(
                "select resource_type from artifact_bindings where id=$1", model_binding_id
            )
            == "checker_model_call"
        )
        assert (
            await connection.fetchval(
                "select state from model_usage_effects where id=$1", setup_effect_id
            )
            == "completed"
        )
        assert (
            await connection.fetchval(
                "select count(*) from checker_runs where input_context_custody is not null"
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "select count(*) from artifact_put_attempts "
                "where checker_trial_evidence_id is not null"
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "select count(*) from artifact_operation_receipts "
                "where checker_trial_evidence_id is not null"
            )
            == 0
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_checker_and_model_lineages_survive_0062_to_head(
    tmp_path,
    isolated_database_env,
    signed_access,
    monkeypatch,
    migration_lock,
) -> None:
    """Preserve three real owner lineages before admitting revision or trial custody."""
    with migration_lock():
        await _execute(
            isolated_database_env,
            "drop schema public cascade",
            "create schema public",
        )
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0062_model_usage")
        await _execute(isolated_database_env, *_PROJECTION_SHIMS)
        await db_session.dispose_engine()
        admin_access = await _fresh_admin_access(signed_access)
        identities = await _arrange_retained_lineages(
            tmp_path,
            isolated_database_env,
            admin_access,
        )
        await db_session.dispose_engine()
        await _assert_projection_shims_null(isolated_database_env)
        await _execute(isolated_database_env, *_DROP_PROJECTION_SHIMS)
        await _assert_exact_0062_schema(isolated_database_env, monkeypatch)
        before = await _retained_rows(isolated_database_env)

        await asyncio.to_thread(command.upgrade, _alembic_config(), HEAD_REVISION)
        after = await _retained_rows(isolated_database_env)
        assert after == before
        await _assert_head_lineage_projection(isolated_database_env, *identities)
