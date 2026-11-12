"""Retain captured checker and model ART lineages across the 0062-to-head upgrade.

The synthetic archive comes from the pinned predecessor's original owner journey,
after its null-projection and exact-schema checks and before upgrading. Restoring
those rows keeps migration proof independent of the current guide compiler.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from pathlib import Path

from alembic import command
import asyncpg
import pytest

from app.db import session as db_session
from tests import conftest as suite_fixtures
from tests.historical_submission_fixtures import _restore_validated_snapshot_rows
from tests.test_alembic import HEAD_REVISION, _alembic_config


pytestmark = pytest.mark.postgres_schema_contract

_SCHEMA_0062_SHA256 = "d14a06c088aae0e8876bebb637a7b3fb0c19344f8cc4fdfd31aa2c1a47348593"
_ARCHIVE = Path(__file__).with_name("fixtures") / "historical_checker_model_rows.json.gz"
_ARCHIVE_SHA256 = "121c902b53586e6cb8e86db914d1bbf38214faf93b95f63ee272f3009f227feb"
_ARCHIVE_SOURCE = "e2b926288899bcd9b05e1a560ec19b6bca8cfcfc"


def _historical_lineage_snapshot():
    """Load synthetic rows captured by the genuine 0062 owners before specification changes."""
    encoded = _ARCHIVE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == _ARCHIVE_SHA256
    body = json.loads(gzip.decompress(encoded))
    assert body["schema_version"] == "workstream.historical_checker_model_rows.v1"
    assert body["source_revision"] == _ARCHIVE_SOURCE
    assert body["source_test"] == (
        "tests/test_checker_evidence_migrations.py::"
        "test_real_checker_and_model_lineages_survive_0062_to_head"
    )
    assert body["predecessor_schema_sha256"] == _SCHEMA_0062_SHA256
    assert body["snapshot"]["revision"] == "0062_model_usage"
    return body["snapshot"]


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
        if table not in {
            "checker_trial_evidence", "submission_intake_operations",
            "submission_source_capacity_profiles", "submission_source_charges",
            "submission_source_upload_receipts", "submission_source_cleanup_claims",
        }
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
    isolated_database_env,
    monkeypatch,
    migration_lock,
) -> None:
    """Preserve three captured owner lineages before admitting revision or trial custody."""
    with migration_lock():
        await _execute(
            isolated_database_env,
            "drop schema public cascade",
            "create schema public",
        )
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0062_model_usage")
        await db_session.dispose_engine()
        identities = await _restore_validated_snapshot_rows(
            isolated_database_env,
            _historical_lineage_snapshot(),
            expected_revision="0062_model_usage",
        )
        await _assert_exact_0062_schema(isolated_database_env, monkeypatch)
        before = await _retained_rows(isolated_database_env)

        await asyncio.to_thread(command.upgrade, _alembic_config(), HEAD_REVISION)
        after = await _retained_rows(isolated_database_env)
        assert after == before
        await _assert_head_lineage_projection(
            isolated_database_env,
            identities["legacy_binding_id"],
            identities["model_binding_id"],
            identities["setup_effect_id"],
        )
