from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from alembic import command
from alembic.config import Config
from migration_contracts import service_identity_0023 as frozen_service_identity_contract
from migration_contracts.service_identity_0023 import (
    SERVICE_IDENTITY_VALUES as FROZEN_SERVICE_IDENTITY_VALUES,
    ServiceIdentityMappingError as FrozenServiceIdentityMappingError,
    protected_mapping_roots as frozen_protected_mapping_roots,
    validate_mapping_path as validate_frozen_mapping_path,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.auth.dev import actor_id_from_external_identity
from app.modules.authorization.catalogue import (
    ACTION_DEFINITIONS,
    HISTORICAL_PERMISSION_IDS,
    NEW_PERMISSION_IDS,
    ActionOwner,
)
from app.modules.actors.legacy_classification import (
    CLASSIFICATION_FILE_ENV,
    LegacyActorClassification,
    LegacyActorClassificationManifest,
    LegacyActorRow,
    LegacyClassificationError,
    build_envelope,
    canonical_envelope_bytes,
    database_binding_identifier,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.actors.service_identity_migration import (
    MAPPING_FILE_ENV,
    ServiceActorIdentityMapping,
    ServiceActorIdentityMappingDraft,
    build_envelope as build_service_identity_envelope,
    publish_envelope as publish_service_identity_envelope,
    snapshot_existing_service_rows,
)


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


def test_service_identity_migration_contract_is_frozen_from_application_modules() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    revision_source = (
        backend_root / "alembic/versions/0023_service_actor_identity.py"
    ).read_text(encoding="utf-8")
    contract_source = (
        backend_root / "migration_contracts/service_identity_0023.py"
    ).read_text(encoding="utf-8")
    assert "from migration_contracts.service_identity_0023 import" in revision_source
    assert "app.modules" not in revision_source
    assert "app.modules" not in contract_source
    assert "repository_root=MIGRATION_REPOSITORY_ROOT" in revision_source
    assert "REPOSITORY_ROOT" not in contract_source
    assert FROZEN_SERVICE_IDENTITY_VALUES == tuple(identity.value for identity in ServiceIdentity)


def test_frozen_mapping_path_custody_is_independent_of_install_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        frozen_service_identity_contract,
        "__file__",
        "/installed/site-packages/migration_contracts/service_identity_0023.py",
    )
    roots = frozen_protected_mapping_roots(repository_root)
    assert repository_root in roots
    for root in roots:
        with pytest.raises(
            FrozenServiceIdentityMappingError,
            match="service_mapping_path_forbidden",
        ):
            validate_frozen_mapping_path(
                root / "private-envelope.json",
                repository_root=repository_root,
                output=True,
            )

    deployment_root = tmp_path / "deployed"
    private_root = tmp_path / "private"
    deployment_root.mkdir()
    private_root.mkdir()
    assert validate_frozen_mapping_path(
        private_root / "private-envelope.json",
        repository_root=deployment_root,
        output=True,
    ) == private_root / "private-envelope.json"


def test_alembic_upgrade_and_downgrade(isolated_database_env: str, migration_lock) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.downgrade(config, "base")


def test_outbox_migration_schema_and_downgrade_writer_guard(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove exact 0029 schema plus ACCESS EXCLUSIVE commit/rollback behavior."""
    config = _alembic_config()
    committed_project_id = str(uuid4())
    rolled_back_project_id = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            schema = asyncio.run(_outbox_schema(isolated_database_env))
            assert schema == {
                "revision": "0029_shared_transactional_outbox",
                "columns": {
                    "aggregate_id",
                    "aggregate_type",
                    "archived_at",
                    "attempt_count",
                    "causation_event_id",
                    "claim_expires_at",
                    "claim_generation",
                    "claim_owner",
                    "claimed_at",
                    "correlation_id",
                    "delivery_state",
                    "event_id",
                    "event_type",
                    "event_version",
                    "finalized_at",
                    "idempotency_key",
                    "last_attempt_at",
                    "last_error_code",
                    "next_attempt_at",
                    "occurred_at",
                    "payload",
                    "payload_digest",
                    "producer",
                    "project_id",
                },
                "nullable": {
                    "next_attempt_at",
                    "causation_event_id",
                    "claim_owner",
                    "claimed_at",
                    "claim_expires_at",
                    "last_attempt_at",
                    "last_error_code",
                    "finalized_at",
                    "archived_at",
                },
                "indexes": {
                    "ix_outbox_events_aggregate",
                    "ix_outbox_events_eligible",
                    "ix_outbox_events_expired_claims",
                    "ix_outbox_events_project_drain",
                    "ix_outbox_events_retention",
                    "pk_outbox_events",
                    "uq_outbox_events_idempotency_key",
                },
                "triggers": {"outbox_events_custody", "outbox_events_reject_truncate"},
            }

            committed = asyncio.run(
                _outbox_downgrade_writer_race(
                    isolated_database_env,
                    config,
                    project_id=committed_project_id,
                    commit_writer=True,
                )
            )
            assert committed == "refused_after_commit"
            assert asyncio.run(_current_revision(isolated_database_env)) == (
                "0029_shared_transactional_outbox"
            )
            asyncio.run(_remove_outbox_migration_row(isolated_database_env, committed_project_id))
            command.downgrade(config, "0028_artifact_admission")
            assert "outbox_events" not in asyncio.run(_fetch_table_names(isolated_database_env))

            command.upgrade(config, "head")
            rolled_back = asyncio.run(
                _outbox_downgrade_writer_race(
                    isolated_database_env,
                    config,
                    project_id=rolled_back_project_id,
                    commit_writer=False,
                )
            )
            assert rolled_back == "succeeded_after_rollback"
            assert asyncio.run(_current_revision(isolated_database_env)) == (
                "0028_artifact_admission"
            )
        finally:
            command.upgrade(config, "head")
            asyncio.run(_remove_outbox_migration_row(isolated_database_env, committed_project_id))
            asyncio.run(_remove_outbox_migration_row(isolated_database_env, rolled_back_project_id))
            command.downgrade(config, "base")


def test_current_schema_uses_project_policy_contract(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove current schema stores guide prose and policy records separately."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            columns = asyncio.run(_fetch_columns(isolated_database_env))
        finally:
            command.downgrade(config, "base")

    assert {
        "projects.id",
        "projects.name",
        "projects.slug",
        "projects.status",
        "project_guides.content_markdown",
        "project_guides.approved_by",
        "project_guides.effective_at",
        "submission_artifact_policies.policy_body",
        "effective_project_submission_artifact_policies.effective_policy",
        "pre_submit_checker_policies.compiled_bundle",
        "checker_policies.source_snapshot_id",
        "checker_policies.source_snapshot_hash",
        "checker_policies.effective_policy_id",
        "checker_policies.effective_policy_hash",
        "checker_policies.pre_submit_checker_policy_id",
        "checker_policies.pre_submit_checker_bundle_hash",
        "payment_policies.base_amount",
        "payment_policies.currency",
        "artifact_upload_sessions.id",
        "artifact_upload_items.id",
        "artifact_contents.sha256",
        "artifact_bindings.scope_version",
        "artifact_storage_namespaces.namespace_fingerprint",
        "artifact_replicas.provider_object_ref",
        "artifact_replicas.storage_namespace_id",
        "artifact_operation_receipts.request_digest",
        "outbox_events.event_id",
        "outbox_events.payload_digest",
        "outbox_events.delivery_state",
    }.issubset(columns)
    discarded_columns = {
        "projects.base_amount",
        "projects.currency",
        "project_guides.required_task_fields",
        "project_guides.required_submission_fields",
        "project_guides.task_instructions",
        "project_guides.output_requirements",
        "project_guides.acceptance_criteria",
        "project_guides.rejection_criteria",
        "project_guides.reviewer_rubric",
        "project_guides.forbidden_actions",
        "project_guides.required_skills",
        "project_guides.difficulty_scale",
        "project_guides.estimated_time_policy",
        "project_guides.common_rejection_reasons",
        "project_guides.evidence_policy",
        "project_guides.unacceptable_work_policy",
        "workstream_tasks.required_files",
        "workstream_tasks.required_evidence",
        "workstream_tasks.locked_checker_policy_version",
        "submissions.locked_checker_policy_version",
        "checker_runs.locked_checker_policy_version",
        "artifact_replicas.provider_artifact_id",
        "artifact_replicas.provider_manifest_id",
        "artifact_replicas.retention_state",
        "artifact_operation_receipts.provider_receipt_id",
        "artifact_operation_receipts.retention_reference",
    }
    assert columns.isdisjoint(discarded_columns)


def test_post_submit_policy_upgrade_leaves_pre_provenance_rows_fail_closed(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0008 does not create fake post-submit authority for pre-provenance rows."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    pre_provenance_project_id = str(uuid4())
    pre_provenance_guide_id = str(uuid4())
    pre_provenance_policy_id = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0007_task_locked_context")
            asyncio.run(
                _seed_pre_provenance_post_submit_policy(
                    isolated_database_env,
                    pre_provenance_project_id,
                    pre_provenance_guide_id,
                    pre_provenance_policy_id,
                )
            )
            command.upgrade(config, "0008_post_submit_checker_policy")
            policy_hash = asyncio.run(
                _fetch_pre_provenance_post_submit_policy_hash(
                    isolated_database_env,
                    pre_provenance_policy_id,
                )
            )
        finally:
            command.downgrade(config, "base")

    assert policy_hash is None


def test_post_submit_policy_upgrade_blocks_pre_provenance_runtime_rows(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0008 fails clearly when runtime rows cannot gain trusted provenance."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    ids = {
        name: str(uuid4()) for name in ("project", "guide", "policy", "task", "submission", "run")
    }
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0007_task_locked_context")
            asyncio.run(_seed_pre_provenance_runtime_rows(isolated_database_env, ids))

            with pytest.raises(RuntimeError, match="cannot infer locked post-submit"):
                command.upgrade(config, "0008_post_submit_checker_policy")

            columns_exist = asyncio.run(
                _post_submit_lock_columns_exist(isolated_database_env, "submissions")
            )
        finally:
            command.downgrade(config, "base")

    assert columns_exist is False


def test_canonical_actor_registry_separates_authority_from_legacy_workflow_metadata(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove obsolete profile tables are removed from the current schema."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0021_auth_action_evidence")
            table_names = asyncio.run(_fetch_table_names(isolated_database_env))
        finally:
            command.downgrade(config, "base")

    assert "actor_profiles" in table_names
    assert "actor_identity_links" in table_names
    assert "legacy_actor_identities" in table_names
    assert "legacy_workflow_eligibility" in table_names
    assert "actor_identities" not in table_names
    assert "worker_profiles" not in table_names
    assert "reviewer_profiles" not in table_names


def test_canonical_actor_upgrade_rejects_unclassified_legacy_rows(
    isolated_database_env: str,
    migration_lock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed before changing tables when non-empty legacy data is ambiguous."""
    config = _alembic_config()
    actor_id = actor_id_from_external_identity(
        "https://identity.test",
        "unclassified-human",
    )
    monkeypatch.delenv(CLASSIFICATION_FILE_ENV, raising=False)
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0019_authority_idempotency")
            asyncio.run(
                _seed_pre_0020_actor(
                    isolated_database_env,
                    actor_id=actor_id,
                    subject="unclassified-human",
                )
            )

            with pytest.raises(
                LegacyClassificationError,
                match="^classification_file_not_configured$",
            ):
                command.upgrade(config, "0020_canonical_actor_profile")

            state = asyncio.run(_pre_0020_actor_state(isolated_database_env, actor_id))
        finally:
            command.downgrade(config, "base")

    assert state == {"revision": "0019_authority_idempotency", "legacy_rows": 1}


def test_canonical_actor_upgrade_redacts_invalid_legacy_row_values(
    isolated_database_env: str,
    migration_lock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep invalid source identity values out of migration diagnostics."""
    config = _alembic_config()
    raw_actor_id = "raw-private-invalid-actor-id"
    monkeypatch.delenv(CLASSIFICATION_FILE_ENV, raising=False)
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0019_authority_idempotency")
            asyncio.run(
                _seed_pre_0020_actor(
                    isolated_database_env,
                    actor_id=raw_actor_id,
                    subject="raw-private-subject",
                )
            )
            with pytest.raises(LegacyClassificationError) as captured:
                command.upgrade(config, "0020_canonical_actor_profile")
            assert str(captured.value) == "invalid_source_rows"
            assert raw_actor_id not in str(captured.value)
            state = asyncio.run(_pre_0020_actor_state(isolated_database_env, raw_actor_id))
        finally:
            command.downgrade(config, "base")

    assert state == {"revision": "0019_authority_idempotency", "legacy_rows": 1}


def test_canonical_actor_classified_upgrade_preserves_identity_and_attribution(
    isolated_database_env: str,
    migration_lock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Consume bound evidence once and downgrade later without the external file."""
    config = _alembic_config()
    issuer = "https://identity.test"
    subject = "classified-human"
    actor_id = actor_id_from_external_identity(issuer, subject)
    audit_event_id = str(uuid4())
    envelope_path = tmp_path / "classification-envelope.json"
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0019_authority_idempotency")
            asyncio.run(
                _seed_pre_0020_actor(
                    isolated_database_env,
                    actor_id=actor_id,
                    subject=subject,
                    audit_event_id=audit_event_id,
                )
            )
            binding = asyncio.run(_legacy_database_binding(isolated_database_env))
            row = LegacyActorRow(actor_id=actor_id, issuer=issuer, subject=subject)
            envelope = build_envelope(
                LegacyActorClassificationManifest(
                    schema_version=1,
                    classifications=(
                        LegacyActorClassification(
                            actor_id=actor_id,
                            issuer=issuer,
                            subject=subject,
                            subject_kind="human",
                        ),
                    ),
                ),
                (row,),
                database_binding=binding,
                generated_at="2026-07-15T12:00:00Z",
            )
            envelope_path.write_bytes(canonical_envelope_bytes(envelope))
            os.chmod(envelope_path, 0o600)
            monkeypatch.setenv(CLASSIFICATION_FILE_ENV, str(envelope_path))

            command.upgrade(config, "0020_canonical_actor_profile")
            upgraded = asyncio.run(
                _canonical_actor_migration_state(
                    isolated_database_env,
                    actor_id,
                    audit_event_id,
                )
            )
            asyncio.run(
                _update_canonical_actor_display_fields(
                    isolated_database_env,
                    actor_id,
                    display_name="Canonical Human",
                    contact_email=None,
                )
            )
            envelope_path.unlink()
            monkeypatch.delenv(CLASSIFICATION_FILE_ENV, raising=False)
            command.downgrade(config, "0019_authority_idempotency")
            restored = asyncio.run(_pre_0020_actor_state(isolated_database_env, actor_id))
            restored_display = asyncio.run(
                _pre_0020_actor_display_fields(isolated_database_env, actor_id)
            )
            with pytest.raises(
                LegacyClassificationError,
                match="^classification_file_not_configured$",
            ):
                command.upgrade(config, "0020_canonical_actor_profile")
            reupgrade_rejected = asyncio.run(_pre_0020_actor_state(isolated_database_env, actor_id))
        finally:
            command.downgrade(config, "base")

    assert upgraded == {
        "profile_id": actor_id,
        "actor_kind": "human",
        "display_name": None,
        "contact_email": None,
        "identity_link_id": str(uuid5(NAMESPACE_URL, f"workstream:identity-link:{actor_id}")),
        "identity_subject": subject,
        "legacy_profile_type": "worker",
        "audit_actor_id": actor_id,
        "classified_count": 1,
        "source_checksum": envelope.source_row_set_sha256,
    }
    assert restored == {"revision": "0019_authority_idempotency", "legacy_rows": 1}
    assert restored_display == {
        "display_name": "Canonical Human",
        "email": None,
    }
    assert reupgrade_rejected == restored


def test_actor_profile_registry_unique_constraints_are_enforced(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove actor registry uniqueness is enforced by Postgres."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(_assert_actor_registry_unique_constraints(isolated_database_env))
        finally:
            command.downgrade(config, "base")


def test_canonical_actor_downgrade_refuses_nonactive_authority_state(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prevent rollback from silently restoring revoked or inactive actors."""
    config = _alembic_config()
    actor_id = actor_id_from_external_identity("https://identity.test", "rollback-guard")
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            retained_revision = asyncio.run(_current_revision(isolated_database_env))
            asyncio.run(_seed_canonical_actor_for_downgrade_guard(isolated_database_env, actor_id))
            for state in ("revoked", "suspended", "deactivated"):
                asyncio.run(
                    _set_canonical_actor_guard_state(isolated_database_env, actor_id, state)
                )
                with pytest.raises(
                    RuntimeError,
                    match="^canonical actor downgrade refused: inactive authority state$",
                ):
                    command.downgrade(config, "0019_authority_idempotency")
                assert asyncio.run(_current_revision(isolated_database_env)) == retained_revision
                asyncio.run(
                    _reset_canonical_actor_guard_state(
                        isolated_database_env,
                        actor_id,
                    )
                )
            command.downgrade(config, "0019_authority_idempotency")
        finally:
            command.downgrade(config, "base")


def test_authorization_action_evidence_constraints_and_guarded_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove exact action parity, rollback custody, and downgrade locking."""
    config = _alembic_config()
    historical_event = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0020_canonical_actor_profile")
            asyncio.run(_insert_authority_audit_fixture(isolated_database_env, historical_event))
            historical_before = asyncio.run(
                _authorization_action_row(isolated_database_env, historical_event)
            )
            command.upgrade(config, "0021_auth_action_evidence")
            schema = asyncio.run(_authorization_action_schema(isolated_database_env))
            historical_upgraded = asyncio.run(
                _authorization_action_row(isolated_database_env, historical_event)
            )
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env,
                    definitions=tuple(
                        definition
                        for definition in ACTION_DEFINITIONS
                        if definition.owner
                        not in {
                            ActionOwner.AUTH_08,
                            ActionOwner.AUTH_09B,
                            ActionOwner.AUTH_09C,
                            ActionOwner.AUTH_09D_A,
                            ActionOwner.AUTH_09D_B,
                        }
                    ),
                )
            )

            action_event = asyncio.run(_insert_authorization_action_event(isolated_database_env))
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade non-empty authorization action evidence$",
            ):
                command.downgrade(config, "0020_canonical_actor_profile")
            asyncio.run(_remove_authorization_action_events(isolated_database_env, [action_event]))

            permission_event = asyncio.run(
                _insert_authorization_action_event(isolated_database_env)
            )
            asyncio.run(
                _convert_to_permission_only_forward_evidence(
                    isolated_database_env, permission_event
                )
            )
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade non-empty authorization action evidence$",
            ):
                command.downgrade(config, "0020_canonical_actor_profile")
            asyncio.run(
                _remove_authorization_action_events(isolated_database_env, [permission_event])
            )

            target_reference_event = asyncio.run(
                _insert_forward_permission_reference(
                    isolated_database_env,
                    historical_event,
                    reference_field="target",
                )
            )
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade non-empty authorization action evidence$",
            ):
                command.downgrade(config, "0020_canonical_actor_profile")
            asyncio.run(
                _remove_authorization_action_events(isolated_database_env, [target_reference_event])
            )

            invalidation_reference_event = asyncio.run(
                _insert_forward_permission_reference(
                    isolated_database_env,
                    historical_event,
                    reference_field="invalidation",
                )
            )
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade non-empty authorization action evidence$",
            ):
                command.downgrade(config, "0020_canonical_actor_profile")
            asyncio.run(
                _remove_authorization_action_events(
                    isolated_database_env, [invalidation_reference_event]
                )
            )

            command.downgrade(config, "0020_canonical_actor_profile")
            downgraded = asyncio.run(_authorization_action_schema(isolated_database_env))
            historical_downgraded = asyncio.run(
                _authorization_action_row(isolated_database_env, historical_event)
            )
            asyncio.run(_assert_historical_permission_registry(isolated_database_env))
            asyncio.run(
                _remove_authorization_action_events(isolated_database_env, [historical_event])
            )
            command.upgrade(config, "0021_auth_action_evidence")

            lock_observed, raced_event = _action_downgrade_waits_for_insert(
                config, isolated_database_env
            )
            asyncio.run(_remove_authorization_action_events(isolated_database_env, [raced_event]))
            command.downgrade(config, "0020_canonical_actor_profile")
            command.upgrade(config, "0021_auth_action_evidence")
        finally:
            command.downgrade(config, "base")

    assert schema == {
        "revision": "0021_auth_action_evidence",
        "action_column": True,
        "action_constraint": True,
    }
    assert downgraded == {
        "revision": "0020_canonical_actor_profile",
        "action_column": False,
        "action_constraint": False,
    }
    assert (
        historical_before
        == historical_upgraded
        == historical_downgraded
        == {
            "event_type": "SensitiveAuthorizationAllowed",
            "permission_id": "actor.profile.read_any",
            "action_id": None,
        }
    )
    assert lock_observed is True


def test_bootstrap_admin_grant_schema_is_immutable_and_guarded(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove clean migration reversibility and irreversible grant history guards."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0021_auth_action_evidence")
            for event_type in (
                "InitialAccessAdministratorBootstrapped",
                "AdminRoleGrantIssueDenied",
                "LastAccessAdministratorOperationDenied",
            ):
                asyncio.run(_insert_orphan_admin_evidence(isolated_database_env, event_type))
                with pytest.raises(
                    RuntimeError,
                    match="^cannot adopt orphan administrative grant evidence$",
                ):
                    command.upgrade(config, "0022_bootstrap_admin_grants")
                asyncio.run(_clear_orphan_admin_state(isolated_database_env))
            asyncio.run(_insert_orphan_admin_idempotency(isolated_database_env))
            with pytest.raises(
                RuntimeError,
                match="^cannot adopt orphan administrative idempotency$",
            ):
                command.upgrade(config, "0022_bootstrap_admin_grants")
            asyncio.run(_clear_orphan_admin_state(isolated_database_env))
            command.upgrade(config, "0022_bootstrap_admin_grants")
            assert asyncio.run(_admin_authority_schema(isolated_database_env)) == {
                "revision": "0022_bootstrap_admin_grants",
                "grant_table": True,
                "control": (False, None, 0),
            }
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env,
                    definitions=tuple(
                        definition
                        for definition in ACTION_DEFINITIONS
                        if definition.owner
                        not in {
                            ActionOwner.AUTH_09B,
                            ActionOwner.AUTH_09C,
                            ActionOwner.AUTH_09D_A,
                            ActionOwner.AUTH_09D_B,
                        }
                    ),
                )
            )
            command.downgrade(config, "0021_auth_action_evidence")
            command.upgrade(config, "0022_bootstrap_admin_grants")

            proof = asyncio.run(_exercise_admin_authority_guards(isolated_database_env))
            assert proof == {
                "service_target_rejected": True,
                "missing_authorizer_rejected": True,
                "mixed_bootstrap_attribution_rejected": True,
                "orphan_bootstrap_commit_rejected": True,
                "mismatched_bootstrap_control_rejected": True,
                "second_bootstrap_rejected": True,
                "immutable_provenance_rejected": True,
                "incomplete_revocation_rejected": True,
                "immutable_provenance_preserved": True,
                "immutable_reason_rejected": True,
                "delete_rejected": True,
                "truncate_rejected": True,
                "control_reset_rejected": True,
                "revoked_status": "revoked",
                "revoked_version": 2,
                "grant_reason": "Operations assignment",
                "revoked_reason": "Rotation ended",
                "bootstrap_completed": True,
            }
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade non-empty administrative authority$",
            ):
                command.downgrade(config, "0021_auth_action_evidence")
            asyncio.run(_clear_admin_authority_guard_fixtures(isolated_database_env))
            command.downgrade(config, "0021_auth_action_evidence")
            command.upgrade(config, "0022_bootstrap_admin_grants")
        finally:
            command.downgrade(config, "base")


