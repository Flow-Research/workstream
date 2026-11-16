"""Retain captured checker/model ART through 0068, then refuse incompatible rewards.

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
from tests.test_alembic import _alembic_config
from tests.finance.migration_support import assert_reward_cutover_refusal


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


# Literal inventory from e2b9262 original exact0062 contract, which explicitly
# excluded checker_trial_evidence from its then-head0065 conftest inventory.
_SCHEMA_0062_PROTECTED = ('actor_profile_migration_state', 'alembic_version', 'iso_4217_currency_codes')
_SCHEMA_0062_RESETTABLE = (
    'joint_lifecycle_release_control',
    'joint_lifecycle_transitions',
    'actor_identity_links',
    'actor_profiles',
    'admin_role_grants',
    'api_rate_control_counters',
    'artifact_admission_charges',
    'artifact_admission_scopes',
    'artifact_bindings',
    'artifact_contents',
    'artifact_operation_receipts',
    'artifact_provider_activations',
    'artifact_provider_probe_results',
    'artifact_put_attempt_charges',
    'artifact_put_attempts',
    'artifact_put_observation_receipts',
    'artifact_recovery_attempts',
    'artifact_replicas',
    'artifact_storage_namespaces',
    'artifact_task_import_sources',
    'artifact_verification_jobs',
    'artifact_verification_receipts',
    'audit_events',
    'authority_control',
    'authority_idempotency_records',
    'checker_policies',
    'checker_model_invocation_grants',
    'checker_model_invocation_grant_calls',
    'model_usage_profiles',
    'model_usage_budget_accounts',
    'model_usage_budget_configurations',
    'checker_model_usage_envelopes',
    'checker_model_usage_slots',
    'setup_model_usage_envelopes',
    'setup_model_usage_slots',
    'model_usage_effects',
    'checker_model_usage_recoveries',
    'external_checker_registry_entries',
    'checker_retry_receipts',
    'checker_result_findings',
    'checker_results',
    'checker_runs',
    'checker_submission_fences',
    'compensation_adapter_binding_lifecycle_events',
    'contribution_policy_lifecycle_events',
    'contribution_policy_transition_custody',
    'contribution_award_definitions',
    'contribution_policies',
    'contribution_policy_versions',
    'contribution_rules',
    'effective_project_submission_artifact_policies',
    'evidence_items',
    'guide_source_artifact_ingests',
    'guide_source_artifact_incidents',
    'guide_source_artifact_bindings',
    'guide_source_extracted_contents',
    'guide_source_extraction_attempts',
    'guide_source_extraction_retry_budgets',
    'guide_source_extraction_usages',
    'guide_source_format_classifications',
    'guide_mutation_idempotency_records',
    'guide_source_snapshot_items',
    'guide_source_snapshots',
    'guide_sufficiency_reports',
    'guide_sufficiency_report_source_usages',
    'guide_sufficiency_mutation_idempotency_records',
    'legacy_actor_identities',
    'legacy_workflow_eligibility',
    'outbox_delivery_attempts',
    'outbox_events',
    'policy_mutation_idempotency_records',
    'pre_submit_checker_policies',
    'pre_submit_evidence_results',
    'pre_submit_evidence_sets',
    'pre_submit_execution_attempts',
    'project_compensation_adapter_bindings',
    'project_compensation_units',
    'project_compensation_unit_creation_events',
    'project_create_idempotency_records',
    'project_guides',
    'project_guide_compilation_attempts',
    'project_guide_runtime_allocations',
    'project_guide_document_accesses',
    'project_guide_component_projection_operations',
    'project_guide_setup_finalizations',
    'project_guide_proposal_approvals',
    'project_guide_proposal_corrections',
    'project_guide_compilations',
    'project_guide_compilation_request_operations',
    'project_role_grants',
    'project_role_qualification_snapshots',
    'project_post_policy_operations',
    'project_setup_runs',
    'projects',
    'review_policies',
    'revision_policies',
    'review_admission_idempotency_records',
    'final_acceptances',
    'contribution_export_snapshots',
    'contribution_records',
    'compensation_awards',
    'reviews',
    'review_findings',
    'finding_resolutions',
    'review_decision_requests',
    'review_packet_manifests',
    'review_packet_guide_items',
    'review_leases',
    'review_queue_entries',
    'submission_policy_mutation_idempotency_records',
    'submission_artifact_policies',
    'selected_pre_submit_runs',
    'submission_bundle_admissions',
    'submission_dispatches',
    'submission_binding_receipts',
    'submission_bundle_durable_intents',
    'submissions',
    'task_assignments',
    'task_import_batch_command_receipts',
    'task_import_batch_members',
    'task_import_batches',
    'task_batch_transition_members',
    'task_batch_transition_receipts',
    'task_command_receipts',
    'task_revision_preparations',
    'task_revision_expirations',
    'task_revision_exhaustions',
    'task_post_submit_routing_manifests',
    'task_post_submit_routing_requests',
    'workstream_tasks',
)

async def _assert_exact_0062_schema(database_url: str) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(suite_fixtures, "PROTECTED_TEST_TABLES", _SCHEMA_0062_PROTECTED)
        patch.setattr(suite_fixtures, "RESETTABLE_TEST_TABLES", _SCHEMA_0062_RESETTABLE)
        patch.setattr(suite_fixtures, "EXPECTED_PUBLIC_SCHEMA_SHA256", _SCHEMA_0062_SHA256)
        connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await suite_fixtures._assert_canonical_test_schema(connection)
            assert await connection.fetchval("select version_num from alembic_version") == "0062_model_usage"
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


async def _assert_retained_lineage_projection(
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
async def test_checker_and_model_lineages_survive_0068_and_refuse_reward_cutover(
    isolated_database_env,
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
        await _assert_exact_0062_schema(isolated_database_env)
        before = await _retained_rows(isolated_database_env)

        await asyncio.to_thread(command.upgrade, _alembic_config(), "0068_issuer_profile_email")
        after = await _retained_rows(isolated_database_env)
        assert after == before
        await _assert_retained_lineage_projection(
            isolated_database_env,
            identities["legacy_binding_id"],
            identities["model_binding_id"],
            identities["setup_effect_id"],
        )

        await assert_reward_cutover_refusal(isolated_database_env)