def test_fixed_service_identity_schema_mapping_and_guarded_downgrade(
    isolated_database_env: str,
    migration_lock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove exact legacy mapping, static action parity, and destructive rollback guards."""
    config = _alembic_config()
    service_id = actor_id_from_external_identity(
        "https://identity.test", "auth09-legacy-service"
    )
    envelope_path = tmp_path / "service-identity-envelope.json"
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0022_bootstrap_admin_grants")
            command.upgrade(config, "0023_service_actor_identity")
            assert asyncio.run(_service_identity_schema(isolated_database_env)) == {
                "revision": "0023_service_actor_identity",
                "service_identity_column": True,
                "mapped_count": 0,
                "manifest_digest": None,
                "envelope_digest": None,
            }
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env,
                    definitions=tuple(
                        definition
                        for definition in ACTION_DEFINITIONS
                        if definition.owner
                        in {
                            ActionOwner.AUTH_09B,
                            ActionOwner.AUTH_09C,
                            ActionOwner.AUTH_09D_A,
                            ActionOwner.AUTH_09D_B,
                        }
                    ),
                )
            )
            command.downgrade(config, "0022_bootstrap_admin_grants")

            asyncio.run(
                _insert_service_actor_before_fixed_identity(
                    isolated_database_env,
                    service_id,
                    "auth09-legacy-service",
                )
            )
            monkeypatch.delenv(MAPPING_FILE_ENV, raising=False)
            with pytest.raises(
                FrozenServiceIdentityMappingError,
                match="^service_mapping_required$",
            ):
                command.upgrade(config, "0023_service_actor_identity")
            assert asyncio.run(_current_revision(isolated_database_env)) == (
                "0022_bootstrap_admin_grants"
            )

            asyncio.run(
                _write_service_identity_envelope(
                    isolated_database_env,
                    envelope_path,
                )
            )
            monkeypatch.setenv(MAPPING_FILE_ENV, str(envelope_path))
            command.upgrade(config, "0023_service_actor_identity")
            mapped = asyncio.run(_service_identity_schema(isolated_database_env))
            assert mapped["revision"] == "0023_service_actor_identity"
            assert mapped["service_identity"] == "workstream.artifact.verifier"
            assert mapped["mapped_count"] == 1
            assert len(mapped["source_digest"]) == 64
            assert len(mapped["manifest_digest"]) == 64
            assert len(mapped["envelope_digest"]) == 64
            assert mapped["private_evidence_columns"] is False
            assert asyncio.run(_service_identity_guards(isolated_database_env, service_id)) == {
                "identity_update_rejected": True,
                "kind_update_rejected": True,
                "human_identity_rejected": True,
                "unknown_identity_rejected": True,
                "duplicate_identity_rejected": True,
            }
            assert asyncio.run(
                _service_identity_evidence_guards(isolated_database_env)
            ) == {
                "update_rejected": True,
                "delete_rejected": True,
                "truncate_rejected": True,
                "invalid_count_rejected": True,
                "invalid_source_digest_rejected": True,
                "invalid_manifest_digest_rejected": True,
                "invalid_database_binding_rejected": True,
            }
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade fixed service identity authority$",
            ):
                command.downgrade(config, "0022_bootstrap_admin_grants")
            asyncio.run(_remove_fixed_service_actor(isolated_database_env, service_id))
            command.downgrade(config, "0022_bootstrap_admin_grants")
            monkeypatch.delenv(MAPPING_FILE_ENV, raising=False)
            command.upgrade(config, "0023_service_actor_identity")

            auth09_definitions = tuple(
                definition
                for definition in ACTION_DEFINITIONS
                if definition.owner
                in {
                    ActionOwner.AUTH_09B,
                    ActionOwner.AUTH_09C,
                    ActionOwner.AUTH_09D_A,
                    ActionOwner.AUTH_09D_B,
                }
            )
            assert len(auth09_definitions) == 8
            for definition in auth09_definitions:
                event_id = asyncio.run(
                    _insert_authorization_action_event_for(
                        isolated_database_env,
                        definition.action_id.value,
                        definition.permission_id.value,
                    )
                )
                with pytest.raises(
                    RuntimeError,
                    match="^cannot downgrade fixed service identity authority$",
                ):
                    command.downgrade(config, "0022_bootstrap_admin_grants")
                asyncio.run(
                    _remove_authorization_action_events(isolated_database_env, [event_id])
                )
            command.downgrade(config, "0022_bootstrap_admin_grants")
            command.upgrade(config, "0023_service_actor_identity")
        finally:
            monkeypatch.delenv(MAPPING_FILE_ENV, raising=False)
            command.downgrade(config, "base")


def test_service_link_verification_timestamp_schema_and_guarded_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Allow null verification only for services and refuse proof-losing rollback."""
    config = _alembic_config()
    human_id, human_link_id = str(uuid4()), str(uuid4())
    rejected_human_id, rejected_human_link_id = str(uuid4()), str(uuid4())
    service_id, service_link_id = str(uuid4()), str(uuid4())

    async def seed_human_before_upgrade() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "insert into actor_profiles "
                        "(id,actor_kind,status,provisioning_method,created_by) values "
                        "(:id,'human','active','automatic_first_access',:id)"
                    ),
                    {"id": human_id},
                )
                await connection.execute(
                    text(
                        "insert into actor_identity_links "
                        "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                        "values (:link,:actor,'issuer-0024','human-0024','human','active',:actor)"
                    ),
                    {"link": human_link_id, "actor": human_id},
                )
        finally:
            await engine.dispose()

    async def schema_state() -> dict[str, object]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                column = (
                    (
                        await connection.execute(
                            text(
                                "select is_nullable,column_default from information_schema.columns "
                                "where table_schema='public' and table_name='actor_identity_links' "
                                "and column_name='last_verified_at'"
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                human_verified = await connection.scalar(
                    text(
                        "select last_verified_at is not null from actor_identity_links "
                        "where id=:id"
                    ),
                    {"id": human_link_id},
                )
                constraint = await connection.scalar(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint where "
                        "conrelid='actor_identity_links'::regclass and "
                        "conname='ck_actor_identity_links_human_verified'"
                    )
                )
                return {
                    "nullable": column["is_nullable"],
                    "default": column["column_default"],
                    "human_verified": human_verified,
                    "constraint": constraint,
                }
        finally:
            await engine.dispose()

    async def insert_service_and_reject_null_human() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "insert into actor_profiles "
                        "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                        "values (:id,'service','active','manual_service_provisioning',"
                        "'workstream.artifact.verifier',:id)"
                    ),
                    {"id": service_id},
                )
                await connection.execute(
                    text(
                        "insert into actor_identity_links "
                        "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                        "last_verified_at) values (:link,:actor,'issuer-0024','service-0024',"
                        "'service','active',:actor,null)"
                    ),
                    {"link": service_link_id, "actor": service_id},
                )
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "insert into actor_profiles "
                            "(id,actor_kind,status,provisioning_method,created_by) values "
                            "(:id,'human','active','automatic_first_access',:id)"
                        ),
                        {"id": rejected_human_id},
                    )
                    await connection.execute(
                        text(
                            "insert into actor_identity_links "
                            "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                            "last_verified_at) values (:link,:actor,'issuer-0024',"
                            "'rejected-human-0024','human','active',:actor,null)"
                        ),
                        {"link": rejected_human_link_id, "actor": rejected_human_id},
                    )
        finally:
            await engine.dispose()

    async def make_service_downgrade_safe() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update actor_identity_links set last_verified_at=clock_timestamp() "
                        "where id=:id"
                    ),
                    {"id": service_link_id},
                )
        finally:
            await engine.dispose()

    async def cleanup() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("alter table actor_identity_links disable trigger user")
                )
                await connection.execute(text("alter table actor_profiles disable trigger user"))
                await connection.execute(
                    text(
                        "delete from actor_identity_links where id in (:human_link,:service_link)"
                    ),
                    {"human_link": human_link_id, "service_link": service_link_id},
                )
                await connection.execute(
                    text(
                        "delete from actor_profiles where id in "
                        "(:human,:rejected_human,:service)"
                    ),
                    {
                        "human": human_id,
                        "rejected_human": rejected_human_id,
                        "service": service_id,
                    },
                )
                await connection.execute(text("alter table actor_profiles enable trigger user"))
                await connection.execute(
                    text("alter table actor_identity_links enable trigger user")
                )
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0023_service_actor_identity")
            asyncio.run(seed_human_before_upgrade())
            command.upgrade(config, "0024_service_link_verification")
            state = asyncio.run(schema_state())
            assert state["nullable"] == "YES"
            assert state["default"] is None
            assert state["human_verified"] is True
            assert "subject_kind" in str(state["constraint"])
            assert "last_verified_at IS NOT NULL" in str(state["constraint"])
            asyncio.run(insert_service_and_reject_null_human())
            with pytest.raises(
                RuntimeError,
                match="^cannot downgrade with unverified service identity links$",
            ):
                command.downgrade(config, "0023_service_actor_identity")
            assert asyncio.run(_current_revision(isolated_database_env)) == (
                "0024_service_link_verification"
            )
            asyncio.run(make_service_downgrade_safe())
            command.downgrade(config, "0023_service_actor_identity")
            historical = asyncio.run(schema_state())
            assert historical["nullable"] == "NO"
            assert "now()" in str(historical["default"])
            assert historical["constraint"] is None
            command.upgrade(config, "0024_service_link_verification")
            asyncio.run(cleanup())
        finally:
            try:
                asyncio.run(make_service_downgrade_safe())
                asyncio.run(cleanup())
            except DBAPIError:
                pass
            command.downgrade(config, "base")


def test_artifact_foundation_upgrade_preserves_prior_head_and_promotes_nothing(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Upgrade populated 0015 data without interpreting legacy declarations."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    project_id = str(uuid4())
    runtime_ids = {
        name: str(uuid4())
        for name in (
            "project",
            "guide",
            "snapshot",
            "submission_policy",
            "effective_policy",
            "pre_submit_policy",
            "policy",
            "review_policy",
            "revision_policy",
            "payment_policy",
            "task",
            "submission",
            "run",
        )
    }
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0015_post_submit_correction")
            asyncio.run(_seed_artifact_prior_head(isolated_database_env, project_id))
            asyncio.run(_seed_artifact_prior_head_runtime_rows(isolated_database_env, runtime_ids))
            before = asyncio.run(_artifact_prior_head_project(isolated_database_env, project_id))
            runtime_before = asyncio.run(
                _artifact_prior_head_runtime_rows(isolated_database_env, runtime_ids)
            )
            command.upgrade(config, "0016_artifact_domain")
            after = asyncio.run(_artifact_prior_head_project(isolated_database_env, project_id))
            runtime_after = asyncio.run(
                _artifact_prior_head_runtime_rows(isolated_database_env, runtime_ids)
            )
            artifact_counts = asyncio.run(_artifact_table_counts(isolated_database_env))
        finally:
            command.downgrade(config, "base")

    assert after == before
    assert runtime_after == runtime_before
    assert artifact_counts == {name: 0 for name in artifact_counts}


def test_artifact_foundation_enforces_immutable_facts_and_guarded_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove PostgreSQL rejects malformed/mutable facts and non-empty downgrade."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    ids = {
        name: str(uuid4())
        for name in (
            "project",
            "content",
            "session",
            "item",
            "replica",
            "receipt",
            "binding",
            "binding_v2",
        )
    }
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0016_artifact_domain")
            asyncio.run(_assert_artifact_fact_guards(isolated_database_env, ids))
            with pytest.raises(RuntimeError, match="non-empty artifact foundation"):
                command.downgrade(config, "0015_post_submit_correction")
            asyncio.run(_truncate_artifact_foundation(isolated_database_env))
            command.downgrade(config, "0015_post_submit_correction")
            command.upgrade(config, "0016_artifact_domain")
            assert all(
                count == 0
                for count in asyncio.run(_artifact_table_counts(isolated_database_env)).values()
            )
        finally:
            command.downgrade(config, "base")


def test_artifact_store_v2_empty_clean_cut_and_reversible_shape(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Migrate only empty v1 tables and restore their empty shape on downgrade."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0023_service_actor_identity")
            command.upgrade(config, "0025_artifact_store_v2")
            v2_columns = asyncio.run(_fetch_columns(isolated_database_env))
            command.downgrade(config, "0023_service_actor_identity")
            v1_columns = asyncio.run(_fetch_columns(isolated_database_env))
            command.upgrade(config, "0025_artifact_store_v2")
        finally:
            command.downgrade(config, "base")

    assert {
        "artifact_storage_namespaces.namespace_fingerprint",
        "artifact_upload_items.provider_object_ref",
        "artifact_replicas.storage_namespace_id",
        "artifact_replicas.namespace_fingerprint",
        "artifact_replicas.provider_profile",
        "artifact_replicas.provider_object_ref",
        "artifact_operation_receipts.replayed",
    }.issubset(v2_columns)
    assert {
        "artifact_upload_items.provider_operation_reference",
        "artifact_replicas.provider_artifact_id",
        "artifact_replicas.provider_manifest_id",
        "artifact_replicas.retention_state",
        "artifact_operation_receipts.provider_receipt_id",
        "artifact_operation_receipts.retention_reference",
    }.issubset(v1_columns)
    assert {
        "artifact_upload_items.provider_object_ref",
        "artifact_replicas.storage_namespace_id",
        "artifact_replicas.namespace_fingerprint",
        "artifact_replicas.provider_profile",
        "artifact_replicas.provider_object_ref",
        "artifact_operation_receipts.provider_object_ref",
        "artifact_operation_receipts.replayed",
    }.isdisjoint(v1_columns)
    assert "artifact_storage_namespaces.id" not in v1_columns


def test_artifact_store_v2_refuses_populated_v1_before_ddl(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Never fabricate namespace or verification provenance for a v1 row."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0023_service_actor_identity")
            asyncio.run(_seed_artifact_content(isolated_database_env))
            with pytest.raises(
                RuntimeError,
                match="artifact storage clean cut requires empty pre-production tables",
            ):
                command.upgrade(config, "0025_artifact_store_v2")
            refused = asyncio.run(_artifact_v2_refusal_state(isolated_database_env))
            asyncio.run(_truncate_artifact_foundation(isolated_database_env))
            command.upgrade(config, "0025_artifact_store_v2")
        finally:
            command.downgrade(config, "base")

    assert refused == {
        "revision": "0023_service_actor_identity",
        "namespace_table_exists": False,
        "v1_content_count": 1,
    }


def test_artifact_store_v2_refuses_populated_v2_downgrade_before_ddl(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Never drop a namespace-only v2 deployment fence during downgrade."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0025_artifact_store_v2")
            asyncio.run(_seed_v2_artifact_namespace(isolated_database_env))
            with pytest.raises(
                RuntimeError,
                match="artifact storage clean cut requires empty pre-production tables",
            ):
                command.downgrade(config, "0023_service_actor_identity")
            refused_revision = asyncio.run(_current_revision(isolated_database_env))
            refused_columns = asyncio.run(_fetch_columns(isolated_database_env))
            refused_namespace_count = asyncio.run(
                _artifact_namespace_count(isolated_database_env)
            )
            asyncio.run(_truncate_v2_artifact_namespace(isolated_database_env))
            command.downgrade(config, "0023_service_actor_identity")
        finally:
            asyncio.run(_truncate_v2_artifact_namespace(isolated_database_env))
            command.downgrade(config, "base")

    assert refused_revision == "0025_artifact_store_v2"
    assert refused_namespace_count == 1
    assert "artifact_replicas.provider_object_ref" in refused_columns


def test_artifact_store_v2_waits_for_concurrent_v1_writer_and_refuses(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Serialize the clean-cut emptiness check against every v1 writer."""
    config = _alembic_config()
    inserted = threading.Event()
    release_insert = threading.Event()
    upgrade_started = threading.Event()

    def guarded_upgrade() -> None:
        upgrade_started.set()
        command.upgrade(config, "0025_artifact_store_v2")

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0023_service_actor_identity")
            with ThreadPoolExecutor(max_workers=2) as pool:
                insert_future = pool.submit(
                    asyncio.run,
                    _insert_v1_artifact_content_until_released(
                        isolated_database_env,
                        inserted,
                        release_insert,
                    ),
                )
                assert inserted.wait(timeout=5)
                upgrade_future = pool.submit(guarded_upgrade)
                assert upgrade_started.wait(timeout=5)
                time.sleep(0.2)
                assert upgrade_future.done() is False
                release_insert.set()
                insert_future.result(timeout=5)
                with pytest.raises(
                    RuntimeError,
                    match="artifact storage clean cut requires empty pre-production tables",
                ):
                    upgrade_future.result(timeout=5)

            refused = asyncio.run(_artifact_v2_refusal_state(isolated_database_env))
            asyncio.run(_truncate_artifact_foundation(isolated_database_env))
            command.upgrade(config, "0025_artifact_store_v2")
        finally:
            release_insert.set()
            asyncio.run(_truncate_artifact_foundation(isolated_database_env))
            command.downgrade(config, "base")

    assert refused == {
        "revision": "0023_service_actor_identity",
        "namespace_table_exists": False,
        "v1_content_count": 1,
    }


def test_actor_profile_lifecycle_fresh_and_prior_head_upgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Install 0026 from the exact prior head and preserve reversible shape."""
    config = _alembic_config()

    async def shape() -> tuple[str, bool, bool]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                return (
                    str(await connection.scalar(text("select version_num from alembic_version"))),
                    bool(
                        await connection.scalar(
                            text(
                                "select exists(select 1 from information_schema.columns "
                                "where table_name='actor_profiles' and column_name='reactivated_at')"
                            )
                        )
                    ),
                    bool(
                        await connection.scalar(
                            text(
                                "select exists(select 1 from pg_constraint where "
                                "conname='ck_actor_identity_links_reactivation_fields')"
                            )
                        )
                    ),
                )
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0025_artifact_store_v2")
            assert asyncio.run(shape()) == ("0025_artifact_store_v2", False, False)
            command.upgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(shape()) == ("0026_actor_profile_lifecycle", True, True)
            command.downgrade(config, "0025_artifact_store_v2")
            assert asyncio.run(shape()) == ("0025_artifact_store_v2", False, False)
            command.upgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(shape()) == ("0026_actor_profile_lifecycle", True, True)
        finally:
            command.downgrade(config, "base")


def test_actor_profile_lifecycle_constraint_and_trigger_parity(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Enforce normalized attribution and only legal profile lifecycle transitions."""
    config = _alembic_config()
    actor_id = str(uuid4())

    async def prove_guards() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await _insert_canonical_actor(connection, actor_id, "lifecycle-parity", "human")
                await connection.execute(
                    text(
                        "update actor_profiles set status='suspended',suspended_by=:actor,"
                        "suspended_at=clock_timestamp(),suspension_reason='investigate' where id=:actor"
                    ),
                    {"actor": actor_id},
                )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update actor_profiles set status='active',suspended_by=null,"
                            "suspended_at=null,suspension_reason=null where id=:actor"
                        ),
                        {"actor": actor_id},
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update actor_profiles set status='active',suspended_by=null,"
                        "suspended_at=null,suspension_reason=null,reactivated_by=:actor,"
                        "reactivated_at=clock_timestamp(),reactivation_reason='restored' where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(
                    text(
                        "update actor_profiles set status='suspended',suspended_by=:actor,"
                        "suspended_at=clock_timestamp(),suspension_reason='second review' "
                        "where id=:actor"
                    ),
                    {"actor": actor_id},
                )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update actor_profiles set status='active',suspended_by=null,"
                            "suspended_at=null,suspension_reason=null where id=:actor"
                        ),
                        {"actor": actor_id},
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update actor_profiles set status='active',suspended_by=null,"
                        "suspended_at=null,suspension_reason=null,reactivated_by=:actor,"
                        "reactivated_at=clock_timestamp(),reactivation_reason='restored again' "
                        "where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(
                    text(
                        "update actor_identity_links set status='revoked',revoked_by=:actor,"
                        "revoked_at=clock_timestamp(),revoked_reason='link review' "
                        "where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update actor_identity_links set status='active',revoked_by=null,"
                            "revoked_at=null,revoked_reason=null where actor_profile_id=:actor"
                        ),
                        {"actor": actor_id},
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update actor_identity_links set status='active',revoked_by=null,"
                        "revoked_at=null,revoked_reason=null,reactivated_by=:actor,"
                        "reactivated_at=clock_timestamp(),reactivation_reason='link restored' "
                        "where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(
                    text(
                        "update actor_identity_links set status='revoked',revoked_by=:actor,"
                        "revoked_at=clock_timestamp(),revoked_reason='second link review' "
                        "where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update actor_identity_links set status='active',revoked_by=null,"
                            "revoked_at=null,revoked_reason=null where actor_profile_id=:actor"
                        ),
                        {"actor": actor_id},
                    )
            invalid = (
                "update actor_profiles set reactivation_reason='rewritten' where id=:actor",
                "update actor_profiles set status='suspended',suspended_by=:actor,"
                "suspended_at=clock_timestamp(),suspension_reason=' padded ' where id=:actor",
                "update actor_identity_links set reactivation_reason='rewritten' "
                "where actor_profile_id=:actor",
            )
            for statement in invalid:
                with pytest.raises(DBAPIError):
                    async with engine.begin() as connection:
                        await connection.execute(text(statement), {"actor": actor_id})
            invalid_reason_updates = (
                (
                    "actor_profiles",
                    "update actor_profiles set status='suspended',suspended_by=:actor,"
                    "suspended_at=clock_timestamp(),suspension_reason=chr(9)||'hold' "
                    "where id=:actor",
                ),
                (
                    "actor_profiles",
                    "update actor_profiles set reactivation_reason='restored'||chr(10) "
                    "where id=:actor",
                ),
                (
                    "actor_profiles",
                    "update actor_profiles set status='deactivated',deactivated_by=:actor,"
                    "deactivated_at=clock_timestamp(),deactivation_reason=chr(13)||'terminal' "
                    "where id=:actor",
                ),
                (
                    "actor_identity_links",
                    "update actor_identity_links set revoked_reason=chr(12)||'link review' "
                    "where actor_profile_id=:actor",
                ),
                (
                    "actor_identity_links",
                    "update actor_identity_links set reactivation_reason='link restored'||chr(11) "
                    "where actor_profile_id=:actor",
                ),
            )
            for table, statement in invalid_reason_updates:
                with pytest.raises(DBAPIError):
                    async with engine.begin() as connection:
                        await connection.execute(text(f"alter table {table} disable trigger user"))
                        await connection.execute(text(statement), {"actor": actor_id})
            python_strip_code_points = (
                9,
                10,
                11,
                12,
                13,
                28,
                29,
                30,
                31,
                32,
                133,
                160,
                5760,
                8192,
                8193,
                8194,
                8195,
                8196,
                8197,
                8198,
                8199,
                8200,
                8201,
                8202,
                8232,
                8233,
                8239,
                8287,
                12288,
            )
            assert python_strip_code_points == tuple(
                code_point
                for code_point in range(0x110000)
                if chr(code_point).isspace()
            )
            for code_point in python_strip_code_points:
                with pytest.raises(DBAPIError):
                    async with engine.begin() as connection:
                        await connection.execute(
                            text("alter table actor_profiles disable trigger user")
                        )
                        await connection.execute(
                            text(
                                "update actor_profiles set status='suspended',"
                                "suspended_by=:actor,suspended_at=clock_timestamp(),"
                                "suspension_reason=chr(:code_point)||'hold' where id=:actor"
                            ),
                            {"actor": actor_id, "code_point": code_point},
                        )
            async with engine.begin() as connection:
                await connection.execute(text("alter table actor_profiles disable trigger user"))
                await connection.execute(
                    text(
                        "update actor_profiles set reactivated_by=null,reactivated_at=null,"
                        "reactivation_reason=null where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(text("alter table actor_profiles enable trigger user"))
                await connection.execute(
                    text("alter table actor_identity_links disable trigger user")
                )
                await connection.execute(
                    text(
                        "update actor_identity_links set status='active',revoked_by=null,"
                        "revoked_at=null,revoked_reason=null,reactivated_by=null,"
                        "reactivated_at=null,reactivation_reason=null "
                        "where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(
                    text("alter table actor_identity_links enable trigger user")
                )
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(prove_guards())
        finally:
            command.downgrade(config, "base")


def test_actor_profile_lifecycle_upgrade_refuses_dirty_rows(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Refuse partial provenance and non-normalized reasons before 0026 DDL."""
    config = _alembic_config()
    cases = (
        (
            str(uuid4()),
            "partial-link-reactivation",
            "update actor_identity_links set reactivated_by=:actor "
            "where actor_profile_id=:actor",
            "update actor_identity_links set reactivated_by=null "
            "where actor_profile_id=:actor",
        ),
        (
            str(uuid4()),
            "padded-profile-suspension",
            "update actor_profiles set status='suspended',suspended_by=:actor,"
            "suspended_at=clock_timestamp(),suspension_reason=' padded ' where id=:actor",
            "update actor_profiles set suspension_reason='valid suspension' where id=:actor",
        ),
        (
            str(uuid4()),
            "tab-padded-profile-suspension",
            "update actor_profiles set status='suspended',suspended_by=:actor,"
            "suspended_at=clock_timestamp(),suspension_reason=chr(9)||'padded' "
            "where id=:actor",
            "update actor_profiles set suspension_reason='valid suspension' where id=:actor",
        ),
        (
            str(uuid4()),
            "multibyte-profile-deactivation",
            "update actor_profiles set status='deactivated',deactivated_by=:actor,"
            "deactivated_at=clock_timestamp(),deactivation_reason=repeat(chr(233),251) "
            "where id=:actor",
            "update actor_profiles set deactivation_reason='valid deactivation' where id=:actor",
        ),
        (
            str(uuid4()),
            "nbsp-profile-deactivation",
            "update actor_profiles set status='deactivated',deactivated_by=:actor,"
            "deactivated_at=clock_timestamp(),deactivation_reason=chr(160)||'padded' "
            "where id=:actor",
            "update actor_profiles set deactivation_reason='valid deactivation' where id=:actor",
        ),
        (
            str(uuid4()),
            "padded-link-revocation",
            "update actor_identity_links set status='revoked',revoked_by=:actor,"
            "revoked_at=clock_timestamp(),revoked_reason=' padded ' "
            "where actor_profile_id=:actor",
            "update actor_identity_links set revoked_reason='valid revocation' "
            "where actor_profile_id=:actor",
        ),
        (
            str(uuid4()),
            "newline-padded-link-revocation",
            "update actor_identity_links set status='revoked',revoked_by=:actor,"
            "revoked_at=clock_timestamp(),revoked_reason='padded'||chr(10) "
            "where actor_profile_id=:actor",
            "update actor_identity_links set revoked_reason='valid revocation' "
            "where actor_profile_id=:actor",
        ),
        (
            str(uuid4()),
            "multibyte-link-reactivation",
            "update actor_identity_links set reactivated_by=:actor,"
            "reactivated_at=clock_timestamp(),reactivation_reason=repeat(chr(233),251) "
            "where actor_profile_id=:actor",
            "update actor_identity_links set reactivation_reason='valid reactivation' "
            "where actor_profile_id=:actor",
        ),
    )

    async def seed_actors() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                for actor_id, subject, _, _ in cases:
                    await _insert_canonical_actor(connection, actor_id, subject, "human")
        finally:
            await engine.dispose()

    async def execute(statement: str, actor_id: str) -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(statement), {"actor": actor_id})
        finally:
            await engine.dispose()

    async def prior_head_state(actor_id: str) -> tuple[object, ...]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                columns = await connection.execute(
                    text(
                        "select exists(select 1 from information_schema.columns "
                        "where table_schema='public' and table_name='actor_profiles' "
                        "and column_name='reactivated_by')"
                    )
                )
                profile = await connection.execute(
                    text(
                        "select status,suspension_reason,deactivation_reason "
                        "from actor_profiles where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                link = await connection.execute(
                    text(
                        "select status,revoked_reason,reactivated_by,reactivation_reason "
                        "from actor_identity_links where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
                audit_count = await connection.scalar(text("select count(*) from audit_events"))
                return (
                    columns.scalar_one(),
                    tuple(profile.one()),
                    tuple(link.one()),
                    audit_count,
                )
        finally:
            await engine.dispose()

    async def restore_active_fixtures() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("alter table actor_profiles disable trigger user"))
                await connection.execute(
                    text(
                        "update actor_profiles set status='active',suspended_by=null,"
                        "suspended_at=null,suspension_reason=null,deactivated_by=null,"
                        "deactivated_at=null,deactivation_reason=null,reactivated_by=null,"
                        "reactivated_at=null,reactivation_reason=null where id=any(:actors)"
                    ),
                    {"actors": [case[0] for case in cases]},
                )
                await connection.execute(text("alter table actor_profiles enable trigger user"))
                await connection.execute(
                    text("alter table actor_identity_links disable trigger user")
                )
                await connection.execute(
                    text(
                        "update actor_identity_links set status='active',revoked_by=null,"
                        "revoked_at=null,revoked_reason=null,reactivated_by=null,"
                        "reactivated_at=null,reactivation_reason=null "
                        "where actor_profile_id=any(:actors)"
                    ),
                    {"actors": [case[0] for case in cases]},
                )
                await connection.execute(
                    text("alter table actor_identity_links enable trigger user")
                )
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0025_artifact_store_v2")
            asyncio.run(seed_actors())
            for actor_id, _, dirty_statement, clean_statement in cases:
                asyncio.run(execute(dirty_statement, actor_id))
                before = asyncio.run(prior_head_state(actor_id))
                with pytest.raises(RuntimeError, match="dirty actor lifecycle rows"):
                    command.upgrade(config, "head")
                assert asyncio.run(_current_revision(isolated_database_env)) == (
                    "0025_artifact_store_v2"
                )
                assert asyncio.run(prior_head_state(actor_id)) == before
                asyncio.run(execute(clean_statement, actor_id))
            command.upgrade(config, "head")
            asyncio.run(restore_active_fixtures())
        finally:
            command.downgrade(config, "base")


def test_actor_profile_lifecycle_safe_downgrade_and_reupgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Restore the exact prior schema when no forward evidence exists."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0026_actor_profile_lifecycle")
            command.downgrade(config, "0025_artifact_store_v2")
            assert asyncio.run(_current_revision(isolated_database_env)) == "0025_artifact_store_v2"
            command.upgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(_current_revision(isolated_database_env)) == "0026_actor_profile_lifecycle"
        finally:
            command.downgrade(config, "base")


def test_actor_profile_lifecycle_downgrade_refuses_forward_evidence(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Keep the full head intact for every lifecycle-evidence branch."""
    config = _alembic_config()
    actor_id = str(uuid4())

    async def seed_actor() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await _insert_canonical_actor(connection, actor_id, "forward-lifecycle", "human")
        finally:
            await engine.dispose()

    async def write_profile_reactivation(*, clear: bool = False) -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                if clear:
                    await connection.execute(text("alter table actor_profiles disable trigger user"))
                    await connection.execute(
                        text(
                            "update actor_profiles set reactivated_by=null,reactivated_at=null,"
                            "reactivation_reason=null where id=:actor"
                        ),
                        {"actor": actor_id},
                    )
                    await connection.execute(text("alter table actor_profiles enable trigger user"))
                    return
                await connection.execute(
                    text(
                        "update actor_profiles set status='suspended',suspended_by=:actor,"
                        "suspended_at=clock_timestamp(),suspension_reason='hold' where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(
                    text(
                        "update actor_profiles set status='active',suspended_by=null,"
                        "suspended_at=null,suspension_reason=null,reactivated_by=:actor,"
                        "reactivated_at=clock_timestamp(),reactivation_reason='restored' where id=:actor"
                    ),
                    {"actor": actor_id},
                )
        finally:
            await engine.dispose()

    async def insert_audit_blocker(blocker: str) -> str:
        engine = create_async_engine(isolated_database_env)
        event_id = str(uuid4())
        try:
            async with engine.begin() as connection:
                link_id = await connection.scalar(
                    text(
                        "select id from actor_identity_links where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
                if blocker in {"ActorProfileReactivated", "ActorIdentityLinkReactivated"}:
                    is_profile = blocker == "ActorProfileReactivated"
                    resource_type = "actor_profile" if is_profile else "actor_identity_link"
                    resource_id = actor_id if is_profile else link_id
                    permission_id = (
                        "actor.profile.reactivate"
                        if is_profile
                        else "actor.identity_link.reactivate"
                    )
                    reason = "administrative_correction" if is_profile else "identity_lifecycle_change"
                    before_facts = '{"status":"suspended"}' if is_profile else '{"status":"revoked"}'
                    await connection.execute(
                        text(
                            "alter table audit_events disable trigger "
                            "audit_events_validate_idempotency"
                        )
                    )
                    await connection.execute(
                        text(
                            "insert into audit_events "
                            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,"
                            "claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                            "event_version,actor_ref_kind,request_id,correlation_id,"
                            "target_actor_ref_kind,target_actor_ref,permission_id,"
                            "resource_type,resource_id,target_ref_kind,target_ref_id,reason,"
                            "before_facts,after_facts) values "
                            "(:id,:resource_type,:resource_id,:event_type,:actor,'[]'::json,"
                            "'{}'::json,'local_authority',false,'{}'::json,'authority',1,"
                            "'actor_profile',:request_id,:correlation_id,'actor_profile',:actor,"
                            ":permission_id,:resource_type,:resource_id,"
                            ":resource_type,:resource_id,:reason,cast(:before_facts as json),"
                            "'{\"status\":\"active\"}'::json)"
                        ),
                        {
                            "id": event_id,
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            "event_type": blocker,
                            "actor": actor_id,
                            "request_id": str(uuid4()),
                            "correlation_id": str(uuid4()),
                            "permission_id": permission_id,
                            "reason": reason,
                            "before_facts": before_facts,
                        },
                    )
                    await connection.execute(
                        text(
                            "alter table audit_events enable trigger "
                            "audit_events_validate_idempotency"
                        )
                    )
                else:
                    await connection.execute(
                        text(
                            "insert into audit_events "
                            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,"
                            "claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                            "event_version,actor_ref_kind,request_id,correlation_id,"
                            "target_actor_ref_kind,target_actor_ref,permission_id,action_id,"
                            "resource_type,resource_id,target_ref_kind,target_ref_id,reason,"
                            "denial_code,after_facts) values "
                            "(:id,'authorization_decision',:id,'SensitiveAuthorizationDenied',"
                            ":actor,'[]'::json,'{}'::json,'local_authority',false,'{}'::json,"
                            "'authority',1,'actor_profile',:request_id,:correlation_id,"
                            "'actor_profile',:actor,'actor.identity_link.revoke',"
                            "'actor.identity_link.revoke','actor_identity_link',:link_id,"
                            "'actor_identity_link',:link_id,'authorization_evaluation',"
                            ":denial_code,cast(:after_facts as json))"
                        ),
                        {
                            "id": event_id,
                            "actor": actor_id,
                            "request_id": str(uuid4()),
                            "correlation_id": str(uuid4()),
                            "link_id": link_id,
                            "denial_code": blocker,
                            "after_facts": '{"allowed": false}',
                        },
                    )
            return event_id
        finally:
            await engine.dispose()

    async def remove_audit_blocker(event_id: str) -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger "
                        "audit_events_reject_update_delete"
                    )
                )
                await connection.execute(
                    text("delete from audit_events where id=:id"), {"id": event_id}
                )
                await connection.execute(
                    text(
                        "alter table audit_events enable trigger "
                        "audit_events_reject_update_delete"
                    )
                )
        finally:
            await engine.dispose()

    async def forward_state() -> tuple[object, ...]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                profile = await connection.execute(
                    text(
                        "select reactivated_by,reactivated_at,reactivation_reason "
                        "from actor_profiles where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                events = await connection.execute(
                    text(
                        "select id,event_type,denial_code from audit_events "
                        "where event_domain='authority' order by id"
                    )
                )
                column_exists = await connection.scalar(
                    text(
                        "select exists(select 1 from information_schema.columns "
                        "where table_schema='public' and table_name='actor_profiles' "
                        "and column_name='reactivated_by')"
                    )
                )
                return column_exists, tuple(profile.one()), tuple(events.all())
        finally:
            await engine.dispose()

    def refuse_downgrade_without_change() -> None:
        before = asyncio.run(forward_state())
        with pytest.raises(RuntimeError, match="cannot downgrade actor lifecycle evidence"):
            command.downgrade(config, "0025_artifact_store_v2")
        assert asyncio.run(_current_revision(isolated_database_env)) == (
            "0026_actor_profile_lifecycle"
        )
        assert asyncio.run(forward_state()) == before

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0026_actor_profile_lifecycle")
            asyncio.run(seed_actor())
            asyncio.run(write_profile_reactivation())
            refuse_downgrade_without_change()
            asyncio.run(write_profile_reactivation(clear=True))
            for blocker in (
                "ActorProfileReactivated",
                "ActorIdentityLinkReactivated",
                "identity_link_already_revoked",
                "identity_link_not_revoked",
            ):
                event_id = asyncio.run(insert_audit_blocker(blocker))
                refuse_downgrade_without_change()
                asyncio.run(remove_audit_blocker(event_id))
            command.downgrade(config, "0025_artifact_store_v2")
        finally:
            command.downgrade(config, "base")


def test_contributor_foundation_upgrade_guards_and_reversible_preservation(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Preserve valid attribution and enforce canonical-human lineage in PostgreSQL."""
    config = _alembic_config()
    human_id = str(uuid4())

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0026_actor_profile_lifecycle")
            fixture = asyncio.run(
                _seed_contributor_prior_head(
                    isolated_database_env,
                    assignment_values=(human_id,),
                    submission_values=(human_id,),
                    human_ids=(human_id,),
                )
            )
            before = asyncio.run(_contributor_foundation_shape(isolated_database_env))
            assert before["revision"] == "0026_actor_profile_lifecycle"
            assert before["assignment_column"] == ("worker_id", 100)
            assert before["submission_column"] == ("worker_id", 100)

            command.upgrade(config, "0027_contributor_foundation")
            upgraded = asyncio.run(_contributor_foundation_shape(isolated_database_env))
            assert upgraded == {
                "revision": "0027_contributor_foundation",
                "assignment_column": ("contributor_id", 36),
                "submission_column": ("contributor_id", 36),
                "assignment_index": "ix_task_assignments_contributor_id",
                "submission_index": "ix_submissions_contributor_id",
                "foreign_keys": (
                    "fk_submissions_contributor_id_actor_profiles",
                    "fk_task_assignments_contributor_id_actor_profiles",
                ),
                "function": True,
                "triggers": (
                    "submissions_contributor_human",
                    "task_assignments_contributor_human",
                ),
                "assignment_values": (human_id,),
                "submission_values": (human_id,),
            }
            direct_sql = asyncio.run(
                _exercise_contributor_lineage_guards(
                    isolated_database_env,
                    fixture=fixture,
                    human_id=human_id,
                )
            )
            assert direct_sql == {
                "missing_assignment": "23503",
                "service_assignment": "23514",
                "missing_assignment_update": "23503",
                "service_assignment_update": "23514",
                "missing_submission": "23503",
                "service_submission": "23514",
                "missing_submission_update": "23503",
                "service_submission_update": "23514",
                "suspended_human_inserted": True,
                "deactivated_human_inserted": True,
                "unrelated_update_preserved": True,
            }
            assert asyncio.run(
                _exercise_contributor_lineage_function_contract(
                    isolated_database_env
                )
            ) == {
                "zero_arguments": "55000",
                "extra_arguments": "55000",
                "absent_field": "55000",
                "nullable_field_accepted": True,
            }

            asyncio.run(_add_contributor_function_dependency(isolated_database_env))
            intact = asyncio.run(_contributor_foundation_shape(isolated_database_env))
            with pytest.raises(RuntimeError, match='"total":1'):
                command.downgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(_contributor_foundation_shape(isolated_database_env)) == intact
            asyncio.run(_drop_contributor_function_dependency(isolated_database_env))

            command.downgrade(config, "0026_actor_profile_lifecycle")
            restored = asyncio.run(_contributor_foundation_shape(isolated_database_env))
            assert restored["revision"] == "0026_actor_profile_lifecycle"
            assert restored["assignment_column"] == ("worker_id", 100)
            assert restored["submission_column"] == ("worker_id", 100)
            assert restored["assignment_index"] == "ix_task_assignments_worker_id"
            assert restored["submission_index"] == "ix_submissions_worker_id"
            assert human_id in restored["assignment_values"]
            assert restored["submission_values"] == (human_id,)

            command.upgrade(config, "0027_contributor_foundation")
            assert asyncio.run(_current_revision(isolated_database_env)) == (
                "0027_contributor_foundation"
            )
        finally:
            command.downgrade(config, "0023_service_actor_identity")
            asyncio.run(_clear_contributor_migration_fixtures(isolated_database_env))
            command.downgrade(config, "base")


def test_contributor_foundation_preflight_refuses_all_unsafe_classes_atomically(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Classify both source tables without guessing or partially changing schema."""
    config = _alembic_config()
    missing_ids = (str(uuid4()), str(uuid4()))
    assignment_malformed = tuple(
        f"private.person.{index}@example.test" for index in range(22)
    )
    submission_malformed = tuple(
        f"eyJhbGciOiJSUzI1NiJ9.secret-token-material-{index}"
        for index in range(22)
    )

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0026_actor_profile_lifecycle")
            fixture = asyncio.run(
                _seed_contributor_prior_head(
                    isolated_database_env,
                    assignment_values=assignment_malformed
                    + (missing_ids[0], "service"),
                    submission_values=submission_malformed
                    + (missing_ids[1], "service"),
                )
            )
            service_id = str(fixture["service_id"])
            before = asyncio.run(_contributor_foundation_shape(isolated_database_env))

            with pytest.raises(RuntimeError, match="contributor foundation preflight") as failure:
                command.upgrade(config, "0027_contributor_foundation")

            message = str(failure.value)
            assert "malformed" in message
            assert "missing" in message
            assert "service" in message
            assert service_id in message
            assert all(missing_id in message for missing_id in missing_ids)
            diagnostic = json.loads(message.split("preflight failed: ", 1)[1])
            for table in ("task_assignments", "submissions"):
                malformed = diagnostic[table]["malformed"]
                assert malformed["total"] == 22
                assert len(malformed["rows"]) == 20
                assert [row[0] for row in malformed["rows"]] == sorted(
                    row[0] for row in malformed["rows"]
                )
                assert all(
                    row[1] == "<redacted-malformed>"
                    for row in malformed["rows"]
                )
            assert all(
                value not in message
                for value in assignment_malformed + submission_malformed
            )
            assert all(
                row_id in message
                for row_id in (
                    tuple(fixture["assignment_ids"])[-2:]
                    + tuple(fixture["submission_ids"])[-2:]
                )
            )
            assert "issuer" not in message
            assert "subject" not in message
            assert asyncio.run(_contributor_foundation_shape(isolated_database_env)) == before
        finally:
            command.downgrade(config, "0023_service_actor_identity")
            asyncio.run(_clear_contributor_migration_fixtures(isolated_database_env))
            command.downgrade(config, "base")


def test_api_rate_control_schema_preserves_domain_and_guards_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0017 schema guards, preservation, and transactional downgrade refusal."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    project_id = str(uuid4())
    artifact_id = str(uuid4())
    digest = bytes(range(32))

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0015_post_submit_correction")
            asyncio.run(_seed_artifact_prior_head(isolated_database_env, project_id))
            command.upgrade(config, "0016_artifact_domain")
            before = asyncio.run(_artifact_prior_head_project(isolated_database_env, project_id))
            artifact_before = asyncio.run(
                _seed_and_fetch_0016_artifact(isolated_database_env, artifact_id)
            )

            command.upgrade(config, "0017_api_controls")
            after = asyncio.run(_artifact_prior_head_project(isolated_database_env, project_id))
            artifact_after = asyncio.run(_fetch_0016_artifact(isolated_database_env, artifact_id))
            schema = asyncio.run(_api_rate_control_schema(isolated_database_env))
            asyncio.run(_assert_api_rate_control_guards(isolated_database_env, digest))

            with pytest.raises(RuntimeError, match="non-empty API rate controls"):
                command.downgrade(config, "0016_artifact_domain")

            asyncio.run(_clear_api_rate_controls(isolated_database_env))
            inserted = threading.Event()
            release_insert = threading.Event()
            downgrade_started = threading.Event()

            def guarded_downgrade() -> None:
                downgrade_started.set()
                command.downgrade(config, "0016_artifact_domain")

            with ThreadPoolExecutor(max_workers=2) as pool:
                insert_future = pool.submit(
                    asyncio.run,
                    _insert_rate_control_until_released(
                        isolated_database_env,
                        digest,
                        inserted,
                        release_insert,
                    ),
                )
                assert inserted.wait(timeout=5)
                downgrade_future = pool.submit(guarded_downgrade)
                assert downgrade_started.wait(timeout=5)
                time.sleep(0.2)
                assert downgrade_future.done() is False
                release_insert.set()
                insert_future.result(timeout=5)
                with pytest.raises(RuntimeError, match="non-empty API rate controls"):
                    downgrade_future.result(timeout=5)

            refused_state = asyncio.run(_api_rate_control_state(isolated_database_env))
            asyncio.run(_clear_api_rate_controls(isolated_database_env))
            command.downgrade(config, "0016_artifact_domain")
            downgraded_state = asyncio.run(_api_rate_control_state(isolated_database_env))
            command.upgrade(config, "0017_api_controls")
        finally:
            asyncio.run(_clear_api_rate_controls(isolated_database_env))
            asyncio.run(_truncate_artifact_foundation(isolated_database_env))
            command.downgrade(config, "base")
            command.upgrade(config, "head")

    assert after == before
    assert artifact_after == artifact_before
    assert schema == {
        "columns": {
            "control_scope:character varying:NO",
            "key_digest:bytea:NO",
            "window_started_at:timestamp with time zone:NO",
            "window_expires_at:timestamp with time zone:NO",
            "request_count:bigint:NO",
            "updated_at:timestamp with time zone:NO",
        },
        "constraints": {
            "pk_api_rate_control_counters",
            "ck_api_rate_control_counters_scope_token",
            "ck_api_rate_control_counters_digest_length",
            "ck_api_rate_control_counters_request_count",
            "ck_api_rate_control_counters_window_order",
        },
        "indexes": {
            "pk_api_rate_control_counters",
            "ix_api_rate_control_counters_window_expires_at",
        },
    }
    assert refused_state == {
        "revision": "0017_api_controls",
        "table_exists": True,
        "row_count": 1,
    }
    assert downgraded_state == {
        "revision": "0016_artifact_domain",
        "table_exists": False,
        "row_count": None,
    }


def test_authority_audit_schema_preserves_legacy_and_guards_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0018 preserves legacy evidence and refuses destructive downgrade."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    legacy_id = str(uuid4())
    authority_id = str(uuid4())

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0017_api_controls")
            before = asyncio.run(_seed_and_fetch_legacy_audit(isolated_database_env, legacy_id))

            command.upgrade(config, "0018_authority_audit_evidence")
            after = asyncio.run(_fetch_audit_row(isolated_database_env, legacy_id))
            schema = asyncio.run(_authority_audit_schema(isolated_database_env))
            occurred_at = asyncio.run(
                _insert_authority_audit_fixture(isolated_database_env, authority_id)
            )

            with pytest.raises(RuntimeError, match="non-empty authority audit"):
                command.downgrade(config, "0017_api_controls")
            refused = asyncio.run(_authority_audit_state(isolated_database_env))

            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, authority_id))
            command.downgrade(config, "0017_api_controls")
            downgraded = asyncio.run(_fetch_audit_row(isolated_database_env, legacy_id))
            command.upgrade(config, "0018_authority_audit_evidence")
            restored_schema = asyncio.run(_authority_audit_schema(isolated_database_env))
        finally:
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, authority_id))
            command.downgrade(config, "base")
            command.upgrade(config, "head")

    assert after == {**before, "event_domain": "legacy_lifecycle"}
    assert downgraded == before
    assert occurred_at.year >= 2026
    assert refused == {
        "revision": "0018_authority_audit_evidence",
        "authority_rows": 1,
    }
    assert schema == restored_schema
    assert schema == {
        "columns": {
            "actor_ref_kind:varchar:YES",
            "after_facts:json:YES",
            "before_facts:json:YES",
            "correlation_id:uuid:YES",
            "denial_code:varchar:YES",
            "event_domain:varchar:NO",
            "event_version:int4:YES",
            "idempotency_reference:uuid:YES",
            "invalidation_cause_event_id:varchar:YES",
            "invalidation_target_kind:varchar:YES",
            "invalidation_target_ref:varchar:YES",
            "matched_grant_id:varchar:YES",
            "occurred_at:timestamptz:YES",
            "permission_id:varchar:YES",
            "project_id:varchar:YES",
            "request_id:uuid:YES",
            "resource_id:varchar:YES",
            "resource_type:varchar:YES",
            "target_actor_ref:varchar:YES",
            "target_actor_ref_kind:varchar:YES",
            "target_ref_id:varchar:YES",
            "target_ref_kind:varchar:YES",
        },
        "constraints": {
            "ck_audit_events_authority_privacy_bounds",
            "ck_audit_events_authority_registries",
            "ck_audit_events_authority_tokens",
            "ck_audit_events_domain_shape",
            "ck_audit_events_fact_bounds",
            "ck_audit_events_foundation_shapes",
            "ck_audit_events_reference_pairs",
            "fk_audit_events_invalidation_cause",
        },
        "indexes": {
            "ix_audit_events_actor_ref",
            "ix_audit_events_correlation_id",
            "ix_audit_events_occurred_at",
            "ix_audit_events_project_id",
            "ix_audit_events_request_id",
        },
        "triggers": {
            "audit_events_reject_truncate",
            "audit_events_reject_update_delete",
            "audit_events_set_authority_time",
        },
        "functions": {
            "authority_facts_are_safe",
            "authority_grant_facts_are_safe",
            "authority_event_facts_are_safe",
            "reject_audit_event_mutation",
            "set_authority_audit_database_time",
        },
        "legacy_default": True,
        "external_identity_nullable": True,
    }


def test_authority_idempotency_schema_preserves_audit_and_guards_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0019 state, linkage, forward compatibility, and downgrade custody."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    orphan_event, orphan_ref = str(uuid4()), str(uuid4())
    record_id, actor_id, target_id = str(uuid4()), str(uuid4()), str(uuid4())

    with migration_lock():
        try:
            command.downgrade(config, "0018_authority_audit_evidence")
            asyncio.run(
                _insert_pre_0019_forward_reference(isolated_database_env, orphan_event, orphan_ref)
            )
            command.upgrade(config, "0019_authority_idempotency")
            schema = asyncio.run(_authority_idempotency_schema(isolated_database_env))
            invalid = asyncio.run(_authority_idempotency_invalid_writes(isolated_database_env))
            asyncio.run(
                _insert_committed_authority_idempotency(
                    isolated_database_env, record_id, actor_id, target_id
                )
            )
            immutable = asyncio.run(
                _authority_idempotency_immutable_writes(isolated_database_env, record_id)
            )
            with pytest.raises(RuntimeError, match="non-empty authority idempotency"):
                command.downgrade(config, "0018_authority_audit_evidence")
            refused = asyncio.run(_authority_idempotency_state(isolated_database_env, orphan_event))
            asyncio.run(
                _remove_authority_idempotency_fixture(
                    isolated_database_env, record_id, orphan_event=None
                )
            )
            downgrade_lock_observed = _authority_downgrade_waits_for_writer(
                config, isolated_database_env
            )
            preserved = asyncio.run(
                _authority_idempotency_state(isolated_database_env, orphan_event)
            )
            command.upgrade(config, "0019_authority_idempotency")
            restored = asyncio.run(_authority_idempotency_schema(isolated_database_env))
        finally:
            command.upgrade(config, "head")
            asyncio.run(
                _remove_authority_idempotency_fixture(
                    isolated_database_env, record_id, orphan_event=orphan_event
                )
            )

    assert schema == restored
    assert schema == {
        "columns": {
            "actor_ref:varchar:NO",
            "actor_ref_kind:varchar:NO",
            "committed_at:timestamptz:YES",
            "created_at:timestamptz:NO",
            "id:uuid:NO",
            "idempotency_key:uuid:NO",
            "operation:varchar:NO",
            "request_digest:varchar:NO",
            "response_http_status:int2:YES",
            "response_resource_id:uuid:YES",
            "response_resource_type:varchar:YES",
            "response_resource_version:int8:YES",
            "status:varchar:NO",
        },
        "constraints": {
            "authority_idempotency_pending_guard",
            "ck_authority_idempotency_records_actor_kind",
            "ck_authority_idempotency_records_actor_reference",
            "ck_authority_idempotency_records_operation",
            "ck_authority_idempotency_records_request_digest",
            "ck_authority_idempotency_records_response_status",
            "ck_authority_idempotency_records_response_type",
            "ck_authority_idempotency_records_response_version",
            "ck_authority_idempotency_records_state_shape",
            "ck_authority_idempotency_records_status",
            "pk_authority_idempotency_records",
            "uq_authority_idempotency_records_actor_reference",
            "uq_authority_idempotency_records_replay_namespace",
        },
        "triggers": {
            "authority_idempotency_guard",
            "authority_idempotency_pending_guard",
            "authority_idempotency_reject_truncate",
        },
        "audit_fk_validated": False,
        "audit_trigger": True,
    }
    assert invalid == {"initial_committed": True, "pending_commit": True, "new_orphan": True}
    assert immutable == {
        "update": True,
        "delete": True,
        "truncate": True,
        "database_timestamps": True,
    }
    assert downgrade_lock_observed is True
    assert refused == {"revision": "0019_authority_idempotency", "records": 1, "orphan": 1}
    assert preserved == {"revision": "0018_authority_audit_evidence", "records": None, "orphan": 1}


async def _outbox_schema(database_url: str) -> dict[str, object]:
    """Return the exact shared-outbox migration surface."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_rows = (
                await connection.execute(
                    text(
                        "select column_name, is_nullable from information_schema.columns "
                        "where table_schema='public' and table_name='outbox_events'"
                    )
                )
            ).all()
            indexes = set(
                (
                    await connection.scalars(
                        text(
                            "select indexname from pg_indexes "
                            "where schemaname='public' and tablename='outbox_events'"
                        )
                    )
                ).all()
            )
            triggers = set(
                (
                    await connection.scalars(
                        text(
                            "select tgname from pg_trigger "
                            "where tgrelid='outbox_events'::regclass and not tgisinternal"
                        )
                    )
                ).all()
            )
            return {
                "revision": str(
                    await connection.scalar(text("select version_num from alembic_version"))
                ),
                "columns": {row.column_name for row in column_rows},
                "nullable": {
                    row.column_name for row in column_rows if row.is_nullable == "YES"
                },
                "indexes": indexes,
                "triggers": triggers,
            }
    finally:
        await engine.dispose()


async def _outbox_downgrade_writer_race(
    database_url: str,
    config: Config,
    *,
    project_id: str,
    commit_writer: bool,
) -> str:
    """Hold one append open while downgrade waits, then commit or roll it back."""
    engine = create_async_engine(database_url)
    event_id = str(uuid4())
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(
                text(
                    "insert into projects(id,name,slug,status) "
                    "values (:id,'Outbox migration',:slug,'active')"
                ),
                {"id": project_id, "slug": f"outbox-migration-{project_id}"},
            )
            await connection.execute(
                text(
                    "insert into outbox_events "
                    "(event_id,event_type,event_version,aggregate_type,aggregate_id,project_id,"
                    "correlation_id,idempotency_key,payload,payload_digest) values "
                    "(:event_id,'MigrationProbe',1,'migration_probe',:aggregate_id,:project_id,"
                    ":correlation_id,:idempotency_key,'{}'::jsonb,:digest)"
                ),
                {
                    "event_id": event_id,
                    "aggregate_id": str(uuid4()),
                    "project_id": project_id,
                    "correlation_id": f"migration:{event_id}",
                    "idempotency_key": f"migration:{event_id}:v1",
                    "digest": "sha256:" + ("0" * 64),
                },
            )
            downgrade = asyncio.create_task(
                asyncio.to_thread(
                    command.downgrade,
                    config,
                    "0028_artifact_admission",
                )
            )
            await asyncio.sleep(0.1)
            assert not downgrade.done()
            if commit_writer:
                await transaction.commit()
                with pytest.raises(RuntimeError, match="cannot downgrade with shared outbox events"):
                    await asyncio.wait_for(downgrade, timeout=5)
                return "refused_after_commit"
            await transaction.rollback()
            await asyncio.wait_for(downgrade, timeout=5)
            return "succeeded_after_rollback"
    finally:
        await engine.dispose()


async def _remove_outbox_migration_row(database_url: str, project_id: str) -> None:
    """Remove only migration-test truth under explicit disabled trigger custody."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            table_exists = await connection.scalar(
                text("select to_regclass('public.outbox_events') is not null")
            )
            if table_exists:
                await connection.execute(text("alter table outbox_events disable trigger user"))
                await connection.execute(
                    text("delete from outbox_events where project_id=:project_id"),
                    {"project_id": project_id},
                )
                await connection.execute(text("alter table outbox_events enable trigger user"))
            project_exists = await connection.scalar(
                text("select to_regclass('public.projects') is not null")
            )
            if project_exists:
                await connection.execute(
                    text("delete from projects where id=:project_id"),
                    {"project_id": project_id},
                )
    finally:
        await engine.dispose()


async def _fetch_columns(database_url: str) -> set[str]:
    """Return current public table columns as table.column names."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        select table_name, column_name
                        from information_schema.columns
                        where table_schema = 'public'
                        """
                    )
                )
            ).all()
            return {f"{row.table_name}.{row.column_name}" for row in rows}
    finally:
        await engine.dispose()


async def _fetch_table_names(database_url: str) -> set[str]:
    """Return current public table names."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        select table_name
                        from information_schema.tables
                        where table_schema = 'public'
                        """
                    )
                )
            ).all()
            return {row.table_name for row in rows}
    finally:
        await engine.dispose()


async def _seed_pre_0020_actor(
    database_url: str,
    *,
    actor_id: str,
    subject: str,
    audit_event_id: str | None = None,
) -> None:
    """Seed one valid legacy identity, typed profile, and optional attribution."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into actor_identities "
                    "(actor_id,external_subject,external_issuer,display_name,email,"
                    "last_seen_roles,last_claim_snapshot,auth_source,is_dev_auth) values "
                    "(:actor,:subject,'https://identity.test','Legacy Human',"
                    "'legacy@example.test','[\"worker\"]'::json,'{}'::json,'flow',false)"
                ),
                {"actor": actor_id, "subject": subject},
            )
            await connection.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_id,profile_type,status,skill_tags,scope_type,scope_id,"
                    "profile_metadata) values "
                    "(:id,:actor,'worker','active','[\"stem\"]'::json,'global','global',"
                    '\'{"source":"legacy"}\'::json)'
                ),
                {"id": str(uuid4()), "actor": actor_id},
            )
            if audit_event_id is not None:
                await connection.execute(
                    text(
                        "insert into audit_events "
                        "(id,entity_type,entity_id,event_type,actor_id,external_subject,"
                        "external_issuer,actor_roles,claim_snapshot,auth_source,is_dev_auth,"
                        "reason,event_payload) values "
                        "(:id,'task','legacy-task','task_created',:actor,:subject,"
                        "'https://identity.test','[\"worker\"]'::json,'{}'::json,'flow',"
                        "false,'migration attribution proof','{}'::json)"
                    ),
                    {"id": audit_event_id, "actor": actor_id, "subject": subject},
                )
    finally:
        await engine.dispose()


async def _legacy_database_binding(database_url: str) -> str:
    """Return the classification binding for the current isolated database."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            database_name, database_oid = (
                await connection.execute(
                    text(
                        "select current_database(), oid from pg_database "
                        "where datname=current_database()"
                    )
                )
            ).one()
        return database_binding_identifier(database_name, database_oid)
    finally:
        await engine.dispose()


async def _pre_0020_actor_state(database_url: str, actor_id: str) -> dict[str, object]:
    """Return prior-head revision and retained legacy actor count."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "legacy_rows": await connection.scalar(
                    text("select count(*) from actor_identities where actor_id=:actor"),
                    {"actor": actor_id},
                ),
            }
    finally:
        await engine.dispose()


async def _pre_0020_actor_display_fields(
    database_url: str,
    actor_id: str,
) -> dict[str, str | None]:
    """Return restored legacy display fields after canonical downgrade."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("select display_name,email from actor_identities where actor_id=:actor"),
                    {"actor": actor_id},
                )
            ).one()
            return {"display_name": row.display_name, "email": row.email}
    finally:
        await engine.dispose()


async def _update_canonical_actor_display_fields(
    database_url: str,
    actor_id: str,
    *,
    display_name: str | None,
    contact_email: str | None,
) -> None:
    """Apply canonical self-service fields before downgrade proof."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update actor_profiles set display_name=:display_name, "
                    "contact_email=:contact_email,updated_at=now() where id=:actor"
                ),
                {
                    "actor": actor_id,
                    "display_name": display_name,
                    "contact_email": contact_email,
                },
            )
    finally:
        await engine.dispose()


async def _canonical_actor_migration_state(
    database_url: str,
    actor_id: str,
    audit_event_id: str,
) -> dict[str, object]:
    """Return canonical, compatibility, evidence, and attribution migration facts."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            profile = (
                await connection.execute(
                    text(
                        "select id,actor_kind,display_name,contact_email "
                        "from actor_profiles where id=:actor"
                    ),
                    {"actor": actor_id},
                )
            ).one()
            identity_link = (
                await connection.execute(
                    text(
                        "select id,subject from actor_identity_links where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
            ).one()
            legacy_profile_type = await connection.scalar(
                text("select profile_type from legacy_workflow_eligibility where actor_id=:actor"),
                {"actor": actor_id},
            )
            audit_actor_id = await connection.scalar(
                text("select actor_id from audit_events where id=:event"),
                {"event": audit_event_id},
            )
            migration_state = (
                await connection.execute(
                    text(
                        "select classified_count,source_row_set_sha256 "
                        "from actor_profile_migration_state where id=1"
                    )
                )
            ).one()
            return {
                "profile_id": profile.id,
                "actor_kind": profile.actor_kind,
                "display_name": profile.display_name,
                "contact_email": profile.contact_email,
                "identity_link_id": identity_link.id,
                "identity_subject": identity_link.subject,
                "legacy_profile_type": legacy_profile_type,
                "audit_actor_id": audit_actor_id,
                "classified_count": migration_state.classified_count,
                "source_checksum": migration_state.source_row_set_sha256,
            }
    finally:
        await engine.dispose()


async def _current_revision(database_url: str) -> str:
    """Return the exact current Alembic revision."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return str(await connection.scalar(text("select version_num from alembic_version")))
    finally:
        await engine.dispose()


async def _seed_canonical_actor_for_downgrade_guard(
    database_url: str,
    actor_id: str,
) -> None:
    """Seed one complete active canonical actor for rollback guard tests."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await _insert_canonical_actor(connection, actor_id, "rollback-guard", "human")
    finally:
        await engine.dispose()


async def _set_canonical_actor_guard_state(
    database_url: str,
    actor_id: str,
    state: str,
) -> None:
    """Put one actor in a reviewed rollback stop state."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            if state == "revoked":
                await connection.execute(
                    text(
                        "update actor_identity_links set status='revoked', "
                        "revoked_by=:actor, revoked_at=now(), revoked_reason='test guard' "
                        "where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
            elif state == "suspended":
                await connection.execute(
                    text(
                        "update actor_profiles set status='suspended', suspended_by=:actor, "
                        "suspended_at=now(), suspension_reason='test guard' where id=:actor"
                    ),
                    {"actor": actor_id},
                )
            elif state == "deactivated":
                await connection.execute(
                    text(
                        "update actor_profiles set status='deactivated', deactivated_by=:actor, "
                        "deactivated_at=now(), deactivation_reason='test guard' where id=:actor"
                    ),
                    {"actor": actor_id},
                )
            else:
                raise AssertionError(f"unknown test state: {state}")
    finally:
        await engine.dispose()


async def _reset_canonical_actor_guard_state(
    database_url: str,
    actor_id: str,
) -> None:
    """Restore test-owned state after proving the migration refuses it."""
    engine = create_async_engine(database_url)
    history_guards_disabled = False
    try:
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "alter table actor_profiles disable trigger actor_profile_history_guard"
                    )
                )
                await connection.execute(
                    text(
                        "alter table actor_identity_links disable trigger "
                        "actor_identity_link_history_guard"
                    )
                )
            history_guards_disabled = True
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update actor_profiles set status='active', suspended_by=null, "
                        "suspended_at=null, suspension_reason=null, deactivated_by=null, "
                        "deactivated_at=null, deactivation_reason=null, reactivated_by=null, "
                        "reactivated_at=null, reactivation_reason=null where id=:actor"
                    ),
                    {"actor": actor_id},
                )
                await connection.execute(
                    text(
                        "update actor_identity_links set status='active', revoked_by=null, "
                        "revoked_at=null, revoked_reason=null, reactivated_by=null, "
                        "reactivated_at=null, reactivation_reason=null "
                        "where actor_profile_id=:actor"
                    ),
                    {"actor": actor_id},
                )
        finally:
            if history_guards_disabled:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "alter table actor_profiles enable trigger actor_profile_history_guard"
                        )
                    )
                    await connection.execute(
                        text(
                            "alter table actor_identity_links enable trigger "
                            "actor_identity_link_history_guard"
                        )
                    )
    finally:
        await engine.dispose()


async def _assert_actor_registry_unique_constraints(database_url: str) -> None:
    """Prove canonical indexes, constraints, timestamps, and history guards."""
    engine = create_async_engine(database_url)
    actor_id = actor_id_from_external_identity("https://identity.test", "unique-actor")
    try:
        async with engine.begin() as connection:
            await _insert_canonical_actor(connection, actor_id, "unique-actor", "human")
            index_rows = (
                await connection.execute(
                    text(
                        "select indexname,indexdef from pg_indexes "
                        "where schemaname=current_schema() and "
                        "tablename in ('actor_profiles','actor_identity_links')"
                    )
                )
            ).all()
            indexes = {row.indexname: row.indexdef for row in index_rows}
            assert "(status, actor_kind)" in indexes["ix_actor_profiles_status_actor_kind"]
            assert "(last_seen_at)" in indexes["ix_actor_profiles_last_seen_at"]
            assert (
                "(issuer, subject, status)"
                in indexes["ix_actor_identity_links_issuer_subject_status"]
            )
            assert "ix_actor_profiles_actor_kind" not in indexes
            assert "ix_actor_profiles_status" not in indexes
            assert "ix_actor_identity_links_status" not in indexes
            timestamps = (
                await connection.execute(
                    text(
                        "select p.created_at,p.updated_at,l.linked_at,l.last_verified_at "
                        "from actor_profiles p join actor_identity_links l "
                        "on l.actor_profile_id=p.id where p.id=:actor"
                    ),
                    {"actor": actor_id},
                )
            ).one()
            assert all(value is not None and value.tzinfo is not None for value in timestamps)

        await _expect_integrity_error(
            engine,
            text(
                "insert into actor_profiles "
                "(id,actor_kind,status,provisioning_method,created_by) values "
                "(:actor,'human','active','automatic_first_access',:actor)"
            ),
            {"actor": actor_id},
        )
        await _expect_integrity_error(
            engine,
            text(
                "insert into actor_identity_links "
                "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                "last_verified_at) values (:id,:actor,'https://identity.test',"
                "'second-link','human','active',:actor,clock_timestamp())"
            ),
            {"id": str(uuid4()), "actor": actor_id},
        )

        invalid_profiles = (
            ("not-a-uuid", "human", "active", "automatic_first_access", {}),
            (str(uuid4()), "agent", "active", "automatic_first_access", {}),
            (str(uuid4()), "human", "unknown", "automatic_first_access", {}),
            (str(uuid4()), "human", "active", "manual_service_provisioning", {}),
            (
                str(uuid4()),
                "human",
                "suspended",
                "automatic_first_access",
                {},
            ),
        )
        for invalid_id, kind, status, method, lifecycle in invalid_profiles:
            await _expect_integrity_error(
                engine,
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,created_by) values "
                    "(:id,:kind,:status,:method,:id)"
                ),
                {
                    "id": invalid_id,
                    "kind": kind,
                    "status": status,
                    "method": method,
                    **lifecycle,
                },
            )

        invalid_links = (
            {"link_id": "not-a-uuid"},
            {"issuer": " "},
            {"link_subject": " "},
            {"subject_kind": "agent"},
            {"status": "unknown"},
            {"status": "revoked"},
        )
        for position, overrides in enumerate(invalid_links):
            await _expect_invalid_canonical_pair(
                engine,
                subject=f"invalid-link-{position}",
                **overrides,
            )

        await _expect_dbapi_error(
            engine,
            text("update actor_profiles set actor_kind='service' where id=:actor"),
            {"actor": actor_id},
        )
        await _expect_dbapi_error(
            engine,
            text("update actor_identity_links set subject='changed' where actor_profile_id=:actor"),
            {"actor": actor_id},
        )
        await _expect_dbapi_error(
            engine,
            text("delete from actor_profiles where id=:actor"),
            {"actor": actor_id},
        )
        await _expect_dbapi_error(
            engine,
            text("delete from actor_identity_links where actor_profile_id=:actor"),
            {"actor": actor_id},
        )
        orphan_id = actor_id_from_external_identity("https://identity.test", "orphan-profile")
        await _expect_integrity_error(
            engine,
            text(
                "insert into actor_profiles "
                "(id,actor_kind,status,provisioning_method,created_by) values "
                "(:actor,'human','active','automatic_first_access',:actor)"
            ),
            {"actor": orphan_id},
        )

        connection = await engine.connect()
        transaction = await connection.begin()
        try:
            await connection.execute(
                text(
                    "update actor_profiles set status='deactivated', "
                    "deactivated_by=:actor,deactivated_at=now(),"
                    "deactivation_reason='terminal proof' where id=:actor"
                ),
                {"actor": actor_id},
            )
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "update actor_profiles set status='active',deactivated_by=null,"
                        "deactivated_at=null,deactivation_reason=null where id=:actor"
                    ),
                    {"actor": actor_id},
                )
        finally:
            await transaction.rollback()
            await connection.close()

        width_actor_id = actor_id_from_external_identity("https://identity.test", "s" * 200)
        async with engine.begin() as connection:
            await _insert_canonical_actor(connection, width_actor_id, "s" * 200, "human")
        oversized_actor_id = actor_id_from_external_identity("https://identity.test", "s" * 201)
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await _insert_canonical_actor(connection, oversized_actor_id, "s" * 201, "human")

        other_actor_id = actor_id_from_external_identity(
            "https://identity.test", "other-unique-actor"
        )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await _insert_canonical_actor(
                    connection,
                    other_actor_id,
                    "unique-actor",
                    "human",
                )

        mismatched_actor_id = actor_id_from_external_identity(
            "https://identity.test", "kind-mismatch"
        )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await _insert_canonical_actor(
                    connection,
                    mismatched_actor_id,
                    "kind-mismatch",
                    "service",
                    link_kind="human",
                )
    finally:
        await engine.dispose()


async def _insert_canonical_actor(
    connection,
    actor_id: str,
    subject: str,
    actor_kind: str,
    *,
    link_kind: str | None = None,
) -> None:
    """Insert a complete profile-link pair in one deferred-constraint transaction."""
    provisioning = (
        "automatic_first_access" if actor_kind == "human" else "manual_service_provisioning"
    )
    await connection.execute(
        text(
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,created_by) values "
            "(:actor,:kind,'active',:provisioning,:actor)"
        ),
        {"actor": actor_id, "kind": actor_kind, "provisioning": provisioning},
    )
    await connection.execute(
        text(
            "insert into actor_identity_links "
            "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
            "last_verified_at) values (:id,:actor,'https://identity.test',:subject,"
            ":kind,'active',:actor,clock_timestamp())"
        ),
        {
            "id": str(uuid4()),
            "actor": actor_id,
            "subject": subject,
            "kind": link_kind or actor_kind,
        },
    )


async def _expect_invalid_canonical_pair(
    engine,
    *,
    subject: str,
    link_id: str | None = None,
    issuer: str = "https://identity.test",
    link_subject: str | None = None,
    subject_kind: str = "human",
    status: str = "active",
) -> None:
    """Assert that a malformed identity link cannot commit with its profile."""
    actor_id = actor_id_from_external_identity("https://identity.test", subject)
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,created_by) values "
                    "(:actor,'human','active','automatic_first_access',:actor)"
                ),
                {"actor": actor_id},
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links "
                    "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                    "last_verified_at) values (:id,:actor,:issuer,:subject,:kind,:status,"
                    ":actor,clock_timestamp())"
                ),
                {
                    "id": link_id or str(uuid4()),
                    "actor": actor_id,
                    "issuer": issuer,
                    "subject": subject if link_subject is None else link_subject,
                    "kind": subject_kind,
                    "status": status,
                },
            )


async def _expect_integrity_error(engine, statement, params: dict) -> None:
    """Assert that one SQL statement raises a database integrity error."""
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(statement, params)


async def _expect_dbapi_error(engine, statement, params: dict) -> None:
    """Assert that one statement is rejected by a database trigger or constraint."""
    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            await connection.execute(statement, params)


async def _seed_pre_provenance_post_submit_policy(
    database_url: str,
    project_id: str,
    guide_id: str,
    policy_id: str,
) -> None:
    """Seed a valid 0007 checker policy row before post-submit hashes exist."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (
                        id,
                        name,
                        slug,
                        status
                    )
                    values (
                        :project_id,
                        'Pre-provenance policy project',
                        'pre-provenance-policy-project',
                        'draft'
                    )
                    """
                ),
                {"project_id": project_id},
            )
            await connection.execute(
                text(
                    """
                    insert into project_guides (
                        id,
                        project_id,
                        version,
                        status,
                        content_markdown,
                        created_by
                    )
                    values (
                        :guide_id,
                        :project_id,
                        'v1',
                        'draft',
                        '# Pre-provenance guide',
                        'pre-provenance-test'
                    )
                    """
                ),
                {"guide_id": guide_id, "project_id": project_id},
            )
            await connection.execute(
                text(
                    """
                    insert into checker_policies (
                        id,
                        project_id,
                        guide_version,
                        required_checkers,
                        warning_checkers,
                        blocking_severities
                    )
                    values (
                        :policy_id,
                        :project_id,
                        'v1',
                        '["check_policy_context_present"]'::json,
                        '[]'::json,
                        '["high"]'::json
                    )
                    """
                ),
                {"policy_id": policy_id, "project_id": project_id},
            )
    finally:
        await engine.dispose()


async def _seed_pre_provenance_runtime_rows(database_url: str, ids: dict[str, str]) -> None:
    """Seed 0007 runtime rows that cannot be trusted under 0008 provenance."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (
                        id,
                        name,
                        slug,
                        status
                    )
                    values (
                        :project_id,
                        'Pre-provenance runtime project',
                        'pre-provenance-runtime-project',
                        'draft'
                    )
                    """
                ),
                {"project_id": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into project_guides (
                        id,
                        project_id,
                        version,
                        status,
                        content_markdown,
                        created_by
                    )
                    values (
                        :guide_id,
                        :project_id,
                        'v1',
                        'active',
                        '# Pre-provenance runtime guide',
                        'pre-provenance-test'
                    )
                    """
                ),
                {"guide_id": ids["guide"], "project_id": ids["project"]},
            )
            await _seed_pre_provenance_policies(connection, ids["project"], ids["policy"])
            await connection.execute(
                text(
                    """
                    insert into workstream_tasks (
                        id,
                        project_id,
                        locked_guide_version,
                        locked_review_policy_version,
                        locked_revision_policy_version,
                        locked_payment_policy_version,
                        source_type,
                        title,
                        description,
                        skill_tags,
                        status,
                        created_by
                    )
                    values (
                        :task_id,
                        :project_id,
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'manual',
                        'Pre-provenance runtime task',
                        'Already in progress before 0008.',
                        '[]'::json,
                        'in_progress',
                        'pre-provenance-test'
                    )
                    """
                ),
                {"task_id": ids["task"], "project_id": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into submissions (
                        id,
                        task_id,
                        worker_id,
                        version,
                        status,
                        summary,
                        package_hash,
                        artifact_hash_manifest,
                        worker_attestation,
                        locked_guide_version,
                        locked_review_policy_version,
                        locked_revision_policy_version,
                        locked_payment_policy_version
                    )
                    values (
                        :submission_id,
                        :task_id,
                        'pre-provenance-worker',
                        1,
                        'submitted',
                        'Pre-provenance submitted packet',
                        'sha256:pre-provenance-package',
                        '[]'::json,
                        'pre-provenance attestation',
                        'v1',
                        'v1',
                        'v1',
                        'v1'
                    )
                    """
                ),
                {"submission_id": ids["submission"], "task_id": ids["task"]},
            )
            await connection.execute(
                text(
                    """
                    insert into checker_runs (
                        id,
                        task_id,
                        submission_id,
                        submission_version,
                        trigger_source,
                        status,
                        routing_recommendation,
                        outcome_source,
                        triggered_by,
                        triggered_by_subject,
                        triggered_by_issuer,
                        trigger_auth_source,
                        attempt_number,
                        is_current_for_submission,
                        locked_guide_version,
                        locked_review_policy_version,
                        locked_revision_policy_version,
                        locked_payment_policy_version,
                        package_hash,
                        artifact_hash_manifest,
                        artifact_manifest_hash,
                        passed_count,
                        warning_count,
                        failed_count,
                        blocking_count
                    )
                    values (
                        :run_id,
                        :task_id,
                        :submission_id,
                        1,
                        'submission_lock',
                        'completed',
                        'allow_review',
                        'auto_checker',
                        'pre-provenance-test',
                        'pre-provenance-test',
                        'flow-pre-provenance',
                        'flow',
                        1,
                        true,
                        'v1',
                        'v1',
                        'v1',
                        'v1',
                        'sha256:pre-provenance-package',
                        '[]'::json,
                        'sha256:pre-provenance-manifest',
                        1,
                        0,
                        0,
                        0
                    )
                    """
                ),
                {
                    "run_id": ids["run"],
                    "task_id": ids["task"],
                    "submission_id": ids["submission"],
                },
            )
    finally:
        await engine.dispose()


async def _seed_pre_provenance_policies(
    connection, project_id: str, checker_policy_id: str
) -> None:
    """Seed v0.1 guide policies required by locked task foreign keys."""
    await connection.execute(
        text(
            """
            insert into checker_policies (
                id,
                project_id,
                guide_version,
                required_checkers,
                warning_checkers,
                blocking_severities
            )
            values (
                :checker_policy_id,
                :project_id,
                'v1',
                '["check_policy_context_present"]'::json,
                '[]'::json,
                '["high"]'::json
            )
            """
        ),
        {"checker_policy_id": checker_policy_id, "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into review_policies (
                id,
                project_id,
                guide_version,
                requires_second_review,
                allowed_decisions,
                minimum_finding_fields
            )
            values (
                :review_policy_id,
                :project_id,
                'v1',
                false,
                '["accept", "needs_revision", "reject"]'::json,
                '[]'::json
            )
            """
        ),
        {"review_policy_id": str(uuid4()), "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into revision_policies (
                id,
                project_id,
                guide_version,
                max_revision_rounds,
                revision_deadline_hours,
                auto_reject_after_limit,
                allowed_resubmission_states
            )
            values (
                :revision_policy_id,
                :project_id,
                'v1',
                7,
                48,
                true,
                '["needs_revision"]'::json
            )
            """
        ),
        {"revision_policy_id": str(uuid4()), "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into payment_policies (
                id,
                project_id,
                guide_version,
                base_amount,
                currency,
                payout_type
            )
            values (
                :payment_policy_id,
                :project_id,
                'v1',
                25.00,
                'USD',
                'fixed'
            )
            """
        ),
        {"payment_policy_id": str(uuid4()), "project_id": project_id},
    )


async def _post_submit_lock_columns_exist(database_url: str, table_name: str) -> bool:
    """Return whether a post-submit lock column was added to a table."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            count = await connection.scalar(
                text(
                    """
                    select count(*)
                    from information_schema.columns
                    where table_name = :table_name
                      and column_name = 'locked_post_submit_checker_policy_id'
                    """
                ),
                {"table_name": table_name},
            )
            return bool(count)
    finally:
        await engine.dispose()


async def _fetch_pre_provenance_post_submit_policy_hash(
    database_url: str,
    policy_id: str,
) -> str | None:
    """Return the post-submit policy hash created by the 0008 migration, if any."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            return await connection.scalar(
                text("select policy_hash from checker_policies where id = :policy_id"),
                {"policy_id": policy_id},
            )
    finally:
        await engine.dispose()


async def _seed_artifact_prior_head(database_url: str, project_id: str) -> None:
    """Seed one representative legacy row at the previous migration head."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (id, name, slug, status)
                    values (:id, 'Prior artifact project', :slug, 'draft')
                    """
                ),
                {"id": project_id, "slug": f"prior-artifact-{project_id}"},
            )
    finally:
        await engine.dispose()


async def _seed_artifact_prior_head_runtime_rows(
    database_url: str,
    ids: dict[str, str],
) -> None:
    """Seed representative runtime rows valid at the 0015 migration head."""
    snapshot_id = ids["snapshot"]
    submission_policy_id = ids["submission_policy"]
    effective_policy_id = ids["effective_policy"]
    pre_submit_policy_id = ids["pre_submit_policy"]
    review_policy_id = ids["review_policy"]
    revision_policy_id = ids["revision_policy"]
    payment_policy_id = ids["payment_policy"]
    snapshot_hash = f"sha256:{'a' * 64}"
    submission_policy_hash = f"sha256:{'b' * 64}"
    effective_policy_hash = f"sha256:{'c' * 64}"
    pre_submit_bundle_hash = f"sha256:{'d' * 64}"
    post_submit_policy_hash = f"sha256:{'e' * 64}"
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (id, name, slug, status)
                    values (:id, 'Artifact runtime project', :slug, 'active')
                    """
                ),
                {"id": ids["project"], "slug": f"artifact-runtime-{ids['project']}"},
            )
            await connection.execute(
                text(
                    """
                    insert into project_guides (
                        id, project_id, version, status, content_markdown,
                        created_by, approved_by
                    )
                    values (
                        :id, :project_id, 'v1', 'active', '# Artifact runtime guide',
                        'artifact-migration-test', 'artifact-migration-test'
                    )
                    """
                ),
                {"id": ids["guide"], "project_id": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into guide_source_snapshots (
                        id, project_id, guide_id, guide_version,
                        manifest_schema_version, manifest_json, bundle_hash, captured_by
                    )
                    values (
                        :id, :project_id, :guide_id, 'v1', '1', '{}'::json,
                        :bundle_hash, 'artifact-migration-test'
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "project_id": ids["project"],
                    "guide_id": ids["guide"],
                    "bundle_hash": snapshot_hash,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into submission_artifact_policies (
                        id, project_id, guide_id, guide_version,
                        source_snapshot_id, source_snapshot_hash, policy_version,
                        lifecycle_status, policy_body, policy_hash, derivation_source,
                        source_material_refs, created_by, approved_by_role,
                        approved_by_actor, approved_at
                    )
                    values (
                        :id, :project_id, :guide_id, 'v1', :snapshot_id,
                        :snapshot_hash, 'v1', 'approved', '{}'::json, :policy_hash,
                        'migration_test', '[]'::json, 'artifact-migration-test',
                        'admin', 'artifact-migration-test', now()
                    )
                    """
                ),
                {
                    "id": submission_policy_id,
                    "project_id": ids["project"],
                    "guide_id": ids["guide"],
                    "snapshot_id": snapshot_id,
                    "snapshot_hash": snapshot_hash,
                    "policy_hash": submission_policy_hash,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into effective_project_submission_artifact_policies (
                        id, project_id, guide_id, guide_version,
                        source_snapshot_id, source_snapshot_hash,
                        submission_artifact_policy_id, submission_artifact_policy_hash,
                        lifecycle_status, merge_algorithm_version, effective_policy,
                        effective_policy_hash, created_by
                    )
                    values (
                        :id, :project_id, :guide_id, 'v1', :snapshot_id,
                        :snapshot_hash, :submission_policy_id, :submission_policy_hash,
                        'approved', '1', '{}'::json, :effective_policy_hash,
                        'artifact-migration-test'
                    )
                    """
                ),
                {
                    "id": effective_policy_id,
                    "project_id": ids["project"],
                    "guide_id": ids["guide"],
                    "snapshot_id": snapshot_id,
                    "snapshot_hash": snapshot_hash,
                    "submission_policy_id": submission_policy_id,
                    "submission_policy_hash": submission_policy_hash,
                    "effective_policy_hash": effective_policy_hash,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into pre_submit_checker_policies (
                        id, project_id, guide_id, guide_version,
                        source_snapshot_id, source_snapshot_hash, effective_policy_id,
                        effective_policy_hash, lifecycle_status, compiler_version,
                        compiled_bundle, compiled_bundle_hash, checker_names,
                        checker_configs, created_by
                    )
                    values (
                        :id, :project_id, :guide_id, 'v1', :snapshot_id,
                        :snapshot_hash, :effective_policy_id, :effective_policy_hash,
                        'compiled', '1', '{}'::json, :bundle_hash, '[]'::json,
                        '{}'::json, 'artifact-migration-test'
                    )
                    """
                ),
                {
                    "id": pre_submit_policy_id,
                    "project_id": ids["project"],
                    "guide_id": ids["guide"],
                    "snapshot_id": snapshot_id,
                    "snapshot_hash": snapshot_hash,
                    "effective_policy_id": effective_policy_id,
                    "effective_policy_hash": effective_policy_hash,
                    "bundle_hash": pre_submit_bundle_hash,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into checker_policies (
                        id, project_id, guide_id, guide_version,
                        source_snapshot_id, source_snapshot_hash, effective_policy_id,
                        effective_policy_hash, pre_submit_checker_policy_id,
                        pre_submit_checker_bundle_hash, required_checkers,
                        warning_checkers, blocking_severities, policy_hash, policy_body,
                        lifecycle_status, approved_by_role, approved_by_actor,
                        approved_at, created_by
                    )
                    values (
                        :id, :project_id, :guide_id, 'v1', :snapshot_id,
                        :snapshot_hash, :effective_policy_id, :effective_policy_hash,
                        :pre_submit_policy_id, :pre_submit_bundle_hash,
                        '["artifact_integrity"]'::json, '[]'::json, '["high"]'::json,
                        :policy_hash, '{}'::json, 'approved', 'admin',
                        'artifact-migration-test', now(), 'artifact-migration-test'
                    )
                    """
                ),
                {
                    "id": ids["policy"],
                    "project_id": ids["project"],
                    "guide_id": ids["guide"],
                    "snapshot_id": snapshot_id,
                    "snapshot_hash": snapshot_hash,
                    "effective_policy_id": effective_policy_id,
                    "effective_policy_hash": effective_policy_hash,
                    "pre_submit_policy_id": pre_submit_policy_id,
                    "pre_submit_bundle_hash": pre_submit_bundle_hash,
                    "policy_hash": post_submit_policy_hash,
                },
            )
            await _seed_pre_provenance_policies_without_checker(
                connection,
                ids["project"],
                review_policy_id,
                revision_policy_id,
                payment_policy_id,
            )
            lock_params = {
                "project_id": ids["project"],
                "post_policy_id": ids["policy"],
                "post_policy_hash": post_submit_policy_hash,
                "snapshot_id": snapshot_id,
                "snapshot_hash": snapshot_hash,
                "effective_policy_id": effective_policy_id,
                "effective_policy_hash": effective_policy_hash,
                "pre_submit_policy_id": pre_submit_policy_id,
                "pre_submit_bundle_hash": pre_submit_bundle_hash,
            }
            await connection.execute(
                text(
                    """
                    insert into workstream_tasks (
                        id, project_id, locked_guide_version,
                        locked_post_submit_checker_policy_id,
                        locked_post_submit_checker_policy_version,
                        locked_post_submit_checker_policy_hash,
                        locked_post_submit_checker_policy_body,
                        locked_review_policy_version, locked_revision_policy_version,
                        locked_payment_policy_version, locked_guide_source_snapshot_id,
                        locked_guide_source_snapshot_hash,
                        locked_effective_project_submission_artifact_policy_id,
                        locked_effective_project_submission_artifact_policy_hash,
                        locked_pre_submit_checker_policy_id,
                        locked_pre_submit_checker_bundle_hash, source_type, title,
                        description, skill_tags, status, created_by
                    )
                    values (
                        :id, :project_id, 'v1', :post_policy_id, 'v1',
                        :post_policy_hash, '{}'::json, 'v1', 'v1', 'v1',
                        :snapshot_id, :snapshot_hash, :effective_policy_id,
                        :effective_policy_hash, :pre_submit_policy_id,
                        :pre_submit_bundle_hash, 'manual', 'Artifact runtime task',
                        'Representative task at migration 0015.', '[]'::json,
                        'in_progress', 'artifact-migration-test'
                    )
                    """
                ),
                {"id": ids["task"], **lock_params},
            )
            await connection.execute(
                text(
                    """
                    insert into submissions (
                        id, task_id, worker_id, version, status, summary,
                        package_hash, artifact_hash_manifest, worker_attestation,
                        locked_guide_version, locked_post_submit_checker_policy_id,
                        locked_post_submit_checker_policy_version,
                        locked_post_submit_checker_policy_hash,
                        locked_post_submit_checker_policy_body,
                        locked_review_policy_version, locked_revision_policy_version,
                        locked_payment_policy_version, locked_guide_source_snapshot_id,
                        locked_guide_source_snapshot_hash,
                        locked_effective_project_submission_artifact_policy_id,
                        locked_effective_project_submission_artifact_policy_hash,
                        locked_pre_submit_checker_policy_id,
                        locked_pre_submit_checker_bundle_hash
                    )
                    values (
                        :id, :task_id, 'artifact-worker', 1, 'submitted',
                        'Representative submission at migration 0015.',
                        'sha256:artifact-package', '[]'::json,
                        'artifact migration attestation', 'v1', :post_policy_id,
                        'v1', :post_policy_hash, '{}'::json, 'v1', 'v1', 'v1',
                        :snapshot_id, :snapshot_hash, :effective_policy_id,
                        :effective_policy_hash, :pre_submit_policy_id,
                        :pre_submit_bundle_hash
                    )
                    """
                ),
                {"id": ids["submission"], "task_id": ids["task"], **lock_params},
            )
            await connection.execute(
                text(
                    """
                    insert into checker_runs (
                        id, task_id, submission_id, submission_version,
                        trigger_source, status, routing_recommendation, outcome_source,
                        triggered_by, triggered_by_subject, triggered_by_issuer,
                        trigger_auth_source, attempt_number, is_current_for_submission,
                        locked_guide_version, locked_post_submit_checker_policy_id,
                        locked_post_submit_checker_policy_version,
                        locked_post_submit_checker_policy_hash,
                        locked_post_submit_checker_policy_body,
                        locked_review_policy_version, locked_revision_policy_version,
                        locked_payment_policy_version, package_hash,
                        artifact_hash_manifest, artifact_manifest_hash, passed_count,
                        warning_count, failed_count, blocking_count
                    )
                    values (
                        :id, :task_id, :submission_id, 1, 'submission_lock',
                        'completed', 'allow_review', 'auto_checker',
                        'artifact-migration-test', 'artifact-migration-test',
                        'flow-test', 'flow', 1, true, 'v1', :post_policy_id, 'v1',
                        :post_policy_hash, '{}'::json, 'v1', 'v1', 'v1',
                        'sha256:artifact-package', '[]'::json,
                        'sha256:artifact-manifest', 1, 0, 0, 0
                    )
                    """
                ),
                {
                    "id": ids["run"],
                    "task_id": ids["task"],
                    "submission_id": ids["submission"],
                    **lock_params,
                },
            )
    finally:
        await engine.dispose()


async def _seed_pre_provenance_policies_without_checker(
    connection,
    project_id: str,
    review_policy_id: str,
    revision_policy_id: str,
    payment_policy_id: str,
) -> None:
    """Seed the non-checker guide policies needed by a locked task."""
    await connection.execute(
        text(
            """
            insert into review_policies (
                id, project_id, guide_version, requires_second_review,
                allowed_decisions, minimum_finding_fields
            ) values (
                :id, :project_id, 'v1', false,
                '["accept", "needs_revision", "reject"]'::json, '[]'::json
            )
            """
        ),
        {"id": review_policy_id, "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into revision_policies (
                id, project_id, guide_version, max_revision_rounds,
                revision_deadline_hours, auto_reject_after_limit,
                allowed_resubmission_states
            ) values (
                :id, :project_id, 'v1', 7, 48, true, '["needs_revision"]'::json
            )
            """
        ),
        {"id": revision_policy_id, "project_id": project_id},
    )
    await connection.execute(
        text(
            """
            insert into payment_policies (
                id, project_id, guide_version, base_amount, currency, payout_type
            ) values (:id, :project_id, 'v1', 25.00, 'USD', 'fixed')
            """
        ),
        {"id": payment_policy_id, "project_id": project_id},
    )


async def _artifact_prior_head_project(database_url: str, project_id: str) -> dict[str, str]:
    """Return exact prior-head project values for migration comparison."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text("select id, name, slug, status from projects where id = :id"),
                        {"id": project_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)
    finally:
        await engine.dispose()


async def _artifact_prior_head_runtime_rows(
    database_url: str, ids: dict[str, str]
) -> dict[str, dict]:
    """Return every column from representative populated 0015 domain rows."""
    table_ids = {
        "projects": ids["project"],
        "project_guides": ids["guide"],
        "guide_source_snapshots": ids["snapshot"],
        "submission_artifact_policies": ids["submission_policy"],
        "effective_project_submission_artifact_policies": ids["effective_policy"],
        "pre_submit_checker_policies": ids["pre_submit_policy"],
        "checker_policies": ids["policy"],
        "review_policies": ids["review_policy"],
        "revision_policies": ids["revision_policy"],
        "payment_policies": ids["payment_policy"],
        "workstream_tasks": ids["task"],
        "submissions": ids["submission"],
        "checker_runs": ids["run"],
    }
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows: dict[str, dict] = {}
            for table_name, row_id in table_ids.items():
                value = await connection.scalar(
                    text(
                        f"select row_to_json(selected) from "
                        f"(select * from {table_name} where id = :id) selected"
                    ),
                    {"id": row_id},
                )
                assert isinstance(value, dict)
                rows[table_name] = value
            return rows
    finally:
        await engine.dispose()


async def _artifact_table_counts(database_url: str) -> dict[str, int]:
    """Return row counts for every additive artifact table."""
    tables = (
        "artifact_upload_sessions",
        "artifact_upload_items",
        "artifact_contents",
        "artifact_bindings",
        "artifact_replicas",
        "artifact_operation_receipts",
    )
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            counts: dict[str, int] = {}
            for table in tables:
                count = await connection.scalar(text(f"select count(*) from {table}"))
                counts[table] = int(count or 0)
            return counts
    finally:
        await engine.dispose()


async def _seed_artifact_content(database_url: str) -> None:
    """Insert one content fact that a clean-cut migration must refuse."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into artifact_contents "
                    "(id, sha256, byte_count, media_type, normalized_display_name) "
                    "values (:id, :sha256, 1, 'application/octet-stream', 'legacy.bin')"
                ),
                {"id": str(uuid4()), "sha256": "sha256:" + "1" * 64},
            )
    finally:
        await engine.dispose()


async def _seed_v2_artifact_namespace(database_url: str) -> None:
    """Insert the v2-only namespace fact that downgrade must preserve."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into artifact_storage_namespaces "
                    "(id, backend, adapter, provider_profile, namespace_descriptor, "
                    "namespace_fingerprint) values "
                    "('primary', 'local', 'local', 'local-v2', '{}'::json, :fingerprint)"
                ),
                {"fingerprint": "sha256:" + "3" * 64},
            )
    finally:
        await engine.dispose()


async def _artifact_namespace_count(database_url: str) -> int:
    """Return the current v2 deployment-namespace fact count."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            count = await connection.scalar(
                text("select count(*) from artifact_storage_namespaces")
            )
            return int(count or 0)
    finally:
        await engine.dispose()


async def _truncate_v2_artifact_namespace(database_url: str) -> None:
    """Clear the v2 namespace when its table exists during test cleanup."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("select to_regclass('public.artifact_storage_namespaces') is not null")
            )
            if exists:
                await connection.execute(
                    text("truncate table artifact_storage_namespaces cascade")
                )
    finally:
        await engine.dispose()


async def _insert_v1_artifact_content_until_released(
    database_url: str,
    inserted: threading.Event,
    release: threading.Event,
) -> None:
    """Hold one uncommitted v1 writer while the clean-cut upgrade requests locks."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into artifact_contents "
                    "(id, sha256, byte_count, media_type, normalized_display_name) "
                    "values (:id, :sha256, 1, 'application/octet-stream', 'raced.bin')"
                ),
                {"id": str(uuid4()), "sha256": "sha256:" + "2" * 64},
            )
            inserted.set()
            assert await asyncio.to_thread(release.wait, 5)
    finally:
        await engine.dispose()


async def _artifact_v2_refusal_state(database_url: str) -> dict[str, object]:
    """Return transactional proof that refusal changed no v1 schema or data."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("select version_num from alembic_version"))
            namespace_table = await connection.scalar(
                text("select to_regclass('public.artifact_storage_namespaces') is not null")
            )
            content_count = await connection.scalar(
                text("select count(*) from artifact_contents")
            )
            return {
                "revision": revision,
                "namespace_table_exists": namespace_table,
                "v1_content_count": content_count,
            }
    finally:
        await engine.dispose()


async def _assert_artifact_fact_guards(database_url: str, ids: dict[str, str]) -> None:
    """Exercise digest and immutable-row guards directly in PostgreSQL."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into projects (id, name, slug, status)
                    values (:project_id, 'Artifact guards', :slug, 'draft')
                    """
                ),
                {"project_id": ids["project"], "slug": f"guards-{ids['project']}"},
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_contents (id, sha256, byte_count)
                    values (:content_id, :sha256, 0)
                    """
                ),
                {"content_id": ids["content"], "sha256": "sha256:" + "0" * 64},
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_upload_sessions (
                        id, actor_id, project_id, permitted_roles, state,
                        maximum_bytes, current_bytes, reserved_bytes,
                        maximum_items, current_items, reserved_items, expires_at, cas_version
                    ) values (
                        :id, 'actor', :project, '[]'::json, 'open',
                        8, 0, 4, 1, 0, 1, now() + interval '1 hour', 0
                    )
                    """
                ),
                {"id": ids["session"], "project": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_upload_items (
                        id, session_id, logical_role, display_name, reserved_bytes,
                        idempotency_key, request_digest, state, cas_version
                    ) values (
                        :id, :session, 'packet', 'packet.bin', 4,
                        'idem', :digest, 'reserved', 0
                    )
                    """
                ),
                {"id": ids["item"], "session": ids["session"], "digest": "sha256:" + "1" * 64},
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_replicas (
                        id, content_id, adapter, provider_artifact_id,
                        verification_state, retention_state, availability_state, integrity_state
                    ) values (
                        :id, :content, 'local', 'artifact-provider-id',
                        'pending', 'unretained', 'available', 'valid'
                    )
                    """
                ),
                {"id": ids["replica"], "content": ids["content"]},
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_operation_receipts (
                        id, upload_item_id, replica_id, adapter, service_principal,
                        operation, idempotency_key, request_digest, response_digest,
                        provider_receipt_id, provider_operation_reference, outcome, attempt_number,
                        correlation_id, provider_recorded_at, details
                    ) values (
                        :id, :item, :replica, 'local', 'workstream.artifact',
                        'store', 'idem', :request_digest, :response_digest,
                        'provider-receipt', 'provider-operation', 'stored', 1,
                        'correlation', now(), '{}'::json
                    )
                    """
                ),
                {
                    "id": ids["receipt"],
                    "item": ids["item"],
                    "replica": ids["replica"],
                    "request_digest": "sha256:" + "1" * 64,
                    "response_digest": "sha256:" + "2" * 64,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_bindings (
                        id, content_id, project_id, resource_type, resource_id,
                        logical_role, scope_version, actor_id, attribution_type
                    ) values (
                        :id, :content, :project, 'submission', 'submission-1',
                        'packet', 1, 'actor', 'submitted_by'
                    )
                    """
                ),
                {"id": ids["binding"], "content": ids["content"], "project": ids["project"]},
            )
            await connection.execute(
                text(
                    """
                    insert into artifact_bindings (
                        id, content_id, project_id, resource_type, resource_id,
                        logical_role, scope_version, actor_id, attribution_type,
                        supersedes_binding_id
                    ) values (
                        :id, :content, :project, 'submission', 'submission-1',
                        'packet', 2, 'actor', 'submitted_by', :predecessor
                    )
                    """
                ),
                {
                    "id": ids["binding_v2"],
                    "content": ids["content"],
                    "project": ids["project"],
                    "predecessor": ids["binding"],
                },
            )
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("update artifact_contents set byte_count = 1 where id = :id"),
                    {"id": ids["content"]},
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        insert into artifact_contents (id, sha256, byte_count)
                        values (:id, 'SHA256:INVALID', 1)
                        """
                    ),
                    {"id": str(uuid4())},
                )
        failing_statements = (
            (
                "update artifact_upload_sessions set state = 'unknown' where id = :id",
                {"id": ids["session"]},
            ),
            (
                "update artifact_upload_sessions set current_bytes = -1 where id = :id",
                {"id": ids["session"]},
            ),
            (
                "update artifact_upload_sessions set state = 'sealed' where id = :id",
                {"id": ids["session"]},
            ),
            (
                "update artifact_upload_sessions set reserved_bytes = 9 where id = :id",
                {"id": ids["session"]},
            ),
            (
                "update artifact_upload_items set state = 'unknown' where id = :id",
                {"id": ids["item"]},
            ),
            (
                "update artifact_upload_items set reserved_bytes = -1 where id = :id",
                {"id": ids["item"]},
            ),
            (
                "update artifact_upload_items set cas_version = -1 where id = :id",
                {"id": ids["item"]},
            ),
            (
                "update artifact_upload_items set content_id = :content, "
                "provider_operation_reference = 'op' where id = :id",
                {"id": ids["item"], "content": ids["content"]},
            ),
            (
                "update artifact_upload_items set state = 'ready' where id = :id",
                {"id": ids["item"]},
            ),
            (
                "update artifact_replicas set verification_state = 'trusted' where id = :id",
                {"id": ids["replica"]},
            ),
            (
                "update artifact_replicas set retention_state = 'held' where id = :id",
                {"id": ids["replica"]},
            ),
            (
                "update artifact_replicas set availability_state = 'online' where id = :id",
                {"id": ids["replica"]},
            ),
            (
                "update artifact_replicas set integrity_state = 'trusted' where id = :id",
                {"id": ids["replica"]},
            ),
            (
                "update artifact_operation_receipts set operation = 'copy' where id = :id",
                {"id": ids["receipt"]},
            ),
            (
                "update artifact_operation_receipts set attempt_number = 0 where id = :id",
                {"id": ids["receipt"]},
            ),
            (
                "update artifact_operation_receipts set outcome = 'verified' where id = :id",
                {"id": ids["receipt"]},
            ),
            (
                "delete from artifact_operation_receipts where id = :id",
                {"id": ids["receipt"]},
            ),
            (
                "update artifact_bindings set logical_role = 'other' where id = :id",
                {"id": ids["binding"]},
            ),
            (
                "delete from artifact_bindings where id = :id",
                {"id": ids["binding_v2"]},
            ),
        )
        for statement, parameters in failing_statements:
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(text(statement), parameters)

        duplicate_statements = (
            (
                "insert into artifact_contents (id, sha256, byte_count) "
                "select :new_id, sha256, byte_count from artifact_contents where id = :id",
                {"new_id": str(uuid4()), "id": ids["content"]},
            ),
            (
                "insert into artifact_upload_items "
                "(id, session_id, logical_role, display_name, reserved_bytes, "
                "idempotency_key, request_digest, state, cas_version) "
                "select :new_id, session_id, logical_role, display_name, reserved_bytes, "
                "idempotency_key, request_digest, state, cas_version "
                "from artifact_upload_items where id = :id",
                {"new_id": str(uuid4()), "id": ids["item"]},
            ),
            (
                "insert into artifact_replicas "
                "(id, content_id, adapter, provider_artifact_id, verification_state, "
                "retention_state, availability_state, integrity_state) "
                "select :new_id, content_id, adapter, provider_artifact_id, "
                "verification_state, retention_state, availability_state, integrity_state "
                "from artifact_replicas where id = :id",
                {"new_id": str(uuid4()), "id": ids["replica"]},
            ),
            (
                "insert into artifact_operation_receipts "
                "(id, upload_item_id, replica_id, adapter, service_principal, operation, "
                "idempotency_key, request_digest, response_digest, provider_receipt_id, "
                "provider_operation_reference, outcome, attempt_number, correlation_id, "
                "provider_recorded_at, details) "
                "select :new_id, upload_item_id, replica_id, adapter, service_principal, "
                "operation, idempotency_key, request_digest, response_digest, "
                "provider_receipt_id || '-duplicate', provider_operation_reference, outcome, "
                "attempt_number, correlation_id || '-duplicate', provider_recorded_at, details "
                "from artifact_operation_receipts where id = :id",
                {"new_id": str(uuid4()), "id": ids["receipt"]},
            ),
        )
        for statement, parameters in duplicate_statements:
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(text(statement), parameters)

        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        insert into artifact_operation_receipts (
                            id, replica_id, adapter, service_principal, operation,
                            idempotency_key, request_digest, response_digest,
                            provider_receipt_id, provider_operation_reference, outcome, attempt_number,
                            correlation_id, retention_reference, retention_class,
                            provider_recorded_at, details
                        ) values (
                            :id, :replica, 'local', 'workstream.artifact', 'retain',
                            'retain-without-owner', :request_digest, :response_digest,
                            'provider-receipt-retain', 'provider-retain', 'retained', 1,
                            'correlation-retain',
                            'reference', 'standard', now(), '{}'::json
                        )
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "replica": ids["replica"],
                        "request_digest": "sha256:" + "3" * 64,
                        "response_digest": "sha256:" + "4" * 64,
                    },
                )
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        insert into artifact_bindings (
                            id, content_id, project_id, resource_type, resource_id,
                            logical_role, scope_version, actor_id, attribution_type,
                            supersedes_binding_id
                        ) values (
                            :id, :content, :project, 'submission', 'submission-1',
                            'packet', 3, 'actor', 'submitted_by', :wrong_predecessor
                        )
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "content": ids["content"],
                        "project": ids["project"],
                        "wrong_predecessor": ids["binding"],
                    },
                )
    finally:
        await engine.dispose()


async def _truncate_artifact_foundation(database_url: str) -> None:
    """Clear artifact rows after guarded-downgrade assertions."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    truncate table
                        artifact_operation_receipts,
                        artifact_replicas,
                        artifact_bindings,
                        artifact_upload_items,
                        artifact_contents,
                        artifact_upload_sessions
                    cascade
                    """
                )
            )
    finally:
        await engine.dispose()


async def _api_rate_control_schema(database_url: str) -> dict[str, set[str]]:
    """Return the exact public schema contract for the rate table."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            columns = (
                await connection.execute(
                    text(
                        "select column_name, data_type, is_nullable "
                        "from information_schema.columns "
                        "where table_schema = 'public' "
                        "and table_name = 'api_rate_control_counters'"
                    )
                )
            ).all()
            constraints = (
                await connection.execute(
                    text(
                        "select conname from pg_constraint "
                        "where conrelid = 'api_rate_control_counters'::regclass"
                    )
                )
            ).scalars()
            indexes = (
                await connection.execute(
                    text(
                        "select indexname from pg_indexes "
                        "where schemaname = 'public' "
                        "and tablename = 'api_rate_control_counters'"
                    )
                )
            ).scalars()
            return {
                "columns": {
                    f"{row.column_name}:{row.data_type}:{row.is_nullable}" for row in columns
                },
                "constraints": set(constraints),
                "indexes": set(indexes),
            }
    finally:
        await engine.dispose()


async def _seed_and_fetch_0016_artifact(database_url: str, artifact_id: str) -> dict[str, object]:
    """Seed one representative 0016 row and return its exact persisted value."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into artifact_contents "
                    "(id, sha256, byte_count, media_type, normalized_display_name) "
                    "values (:id, :sha256, 17, 'text/plain', 'rate-migration.txt')"
                ),
                {"id": artifact_id, "sha256": "sha256:" + "7" * 64},
            )
    finally:
        await engine.dispose()
    return await _fetch_0016_artifact(database_url, artifact_id)


async def _fetch_0016_artifact(database_url: str, artifact_id: str) -> dict[str, object]:
    """Fetch the representative 0016 artifact-domain row."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "select id, sha256, byte_count, media_type, "
                            "normalized_display_name from artifact_contents where id = :id"
                        ),
                        {"id": artifact_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)
    finally:
        await engine.dispose()


async def _insert_rate_control_until_released(
    database_url: str,
    digest: bytes,
    inserted: threading.Event,
    release: threading.Event,
) -> None:
    """Hold an uncommitted writer until the downgrade is waiting on its lock."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into api_rate_control_counters "
                    "(control_scope, key_digest, window_started_at, window_expires_at, "
                    "request_count, updated_at) values "
                    "('first_access', :digest, statement_timestamp(), "
                    "statement_timestamp() + interval '1 minute', 1, statement_timestamp())"
                ),
                {"digest": digest},
            )
            inserted.set()
            assert await asyncio.to_thread(release.wait, 5)
    finally:
        await engine.dispose()


async def _assert_api_rate_control_guards(database_url: str, digest: bytes) -> None:
    """Insert one valid counter and reject every malformed direct variant."""
    engine = create_async_engine(database_url)
    insert_sql = text(
        "insert into api_rate_control_counters "
        "(control_scope, key_digest, window_started_at, window_expires_at, "
        "request_count, updated_at) values "
        "(:scope, :digest, statement_timestamp(), "
        "statement_timestamp() + make_interval(secs => :seconds), "
        ":count, statement_timestamp())"
    )
    valid = {
        "scope": "first_access",
        "digest": digest,
        "seconds": 60,
        "count": 1,
    }
    try:
        async with engine.begin() as connection:
            await connection.execute(insert_sql, valid)

        invalid = [
            {**valid, "scope": "caller_supplied", "digest": bytes([1]) * 32},
            {**valid, "digest": bytes(31)},
            {**valid, "digest": bytes([2]) * 32, "count": 0},
            {**valid, "digest": bytes([3]) * 32, "seconds": 0},
            valid,
        ]
        for values in invalid:
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(insert_sql, values)
    finally:
        await engine.dispose()


async def _api_rate_control_state(database_url: str) -> dict[str, object]:
    """Return revision, table existence, and row count after migration actions."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            revision = await connection.scalar(text("select version_num from alembic_version"))
            exists = await connection.scalar(
                text("select to_regclass('public.api_rate_control_counters') is not null")
            )
            count = None
            if exists:
                count = await connection.scalar(
                    text("select count(*) from api_rate_control_counters")
                )
            return {
                "revision": revision,
                "table_exists": exists,
                "row_count": count,
            }
    finally:
        await engine.dispose()


async def _clear_api_rate_controls(database_url: str) -> None:
    """Clear rate rows only when the migration table exists."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("select to_regclass('public.api_rate_control_counters') is not null")
            )
            if exists:
                await connection.execute(text("delete from api_rate_control_counters"))
    finally:
        await engine.dispose()


async def _seed_and_fetch_legacy_audit(database_url: str, event_id: str) -> dict[str, object]:
    """Insert one prior-head lifecycle event and return its legacy fields."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id, entity_type, entity_id, event_type, from_status, to_status, "
                    "actor_id, external_subject, external_issuer, actor_roles, "
                    "claim_snapshot, auth_source, is_dev_auth, reason, event_payload) "
                    "values (:id, 'task', :entity_id, 'task_created', null, 'draft', "
                    "'legacy-actor', 'opaque-subject', 'https://issuer.example.test', "
                    "'[\"project_manager\"]'::json, '{\"bounded\": true}'::json, "
                    "'verified_token', false, 'created', '{\"source\": \"manual\"}'::json)"
                ),
                {"id": event_id, "entity_id": str(uuid4())},
            )
    finally:
        await engine.dispose()
    return await _fetch_audit_row(database_url, event_id)


async def _fetch_audit_row(database_url: str, event_id: str) -> dict[str, object]:
    """Fetch stable legacy fields and the authority domain when it exists."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            has_domain = await connection.scalar(
                text(
                    "select exists(select 1 from information_schema.columns "
                    "where table_name = 'audit_events' and column_name = 'event_domain')"
                )
            )
            domain = ", event_domain" if has_domain else ""
            row = (
                (
                    await connection.execute(
                        text(
                            "select id, entity_type, entity_id, event_type, from_status, "
                            "to_status, actor_id, external_subject, external_issuer, "
                            "actor_roles, claim_snapshot, auth_source, is_dev_auth, reason, "
                            f"event_payload{domain} from audit_events where id = :id"
                        ),
                        {"id": event_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)
    finally:
        await engine.dispose()


async def _authority_audit_schema(database_url: str) -> dict[str, object]:
    """Return the exact 0018 authority-audit schema surface."""
    new_columns = {
        "event_domain",
        "event_version",
        "occurred_at",
        "actor_ref_kind",
        "request_id",
        "correlation_id",
        "target_actor_ref_kind",
        "target_actor_ref",
        "matched_grant_id",
        "permission_id",
        "project_id",
        "resource_type",
        "resource_id",
        "target_ref_kind",
        "target_ref_id",
        "denial_code",
        "idempotency_reference",
        "invalidation_cause_event_id",
        "invalidation_target_kind",
        "invalidation_target_ref",
        "before_facts",
        "after_facts",
    }
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            columns = (
                (
                    await connection.execute(
                        text(
                            "select column_name, udt_name, is_nullable, column_default "
                            "from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'audit_events'"
                        )
                    )
                )
                .mappings()
                .all()
            )
            by_name = {row["column_name"]: row for row in columns}
            constraints = set(
                (
                    await connection.execute(
                        text(
                            "select conname from pg_constraint where "
                            "conrelid = 'audit_events'::regclass "
                            "and (conname like 'ck_audit_events_%' or "
                            "conname = 'fk_audit_events_invalidation_cause')"
                        )
                    )
                ).scalars()
            )
            indexes = set(
                (
                    await connection.execute(
                        text(
                            "select indexname from pg_indexes where schemaname = 'public' "
                            "and tablename = 'audit_events' and indexname in "
                            "('ix_audit_events_request_id', 'ix_audit_events_correlation_id', "
                            "'ix_audit_events_occurred_at', 'ix_audit_events_project_id', "
                            "'ix_audit_events_actor_ref')"
                        )
                    )
                ).scalars()
            )
            triggers = set(
                (
                    await connection.execute(
                        text(
                            "select tgname from pg_trigger where "
                            "tgrelid = 'audit_events'::regclass and not tgisinternal"
                        )
                    )
                ).scalars()
            )
            functions = set(
                (
                    await connection.execute(
                        text(
                            "select proname from pg_proc where proname in "
                            "('authority_facts_are_safe', 'authority_grant_facts_are_safe', "
                            "'authority_event_facts_are_safe', 'reject_audit_event_mutation', "
                            "'set_authority_audit_database_time')"
                        )
                    )
                ).scalars()
            )
            return {
                "columns": {
                    f"{name}:{by_name[name]['udt_name']}:{by_name[name]['is_nullable']}"
                    for name in new_columns
                },
                "constraints": constraints,
                "indexes": indexes,
                "triggers": triggers,
                "functions": functions,
                "legacy_default": "legacy_lifecycle"
                in (by_name["event_domain"]["column_default"] or ""),
                "external_identity_nullable": all(
                    by_name[name]["is_nullable"] == "YES"
                    for name in ("external_subject", "external_issuer")
                ),
            }
    finally:
        await engine.dispose()


async def _insert_authority_audit_fixture(database_url: str, event_id: str):
    """Insert valid authority evidence while proving database-owned time."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            return await connection.scalar(
                text(
                    "insert into audit_events "
                    "(id, entity_type, entity_id, event_type, actor_id, actor_roles, "
                    "claim_snapshot, auth_source, is_dev_auth, event_payload, event_domain, "
                    "event_version, occurred_at, actor_ref_kind, request_id, correlation_id, "
                    "permission_id, reason, after_facts) values (:id, "
                    "'authorization_decision', :id, 'SensitiveAuthorizationAllowed', "
                    "'workstream:system:bootstrap', '[]'::json, "
                    "'{}'::json, 'local_authority', false, '{}'::json, 'authority', 1, "
                    "'2000-01-01T00:00:00Z', 'system_principal', :request_id, "
                    ":correlation_id, 'actor.profile.read_any', "
                    "'authorization_evaluation', '{\"allowed\": true}') returning occurred_at"
                ),
                {
                    "id": event_id,
                    "request_id": str(uuid4()),
                    "correlation_id": str(uuid4()),
                },
            )
    finally:
        await engine.dispose()


async def _authority_audit_state(database_url: str) -> dict[str, object]:
    """Return migration revision and retained authority evidence count."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "authority_rows": await connection.scalar(
                    text("select count(*) from audit_events where event_domain = 'authority'")
                ),
            }
    finally:
        await engine.dispose()


async def _remove_authority_audit_fixture(database_url: str, event_id: str) -> None:
    """Perform explicit owner-only fixture cleanup under the documented lock."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            has_domain = await connection.scalar(
                text(
                    "select exists(select 1 from information_schema.columns "
                    "where table_name = 'audit_events' and column_name = 'event_domain')"
                )
            )
            if not has_domain:
                return
            await connection.execute(text("lock table audit_events in access exclusive mode"))
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_reject_update_delete")
            )
            await connection.execute(
                text("delete from audit_events where id = :id and event_domain = 'authority'"),
                {"id": event_id},
            )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_reject_update_delete")
            )
    finally:
        await engine.dispose()


async def _insert_pre_0019_forward_reference(
    database_url: str, event_id: str, reference: str
) -> None:
    """Seed the forward reference that 0019's NOT VALID FK must preserve."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into audit_events (id, entity_type, entity_id, event_type, actor_id, "
                    "actor_roles, claim_snapshot, auth_source, is_dev_auth, event_payload, "
                    "event_domain, event_version, actor_ref_kind, request_id, correlation_id, "
                    "permission_id, reason, idempotency_reference, after_facts) values "
                    "(:id, 'authorization_decision', :id, 'SensitiveAuthorizationAllowed', "
                    ":actor, '[]'::json, '{}'::json, 'local_authority', false, '{}'::json, "
                    "'authority', 1, 'actor_profile', :request, :correlation, "
                    "'actor.profile.read_any', 'authorization_evaluation', :reference, "
                    "'{\"allowed\": true}'::json)"
                ),
                {
                    "id": event_id,
                    "actor": str(uuid4()),
                    "request": str(uuid4()),
                    "correlation": str(uuid4()),
                    "reference": reference,
                },
            )
    finally:
        await engine.dispose()


async def _authority_idempotency_schema(database_url: str) -> dict[str, object]:
    """Return the exact 0019 schema and audit-link surface."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            columns = set(
                (
                    await connection.execute(
                        text(
                            "select column_name || ':' || udt_name || ':' || is_nullable "
                            "from information_schema.columns where table_schema='public' "
                            "and table_name='authority_idempotency_records'"
                        )
                    )
                ).scalars()
            )
            constraints = set(
                (
                    await connection.execute(
                        text(
                            "select conname from pg_constraint where "
                            "conrelid='authority_idempotency_records'::regclass"
                        )
                    )
                ).scalars()
            )
            triggers = set(
                (
                    await connection.execute(
                        text(
                            "select tgname from pg_trigger where "
                            "tgrelid='authority_idempotency_records'::regclass and not tgisinternal"
                        )
                    )
                ).scalars()
            )
            return {
                "columns": columns,
                "constraints": constraints,
                "triggers": triggers,
                "audit_fk_validated": await connection.scalar(
                    text(
                        "select convalidated from pg_constraint where "
                        "conname='fk_audit_events_authority_idempotency'"
                    )
                ),
                "audit_trigger": bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from pg_trigger where "
                            "tgname='audit_events_validate_idempotency' and not tgisinternal)"
                        )
                    )
                ),
            }
    finally:
        await engine.dispose()


async def _authority_idempotency_invalid_writes(database_url: str) -> dict[str, bool]:
    """Prove invalid initial state, durable pending, and new orphan fail closed."""
    engine = create_async_engine(database_url)
    results: dict[str, bool] = {}
    try:
        for name, statement, values in (
            (
                "initial_committed",
                "insert into authority_idempotency_records (id,idempotency_key,actor_ref_kind,"
                "actor_ref,operation,request_digest,status,response_resource_type,"
                "response_resource_id,response_http_status,committed_at) values "
                "(:id,:key,'actor_profile',:actor,'actor_profile.suspend',:digest,'committed',"
                "'actor_profile',:resource,200,statement_timestamp())",
                {
                    "id": str(uuid4()),
                    "key": str(uuid4()),
                    "actor": str(uuid4()),
                    "resource": str(uuid4()),
                    "digest": "sha256:" + "a" * 64,
                },
            ),
            (
                "pending_commit",
                "insert into authority_idempotency_records (id,idempotency_key,actor_ref_kind,"
                "actor_ref,operation,request_digest,status) values "
                "(:id,:key,'actor_profile',:actor,'actor_profile.suspend',:digest,'pending')",
                {
                    "id": str(uuid4()),
                    "key": str(uuid4()),
                    "actor": str(uuid4()),
                    "digest": "sha256:" + "a" * 64,
                },
            ),
            (
                "new_orphan",
                "insert into audit_events (id,entity_type,entity_id,event_type,actor_id,"
                "actor_roles,claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                "event_version,actor_ref_kind,request_id,correlation_id,permission_id,reason,"
                "idempotency_reference,after_facts) values (:id,'authorization_decision',:id,"
                "'SensitiveAuthorizationAllowed',:actor,'[]','{}','local_authority',false,'{}',"
                "'authority',1,'actor_profile',:request,:correlation,'actor.profile.read_any',"
                "'authorization_evaluation',:reference,cast(:facts as json))",
                {
                    "id": str(uuid4()),
                    "actor": str(uuid4()),
                    "request": str(uuid4()),
                    "correlation": str(uuid4()),
                    "reference": str(uuid4()),
                    "facts": json.dumps({"allowed": True}),
                },
            ),
        ):
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), values)
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False
        return results
    finally:
        await engine.dispose()


async def _insert_committed_authority_idempotency(
    database_url: str, record_id: str, actor_id: str, target_id: str
) -> None:
    """Insert one complete actor-suspension reservation and evidence pair."""
    engine = create_async_engine(database_url)
    success_id, invalidation_id = str(uuid4()), str(uuid4())
    request_id, correlation_id = str(uuid4()), str(uuid4())
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into authority_idempotency_records (id,idempotency_key,actor_ref_kind,"
                    "actor_ref,operation,request_digest,status) values "
                    "(:id,:key,'actor_profile',:actor,'actor_profile.suspend',:digest,'pending')"
                ),
                {
                    "id": record_id,
                    "key": str(uuid4()),
                    "actor": actor_id,
                    "digest": "sha256:" + "a" * 64,
                },
            )
            common = (
                "actor_roles,claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                "event_version,actor_ref_kind,request_id,correlation_id,permission_id,"
                "resource_type,resource_id,reason,idempotency_reference"
            )
            await connection.execute(
                text(
                    f"insert into audit_events (id,entity_type,entity_id,event_type,actor_id,{common},"
                    "target_ref_kind,target_ref_id,before_facts,after_facts) values "
                    "(:id,'actor_profile',:target,"
                    "'ActorProfileSuspended',:actor,'[]','{}','local_authority',false,'{}',"
                    "'authority',1,'actor_profile',:request,:correlation,'actor.profile.suspend',"
                    "'actor_profile',:target,'security_response',:record,"
                    "'actor_profile',:target,cast(:before_facts as json),cast(:after_facts as json))"
                ),
                {
                    "id": success_id,
                    "target": target_id,
                    "actor": actor_id,
                    "request": request_id,
                    "correlation": correlation_id,
                    "record": record_id,
                    "before_facts": json.dumps({"status": "active"}),
                    "after_facts": json.dumps({"status": "suspended"}),
                },
            )
            await connection.execute(
                text(
                    f"insert into audit_events (id,entity_type,entity_id,event_type,actor_id,{common},"
                    "invalidation_cause_event_id,invalidation_target_kind,invalidation_target_ref,"
                    "before_facts,after_facts) values (:id,'authority_invalidation',:id,"
                    "'AuthorityInvalidationRequested',:actor,'[]','{}','local_authority',false,'{}',"
                    "'authority',1,'actor_profile',:request,:correlation,'actor.profile.suspend',"
                    "'actor_profile',:target,'authority_state_changed',:record,:cause,'actor_profile',"
                    ":target,cast(:before_facts as json),cast(:after_facts as json))"
                ),
                {
                    "id": invalidation_id,
                    "target": target_id,
                    "actor": actor_id,
                    "request": request_id,
                    "correlation": correlation_id,
                    "record": record_id,
                    "cause": success_id,
                    "before_facts": json.dumps({"effective": True}),
                    "after_facts": json.dumps({"effective": False}),
                },
            )
            await connection.execute(
                text(
                    "update authority_idempotency_records set status='committed',"
                    "response_resource_type='actor_profile',response_resource_id=:target,"
                    "response_resource_version=1,response_http_status=200 where id=:id"
                ),
                {"id": record_id, "target": target_id},
            )
    finally:
        await engine.dispose()


async def _authority_idempotency_state(database_url: str, orphan_event: str) -> dict[str, object]:
    """Return revision, optional record count, and preserved orphan count."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text(
                    "select exists(select 1 from information_schema.tables where "
                    "table_name='authority_idempotency_records')"
                )
            )
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "records": await connection.scalar(
                    text("select count(*) from authority_idempotency_records")
                )
                if exists
                else None,
                "orphan": await connection.scalar(
                    text("select count(*) from audit_events where id=:id"), {"id": orphan_event}
                ),
            }
    finally:
        await engine.dispose()


async def _authority_idempotency_immutable_writes(
    database_url: str, record_id: str
) -> dict[str, bool]:
    """Prove committed rows are immutable and carry database-owned timestamps."""
    engine = create_async_engine(database_url)
    results: dict[str, bool] = {}
    try:
        statements = {
            "update": "update authority_idempotency_records set response_http_status=200 where id=:id",
            "delete": "delete from authority_idempotency_records where id=:id",
            "truncate": "truncate authority_idempotency_records",
        }
        for name, statement in statements.items():
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), {"id": record_id})
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False
        async with engine.connect() as connection:
            results["database_timestamps"] = bool(
                await connection.scalar(
                    text(
                        "select created_at is not null and committed_at is not null "
                        "and committed_at >= created_at from authority_idempotency_records "
                        "where id=:id"
                    ),
                    {"id": record_id},
                )
            )
        return results
    finally:
        await engine.dispose()


def _authority_downgrade_waits_for_writer(config: Config, database_url: str) -> bool:
    """Observe downgrade waiting for the deterministic writer-blocking table lock."""
    writer_ready = threading.Event()
    release_writer = threading.Event()

    async def hold_writer_lock() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(
                    text("lock table authority_idempotency_records in row exclusive mode")
                )
                writer_ready.set()
                await asyncio.to_thread(release_writer.wait)
                await transaction.rollback()
        finally:
            await engine.dispose()

    async def observe_downgrade_lock() -> bool:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                for _ in range(5000):
                    waiting = await connection.scalar(
                        text(
                            "select exists(select 1 from pg_locks locks "
                            "join pg_class relation on relation.oid=locks.relation "
                            "where relation.relname='authority_idempotency_records' "
                            "and locks.mode='AccessExclusiveLock' and not locks.granted)"
                        )
                    )
                    if waiting:
                        return True
                    await asyncio.sleep(0)
            return False
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(asyncio.run, hold_writer_lock())
        if not writer_ready.wait(timeout=5):
            release_writer.set()
            writer.result(timeout=5)
            return False
        downgrade = executor.submit(command.downgrade, config, "0018_authority_audit_evidence")
        try:
            observed = asyncio.run(observe_downgrade_lock())
        finally:
            release_writer.set()
        writer.result(timeout=10)
        downgrade.result(timeout=10)
        return observed


async def _remove_authority_idempotency_fixture(
    database_url: str, record_id: str, *, orphan_event: str | None
) -> None:
    """Owner-only cleanup for immutable 0019 fixtures."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text(
                    "select exists(select 1 from information_schema.tables where "
                    "table_name='authority_idempotency_records')"
                )
            )
            if exists:
                await connection.execute(
                    text("lock table authority_idempotency_records in access exclusive mode")
                )
            await connection.execute(text("lock table audit_events in access exclusive mode"))
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_reject_update_delete")
            )
            await connection.execute(
                text("delete from audit_events where idempotency_reference=:record"),
                {"record": record_id},
            )
            if orphan_event:
                await connection.execute(
                    text("delete from audit_events where id=:id"), {"id": orphan_event}
                )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_reject_update_delete")
            )
            if exists:
                await connection.execute(
                    text(
                        "alter table authority_idempotency_records disable trigger "
                        "authority_idempotency_guard"
                    )
                )
                await connection.execute(
                    text("delete from authority_idempotency_records where id=:id"),
                    {"id": record_id},
                )
                await connection.execute(
                    text(
                        "alter table authority_idempotency_records enable trigger "
                        "authority_idempotency_guard"
                    )
                )
    finally:
        await engine.dispose()


_ACTION_EVIDENCE_INSERT = text(
    "insert into audit_events "
    "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
    "auth_source, is_dev_auth, event_payload, event_domain, event_version, actor_ref_kind, "
    "request_id, correlation_id, permission_id, action_id, reason, denial_code, after_facts) "
    "values (:id, 'authorization_decision', :id, 'SensitiveAuthorizationDenied', "
    "'workstream:system:bootstrap', '[]'::json, '{}'::json, 'local_authority', false, "
    "'{}'::json, 'authority', 1, 'system_principal', :request_id, :correlation_id, "
    ":permission_id, :action_id, 'authorization_evaluation', 'permission_not_granted', "
    "'{\"allowed\": false}'::json)"
)

_ALLOWED_ACTION_EVIDENCE_INSERT = text(
    "insert into audit_events "
    "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
    "auth_source, is_dev_auth, event_payload, event_domain, event_version, actor_ref_kind, "
    "request_id, correlation_id, permission_id, action_id, reason, after_facts) "
    "values (:id, 'authorization_decision', :id, 'SensitiveAuthorizationAllowed', "
    "'workstream:system:bootstrap', '[]'::json, '{}'::json, 'local_authority', false, "
    "'{}'::json, 'authority', 1, 'system_principal', :request_id, :correlation_id, "
    ":permission_id, :action_id, 'authorization_evaluation', "
    "'{\"allowed\": true}'::json)"
)


def _action_evidence_values(action_id: str | None, permission_id: str) -> dict[str, str | None]:
    event_id = str(uuid4())
    return {
        "id": event_id,
        "request_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "permission_id": permission_id,
        "action_id": action_id,
    }


async def _authorization_action_schema(database_url: str) -> dict[str, object]:
    """Return the migration revision and action-evidence schema markers."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "action_column": bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from information_schema.columns "
                            "where table_schema='public' and table_name='audit_events' "
                            "and column_name='action_id')"
                        )
                    )
                ),
                "action_constraint": bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from pg_constraint where "
                            "conrelid='audit_events'::regclass and "
                            "conname='ck_audit_events_authorization_action_evidence')"
                        )
                    )
                ),
            }
    finally:
        await engine.dispose()


async def _authorization_action_row(database_url: str, event_id: str) -> dict[str, object]:
    """Fetch stable action evidence across both sides of migration 0021."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            has_action = await connection.scalar(
                text(
                    "select exists(select 1 from information_schema.columns "
                    "where table_schema='public' and table_name='audit_events' "
                    "and column_name='action_id')"
                )
            )
            action_column = ", action_id" if has_action else ""
            row = (
                (
                    await connection.execute(
                        text(
                            "select event_type, permission_id"
                            f"{action_column} from audit_events where id=:id"
                        ),
                        {"id": event_id},
                    )
                )
                .mappings()
                .one()
            )
            result = dict(row)
            result.setdefault("action_id", None)
            return result
    finally:
        await engine.dispose()


async def _assert_authorization_action_sql_pairs(
    database_url: str,
    *,
    definitions: tuple = ACTION_DEFINITIONS,
) -> None:
    """Prove exact pair closure without freezing typed availability in SQL."""
    engine = create_async_engine(database_url)
    try:
        for definition in definitions:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(
                    _ACTION_EVIDENCE_INSERT,
                    _action_evidence_values(
                        definition.action_id.value, definition.permission_id.value
                    ),
                )
                await transaction.rollback()

        for definition in definitions:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(
                    _ALLOWED_ACTION_EVIDENCE_INSERT,
                    _action_evidence_values(
                        definition.action_id.value, definition.permission_id.value
                    ),
                )
                await transaction.rollback()

        unknown_action = _action_evidence_values("unknown.action", "actor.profile.read_self")
        async with engine.connect() as connection:
            transaction = await connection.begin()
            with pytest.raises(IntegrityError):
                await connection.execute(_ACTION_EVIDENCE_INSERT, unknown_action)
            await transaction.rollback()

        for definition in definitions:
            wrong_permission_id = (
                "actor.profile.read_self"
                if definition.permission_id.value != "actor.profile.read_self"
                else "actor.profile.read_any"
            )
            wrong_permission = _action_evidence_values(
                definition.action_id.value, wrong_permission_id
            )
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(_ACTION_EVIDENCE_INSERT, wrong_permission)
                await transaction.rollback()

        for permission in NEW_PERMISSION_IDS:
            missing_action = _action_evidence_values(None, permission.value)
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(_ACTION_EVIDENCE_INSERT, missing_action)
                await transaction.rollback()

        nondecision = text(
            "insert into audit_events "
            "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
            "auth_source, is_dev_auth, event_payload, event_domain, event_version, "
            "actor_ref_kind, request_id, correlation_id, permission_id, action_id, reason, "
            "denial_code) values (:id, 'admin_role_grant', :entity_id, "
            "'AdminRoleGrantIssueDenied', 'workstream:system:bootstrap', '[]'::json, "
            "'{}'::json, 'local_authority', false, '{}'::json, 'authority', 1, "
            "'system_principal', :request_id, :correlation_id, 'actor.profile.read_self', "
            "'actor.profile.read_self', 'authorization_policy_denial', "
            "'permission_not_granted')"
        )
        async with engine.connect() as connection:
            transaction = await connection.begin()
            with pytest.raises(IntegrityError):
                await connection.execute(
                    nondecision,
                    {
                        "id": str(uuid4()),
                        "entity_id": str(uuid4()),
                        "request_id": str(uuid4()),
                        "correlation_id": str(uuid4()),
                    },
                )
            await transaction.rollback()
    finally:
        await engine.dispose()


async def _insert_authorization_action_event(database_url: str) -> str:
    """Commit one valid planned-action denial fixture."""
    values = _action_evidence_values("artifact.binding.read", "artifact.binding.read")
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(_ACTION_EVIDENCE_INSERT, values)
        return values["id"]
    finally:
        await engine.dispose()


async def _convert_to_permission_only_forward_evidence(database_url: str, event_id: str) -> None:
    """Simulate a pre-guard forward row to exercise the second rollback predicate."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("lock table audit_events in access exclusive mode"))
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_reject_update_delete")
            )
            await connection.execute(
                text(
                    "alter table audit_events drop constraint "
                    "ck_audit_events_authorization_action_evidence"
                )
            )
            await connection.execute(
                text("update audit_events set action_id=null where id=:id"),
                {"id": event_id},
            )
            await connection.execute(
                text(
                    "alter table audit_events add constraint "
                    "ck_audit_events_authorization_action_evidence "
                    "check (action_id is null) not valid"
                )
            )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_reject_update_delete")
            )
    finally:
        await engine.dispose()


async def _insert_forward_permission_reference(
    database_url: str,
    cause_event_id: str,
    *,
    reference_field: str,
) -> str:
    """Commit one new permission-registry reference without an action ID."""
    event_id = str(uuid4())
    values = {
        "id": event_id,
        "request_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "permission": "artifact.binding.read",
        "cause_id": cause_event_id,
    }
    if reference_field == "target":
        statement = text(
            "insert into audit_events "
            "(id, entity_type, entity_id, event_type, actor_id, actor_roles, "
            "claim_snapshot, auth_source, is_dev_auth, event_payload, event_domain, "
            "event_version, actor_ref_kind, request_id, correlation_id, permission_id, "
            "target_ref_kind, target_ref_id, reason, after_facts) values "
            "(:id, 'authorization_decision', :id, 'SensitiveAuthorizationAllowed', "
            "'workstream:system:bootstrap', '[]'::json, '{}'::json, 'local_authority', "
            "false, '{}'::json, 'authority', 1, 'system_principal', :request_id, "
            ":correlation_id, 'actor.profile.read_any', 'permission_registry', "
            ":permission, 'authorization_evaluation', '{\"allowed\": true}'::json)"
        )
    elif reference_field == "invalidation":
        statement = text(
            "insert into audit_events "
            "(id, entity_type, entity_id, event_type, actor_id, actor_roles, "
            "claim_snapshot, auth_source, is_dev_auth, event_payload, event_domain, "
            "event_version, actor_ref_kind, request_id, correlation_id, "
            "invalidation_cause_event_id, invalidation_target_kind, "
            "invalidation_target_ref, reason, before_facts, after_facts) values "
            "(:id, 'authority_invalidation', :id, 'AuthorityInvalidationRequested', "
            "'workstream:system:bootstrap', '[]'::json, '{}'::json, 'local_authority', "
            "false, '{}'::json, 'authority', 1, 'system_principal', :request_id, "
            ":correlation_id, :cause_id, 'permission_registry', :permission, "
            "'authority_state_changed', '{\"effective\": true}'::json, "
            "'{\"effective\": false}'::json)"
        )
    else:
        raise ValueError(f"unsupported reference field: {reference_field}")

    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            if reference_field == "invalidation":
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger audit_events_validate_idempotency"
                    )
                )
            await connection.execute(statement, values)
            if reference_field == "invalidation":
                await connection.execute(
                    text(
                        "alter table audit_events enable trigger audit_events_validate_idempotency"
                    )
                )
        return event_id
    finally:
        await engine.dispose()


async def _assert_historical_permission_registry(database_url: str) -> None:
    """Prove downgrade restores every historical permission and rejects every new one."""
    statement = text(
        "insert into audit_events "
        "(id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot, "
        "auth_source, is_dev_auth, event_payload, event_domain, event_version, "
        "actor_ref_kind, request_id, correlation_id, permission_id, reason, after_facts) "
        "values (:id, 'authorization_decision', :id, 'SensitiveAuthorizationAllowed', "
        "'workstream:system:bootstrap', '[]'::json, '{}'::json, 'local_authority', false, "
        "'{}'::json, 'authority', 1, 'system_principal', :request_id, :correlation_id, "
        ":permission_id, 'authorization_evaluation', '{\"allowed\": true}'::json)"
    )
    engine = create_async_engine(database_url)
    try:
        for permission in HISTORICAL_PERMISSION_IDS:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(statement, _action_evidence_values(None, permission.value))
                await transaction.rollback()

        for permission in NEW_PERMISSION_IDS:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        statement, _action_evidence_values(None, permission.value)
                    )
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _remove_authorization_action_events(database_url: str, event_ids: list[str]) -> None:
    """Owner-only cleanup for immutable action-evidence test fixtures."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("lock table audit_events in access exclusive mode"))
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_reject_update_delete")
            )
            await connection.execute(
                text("delete from audit_events where id = any(:ids)"),
                {"ids": event_ids},
            )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_reject_update_delete")
            )
    finally:
        await engine.dispose()


def _action_downgrade_waits_for_insert(config: Config, database_url: str) -> tuple[bool, str]:
    """Prove an insert cannot pass between the downgrade check and destructive DDL."""
    writer_ready = threading.Event()
    release_writer = threading.Event()
    values = _action_evidence_values("artifact.binding.read", "artifact.binding.read")

    async def hold_uncommitted_insert() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(_ACTION_EVIDENCE_INSERT, values)
                writer_ready.set()
                await asyncio.to_thread(release_writer.wait)
                await transaction.commit()
        finally:
            await engine.dispose()

    async def observe_downgrade_lock() -> bool:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                for _ in range(5000):
                    waiting = await connection.scalar(
                        text(
                            "select exists(select 1 from pg_locks locks "
                            "join pg_class relation on relation.oid=locks.relation "
                            "where relation.relname='audit_events' "
                            "and locks.mode='AccessExclusiveLock' and not locks.granted)"
                        )
                    )
                    if waiting:
                        return True
                    await asyncio.sleep(0)
            return False
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(asyncio.run, hold_uncommitted_insert())
        if not writer_ready.wait(timeout=5):
            release_writer.set()
            writer.result(timeout=5)
            return False, values["id"]
        downgrade = executor.submit(command.downgrade, config, "0020_canonical_actor_profile")
        try:
            observed = asyncio.run(observe_downgrade_lock())
        finally:
            release_writer.set()
        writer.result(timeout=10)
        with pytest.raises(
            RuntimeError,
            match="^cannot downgrade non-empty authorization action evidence$",
        ):
            downgrade.result(timeout=10)
        return observed, values["id"]


async def _insert_orphan_admin_evidence(database_url: str, event_type: str) -> None:
    engine = create_async_engine(database_url)
    event_id, target_id = str(uuid4()), str(uuid4())
    denied = event_type != "InitialAccessAdministratorBootstrapped"
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                    "auth_source,is_dev_auth,event_payload,event_domain,event_version,"
                    "actor_ref_kind,request_id,correlation_id,target_actor_ref_kind,"
                    "target_actor_ref,resource_type,resource_id,target_ref_kind,target_ref_id,"
                    "reason,denial_code,after_facts) values "
                    "(:id,'admin_role_grant',:id,:event_type,"
                    "'workstream:system:bootstrap','[]','{}','local_authority',false,'{}',"
                    "'authority',1,'system_principal',:request,:correlation,'actor_profile',"
                    ":target,'admin_role_grant',:id,'admin_role_grant',:id,"
                    ":reason,:denial_code,cast(:facts as json))"
                ),
                {
                    "id": event_id,
                    "event_type": event_type,
                    "target": target_id,
                    "request": str(uuid4()),
                    "correlation": str(uuid4()),
                    "reason": "authorization_policy_denial" if denied else "initial_access_bootstrap",
                    "denial_code": "permission_not_granted" if denied else None,
                    "facts": None
                    if denied
                    else json.dumps(
                        {
                            "status": "active",
                            "role": "access_administrator",
                            "scope_type": "system",
                            "effective": True,
                        }
                    ),
                },
            )
    finally:
        await engine.dispose()


async def _insert_orphan_admin_idempotency(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table authority_idempotency_records disable trigger user")
            )
            await connection.execute(
                text(
                    "insert into authority_idempotency_records "
                    "(id,idempotency_key,actor_ref_kind,actor_ref,operation,request_digest,status) "
                    "values (:id,:key,'actor_profile',:actor,'admin_role_grant.issue',"
                    ":digest,'pending')"
                ),
                {
                    "id": str(uuid4()),
                    "key": str(uuid4()),
                    "actor": str(uuid4()),
                    "digest": "sha256:" + "a" * 64,
                },
            )
            await connection.execute(
                text("alter table authority_idempotency_records enable trigger user")
            )
    finally:
        await engine.dispose()


async def _clear_orphan_admin_state(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("alter table audit_events disable trigger user"))
            await connection.execute(
                text("alter table authority_idempotency_records disable trigger user")
            )
            await connection.execute(
                text(
                    "delete from audit_events where event_type in "
                    "('InitialAccessAdministratorBootstrapped','AdminRoleGrantIssued',"
                    "'AdminRoleGrantRevoked','AdminRoleGrantIssueDenied',"
                    "'LastAccessAdministratorOperationDenied')"
                )
            )
            await connection.execute(
                text(
                    "delete from authority_idempotency_records "
                    "where operation like 'admin_role_grant.%'"
                )
            )
            await connection.execute(
                text("alter table authority_idempotency_records enable trigger user")
            )
            await connection.execute(text("alter table audit_events enable trigger user"))
    finally:
        await engine.dispose()


async def _admin_authority_schema(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            control = (
                await connection.execute(
                    text(
                        "select bootstrap_completed,bootstrap_grant_id,version "
                        "from authority_control where id=1"
                    )
                )
            ).one()
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "grant_table": bool(
                    await connection.scalar(
                        text("select to_regclass('public.admin_role_grants') is not null")
                    )
                ),
                "control": tuple(control),
            }
    finally:
        await engine.dispose()


async def _exercise_admin_authority_guards(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    admin_id = actor_id_from_external_identity("https://identity.test", "auth08-admin")
    target_id = actor_id_from_external_identity("https://identity.test", "auth08-target")
    service_id = actor_id_from_external_identity("https://identity.test", "auth08-service")
    bootstrap_id, grant_id = str(uuid4()), str(uuid4())
    results: dict[str, object] = {}
    try:
        async with engine.begin() as connection:
            await _insert_canonical_actor(connection, admin_id, "auth08-admin", "human")
            await _insert_canonical_actor(connection, target_id, "auth08-target", "human")
            await _insert_canonical_actor(connection, service_id, "auth08-service", "service")

        insert_grant = (
            "insert into admin_role_grants "
            "(id,target_actor_profile_id,role,scope_type,status,version,"
            "granted_by_actor_profile_id,granted_by_system_principal,"
            "granted_by_admin_role_grant_id,grant_reason) values "
            "(:id,:target,:role,:scope,'active',1,:actor,:principal,:authorizer,:reason)"
        )
        invalid_cases = (
            (
                "service_target_rejected",
                {
                    "id": str(uuid4()),
                    "target": service_id,
                    "role": "access_administrator",
                    "scope": "system",
                    "actor": None,
                    "principal": "workstream:system:bootstrap",
                    "authorizer": None,
                    "reason": "Invalid service target",
                },
            ),
            (
                "missing_authorizer_rejected",
                {
                    "id": str(uuid4()),
                    "target": target_id,
                    "role": "operator",
                    "scope": "system",
                    "actor": admin_id,
                    "principal": None,
                    "authorizer": None,
                    "reason": "Missing authorizer",
                },
            ),
            (
                "mixed_bootstrap_attribution_rejected",
                {
                    "id": str(uuid4()),
                    "target": admin_id,
                    "role": "access_administrator",
                    "scope": "system",
                    "actor": admin_id,
                    "principal": "workstream:system:bootstrap",
                    "authorizer": None,
                    "reason": "Mixed attribution",
                },
            ),
        )
        for name, values in invalid_cases:
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(insert_grant), values)
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False

        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(insert_grant),
                    {
                        "id": str(uuid4()),
                        "target": admin_id,
                        "role": "access_administrator",
                        "scope": "system",
                        "actor": None,
                        "principal": "workstream:system:bootstrap",
                        "authorizer": None,
                        "reason": "Orphan bootstrap",
                    },
                )
        except DBAPIError:
            results["orphan_bootstrap_commit_rejected"] = True
        else:
            results["orphan_bootstrap_commit_rejected"] = False

        mismatched_bootstrap_id, mismatched_grant_id = str(uuid4()), str(uuid4())
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(insert_grant),
                    {
                        "id": mismatched_bootstrap_id,
                        "target": admin_id,
                        "role": "access_administrator",
                        "scope": "system",
                        "actor": None,
                        "principal": "workstream:system:bootstrap",
                        "authorizer": None,
                        "reason": "Mismatched bootstrap",
                    },
                )
                await connection.execute(
                    text(insert_grant),
                    {
                        "id": mismatched_grant_id,
                        "target": target_id,
                        "role": "operator",
                        "scope": "system",
                        "actor": admin_id,
                        "principal": None,
                        "authorizer": mismatched_bootstrap_id,
                        "reason": "Mismatched control target",
                    },
                )
                await connection.execute(
                    text(
                        "update authority_control set bootstrap_completed=true,"
                        "bootstrap_grant_id=:grant,version=1 where id=1"
                    ),
                    {"grant": mismatched_grant_id},
                )
        except DBAPIError:
            results["mismatched_bootstrap_control_rejected"] = True
        else:
            results["mismatched_bootstrap_control_rejected"] = False

        async with engine.begin() as connection:
            await connection.execute(
                text(insert_grant),
                {
                    "id": bootstrap_id,
                    "target": admin_id,
                    "role": "access_administrator",
                    "scope": "system",
                    "actor": None,
                    "principal": "workstream:system:bootstrap",
                    "authorizer": None,
                    "reason": "Initial Access Administrator bootstrap",
                },
            )
            await connection.execute(
                text(
                    "update authority_control set bootstrap_completed=true,"
                    "bootstrap_grant_id=:grant,version=1 where id=1"
                ),
                {"grant": bootstrap_id},
            )

        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(insert_grant),
                    {
                        "id": str(uuid4()),
                        "target": target_id,
                        "role": "access_administrator",
                        "scope": "system",
                        "actor": None,
                        "principal": "workstream:system:bootstrap",
                        "authorizer": None,
                        "reason": "Second bootstrap",
                    },
                )
        except DBAPIError:
            results["second_bootstrap_rejected"] = True
        else:
            results["second_bootstrap_rejected"] = False

        async with engine.begin() as connection:
            await connection.execute(
                text(insert_grant),
                {
                    "id": grant_id,
                    "target": target_id,
                    "role": "operator",
                    "scope": "system",
                    "actor": admin_id,
                    "principal": None,
                    "authorizer": bootstrap_id,
                    "reason": "Operations assignment",
                },
            )

        immutable_columns = (
            "id,target_actor_profile_id,role,scope_type,scope_project_id,"
            "granted_by_actor_profile_id,granted_by_system_principal,"
            "granted_by_admin_role_grant_id,grant_reason,granted_at"
        )
        async with engine.connect() as connection:
            immutable_before = tuple(
                (
                    await connection.execute(
                        text(
                            f"select {immutable_columns} from admin_role_grants where id=:id"
                        ),
                        {"id": grant_id},
                    )
                ).one()
            )

        guarded_writes = (
            (
                "immutable_reason_rejected",
                "update admin_role_grants set grant_reason='Changed' where id=:id",
                {"id": grant_id},
            ),
            (
                "delete_rejected",
                "delete from admin_role_grants where id=:id",
                {"id": grant_id},
            ),
            (
                "truncate_rejected",
                "truncate table admin_role_grants",
                {},
            ),
            (
                "control_reset_rejected",
                "update authority_control set bootstrap_completed=false,"
                "bootstrap_grant_id=null,version=0 where id=1",
                {},
            ),
        )
        immutable_updates = (
            ("id", str(uuid4())),
            ("target_actor_profile_id", admin_id),
            ("role", "finance_authority"),
            ("scope_type", "project"),
            ("scope_project_id", str(uuid4())),
            ("granted_by_actor_profile_id", target_id),
            ("granted_by_system_principal", "workstream:system:bootstrap"),
            ("granted_by_admin_role_grant_id", grant_id),
            ("grant_reason", "Changed provenance"),
        )
        immutable_rejected = True
        for column, value in immutable_updates:
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(f"update admin_role_grants set {column}=:value where id=:id"),
                        {"id": grant_id, "value": value},
                    )
            except DBAPIError:
                continue
            immutable_rejected = False
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update admin_role_grants set granted_at=granted_at + interval '1 second' "
                        "where id=:id"
                    ),
                    {"id": grant_id},
                )
        except DBAPIError:
            pass
        else:
            immutable_rejected = False
        results["immutable_provenance_rejected"] = immutable_rejected
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update admin_role_grants set status='revoked',version=2 where id=:id"
                    ),
                    {"id": grant_id},
                )
        except DBAPIError:
            results["incomplete_revocation_rejected"] = True
        else:
            results["incomplete_revocation_rejected"] = False

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update admin_role_grants set status='revoked',version=2,"
                    "revoked_by_actor_profile_id=:actor,"
                    "revoked_by_admin_role_grant_id=:authorizer,"
                    "revoked_reason='Rotation ended',revoked_at=clock_timestamp() where id=:id"
                ),
                {"id": grant_id, "actor": admin_id, "authorizer": bootstrap_id},
            )
        for name, statement, values in guarded_writes:
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), values)
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False

        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        f"select {immutable_columns},status,version,revoked_reason "
                        "from admin_role_grants where id=:id"
                    ),
                    {"id": grant_id},
                )
            ).one()
            immutable_after = tuple(row)[: len(immutable_before)]
            results.update(
                immutable_provenance_preserved=immutable_after == immutable_before,
                revoked_status=row.status,
                revoked_version=row.version,
                grant_reason=row.grant_reason,
                revoked_reason=row.revoked_reason,
                bootstrap_completed=bool(
                    await connection.scalar(
                        text("select bootstrap_completed from authority_control where id=1")
                    )
                ),
            )
        return results
    finally:
        await engine.dispose()


async def _clear_admin_authority_guard_fixtures(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("alter table authority_control disable trigger user"))
            await connection.execute(text("alter table admin_role_grants disable trigger user"))
            await connection.execute(
                text(
                    "update authority_control set bootstrap_completed=false,"
                    "bootstrap_grant_id=null,version=0 where id=1"
                )
            )
            await connection.execute(text("delete from admin_role_grants"))
            await connection.execute(text("alter table admin_role_grants enable trigger user"))
            await connection.execute(text("alter table authority_control enable trigger user"))
    finally:
        await engine.dispose()


async def _current_revision(database_url: str) -> str:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return str(await connection.scalar(text("select version_num from alembic_version")))
    finally:
        await engine.dispose()


async def _insert_service_actor_before_fixed_identity(
    database_url: str,
    actor_profile_id: str,
    subject: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await _insert_canonical_actor(connection, actor_profile_id, subject, "service")
    finally:
        await engine.dispose()


async def _write_service_identity_envelope(database_url: str, path: Path) -> None:
    engine = create_async_engine(database_url)
    try:
        snapshot = await snapshot_existing_service_rows(engine)
        row = snapshot.rows[0]
        draft = ServiceActorIdentityMappingDraft(
            schema_version=1,
            mappings=(
                ServiceActorIdentityMapping(
                    actor_profile_id=row.actor_profile_id,
                    issuer=row.issuer,
                    subject=row.subject,
                    service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                ),
            ),
        )
        envelope = build_service_identity_envelope(
            draft,
            snapshot.rows,
            database_binding=snapshot.database_binding,
            generated_at="2026-07-16T12:00:00Z",
        )
        publish_service_identity_envelope(path, envelope)
    finally:
        await engine.dispose()


async def _service_identity_schema(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            state = (
                await connection.execute(
                    text(
                        "select service_identity_mapped_count,"
                        "service_identity_source_row_set_sha256,"
                        "service_identity_manifest_sha256,"
                        "service_identity_envelope_sha256 "
                        "from actor_profile_migration_state where id=1"
                    )
                )
            ).one()
            result: dict[str, object] = {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "service_identity_column": bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from information_schema.columns "
                            "where table_name='actor_profiles' and "
                            "column_name='service_identity')"
                        )
                    )
                ),
                "mapped_count": state.service_identity_mapped_count,
                "source_digest": state.service_identity_source_row_set_sha256,
                "manifest_digest": state.service_identity_manifest_sha256,
                "envelope_digest": state.service_identity_envelope_sha256,
                "private_evidence_columns": bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from information_schema.columns "
                            "where table_name='actor_profile_migration_state' and "
                            "column_name in ('actor_profile_id','issuer','subject','file_path'))"
                        )
                    )
                ),
            }
            service_identity = await connection.scalar(
                text(
                    "select service_identity from actor_profiles "
                    "where actor_kind='service' limit 1"
                )
            )
            if service_identity is not None:
                result["service_identity"] = service_identity
            if state.service_identity_mapped_count == 0:
                result.pop("source_digest")
                result.pop("private_evidence_columns")
            return result
    finally:
        await engine.dispose()


async def _service_identity_guards(
    database_url: str,
    actor_profile_id: str,
) -> dict[str, bool]:
    engine = create_async_engine(database_url)
    results: dict[str, bool] = {}
    cases = (
        (
            "identity_update_rejected",
            "update actor_profiles set service_identity='workstream.artifact.scheduler' "
            "where id=:actor_id",
            {"actor_id": actor_profile_id},
        ),
        (
            "kind_update_rejected",
            "update actor_profiles set actor_kind='human',"
            "provisioning_method='automatic_first_access',service_identity=null "
            "where id=:actor_id",
            {"actor_id": actor_profile_id},
        ),
        (
            "human_identity_rejected",
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
            "values (:id,'human','active','automatic_first_access',"
            "'workstream.artifact.scheduler',:id)",
            {"id": str(uuid4())},
        ),
        (
            "unknown_identity_rejected",
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
            "values (:id,'service','active','manual_service_provisioning',"
            "'workstream.artifact.unknown',:id)",
            {"id": str(uuid4())},
        ),
        (
            "duplicate_identity_rejected",
            "insert into actor_profiles "
            "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
            "values (:id,'service','active','manual_service_provisioning',"
            "'workstream.artifact.verifier',:id)",
            {"id": str(uuid4())},
        ),
    )
    try:
        for name, statement, values in cases:
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), values)
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False
        return results
    finally:
        await engine.dispose()


async def _service_identity_evidence_guards(database_url: str) -> dict[str, bool]:
    engine = create_async_engine(database_url)
    results: dict[str, bool] = {}
    immutable_cases = {
        "update_rejected": (
            "update actor_profile_migration_state set "
            "service_identity_mapped_count=service_identity_mapped_count where id=1"
        ),
        "delete_rejected": "delete from actor_profile_migration_state where id=1",
        "truncate_rejected": "truncate actor_profile_migration_state",
    }
    constraint_cases = {
        "invalid_count_rejected": (
            "update actor_profile_migration_state set service_identity_mapped_count=8 where id=1"
        ),
        "invalid_source_digest_rejected": (
            "update actor_profile_migration_state set "
            "service_identity_source_row_set_sha256='not-a-digest' where id=1"
        ),
        "invalid_manifest_digest_rejected": (
            "update actor_profile_migration_state set "
            "service_identity_manifest_sha256='not-a-digest' where id=1"
        ),
        "invalid_database_binding_rejected": (
            "update actor_profile_migration_state set "
            "service_identity_database_binding='postgres-v1:not-a-digest' where id=1"
        ),
    }
    try:
        for name, statement in immutable_cases.items():
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement))
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False
        for name, statement in constraint_cases.items():
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "alter table actor_profile_migration_state disable trigger user"
                        )
                    )
                    await connection.execute(text(statement))
            except DBAPIError:
                results[name] = True
            else:
                results[name] = False
        return results
    finally:
        await engine.dispose()


async def _remove_fixed_service_actor(database_url: str, actor_profile_id: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("alter table actor_identity_links disable trigger user"))
            await connection.execute(text("alter table actor_profiles disable trigger user"))
            await connection.execute(
                text("delete from actor_identity_links where actor_profile_id=:actor_id"),
                {"actor_id": actor_profile_id},
            )
            await connection.execute(
                text("delete from actor_profiles where id=:actor_id"),
                {"actor_id": actor_profile_id},
            )
            await connection.execute(text("alter table actor_profiles enable trigger user"))
            await connection.execute(text("alter table actor_identity_links enable trigger user"))
    finally:
        await engine.dispose()


async def _seed_contributor_prior_head(
    database_url: str,
    *,
    assignment_values: tuple[str, ...],
    submission_values: tuple[str, ...],
    human_ids: tuple[str, ...] = (),
) -> dict[str, tuple[str, ...] | str]:
    engine = create_async_engine(database_url)
    assignment_ids = tuple(str(uuid4()) for _ in assignment_values)
    runtime_ids = {
        name: str(uuid4())
        for name in (
            "project",
            "guide",
            "snapshot",
            "submission_policy",
            "effective_policy",
            "pre_submit_policy",
            "policy",
            "review_policy",
            "revision_policy",
            "payment_policy",
            "task",
            "submission",
            "run",
        )
    }
    submission_ids = (runtime_ids["submission"],) + tuple(
        str(uuid4()) for _ in submission_values[1:]
    )
    service_id = str(uuid4())
    try:
        await _seed_artifact_prior_head_runtime_rows(database_url, runtime_ids)
        async with engine.begin() as connection:
            for human_id in human_ids:
                await connection.execute(
                    text(
                        "insert into actor_profiles "
                        "(id,actor_kind,status,provisioning_method,created_by) values "
                        "(:id,'human','active','automatic_first_access',:id)"
                    ),
                    {"id": human_id},
                )
                await connection.execute(
                    text(
                        "insert into actor_identity_links "
                        "(id,actor_profile_id,issuer,subject,subject_kind,status,"
                        "linked_by,last_verified_at) values "
                        "(:link,:actor,'https://identity.test',:subject,'human',"
                        "'active',:actor,clock_timestamp())"
                    ),
                    {
                        "link": str(uuid4()),
                        "actor": human_id,
                        "subject": f"contributor-{human_id}",
                    },
                )
            await connection.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                    "values (:id,'service','active','manual_service_provisioning',"
                    ":identity,:id)"
                ),
                {
                    "id": service_id,
                    "identity": ServiceIdentity.ARTIFACT_VERIFIER.value,
                },
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links "
                    "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                    "last_verified_at) values "
                    "(:link,:actor,'workstream-local',:subject,'service','active',"
                    ":actor,clock_timestamp())"
                ),
                {
                    "link": str(uuid4()),
                    "actor": service_id,
                    "subject": ServiceIdentity.ARTIFACT_VERIFIER.value,
                },
            )
            resolved_assignment_values = tuple(
                service_id if value == "service" else value
                for value in assignment_values
            )
            for index, value in enumerate(assignment_values):
                await connection.execute(
                    text(
                        "insert into task_assignments "
                        "(id,task_id,worker_id,assigned_by,status) values "
                        "(:id,:task,:actor,'migration-test',:status)"
                    ),
                    {
                        "id": assignment_ids[index],
                        "task": runtime_ids["task"],
                        "actor": resolved_assignment_values[index],
                        "status": "active" if index == 0 else "released",
                    },
                )
            resolved_submission_values = tuple(
                service_id if value == "service" else value for value in submission_values
            )
            await connection.execute(
                text("update submissions set worker_id=:actor where id=:id"),
                {
                    "id": submission_ids[0],
                    "actor": resolved_submission_values[0],
                },
            )
            for index, value in enumerate(resolved_submission_values[1:], start=1):
                await connection.execute(
                    text(
                        "insert into submissions "
                        "(id,task_id,worker_id,version,status,summary,package_uri,"
                        "package_hash,artifact_hash_manifest,worker_attestation,"
                        "locked_guide_version,locked_post_submit_checker_policy_id,"
                        "locked_post_submit_checker_policy_version,"
                        "locked_post_submit_checker_policy_hash,"
                        "locked_post_submit_checker_policy_body,"
                        "locked_review_policy_version,locked_revision_policy_version,"
                        "locked_payment_policy_version,locked_guide_source_snapshot_id,"
                        "locked_guide_source_snapshot_hash,"
                        "locked_effective_project_submission_artifact_policy_id,"
                        "locked_effective_project_submission_artifact_policy_hash,"
                        "locked_pre_submit_checker_policy_id,"
                        "locked_pre_submit_checker_bundle_hash,submitted_at,locked_at,"
                        "supersedes_submission_id) "
                        "select :id,task_id,:actor,:version,"
                        "status,summary,package_uri,package_hash,artifact_hash_manifest,"
                        "worker_attestation,locked_guide_version,"
                        "locked_post_submit_checker_policy_id,"
                        "locked_post_submit_checker_policy_version,"
                        "locked_post_submit_checker_policy_hash,"
                        "locked_post_submit_checker_policy_body,"
                        "locked_review_policy_version,locked_revision_policy_version,"
                        "locked_payment_policy_version,locked_guide_source_snapshot_id,"
                        "locked_guide_source_snapshot_hash,"
                        "locked_effective_project_submission_artifact_policy_id,"
                        "locked_effective_project_submission_artifact_policy_hash,"
                        "locked_pre_submit_checker_policy_id,"
                        "locked_pre_submit_checker_bundle_hash,submitted_at,locked_at,null "
                        "from submissions where id=:source"
                    ),
                    {
                        "id": submission_ids[index],
                        "actor": value,
                        "version": index + 1,
                        "source": submission_ids[0],
                    },
                )
        return {
            "assignment_ids": assignment_ids,
            "submission_ids": submission_ids,
            "assignment_task": runtime_ids["task"],
            "submission_task": runtime_ids["task"],
            "service_id": service_id,
        }
    finally:
        await engine.dispose()


async def _clear_contributor_migration_fixtures(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table actor_identity_links disable trigger user")
            )
            await connection.execute(text("alter table actor_profiles disable trigger user"))
            await connection.execute(text("delete from actor_identity_links"))
            await connection.execute(text("delete from actor_profiles"))
            await connection.execute(text("alter table actor_profiles enable trigger user"))
            await connection.execute(
                text("alter table actor_identity_links enable trigger user")
            )
    finally:
        await engine.dispose()


async def _contributor_foundation_shape(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            async def column(table: str) -> tuple[str, int]:
                row = (
                    await connection.execute(
                        text(
                            "select column_name,character_maximum_length "
                            "from information_schema.columns where table_schema='public' "
                            "and table_name=:table and column_name in "
                            "('worker_id','contributor_id')"
                        ),
                        {"table": table},
                    )
                ).one()
                return str(row[0]), int(row[1])

            async def index(table: str) -> str:
                value = await connection.scalar(
                    text(
                        "select indexname from pg_indexes where schemaname='public' "
                        "and tablename=:table and indexname like "
                        "'ix_%_worker_id' or schemaname='public' and tablename=:table "
                        "and indexname like 'ix_%_contributor_id'"
                    ),
                    {"table": table},
                )
                assert value is not None
                return str(value)

            function_exists = bool(
                await connection.scalar(
                    text(
                        "select to_regprocedure("
                        "'public.require_human_actor_profile_reference()') is not null"
                    )
                )
            )
            foreign_keys = tuple(
                str(row)
                for row in (
                    await connection.execute(
                        text(
                            "select conname from pg_constraint where conname in "
                            "('fk_task_assignments_contributor_id_actor_profiles',"
                            "'fk_submissions_contributor_id_actor_profiles') order by conname"
                        )
                    )
                ).scalars()
            )
            triggers = tuple(
                str(row)
                for row in (
                    await connection.execute(
                        text(
                            "select tgname from pg_trigger where not tgisinternal and tgname in "
                            "('task_assignments_contributor_human',"
                            "'submissions_contributor_human') order by tgname"
                        )
                    )
                ).scalars()
            )
            assignment_field = "contributor_id" if function_exists else "worker_id"
            submission_field = "contributor_id" if function_exists else "worker_id"
            assignment_values = tuple(
                str(row)
                for row in (
                    await connection.execute(
                        text(f"select {assignment_field} from task_assignments order by id")
                    )
                ).scalars()
            )
            submission_values = tuple(
                str(row)
                for row in (
                    await connection.execute(
                        text(f"select {submission_field} from submissions order by id")
                    )
                ).scalars()
            )
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "assignment_column": await column("task_assignments"),
                "submission_column": await column("submissions"),
                "assignment_index": await index("task_assignments"),
                "submission_index": await index("submissions"),
                "foreign_keys": foreign_keys,
                "function": function_exists,
                "triggers": triggers,
                "assignment_values": assignment_values,
                "submission_values": submission_values,
            }
    finally:
        await engine.dispose()


def _database_error_sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


async def _exercise_contributor_lineage_guards(
    database_url: str,
    *,
    fixture: dict[str, tuple[str, ...] | str],
    human_id: str,
) -> dict[str, object]:
    engine = create_async_engine(database_url)
    service_id = str(fixture["service_id"])
    assignment_task = str(fixture["assignment_task"])
    submission_task = str(fixture["submission_task"])
    assignment_id = str(tuple(fixture["assignment_ids"])[0])
    submission_id = str(tuple(fixture["submission_ids"])[0])
    missing_id = str(uuid4())
    suspended_id = str(uuid4())
    deactivated_id = str(uuid4())
    results: dict[str, object] = {}
    try:
        for name, statement, values in (
            (
                "missing_assignment",
                "insert into task_assignments "
                "(id,task_id,contributor_id,assigned_by,status) values "
                "(:id,:task,:actor,'test','released')",
                {"id": str(uuid4()), "task": assignment_task, "actor": missing_id},
            ),
            (
                "service_assignment",
                "insert into task_assignments "
                "(id,task_id,contributor_id,assigned_by,status) values "
                "(:id,:task,:actor,'test','released')",
                {"id": str(uuid4()), "task": assignment_task, "actor": service_id},
            ),
            (
                "missing_assignment_update",
                "update task_assignments set contributor_id=:actor where id=:id",
                {"id": assignment_id, "actor": missing_id},
            ),
            (
                "service_assignment_update",
                "update task_assignments set contributor_id=:actor where id=:id",
                {"id": assignment_id, "actor": service_id},
            ),
            (
                "missing_submission",
                "insert into submissions "
                "(id,task_id,contributor_id,version,status,summary,package_uri,"
                "package_hash,artifact_hash_manifest,worker_attestation,"
                "locked_guide_version,locked_post_submit_checker_policy_id,"
                "locked_post_submit_checker_policy_version,"
                "locked_post_submit_checker_policy_hash,"
                "locked_post_submit_checker_policy_body,"
                "locked_review_policy_version,locked_revision_policy_version,"
                "locked_payment_policy_version,locked_guide_source_snapshot_id,"
                "locked_guide_source_snapshot_hash,"
                "locked_effective_project_submission_artifact_policy_id,"
                "locked_effective_project_submission_artifact_policy_hash,"
                "locked_pre_submit_checker_policy_id,"
                "locked_pre_submit_checker_bundle_hash,submitted_at,locked_at,"
                "supersedes_submission_id) "
                "select :id,task_id,:actor,2,status,summary,"
                "package_uri,package_hash,artifact_hash_manifest,worker_attestation,"
                "locked_guide_version,locked_post_submit_checker_policy_id,"
                "locked_post_submit_checker_policy_version,"
                "locked_post_submit_checker_policy_hash,"
                "locked_post_submit_checker_policy_body,locked_review_policy_version,"
                "locked_revision_policy_version,locked_payment_policy_version,"
                "locked_guide_source_snapshot_id,locked_guide_source_snapshot_hash,"
                "locked_effective_project_submission_artifact_policy_id,"
                "locked_effective_project_submission_artifact_policy_hash,"
                "locked_pre_submit_checker_policy_id,locked_pre_submit_checker_bundle_hash,"
                "submitted_at,locked_at,null from submissions where task_id=:task",
                {"id": str(uuid4()), "task": submission_task, "actor": missing_id},
            ),
            (
                "service_submission",
                "insert into submissions "
                "(id,task_id,contributor_id,version,status,summary,package_uri,"
                "package_hash,artifact_hash_manifest,worker_attestation,"
                "locked_guide_version,locked_post_submit_checker_policy_id,"
                "locked_post_submit_checker_policy_version,"
                "locked_post_submit_checker_policy_hash,"
                "locked_post_submit_checker_policy_body,"
                "locked_review_policy_version,locked_revision_policy_version,"
                "locked_payment_policy_version,locked_guide_source_snapshot_id,"
                "locked_guide_source_snapshot_hash,"
                "locked_effective_project_submission_artifact_policy_id,"
                "locked_effective_project_submission_artifact_policy_hash,"
                "locked_pre_submit_checker_policy_id,"
                "locked_pre_submit_checker_bundle_hash,submitted_at,locked_at,"
                "supersedes_submission_id) "
                "select :id,task_id,:actor,3,status,summary,"
                "package_uri,package_hash,artifact_hash_manifest,worker_attestation,"
                "locked_guide_version,locked_post_submit_checker_policy_id,"
                "locked_post_submit_checker_policy_version,"
                "locked_post_submit_checker_policy_hash,"
                "locked_post_submit_checker_policy_body,locked_review_policy_version,"
                "locked_revision_policy_version,locked_payment_policy_version,"
                "locked_guide_source_snapshot_id,locked_guide_source_snapshot_hash,"
                "locked_effective_project_submission_artifact_policy_id,"
                "locked_effective_project_submission_artifact_policy_hash,"
                "locked_pre_submit_checker_policy_id,locked_pre_submit_checker_bundle_hash,"
                "submitted_at,locked_at,null from submissions where task_id=:task",
                {"id": str(uuid4()), "task": submission_task, "actor": service_id},
            ),
            (
                "missing_submission_update",
                "update submissions set contributor_id=:actor where id=:id",
                {"id": submission_id, "actor": missing_id},
            ),
            (
                "service_submission_update",
                "update submissions set contributor_id=:actor where id=:id",
                {"id": submission_id, "actor": service_id},
            ),
        ):
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), values)
            except DBAPIError as error:
                results[name] = _database_error_sqlstate(error)
            else:
                results[name] = None

        async with engine.begin() as connection:
            await connection.execute(
                text("update task_assignments set assigned_by='updated' where id=:id"),
                {"id": assignment_id},
            )
            results["unrelated_update_preserved"] = (
                await connection.scalar(
                    text("select contributor_id=:actor from task_assignments where id=:id"),
                    {"id": assignment_id, "actor": human_id},
                )
                is True
            )
            for actor_id, status in (
                (suspended_id, "suspended"),
                (deactivated_id, "deactivated"),
            ):
                await connection.execute(
                    text(
                        "insert into actor_profiles "
                        "(id,actor_kind,status,provisioning_method,created_by) values "
                        "(:id,'human','active','automatic_first_access',:id)"
                    ),
                    {"id": actor_id},
                )
                await connection.execute(
                    text(
                        "insert into actor_identity_links "
                        "(id,actor_profile_id,issuer,subject,subject_kind,status,"
                        "linked_by,last_verified_at) values "
                        "(:link,:actor,'https://identity.test',:subject,'human',"
                        "'active',:actor,clock_timestamp())"
                    ),
                    {
                        "link": str(uuid4()),
                        "actor": actor_id,
                        "subject": f"historical-{actor_id}",
                    },
                )
                if status == "suspended":
                    await connection.execute(
                        text(
                            "update actor_profiles set status='suspended',"
                            "suspended_by=:actor,suspended_at=clock_timestamp(),"
                            "suspension_reason='migration test' where id=:actor"
                        ),
                        {"actor": actor_id},
                    )
                else:
                    await connection.execute(
                        text(
                            "update actor_profiles set status='deactivated',"
                            "deactivated_by=:actor,deactivated_at=clock_timestamp(),"
                            "deactivation_reason='migration test' where id=:actor"
                        ),
                        {"actor": actor_id},
                    )
                await connection.execute(
                    text(
                        "insert into task_assignments "
                        "(id,task_id,contributor_id,assigned_by,status) values "
                        "(:id,:task,:actor,'test','released')"
                    ),
                    {"id": str(uuid4()), "task": assignment_task, "actor": actor_id},
                )
                results[f"{status}_human_inserted"] = True
        return results
    finally:
        await engine.dispose()


async def _exercise_contributor_lineage_function_contract(
    database_url: str,
) -> dict[str, object]:
    """Prove closed trigger arguments and nullable-field delegation."""
    engine = create_async_engine(database_url)
    results: dict[str, object] = {}
    try:
        for name, arguments in (
            ("zero_arguments", ""),
            ("extra_arguments", "'contributor_id','extra'"),
            ("absent_field", "'missing_field'"),
        ):
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text("create temporary table lineage_probe (contributor_id text)")
                    )
                    await connection.execute(
                        text(
                            "create trigger lineage_probe_guard before insert on "
                            "lineage_probe for each row execute function public."
                            f"require_human_actor_profile_reference({arguments})"
                        )
                    )
                    await connection.execute(
                        text(
                            "insert into lineage_probe (contributor_id) values "
                            "('not-a-canonical-id')"
                        )
                    )
            except DBAPIError as error:
                results[name] = _database_error_sqlstate(error)
            else:
                results[name] = None

        async with engine.begin() as connection:
            await connection.execute(
                text("create temporary table lineage_nullable (contributor_id text)")
            )
            await connection.execute(
                text(
                    "create trigger lineage_nullable_guard before insert on "
                    "lineage_nullable for each row execute function public."
                    "require_human_actor_profile_reference('contributor_id')"
                )
            )
            await connection.execute(
                text("insert into lineage_nullable (contributor_id) values (null)")
            )
            results["nullable_field_accepted"] = (
                await connection.scalar(text("select count(*) from lineage_nullable"))
                == 1
            )
        return results
    finally:
        await engine.dispose()


async def _add_contributor_function_dependency(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "create trigger task_assignments_contributor_dependency "
                    "before update of contributor_id on task_assignments for each row "
                    "execute function require_human_actor_profile_reference('contributor_id')"
                )
            )
    finally:
        await engine.dispose()


async def _drop_contributor_function_dependency(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "drop trigger task_assignments_contributor_dependency "
                    "on task_assignments"
                )
            )
    finally:
        await engine.dispose()


async def _insert_authorization_action_event_for(
    database_url: str,
    action_id: str,
    permission_id: str,
) -> str:
    values = _action_evidence_values(action_id, permission_id)
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(_ACTION_EVIDENCE_INSERT, values)
        return str(values["id"])
    finally:
        await engine.dispose()
