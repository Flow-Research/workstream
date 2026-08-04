from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine

from app.adapters.auth.dev import actor_id_from_external_identity
from app.core.hashing import canonical_json_hash
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import (
    ACTION_DEFINITIONS,
    HISTORICAL_PERMISSION_IDS,
    NEW_PERMISSION_IDS,
    ActionId,
    ActionOwner,
    PermissionId,
)
from app.modules.authorization.runtime import (
    ProjectGuideMutationResourceContext,
    authorization_resource_digest,
)
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    ProjectCreateIdempotencyRecord,
    ProjectGuide,
)
from project_create_fixtures import insert_historical_project, seed_authorized_project

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

HEAD_REVISION = "0051_legacy_intake_removal"

pytestmark = pytest.mark.postgres_schema_contract

_OBSOLETE_ART_UPLOAD_IDS = tuple(
    "artifact.upload_" + value
    for value in (
        "session.create",
        "session.read",
        "item.write",
        "session.seal",
        "session.cancel",
        "session.expire",
    )
)

_PROJECT_MUTATION_OWNERS = {
    ActionOwner.AUTH_12B2,
    ActionOwner.AUTH_12C,
    ActionOwner.AUTH_12D,
    ActionOwner.XINT_003_02B,
    ActionOwner.AUTH_12E,
    ActionOwner.AUTH_12F,
    ActionOwner.AUTH_12G,
    ActionOwner.AUTH_12H,
}


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


def test_service_identity_migration_contract_is_frozen_from_application_modules() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    revision_source = (backend_root / "alembic/versions/0023_service_actor_identity.py").read_text(
        encoding="utf-8"
    )
    contract_source = (backend_root / "migration_contracts/service_identity_0023.py").read_text(
        encoding="utf-8"
    )
    assert "from migration_contracts.service_identity_0023 import" in revision_source
    assert "app.modules" not in revision_source
    assert "app.modules" not in contract_source
    assert "repository_root=MIGRATION_REPOSITORY_ROOT" in revision_source
    assert "REPOSITORY_ROOT" not in contract_source
    assert FROZEN_SERVICE_IDENTITY_VALUES == (
        "workstream.artifact.verifier",
        "workstream.artifact.put_resolver",
        "workstream.artifact.scheduler",
        "workstream.artifact.binding",
        "workstream.artifact.guide_reader",
        "workstream.artifact.materializer",
        "workstream.artifact.checker_output",
    )
    assert tuple(identity.value for identity in ServiceIdentity) == (
        *FROZEN_SERVICE_IDENTITY_VALUES,
        "workstream.project.setup",
        "workstream.review.preference_expiry",
        "workstream.review.lease_expiry",
        "workstream.review.authority_invalidation_reconciliation",
        "workstream.review.reconciliation",
        "workstream.review.artifact_reference_reconciliation",
        "workstream.review.projection",
    )


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
    assert (
        validate_frozen_mapping_path(
            private_root / "private-envelope.json",
            repository_root=deployment_root,
            output=True,
        )
        == private_root / "private-envelope.json"
    )


def test_alembic_upgrade_and_downgrade(isolated_database_env: str, migration_lock) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        constraint_names = asyncio.run(
            _project_setup_run_check_constraint_names(isolated_database_env)
        )
        assert "ck_project_setup_runs_ck_project_setup_runs_status" in constraint_names
        command.downgrade(config, "base")


def test_0051_legacy_intake_safe_empty_round_trip(
    isolated_database_env: str, migration_lock
) -> None:
    """The clean cut removes the namespace and recreates only an empty legacy shape."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0050_guide_source_v2")
            legacy = asyncio.run(_legacy_intake_shape(isolated_database_env))
            assert legacy["revision"] == "0050_guide_source_v2"
            assert legacy["tables"] == (True, True)
            assert legacy["upload_columns"] == (True, True)

            command.upgrade(config, HEAD_REVISION)
            removed = asyncio.run(_legacy_intake_shape(isolated_database_env))
            assert removed["revision"] == HEAD_REVISION
            assert removed["tables"] == (False, False)
            assert removed["upload_columns"] == (False, False)
            assert removed["contributor_constraints"] == ()

            command.downgrade(config, "0050_guide_source_v2")
            restored = asyncio.run(_legacy_intake_shape(isolated_database_env))
            assert restored == legacy
            command.upgrade(config, HEAD_REVISION)
        finally:
            command.downgrade(config, "base")


@pytest.mark.parametrize(
    "blocker",
    (
        "upload_session",
        "upload_item",
        "contributor_attempt",
        "attempt_upload_item",
        "v1_receipt",
        "receipt_upload_item",
    ),
)
def test_0051_legacy_intake_refuses_each_populated_condition_atomically(
    isolated_database_env: str, migration_lock, blocker: str
) -> None:
    """Every historical row class preserves the entire predecessor schema on refusal."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0050_guide_source_v2")
            asyncio.run(_seed_0051_legacy_blocker(isolated_database_env, blocker))
            before = asyncio.run(_legacy_intake_shape(isolated_database_env))
            with pytest.raises(
                RuntimeError, match="legacy contributor artifact intake is populated"
            ):
                command.upgrade(config, HEAD_REVISION)
            assert asyncio.run(_legacy_intake_shape(isolated_database_env)) == before
        finally:
            asyncio.run(_reset_0051_test_schema(isolated_database_env))


async def _reset_0051_test_schema(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("drop schema public cascade"))
            await connection.execute(text("create schema public"))
    finally:
        await engine.dispose()


async def _legacy_intake_shape(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            has_legacy_tables = bool(
                await connection.scalar(
                    text("select to_regclass('artifact_upload_sessions') is not null")
                )
            )
            physical_schema = tuple(
                tuple(row)
                for row in (
                    await connection.execute(
                        text(
                            "select 'column',table_name,column_name,data_type,udt_name,"
                            "is_nullable,coalesce(column_default,''),"
                            "coalesce(character_maximum_length::text,'') "
                            "from information_schema.columns where table_schema='public' and "
                            "table_name in ('artifact_upload_sessions','artifact_upload_items',"
                            "'artifact_put_attempts','artifact_operation_receipts') union all "
                            "select 'constraint',c.relname,q.conname,q.contype::text,"
                            "pg_get_constraintdef(q.oid,true),'','','' from pg_constraint q "
                            "join pg_class c on c.oid=q.conrelid join pg_namespace n "
                            "on n.oid=c.relnamespace where n.nspname='public' and c.relname in "
                            "('artifact_upload_sessions','artifact_upload_items',"
                            "'artifact_put_attempts','artifact_operation_receipts') union all "
                            "select 'index',tablename,indexname,indexdef,'','','','' "
                            "from pg_indexes where schemaname='public' and tablename in "
                            "('artifact_upload_sessions','artifact_upload_items',"
                            "'artifact_put_attempts','artifact_operation_receipts') "
                            "order by 1,2,3,4"
                        )
                    )
                ).all()
            )
            constraints = tuple(
                await connection.scalars(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint "
                        "where conrelid='artifact_put_attempts'::regclass and contype='c' "
                        "and pg_get_constraintdef(oid) ilike '%contributor%' order by conname"
                    )
                )
            )
            return {
                "revision": str(
                    await connection.scalar(text("select version_num from alembic_version"))
                ),
                "tables": (
                    bool(
                        await connection.scalar(
                            text("select to_regclass('artifact_upload_sessions') is not null")
                        )
                    ),
                    bool(
                        await connection.scalar(
                            text("select to_regclass('artifact_upload_items') is not null")
                        )
                    ),
                ),
                "upload_columns": (
                    bool(
                        await connection.scalar(
                            text(
                                "select exists(select 1 from information_schema.columns where table_name='artifact_put_attempts' and column_name='upload_item_id')"
                            )
                        )
                    ),
                    bool(
                        await connection.scalar(
                            text(
                                "select exists(select 1 from information_schema.columns where table_name='artifact_operation_receipts' and column_name='upload_item_id')"
                            )
                        )
                    ),
                ),
                "contributor_constraints": constraints,
                "physical_schema": physical_schema,
                "legacy_rows": tuple(
                    tuple(row)
                    for row in (
                        await connection.execute(
                            text(
                                "select 'session',id,state from artifact_upload_sessions "
                                "union all select 'item',id,state from artifact_upload_items "
                                "union all select 'attempt',id,producer_request_type "
                                "from artifact_put_attempts union all "
                                "select 'receipt',id,contract_version::text "
                                "from artifact_operation_receipts order by 1,2"
                            )
                        )
                    ).all()
                )
                if has_legacy_tables
                else (),
                "row_counts": tuple(
                    (
                        await connection.execute(
                            text(
                                "select (select count(*) from artifact_put_attempts),"
                                "(select count(*) from artifact_operation_receipts),"
                                "(select count(*) from artifact_upload_sessions),"
                                "(select count(*) from artifact_upload_items)"
                            )
                        )
                    ).one()
                )
                if has_legacy_tables
                else (),
            }
    finally:
        await engine.dispose()


async def _seed_0051_legacy_blocker(database_url: str, blocker: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            table = {
                "upload_session": "artifact_upload_sessions",
                "upload_item": "artifact_upload_items",
                "contributor_attempt": "artifact_put_attempts",
                "attempt_upload_item": "artifact_put_attempts",
                "v1_receipt": "artifact_operation_receipts",
                "receipt_upload_item": "artifact_operation_receipts",
            }[blocker]
            constraint_names = tuple(
                await connection.scalars(
                    text(
                        "select conname from pg_constraint where conrelid=cast(:table as regclass) "
                        "and contype in ('c','f') order by conname"
                    ),
                    {"table": table},
                )
            )
            for name in constraint_names:
                await connection.execute(text(f'alter table {table} drop constraint "{name}"'))
            identifier = str(uuid4())
            if blocker == "upload_session":
                await connection.execute(
                    text(
                        "insert into artifact_upload_sessions (id,actor_id,project_id,permitted_roles,state,maximum_bytes,current_bytes,reserved_bytes,maximum_items,current_items,reserved_items,expires_at,cas_version) values (:id,'actor','project','[]'::json,'open',1,0,0,1,0,0,now(),0)"
                    ),
                    {"id": identifier},
                )
            elif blocker == "upload_item":
                await connection.execute(
                    text(
                        "insert into artifact_upload_items (id,session_id,logical_role,display_name,reserved_bytes,idempotency_key,request_digest,state,cas_version) values (:id,'session','result','result.zip',1,'key',:digest,'reserved',0)"
                    ),
                    {"id": identifier, "digest": "sha256:" + "1" * 64},
                )
            elif blocker in {"contributor_attempt", "attempt_upload_item"}:
                await connection.execute(
                    text(
                        "insert into artifact_put_attempts (id,producer_request_type,producer_type,producer_ref,project_id,task_id,upload_item_id,sha256,byte_count,media_type,storage_namespace_id,namespace_fingerprint,canonical_target,operation_identity,request_digest,status,execution_generation,observation_count,maximum_observations,cas_version) values (:id,:request_type,'actor_profile',:actor,'project',:task,:item,:digest,1,'application/zip','primary',:digest,'sha256/11/' || repeat('1',62),:digest,:digest,'prepared',0,0,5,0)"
                    ),
                    {
                        "id": identifier,
                        "request_type": "contributor"
                        if blocker == "contributor_attempt"
                        else "guide",
                        "actor": str(uuid4()),
                        "task": "task" if blocker == "contributor_attempt" else None,
                        "item": None if blocker == "contributor_attempt" else "item",
                        "digest": "sha256:" + "1" * 64,
                    },
                )
            else:
                await connection.execute(
                    text(
                        "insert into artifact_operation_receipts (id,contract_version,put_attempt_id,upload_item_id,replica_id,operation,idempotency_key,request_digest,provider_object_ref,replayed,outcome,attempt_number,correlation_id,details) values (:id,:version,:attempt,:item,'replica','put','key',:digest,'object',false,'stored_pending_verification',1,'correlation','[]'::json)"
                    ),
                    {
                        "id": identifier,
                        "version": 1 if blocker == "v1_receipt" else 2,
                        "attempt": None if blocker == "v1_receipt" else "attempt",
                        "item": "item",
                        "digest": "sha256:" + "1" * 64,
                    },
                )
    finally:
        await engine.dispose()


async def _project_setup_run_check_constraint_names(database_url: str) -> set[str]:
    """Return physical check-constraint names for the setup-run table."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = await connection.scalars(
                text(
                    "select constraint_name from information_schema.table_constraints "
                    "where table_schema = current_schema() "
                    "and table_name = 'project_setup_runs' "
                    "and constraint_type = 'CHECK'"
                )
            )
            return set(rows.all())
    finally:
        await engine.dispose()


def test_0034_project_role_issue_evidence_exact_safe_round_trip(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """0034 changes only its frozen functions and privacy registry, reversibly."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0033_authorization_read_rate")
            asyncio.run(_insert_empty_pending_0034_issue(isolated_database_env))
            predecessor = asyncio.run(
                _project_role_issue_evidence_0034_state(isolated_database_env)
            )

            command.upgrade(config, "0034_project_role_issue_evidence")
            forward = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            assert forward["revision"] == "0034_project_role_issue_evidence"
            assert forward["rows"] == predecessor["rows"] == (1, 0)
            assert forward["triggers"] == predecessor["triggers"]
            assert forward["fact_constraint"] == predecessor["fact_constraint"]
            assert forward["privacy_constraint"] != predecessor["privacy_constraint"]
            assert forward["functions"] != predecessor["functions"]

            command.downgrade(config, "0033_authorization_read_rate")
            restored = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            assert restored == predecessor

            command.upgrade(config, "0034_project_role_issue_evidence")
            assert (
                asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
                == forward
            )
        finally:
            asyncio.run(_clear_pending_0034_issues(isolated_database_env))
            command.downgrade(config, "base")


@pytest.mark.parametrize("drift", ["changed", "missing", "unvalidated", "wrong_table"])
def test_0034_project_role_issue_evidence_refuses_fact_constraint_drift(
    isolated_database_env: str,
    migration_lock,
    drift: str,
) -> None:
    """A detached or changed fact gate cannot be silently accepted by 0034."""
    config = _alembic_config()
    definition = None
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0033_authorization_read_rate")
            before = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            definition = before["fact_constraint"][2]
            asyncio.run(_replace_0034_fact_constraint_with_drift(isolated_database_env, drift))
            drifted = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            with pytest.raises(RuntimeError, match="unexpected authority fact constraint"):
                command.upgrade(config, "0034_project_role_issue_evidence")
            refused = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            assert refused == drifted
            assert refused["revision"] == before["revision"]
            assert refused["functions"] == before["functions"]
            assert refused["triggers"] == before["triggers"]
            assert refused["privacy_constraint"] == before["privacy_constraint"]
            assert refused["rows"] == before["rows"]
        finally:
            asyncio.run(_restore_0034_fact_constraint(isolated_database_env, definition))
            command.downgrade(config, "base")


def test_0034_project_role_issue_evidence_fact_shape_is_closed(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """The richer revoke projection is exact and preserves legacy two-key facts."""
    config = _alembic_config()
    project_id = str(uuid4())
    mappings = {
        "submitter": "auth13_assignment",
        "reviewer": "rev_reviewer_obligation",
        "adjudicator": "none",
    }
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            for role, obligation in mappings.items():
                before = {
                    "effective": True,
                    "role": role,
                    "scope_type": "project",
                    "scope_id": project_id,
                    "future_obligation": obligation,
                }
                after = {**before, "effective": False}
                mismatched_role = "reviewer" if role != "reviewer" else "submitter"
                assert asyncio.run(
                    _facts_are_safe_0034(isolated_database_env, before, after, project_id)
                )
                invalid = (
                    ({key: value for key, value in before.items() if key != "role"}, after),
                    ({**before, "extra": "no"}, {**after, "extra": "no"}),
                    ({**before, "effective": "true"}, after),
                    ({**before, "scope_id": str(uuid4())}, after),
                    ({**before, "future_obligation": "wrong"}, after),
                    (before, {**after, "role": mismatched_role}),
                )
                for invalid_before, invalid_after in invalid:
                    assert (
                        asyncio.run(
                            _facts_are_safe_0034(
                                isolated_database_env,
                                invalid_before,
                                invalid_after,
                                project_id,
                            )
                        )
                        is False
                    )
                for null_before, null_after in ((None, after), (before, None)):
                    assert (
                        asyncio.run(
                            _facts_are_safe_0034(
                                isolated_database_env,
                                null_before,
                                null_after,
                                project_id,
                            )
                        )
                        is False
                    )
            assert asyncio.run(
                _facts_are_safe_0034(
                    isolated_database_env,
                    {"effective": True},
                    {"effective": False},
                    project_id,
                )
            )
        finally:
            command.downgrade(config, "base")


def test_0034_project_role_issue_evidence_rejects_false_invalidation_at_insert(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """An issue reservation cannot accept an invalidation even before completion."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            fixture = asyncio.run(_seed_pending_issue_cause_0034(isolated_database_env))
            with pytest.raises(IntegrityError) as rejected:
                asyncio.run(
                    _insert_false_issue_invalidation_0034(
                        isolated_database_env,
                        fixture,
                    )
                )
            assert getattr(rejected.value.orig, "sqlstate", None) == "23514"
            assert (
                asyncio.run(_count_linked_events_0034(isolated_database_env, fixture["record"]))
                == 1
            )
        finally:
            asyncio.run(_clear_0034_issue_fixture(isolated_database_env))
            command.downgrade(config, "base")


def test_0034_five_key_revoke_invalidation_requires_exact_linkage(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Five-key obligation facts are admitted only for one linked revoke pair."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            for invalid_form in (
                "non_revoke",
                "orphan",
                "mixed_facts",
                "cross_record",
                "null_target_kind",
                "null_target_id",
                "wrong_target_kind",
                "wrong_target_id",
            ):
                records: list[str] = []
                try:
                    if invalid_form == "non_revoke":
                        fixture = asyncio.run(_seed_pending_issue_cause_0034(isolated_database_env))
                        records.append(fixture["record"])
                        cause = fixture
                    else:
                        fixture = asyncio.run(
                            _seed_pending_revoke_cause_0034(isolated_database_env)
                        )
                        records.append(fixture["record"])
                        cause = fixture
                        if invalid_form == "orphan":
                            cause = {**fixture, "cause": str(uuid4())}
                        elif invalid_form == "cross_record":
                            cause = asyncio.run(
                                _seed_pending_revoke_cause_0034(
                                    isolated_database_env,
                                    envelope=fixture,
                                )
                            )
                            records.append(cause["record"])

                    before_facts = _five_key_revoke_facts_0034(fixture, effective=True)
                    after_facts = _five_key_revoke_facts_0034(fixture, effective=False)
                    if invalid_form == "mixed_facts":
                        after_facts = {"effective": False}
                    target_ref_kind: str | None = "project_role_grant"
                    target_ref_id: str | None = cause["grant"]
                    if invalid_form == "null_target_kind":
                        target_ref_kind = None
                    elif invalid_form == "null_target_id":
                        target_ref_id = None
                    elif invalid_form == "wrong_target_kind":
                        target_ref_kind = "actor_profile"
                    elif invalid_form == "wrong_target_id":
                        target_ref_id = str(uuid4())
                    before = asyncio.run(
                        _linked_revoke_fixture_state_0034(isolated_database_env, records)
                    )

                    with pytest.raises(IntegrityError) as rejected:
                        asyncio.run(
                            _insert_revoke_invalidation_0034(
                                isolated_database_env,
                                fixture,
                                cause=cause,
                                before_facts=before_facts,
                                after_facts=after_facts,
                                target_ref_kind=target_ref_kind,
                                target_ref_id=target_ref_id,
                            )
                        )
                    expected_sqlstate = "23503" if invalid_form == "orphan" else "23514"
                    assert getattr(rejected.value.orig, "sqlstate", None) == expected_sqlstate
                    assert (
                        asyncio.run(
                            _linked_revoke_fixture_state_0034(isolated_database_env, records)
                        )
                        == before
                    )
                finally:
                    asyncio.run(_clear_linked_revoke_fixtures_0034(isolated_database_env, records))
        finally:
            command.downgrade(config, "base")


def test_0034_downgrade_refuses_five_key_revoke_evidence_without_mutation(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """A linked five-key revoke pair remains intact when 0034 refuses downgrade."""
    config = _alembic_config()
    records: list[str] = []
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            fixture = asyncio.run(_seed_pending_revoke_cause_0034(isolated_database_env))
            records.append(fixture["record"])
            before_insert = asyncio.run(
                _linked_revoke_fixture_state_0034(isolated_database_env, records)
            )
            invalidation_id = asyncio.run(
                _insert_revoke_invalidation_0034(
                    isolated_database_env,
                    fixture,
                    cause=fixture,
                    before_facts=_five_key_revoke_facts_0034(fixture, effective=True),
                    after_facts=_five_key_revoke_facts_0034(fixture, effective=False),
                    target_ref_kind="project_role_grant",
                    target_ref_id=fixture["grant"],
                )
            )
            admitted = asyncio.run(
                _linked_revoke_fixture_state_0034(isolated_database_env, records)
            )
            assert admitted != before_insert
            assert admitted["event_ids"] == tuple(sorted((fixture["cause"], invalidation_id)))
            assert admitted["event_count"] == 2

            before_downgrade = {
                "migration": asyncio.run(
                    _project_role_issue_evidence_0034_state(isolated_database_env)
                ),
                "fixture": admitted,
            }
            with pytest.raises(
                RuntimeError,
                match="incompatible project-role issue evidence",
            ):
                command.downgrade(config, "0033_authorization_read_rate")
            after_refusal = {
                "migration": asyncio.run(
                    _project_role_issue_evidence_0034_state(isolated_database_env)
                ),
                "fixture": asyncio.run(
                    _linked_revoke_fixture_state_0034(isolated_database_env, records)
                ),
            }
            assert after_refusal == before_downgrade
        finally:
            asyncio.run(_clear_linked_revoke_fixtures_0034(isolated_database_env, records))
            command.downgrade(config, "base")


@pytest.mark.parametrize(
    "drift",
    [
        "guard_function",
        "linked_function",
        "facts_function",
        "trigger_disabled",
        "privacy_constraint",
    ],
)
def test_0034_project_role_issue_evidence_refuses_frozen_definition_drift(
    isolated_database_env: str,
    migration_lock,
    drift: str,
) -> None:
    """Frozen predecessor function and privacy definitions are mandatory."""
    config = _alembic_config()
    definitions = None
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0033_authorization_read_rate")
            definitions = asyncio.run(
                _project_role_issue_evidence_0034_definitions(isolated_database_env)
            )
            before = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            asyncio.run(_install_definition_drift_0034(isolated_database_env, drift))
            drifted = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            if drift in {"guard_function", "linked_function", "facts_function"}:
                message = "unexpected predecessor authority evidence definition"
            elif drift == "trigger_disabled":
                message = "unexpected authority evidence trigger binding"
            else:
                message = "unexpected authority privacy constraint"
            with pytest.raises(RuntimeError, match=message):
                command.upgrade(config, "0034_project_role_issue_evidence")
            assert (
                asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
                == drifted
            )
            assert drifted["revision"] == before["revision"]
            assert drifted["rows"] == before["rows"]
            if drift == "trigger_disabled":
                assert drifted["triggers"] != before["triggers"]
            else:
                assert drifted["triggers"] == before["triggers"]
        finally:
            if definitions is not None:
                asyncio.run(
                    _restore_project_role_issue_evidence_0034_definitions(
                        isolated_database_env,
                        definitions,
                    )
                )
                assert (
                    asyncio.run(
                        _project_role_issue_evidence_0034_definitions(isolated_database_env)
                    )
                    == definitions
                )
            command.downgrade(config, "base")


@pytest.mark.parametrize("incompatible", ["response", "linked_event"])
def test_0034_project_role_issue_evidence_refuses_incompatible_pending_state(
    isolated_database_env: str,
    migration_lock,
    incompatible: str,
) -> None:
    """Pending issue state is admitted only with null response and zero evidence."""
    config = _alembic_config()
    fixture = None
    state_shape_constraint = None
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0033_authorization_read_rate")
            if incompatible == "linked_event":
                fixture = asyncio.run(_seed_pending_issue_cause_0034(isolated_database_env))
            else:
                state_shape_constraint = asyncio.run(
                    _authority_idempotency_state_shape_0034(isolated_database_env)
                )
                assert state_shape_constraint is not None
                asyncio.run(_insert_empty_pending_0034_issue(isolated_database_env))
                fixture = None
                asyncio.run(
                    _add_pending_issue_response_0034(
                        isolated_database_env,
                        state_shape_constraint,
                    )
                )
                incompatible_constraint = asyncio.run(
                    _authority_idempotency_state_shape_0034(isolated_database_env)
                )
                assert incompatible_constraint is not None
                assert incompatible_constraint[:2] == (
                    state_shape_constraint[0],
                    False,
                )
                assert incompatible_constraint[2].removesuffix(
                    " NOT VALID"
                ) == state_shape_constraint[2].removesuffix(" NOT VALID")
            before = asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
            with pytest.raises(RuntimeError, match="incompatible project-role issue evidence"):
                command.upgrade(config, "0034_project_role_issue_evidence")
            assert (
                asyncio.run(_project_role_issue_evidence_0034_state(isolated_database_env))
                == before
            )
        finally:
            if fixture is not None:
                asyncio.run(_clear_0034_issue_fixture(isolated_database_env))
            else:
                asyncio.run(
                    _clear_pending_0034_issues(
                        isolated_database_env,
                        state_shape_constraint,
                    )
                )
                if state_shape_constraint is not None:
                    assert (
                        asyncio.run(_authority_idempotency_state_shape_0034(isolated_database_env))
                        == state_shape_constraint
                    )
            command.downgrade(config, "base")


async def _project_role_issue_evidence_0034_state(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            function_rows = (
                await connection.execute(
                    text(
                        "select proname,pg_get_functiondef(oid) from pg_proc where oid in "
                        "('guard_authority_idempotency_record'::regproc,"
                        "'validate_linked_authority_event'::regproc,"
                        "'authority_event_facts_are_safe'::regproc) order by proname"
                    )
                )
            ).all()
            constraint_rows = {
                row.conname: (row.table_name, row.convalidated, row.definition)
                for row in (
                    await connection.execute(
                        text(
                            "select conname,conrelid::regclass::text table_name,convalidated,"
                            "pg_get_constraintdef(oid) definition from pg_constraint "
                            "where conname in ('ck_audit_events_fact_bounds',"
                            "'ck_audit_events_authority_privacy_bounds',"
                            "'ck_authority_idempotency_records_state_shape')"
                        )
                    )
                ).all()
            }
            triggers = tuple(
                (
                    await connection.execute(
                        text(
                            "select tgname,pg_get_triggerdef(oid,true),tgenabled from pg_trigger "
                            "where tgname in ('authority_idempotency_guard',"
                            "'audit_events_validate_idempotency') order by tgname"
                        )
                    )
                ).all()
            )
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "functions": tuple(
                    (name, hashlib.sha256(definition.encode()).hexdigest())
                    for name, definition in function_rows
                ),
                "fact_constraint": constraint_rows.get("ck_audit_events_fact_bounds"),
                "privacy_constraint": constraint_rows["ck_audit_events_authority_privacy_bounds"],
                "idempotency_state_constraint": constraint_rows.get(
                    "ck_authority_idempotency_records_state_shape"
                ),
                "triggers": triggers,
                "rows": (
                    int(
                        await connection.scalar(
                            text("select count(*) from authority_idempotency_records")
                        )
                    ),
                    int(await connection.scalar(text("select count(*) from audit_events"))),
                ),
            }
    finally:
        await engine.dispose()


async def _install_definition_drift_0034(database_url: str, drift: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            if drift == "guard_function":
                await connection.execute(
                    text(
                        "create or replace function guard_authority_idempotency_record() "
                        "returns trigger language plpgsql as $$ begin return new; end $$"
                    )
                )
            elif drift == "linked_function":
                await connection.execute(
                    text(
                        "create or replace function validate_linked_authority_event() "
                        "returns trigger language plpgsql as $$ begin return new; end $$"
                    )
                )
            elif drift == "facts_function":
                await connection.execute(
                    text(
                        "create or replace function authority_event_facts_are_safe("
                        "event_name text,before_state json,after_state json,"
                        "envelope_project_id text) returns boolean language sql immutable "
                        "as $$ select true $$"
                    )
                )
            elif drift == "trigger_disabled":
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger audit_events_validate_idempotency"
                    )
                )
            else:
                await connection.execute(
                    text(
                        "alter table audit_events drop constraint "
                        "ck_audit_events_authority_privacy_bounds"
                    )
                )
                await connection.execute(
                    text(
                        "alter table audit_events add constraint "
                        "ck_audit_events_authority_privacy_bounds check (true)"
                    )
                )
    finally:
        await engine.dispose()


async def _project_role_issue_evidence_0034_definitions(
    database_url: str,
) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            functions = dict(
                (
                    await connection.execute(
                        text(
                            "select proname,pg_get_functiondef(oid) from pg_proc where oid in "
                            "('guard_authority_idempotency_record'::regproc,"
                            "'validate_linked_authority_event'::regproc,"
                            "'authority_event_facts_are_safe'::regproc)"
                        )
                    )
                ).all()
            )
            privacy_row = (
                await connection.execute(
                    text(
                        "select conrelid::regclass::text,convalidated,"
                        "pg_get_constraintdef(oid) from pg_constraint where conname="
                        "'ck_audit_events_authority_privacy_bounds' and "
                        "conrelid='audit_events'::regclass"
                    )
                )
            ).one()
            trigger_rows = (
                await connection.execute(
                    text(
                        "select tgrelid::regclass::text,tgname,tgenabled from pg_trigger "
                        "where tgname in ('authority_idempotency_guard',"
                        "'audit_events_validate_idempotency') order by tgname"
                    )
                )
            ).all()
            return {
                "functions": functions,
                "privacy": tuple(privacy_row),
                "triggers": tuple(tuple(row) for row in trigger_rows),
            }
    finally:
        await engine.dispose()


async def _restore_project_role_issue_evidence_0034_definitions(
    database_url: str,
    definitions: dict[str, object],
) -> None:
    functions = definitions["functions"]
    assert isinstance(functions, dict)
    privacy = definitions["privacy"]
    assert isinstance(privacy, tuple)
    privacy_table, privacy_validated, privacy_definition = privacy
    assert privacy_table == "audit_events"
    assert isinstance(privacy_validated, bool)
    assert isinstance(privacy_definition, str)
    triggers = definitions["triggers"]
    assert isinstance(triggers, tuple)
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for definition in functions.values():
                assert isinstance(definition, str)
                await connection.exec_driver_sql(definition)
            current_privacy = tuple(
                (
                    await connection.execute(
                        text(
                            "select conrelid::regclass::text,convalidated,"
                            "pg_get_constraintdef(oid) from pg_constraint where conname="
                            "'ck_audit_events_authority_privacy_bounds' and "
                            "conrelid='audit_events'::regclass"
                        )
                    )
                ).one()
            )
            if current_privacy != privacy:
                await _restore_0034_privacy_constraint(
                    connection,
                    privacy_definition,
                    privacy_validated,
                )
            await _restore_0034_trigger_states(connection, triggers)
    finally:
        await engine.dispose()


async def _restore_0034_privacy_constraint(
    connection,
    predecessor_definition: str,
    validated: bool,
) -> None:
    resource_markers = (
        (
            "'project'::character varying, 'project_role_grant'::character varying",
            "'project'::character varying, 'qualification_snapshot'::character varying, "
            "'project_role_grant'::character varying",
        ),
        (
            "('project'::character varying)::text, ('project_role_grant'::character varying)::text",
            "('project'::character varying)::text, "
            "('qualification_snapshot'::character varying)::text, "
            "('project_role_grant'::character varying)::text",
        ),
    )
    predecessor_definition = predecessor_definition.removesuffix(" NOT VALID")
    matches = [
        (old, new)
        for old, new in resource_markers
        if old in predecessor_definition and new not in predecessor_definition
    ]
    assert matches
    old, new = max(matches, key=lambda item: len(item[1]))
    forward_source = predecessor_definition.replace(old, new)
    validation_clause = "" if validated else " not valid"
    await connection.execute(
        text(
            "alter table audit_events drop constraint if exists "
            "ck_audit_events_authority_privacy_bounds"
        )
    )
    await connection.exec_driver_sql(
        "alter table audit_events add constraint "
        "ck_audit_events_authority_privacy_bounds "
        f"{forward_source}{validation_clause}"
    )
    forward_definition = await connection.scalar(
        text(
            "select pg_get_constraintdef(oid) from pg_constraint where conname="
            "'ck_audit_events_authority_privacy_bounds' and "
            "conrelid='audit_events'::regclass"
        )
    )
    assert isinstance(forward_definition, str)
    backward_matches = [
        (candidate_old, candidate_new)
        for candidate_old, candidate_new in resource_markers
        if candidate_new in forward_definition
    ]
    assert backward_matches
    old, new = max(backward_matches, key=lambda item: len(item[1]))
    predecessor_source = forward_definition.removesuffix(" NOT VALID").replace(new, old)
    # Keep this normalization independent of the migration under test. Sharing its
    # implementation would let the repair helper reproduce the same defect and mask drift.
    predecessor_source = re.sub(
        r"\('([^']+)'::character varying\)::text",
        r"'\1'",
        predecessor_source,
    )
    predecessor_source = re.sub(
        r"\(\((\w+)\)::text = ANY \(ARRAY\[([^]]+)\]\)\)",
        r"\1 in (\2)",
        predecessor_source,
    )
    predecessor_source = re.sub(
        r"\(\((\w+)\)::text <> ALL \(ARRAY\[([^]]+)\]\)\)",
        r"\1 not in (\2)",
        predecessor_source,
    )
    await connection.execute(
        text("alter table audit_events drop constraint ck_audit_events_authority_privacy_bounds")
    )
    await connection.exec_driver_sql(
        "alter table audit_events add constraint "
        "ck_audit_events_authority_privacy_bounds "
        f"{predecessor_source}{validation_clause}"
    )


async def _restore_0034_trigger_states(
    connection,
    triggers: tuple[tuple[object, ...], ...],
) -> None:
    allowed_triggers = {
        ("audit_events", "audit_events_reject_truncate"),
        ("audit_events", "audit_events_reject_update_delete"),
        ("audit_events", "audit_events_set_authority_time"),
        ("audit_events", "audit_events_validate_idempotency"),
        ("authority_idempotency_records", "authority_idempotency_guard"),
        (
            "authority_idempotency_records",
            "authority_idempotency_pending_guard",
        ),
        (
            "authority_idempotency_records",
            "authority_idempotency_reject_truncate",
        ),
    }
    operations = {
        "O": "enable trigger",
        "D": "disable trigger",
        "R": "enable replica trigger",
        "A": "enable always trigger",
    }
    for trigger in triggers:
        assert len(trigger) == 3
        table_name, trigger_name, enabled_state = trigger
        assert (table_name, trigger_name) in allowed_triggers
        if isinstance(enabled_state, bytes):
            enabled_state = enabled_state.decode("ascii")
        assert enabled_state in operations
        await connection.exec_driver_sql(
            f"alter table {table_name} {operations[enabled_state]} {trigger_name}"
        )


async def _facts_are_safe_0034(
    database_url: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    project_id: str,
) -> bool | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(
                text(
                    "select authority_event_facts_are_safe("
                    "'AuthorityInvalidationRequested',cast(:before as json),"
                    "cast(:after as json),:project)"
                ),
                {
                    "before": None if before is None else json.dumps(before),
                    "after": None if after is None else json.dumps(after),
                    "project": project_id,
                },
            )
    finally:
        await engine.dispose()


async def _seed_pending_issue_cause_0034(database_url: str) -> dict[str, str]:
    values = {
        "record": str(uuid4()),
        "key": str(uuid4()),
        "actor": str(uuid4()),
        "target": str(uuid4()),
        "project": str(uuid4()),
        "grant": str(uuid4()),
        "manager": str(uuid4()),
        "request": str(uuid4()),
        "correlation": str(uuid4()),
    }
    engine = create_async_engine(database_url)
    trigger_states = None
    try:
        async with engine.begin() as connection:
            trigger_states = tuple(
                tuple(row)
                for row in (
                    await connection.execute(
                        text(
                            "select tgrelid::regclass::text,tgname,tgenabled "
                            "from pg_trigger where "
                            "(tgrelid='authority_idempotency_records'::regclass and "
                            "tgname='authority_idempotency_pending_guard') or "
                            "(tgrelid='audit_events'::regclass and "
                            "tgname='audit_events_validate_idempotency') "
                            "order by tgrelid::regclass::text,tgname"
                        )
                    )
                ).all()
            )
            assert len(trigger_states) == 2
            await connection.execute(
                text(
                    "alter table authority_idempotency_records disable trigger "
                    "authority_idempotency_pending_guard"
                )
            )
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_validate_idempotency")
            )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into authority_idempotency_records "
                    "(id,idempotency_key,actor_ref_kind,actor_ref,operation,request_digest,status) "
                    "values (:record,:key,'actor_profile',:actor,"
                    "'project_role_grant.issue',:digest,'pending')"
                ),
                values | {"digest": f"sha256:{'1' * 64}"},
            )
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                    "auth_source,is_dev_auth,event_payload,event_domain,event_version,"
                    "actor_ref_kind,request_id,correlation_id,target_actor_ref_kind,"
                    "target_actor_ref,matched_grant_id,permission_id,project_id,resource_type,"
                    "resource_id,target_ref_kind,target_ref_id,reason,idempotency_reference,"
                    "after_facts) values (:grant,'project_role_grant',:grant,"
                    "'ProjectRoleGrantIssued',:actor,'[]','{}','local_authority',false,'{}',"
                    "'authority',1,'actor_profile',:request,:correlation,'actor_profile',"
                    ":target,:manager,'project.role_grant.manage',:project,"
                    "'project_role_grant',:grant,'project_role_grant',:grant,"
                    "'authority_assignment',:record,cast(:facts as json))"
                ),
                values
                | {
                    "facts": json.dumps(
                        {
                            "status": "active",
                            "role": "submitter",
                            "scope_type": "project",
                            "scope_id": values["project"],
                            "effective": True,
                        }
                    )
                },
            )
        return values
    finally:
        if trigger_states is not None:
            async with engine.begin() as connection:
                await _restore_0034_trigger_states(connection, trigger_states)
        await engine.dispose()


async def _insert_false_issue_invalidation_0034(
    database_url: str,
    values: dict[str, str],
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                    "auth_source,is_dev_auth,event_payload,event_domain,event_version,"
                    "actor_ref_kind,request_id,correlation_id,permission_id,project_id,"
                    "resource_type,resource_id,reason,idempotency_reference,"
                    "invalidation_cause_event_id,invalidation_target_kind,"
                    "invalidation_target_ref,before_facts,after_facts) values "
                    "(:id,'authority_invalidation',:id,'AuthorityInvalidationRequested',"
                    ":actor,'[]','{}','local_authority',false,'{}','authority',1,"
                    "'actor_profile',:request,:correlation,'project.role_grant.manage',"
                    ":project,'project_role_grant',:grant,'authority_state_changed',:record,"
                    ":grant,'project_role_grant',:grant,cast(:before as json),"
                    "cast(:after as json))"
                ),
                values
                | {
                    "id": str(uuid4()),
                    "before": json.dumps({"effective": True}),
                    "after": json.dumps({"effective": False}),
                },
            )
    finally:
        await engine.dispose()


async def _count_linked_events_0034(database_url: str, record_id: str) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return int(
                await connection.scalar(
                    text("select count(*) from audit_events where idempotency_reference=:record"),
                    {"record": record_id},
                )
            )
    finally:
        await engine.dispose()


def _five_key_revoke_facts_0034(
    values: dict[str, str],
    *,
    effective: bool,
) -> dict[str, object]:
    return {
        "effective": effective,
        "role": "submitter",
        "scope_type": "project",
        "scope_id": values["project"],
        "future_obligation": "auth13_assignment",
    }


async def _seed_pending_revoke_cause_0034(
    database_url: str,
    *,
    envelope: dict[str, str] | None = None,
) -> dict[str, str]:
    values = {
        "record": str(uuid4()),
        "key": str(uuid4()),
        "cause": str(uuid4()),
        "actor": envelope["actor"] if envelope else str(uuid4()),
        "target": envelope["target"] if envelope else str(uuid4()),
        "project": envelope["project"] if envelope else str(uuid4()),
        "grant": envelope["grant"] if envelope else str(uuid4()),
        "manager": envelope["manager"] if envelope else str(uuid4()),
        "request": envelope["request"] if envelope else str(uuid4()),
        "correlation": envelope["correlation"] if envelope else str(uuid4()),
    }
    before_facts = {
        "status": "active",
        "role": "submitter",
        "scope_type": "project",
        "scope_id": values["project"],
        "effective": True,
    }
    after_facts = {**before_facts, "status": "revoked", "effective": False}
    engine = create_async_engine(database_url)
    pending_guard = None
    try:
        async with engine.begin() as connection:
            pending_guard = tuple(
                (
                    await connection.execute(
                        text(
                            "select tgrelid::regclass::text,tgname,tgenabled "
                            "from pg_trigger where tgrelid="
                            "'authority_idempotency_records'::regclass and tgname="
                            "'authority_idempotency_pending_guard'"
                        )
                    )
                ).one()
            )
            await connection.execute(
                text(
                    "alter table authority_idempotency_records disable trigger "
                    "authority_idempotency_pending_guard"
                )
            )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into authority_idempotency_records "
                    "(id,idempotency_key,actor_ref_kind,actor_ref,operation,"
                    "request_digest,status) values "
                    "(:record,:key,'actor_profile',:actor,"
                    "'project_role_grant.revoke',:digest,'pending')"
                ),
                values | {"digest": f"sha256:{'2' * 64}"},
            )
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,"
                    "claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                    "event_version,actor_ref_kind,request_id,correlation_id,"
                    "target_actor_ref_kind,target_actor_ref,matched_grant_id,permission_id,"
                    "project_id,resource_type,resource_id,target_ref_kind,target_ref_id,"
                    "reason,idempotency_reference,before_facts,after_facts) values "
                    "(:cause,'project_role_grant',:grant,'ProjectRoleGrantRevoked',"
                    ":actor,'[]','{}','local_authority',false,'{}','authority',1,"
                    "'actor_profile',:request,:correlation,'actor_profile',:target,"
                    ":manager,'project.role_grant.manage',:project,'project_role_grant',"
                    ":grant,'project_role_grant',:grant,'authority_revocation',:record,"
                    "cast(:before as json),cast(:after as json))"
                ),
                values
                | {
                    "before": json.dumps(before_facts),
                    "after": json.dumps(after_facts),
                },
            )
        return values
    finally:
        if pending_guard is not None:
            async with engine.begin() as connection:
                await _restore_0034_trigger_states(connection, (pending_guard,))
        await engine.dispose()


async def _insert_revoke_invalidation_0034(
    database_url: str,
    record: dict[str, str],
    *,
    cause: dict[str, str],
    before_facts: dict[str, object],
    after_facts: dict[str, object],
    target_ref_kind: str | None,
    target_ref_id: str | None,
) -> str:
    invalidation_id = str(uuid4())
    values = {
        **cause,
        "cause": cause.get("cause", cause["grant"]),
        "id": invalidation_id,
        "record": record["record"],
        "actor": record["actor"],
        "before": json.dumps(before_facts),
        "after": json.dumps(after_facts),
        "target_ref_kind": target_ref_kind,
        "target_ref_id": target_ref_id,
    }
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,"
                    "claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                    "event_version,actor_ref_kind,request_id,correlation_id,"
                    "target_actor_ref_kind,target_actor_ref,permission_id,project_id,"
                    "resource_type,resource_id,target_ref_kind,target_ref_id,reason,"
                    "idempotency_reference,"
                    "invalidation_cause_event_id,invalidation_target_kind,"
                    "invalidation_target_ref,before_facts,after_facts) values "
                    "(:id,'authority_invalidation',:id,'AuthorityInvalidationRequested',"
                    ":actor,'[]','{}','local_authority',false,'{}','authority',1,"
                    "'actor_profile',:request,:correlation,'actor_profile',:target,"
                    "'project.role_grant.manage',:project,'project_role_grant',:grant,"
                    ":target_ref_kind,:target_ref_id,'authority_state_changed',:record,"
                    ":cause,'project_role_grant',"
                    ":grant,cast(:before as json),cast(:after as json))"
                ),
                values,
            )
        return invalidation_id
    finally:
        await engine.dispose()


async def _linked_revoke_fixture_state_0034(
    database_url: str,
    records: list[str],
) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            parameters = {"records": records}
            record_rows = tuple(
                (
                    await connection.execute(
                        text(
                            "select to_jsonb(r)::text from authority_idempotency_records r "
                            "where r.id::text=any(cast(:records as text[])) "
                            "order by r.id::text"
                        ),
                        parameters,
                    )
                ).scalars()
            )
            event_rows = tuple(
                (
                    await connection.execute(
                        text(
                            "select to_jsonb(e)::text from audit_events e "
                            "where e.idempotency_reference::text=any(cast(:records as text[])) "
                            "order by e.id::text"
                        ),
                        parameters,
                    )
                ).scalars()
            )
            event_ids = tuple(
                (
                    await connection.execute(
                        text(
                            "select e.id::text from audit_events e "
                            "where e.idempotency_reference::text=any(cast(:records as text[])) "
                            "order by e.id::text"
                        ),
                        parameters,
                    )
                ).scalars()
            )
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "records": record_rows,
                "events": event_rows,
                "event_ids": event_ids,
                "event_count": len(event_rows),
            }
    finally:
        await engine.dispose()


async def _clear_linked_revoke_fixtures_0034(
    database_url: str,
    records: list[str],
) -> None:
    if not records:
        return
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            if not await connection.scalar(
                text("select to_regclass('authority_idempotency_records') is not null")
            ):
                return
            trigger_rows = (
                await connection.execute(
                    text(
                        "select tgrelid::regclass::text,tgname,tgenabled from pg_trigger "
                        "where tgrelid in ('audit_events'::regclass,"
                        "'authority_idempotency_records'::regclass) and not tgisinternal "
                        "order by tgrelid::regclass::text,tgname"
                    )
                )
            ).all()
            await connection.execute(text("alter table audit_events disable trigger user"))
            await connection.execute(
                text("alter table authority_idempotency_records disable trigger user")
            )
            parameters = {"records": records}
            await connection.execute(
                text(
                    "delete from audit_events where "
                    "idempotency_reference::text=any(cast(:records as text[]))"
                ),
                parameters,
            )
            await connection.execute(
                text(
                    "delete from authority_idempotency_records where "
                    "id::text=any(cast(:records as text[]))"
                ),
                parameters,
            )
            await _restore_0034_trigger_states(
                connection,
                tuple(tuple(row) for row in trigger_rows),
            )
    finally:
        await engine.dispose()


async def _clear_0034_issue_fixture(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            if not await connection.scalar(
                text("select to_regclass('authority_idempotency_records') is not null")
            ):
                return
            await connection.execute(text("alter table audit_events disable trigger user"))
            await connection.execute(
                text("alter table authority_idempotency_records disable trigger user")
            )
            await connection.execute(
                text(
                    "delete from audit_events where idempotency_reference in "
                    "(select id from authority_idempotency_records "
                    "where operation='project_role_grant.issue' and status='pending')"
                )
            )
            await connection.execute(
                text(
                    "delete from authority_idempotency_records "
                    "where operation='project_role_grant.issue' and status='pending'"
                )
            )
            await connection.execute(
                text("alter table authority_idempotency_records enable trigger user")
            )
            await connection.execute(text("alter table audit_events enable trigger user"))
    finally:
        await engine.dispose()


async def _insert_empty_pending_0034_issue(database_url: str) -> None:
    engine = create_async_engine(database_url)
    pending_guard = None
    try:
        async with engine.begin() as connection:
            pending_guard = tuple(
                (
                    await connection.execute(
                        text(
                            "select tgrelid::regclass::text,tgname,tgenabled "
                            "from pg_trigger where tgrelid="
                            "'authority_idempotency_records'::regclass and tgname="
                            "'authority_idempotency_pending_guard'"
                        )
                    )
                ).one()
            )
            await connection.execute(
                text(
                    "alter table authority_idempotency_records disable trigger "
                    "authority_idempotency_pending_guard"
                )
            )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into authority_idempotency_records "
                    "(id,idempotency_key,actor_ref_kind,actor_ref,operation,request_digest,status) "
                    "values (:id,:key,'actor_profile',:actor,'project_role_grant.issue',"
                    ":digest,'pending')"
                ),
                {
                    "id": str(uuid4()),
                    "key": str(uuid4()),
                    "actor": str(uuid4()),
                    "digest": f"sha256:{'0' * 64}",
                },
            )
    finally:
        if pending_guard is not None:
            async with engine.begin() as connection:
                await _restore_0034_trigger_states(connection, (pending_guard,))
        await engine.dispose()


async def _authority_idempotency_state_shape_0034(
    database_url: str,
) -> tuple[str, bool, str] | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select conrelid::regclass::text,convalidated,"
                        "pg_get_constraintdef(oid) from pg_constraint where conname="
                        "'ck_authority_idempotency_records_state_shape' and "
                        "conrelid='authority_idempotency_records'::regclass"
                    )
                )
            ).one_or_none()
            return None if row is None else tuple(row)
    finally:
        await engine.dispose()


async def _add_pending_issue_response_0034(
    database_url: str,
    state_shape_constraint: tuple[str, bool, str],
) -> None:
    table_name, validated, definition = state_shape_constraint
    assert table_name == "authority_idempotency_records"
    assert isinstance(validated, bool)
    assert isinstance(definition, str)
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            current_row = (
                await connection.execute(
                    text(
                        "select conrelid::regclass::text,convalidated,"
                        "pg_get_constraintdef(oid) from pg_constraint where conname="
                        "'ck_authority_idempotency_records_state_shape' and "
                        "conrelid='authority_idempotency_records'::regclass"
                    )
                )
            ).one()
            assert tuple(current_row) == state_shape_constraint
            trigger_rows = (
                await connection.execute(
                    text(
                        "select tgrelid::regclass::text,tgname,tgenabled from pg_trigger "
                        "where tgrelid='authority_idempotency_records'::regclass and "
                        "not tgisinternal order by tgname"
                    )
                )
            ).all()
            assert {row.tgname for row in trigger_rows} == {
                "authority_idempotency_guard",
                "authority_idempotency_pending_guard",
                "authority_idempotency_reject_truncate",
            }
            await connection.execute(
                text(
                    "alter table authority_idempotency_records drop constraint "
                    "ck_authority_idempotency_records_state_shape"
                )
            )
            await connection.execute(
                text("alter table authority_idempotency_records disable trigger user")
            )
            await connection.execute(
                text(
                    "update authority_idempotency_records set "
                    "response_resource_type='project_role_grant',"
                    "response_resource_id=:resource,response_resource_version=1,"
                    "response_http_status=201 where operation='project_role_grant.issue'"
                ),
                {"resource": str(uuid4())},
            )
            await connection.exec_driver_sql(
                "alter table authority_idempotency_records add constraint "
                "ck_authority_idempotency_records_state_shape "
                f"{definition.removesuffix(' NOT VALID')} not valid"
            )
            await _restore_0034_trigger_states(
                connection,
                tuple(tuple(row) for row in trigger_rows),
            )
    finally:
        await engine.dispose()


async def _clear_pending_0034_issues(
    database_url: str,
    state_shape_constraint: tuple[str, bool, str] | None = None,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("select to_regclass('authority_idempotency_records') is not null")
            )
            if exists:
                trigger_rows = (
                    await connection.execute(
                        text(
                            "select tgrelid::regclass::text,tgname,tgenabled from pg_trigger "
                            "where tgrelid='authority_idempotency_records'::regclass "
                            "and not tgisinternal order by tgname"
                        )
                    )
                ).all()
                await connection.execute(
                    text("alter table authority_idempotency_records disable trigger user")
                )
                await connection.execute(
                    text(
                        "delete from authority_idempotency_records "
                        "where operation='project_role_grant.issue' and status='pending'"
                    )
                )
                if state_shape_constraint is not None:
                    table_name, validated, definition = state_shape_constraint
                    assert table_name == "authority_idempotency_records"
                    assert isinstance(validated, bool)
                    assert isinstance(definition, str)
                    await connection.execute(
                        text(
                            "alter table authority_idempotency_records drop constraint "
                            "if exists ck_authority_idempotency_records_state_shape"
                        )
                    )
                    await connection.exec_driver_sql(
                        "alter table authority_idempotency_records add constraint "
                        "ck_authority_idempotency_records_state_shape "
                        f"{definition.removesuffix(' NOT VALID')}"
                        f"{' not valid' if not validated else ''}"
                    )
                await _restore_0034_trigger_states(
                    connection,
                    tuple(tuple(row) for row in trigger_rows),
                )
    finally:
        await engine.dispose()


async def _replace_0034_fact_constraint_with_drift(
    database_url: str,
    drift: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table audit_events drop constraint ck_audit_events_fact_bounds")
            )
            if drift == "changed":
                await connection.execute(
                    text(
                        "alter table audit_events add constraint ck_audit_events_fact_bounds "
                        "check (event_domain <> 'authority' or true)"
                    )
                )
            elif drift == "unvalidated":
                await connection.execute(
                    text(
                        "alter table audit_events add constraint ck_audit_events_fact_bounds "
                        "check (event_domain <> 'authority' or true) not valid"
                    )
                )
            elif drift == "wrong_table":
                await connection.execute(
                    text(
                        "alter table projects add constraint ck_audit_events_fact_bounds "
                        "check (true)"
                    )
                )
    finally:
        await engine.dispose()


async def _restore_0034_fact_constraint(
    database_url: str,
    definition: str | None,
) -> None:
    if definition is None:
        return
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "select conrelid::regclass::text table_name from pg_constraint "
                            "where conname='ck_audit_events_fact_bounds'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for table_name in rows:
                await connection.execute(
                    text(f"alter table {table_name} drop constraint ck_audit_events_fact_bounds")
                )
            await connection.execute(
                text(
                    "alter table audit_events add constraint "
                    f"ck_audit_events_fact_bounds {definition}"
                )
            )
    finally:
        await engine.dispose()


def test_artifact_recovery_schema_and_empty_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """Prove 0032 lineage indexes, custody triggers, and reversible empty state."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            assert asyncio.run(_artifact_recovery_schema(isolated_database_env)) == {
                "revision": HEAD_REVISION,
                "constraints": {
                    "artifact_recovery_attempt_custody",
                    "artifact_verification_lineage_custody",
                    "uq_artifact_recovery_idempotency",
                    "uq_artifact_recovery_retry_job",
                    "uq_artifact_recovery_source_job",
                    "uq_artifact_verification_initial_origin",
                    "uq_artifact_verification_parent",
                },
            }
            command.downgrade(config, "0031_project_role_grants")
            assert "artifact_recovery_attempts" not in asyncio.run(
                _fetch_table_names(isolated_database_env)
            )
        finally:
            command.downgrade(config, "base")


def test_guide_source_artifact_ingest_schema_and_replay(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0038 installs one linear server-owned guide-ingest staging table."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0038_guide_source_ingest")
            assert "guide_source_artifact_ingests" in asyncio.run(
                _fetch_table_names(isolated_database_env)
            )
            asyncio.run(_seed_populated_guide_source_ingest(isolated_database_env))
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade populated guide source artifact ingests",
            ):
                command.downgrade(config, "0037_art_auth_context_evidence")
            asyncio.run(_clear_populated_guide_source_ingest(isolated_database_env))
            command.downgrade(config, "0037_art_auth_context_evidence")
            assert "guide_source_artifact_ingests" not in asyncio.run(
                _fetch_table_names(isolated_database_env)
            )
            command.upgrade(config, "0038_guide_source_ingest")
            assert "guide_source_artifact_ingests" in asyncio.run(
                _fetch_table_names(isolated_database_env)
            )
        finally:
            command.downgrade(config, "base")


def test_0039_backfills_setup_generations_per_guide(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Existing setup runs receive deterministic guide-local generations."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0038_guide_source_ingest")
            expected = asyncio.run(_seed_setup_runs_before_0039(isolated_database_env))

            command.upgrade(config, "0039_guide_source_bindings")
            actual = asyncio.run(_setup_generations_after_0039(isolated_database_env))
            assert actual == expected
            assert "guide_source_artifact_bindings" in asyncio.run(
                _fetch_table_names(isolated_database_env)
            )

            command.downgrade(config, "0038_guide_source_ingest")
            assert "guide_source_artifact_bindings" not in asyncio.run(
                _fetch_table_names(isolated_database_env)
            )
        finally:
            command.downgrade(config, "base")


async def _seed_setup_runs_before_0039(database_url: str) -> list[tuple[str, int]]:
    engine = create_async_engine(database_url)
    project_ids = (str(uuid4()), str(uuid4()))
    guide_ids = (str(uuid4()), str(uuid4()))
    snapshot_ids = (str(uuid4()), str(uuid4()))
    run_ids = (str(uuid4()), str(uuid4()), str(uuid4()))
    digest = "sha256:" + "b" * 64
    try:
        async with engine.begin() as connection:
            for index in range(2):
                parameters = {
                    "project": project_ids[index],
                    "guide": guide_ids[index],
                    "snapshot": snapshot_ids[index],
                    "slug": f"generation-{project_ids[index]}",
                    "digest": digest,
                }
                await connection.execute(
                    text(
                        "insert into projects (id, name, slug, status) "
                        "values (:project, 'Generation project', :slug, 'draft')"
                    ),
                    parameters,
                )
                await connection.execute(
                    text(
                        "insert into project_guides "
                        "(id, project_id, version, status, content_markdown, created_by) "
                        "values (:guide, :project, 'v1', 'draft', '# Guide', 'migration-test')"
                    ),
                    parameters,
                )
                await connection.execute(
                    text(
                        "insert into guide_source_snapshots "
                        "(id, project_id, guide_id, guide_version, manifest_schema_version, "
                        "manifest_json, bundle_hash, captured_by) values "
                        "(:snapshot, :project, :guide, 'v1', '1', '{}'::json, :digest, "
                        "'migration-test')"
                    ),
                    parameters,
                )

            for run_id, guide_index, created_at in (
                (run_ids[1], 0, datetime(2026, 1, 2, tzinfo=UTC)),
                (run_ids[0], 0, datetime(2026, 1, 1, tzinfo=UTC)),
                (run_ids[2], 1, datetime(2026, 1, 1, tzinfo=UTC)),
            ):
                await connection.execute(
                    text(
                        "insert into project_setup_runs "
                        "(id, project_id, guide_id, guide_version, source_snapshot_id, "
                        "source_snapshot_hash, status, current_step, created_by, created_at) "
                        "values (:run, :project, :guide, 'v1', :snapshot, :digest, "
                        "'queued', 'queued', 'migration-test', :created_at)"
                    ),
                    {
                        "run": run_id,
                        "project": project_ids[guide_index],
                        "guide": guide_ids[guide_index],
                        "snapshot": snapshot_ids[guide_index],
                        "digest": digest,
                        "created_at": created_at,
                    },
                )
        return sorted([(run_ids[0], 1), (run_ids[1], 2), (run_ids[2], 1)])
    finally:
        await engine.dispose()


async def _setup_generations_after_0039(database_url: str) -> list[tuple[str, int]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text("select id, setup_generation from project_setup_runs order by id")
            )
            return sorted((str(row.id), int(row.setup_generation)) for row in rows)
    finally:
        await engine.dispose()


async def _seed_populated_guide_source_ingest(database_url: str) -> None:
    engine = create_async_engine(database_url)
    ids = {
        name: str(uuid4())
        for name in ("actor", "identity_link", "project", "guide", "snapshot", "item")
    }
    try:
        async with engine.begin() as connection:
            parameters = {
                **ids,
                "ingest": str(uuid4()),
                "slug": f"migration-{ids['project']}",
                "sha256": "sha256:" + "a" * 64,
            }
            await insert_historical_project(
                connection,
                project_id=ids["project"],
                name="Migration project",
                slug=parameters["slug"],
            )
            statements = (
                (
                    "insert into actor_profiles "
                    "(id, actor_kind, status, provisioning_method, created_by) "
                    "values (:actor, 'human', 'active', 'automatic_first_access', 'migration-test')"
                ),
                (
                    "insert into actor_identity_links "
                    "(id, actor_profile_id, issuer, subject, subject_kind, status, "
                    "linked_by, last_verified_at) values "
                    "(:identity_link, :actor, 'https://identity.test', :actor, 'human', "
                    "'active', 'migration-test', clock_timestamp())"
                ),
                (
                    "insert into project_guides "
                    "(id, project_id, version, status, content_markdown, created_by) "
                    "values (:guide, :project, 'v1', 'draft', '# Guide', 'migration-test')"
                ),
                (
                    "insert into guide_source_snapshots "
                    "(id, project_id, guide_id, guide_version, manifest_schema_version, "
                    "manifest_json, bundle_hash, captured_by) values "
                    "(:snapshot, :project, :guide, 'v1', '1', '{}'::json, :sha256, 'migration-test')"
                ),
                (
                    "insert into guide_source_snapshot_items "
                    "(id, source_snapshot_id, item_order, source_kind, durable_ref, "
                    "ingestion_adapter, content_hash, media_type) values "
                    "(:item, :snapshot, 0, 'upload', 'migration-test', 'upload', :sha256, "
                    "'application/octet-stream')"
                ),
                (
                    "insert into guide_source_artifact_ingests "
                    "(id, source_item_id, actor_profile_id, sha256, byte_count, media_type) "
                    "values (:ingest, :item, :actor, :sha256, 1, 'application/octet-stream')"
                ),
            )
            for statement in statements:
                await connection.execute(text(statement), parameters)
    finally:
        await engine.dispose()


async def _clear_populated_guide_source_ingest(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("delete from guide_source_artifact_ingests"))
    finally:
        await engine.dispose()


async def _artifact_recovery_schema(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("select version_num from alembic_version"))
            names = set(
                (
                    await connection.execute(
                        text(
                            "select conname from pg_constraint where conrelid in "
                            "('artifact_recovery_attempts'::regclass, "
                            "'artifact_verification_jobs'::regclass) "
                            "union select tgname from pg_trigger where tgrelid in "
                            "('artifact_recovery_attempts'::regclass, "
                            "'artifact_verification_jobs'::regclass) and not tgisinternal "
                            "union select indexname from pg_indexes where indexname = "
                            "'uq_artifact_verification_initial_origin'"
                        )
                    )
                ).scalars()
            )
        expected = {
            "artifact_recovery_attempt_custody",
            "artifact_verification_lineage_custody",
            "uq_artifact_recovery_idempotency",
            "uq_artifact_recovery_retry_job",
            "uq_artifact_recovery_source_job",
            "uq_artifact_verification_initial_origin",
            "uq_artifact_verification_parent",
        }
        return {"revision": revision, "constraints": names & expected}
    finally:
        await engine.dispose()


def test_0035_project_read_action_evidence_round_trip(
    isolated_database_env: str, migration_lock
) -> None:
    """Prove all eleven planned pairs and both permissions round-trip exactly."""
    config = _alembic_config()
    definitions = tuple(
        definition
        for definition in ACTION_DEFINITIONS
        if definition.owner in {ActionOwner.AUTH_11B, ActionOwner.AUTH_11C1, ActionOwner.AUTH_11C2}
    )
    assert len(definitions) == 11
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=definitions
                )
            )
            asyncio.run(_assert_removed_art_authority_rejected(isolated_database_env))
            command.downgrade(config, "0034_project_role_issue_evidence")
            command.upgrade(config, "head")
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=definitions
                )
            )
            asyncio.run(_assert_removed_art_authority_rejected(isolated_database_env))
        finally:
            command.downgrade(config, "base")


def test_0035_project_read_action_evidence_refuses_nonempty_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """A committed 11A audit row must block removal of its frozen vocabulary."""
    config = _alembic_config()
    definition = next(item for item in ACTION_DEFINITIONS if item.owner is ActionOwner.AUTH_11B)
    event_id = ""
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            event_id = asyncio.run(
                _insert_authorization_action_event_for(
                    isolated_database_env,
                    definition.action_id.value,
                    definition.permission_id.value,
                )
            )
            with pytest.raises(
                RuntimeError, match="cannot downgrade non-empty project-read action evidence"
            ):
                command.downgrade(config, "0034_project_role_issue_evidence")
            assert asyncio.run(_current_revision(isolated_database_env)) == (HEAD_REVISION)
        finally:
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=event_id))
            command.downgrade(config, "base")


def test_0041_project_mutation_action_evidence_round_trip(
    isolated_database_env: str, migration_lock
) -> None:
    """Prove all eighteen planned action pairs round-trip without new permissions."""
    config = _alembic_config()
    definitions = tuple(
        definition
        for definition in ACTION_DEFINITIONS
        if definition.owner in _PROJECT_MUTATION_OWNERS
    )
    assert len(definitions) == 18
    assert {definition.permission_id for definition in definitions} == {
        PermissionId.PROJECT_CREATE,
        PermissionId.PROJECT_GUIDE_MANAGE,
        PermissionId.PROJECT_REVIEW_POLICY_MANAGE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
    }
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=definitions
                )
            )
            command.downgrade(config, "0040_guide_materialization")
            command.upgrade(config, "head")
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=definitions
                )
            )
        finally:
            command.downgrade(config, "base")


def test_0041_project_mutation_action_evidence_refuses_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """Committed direct and idempotency-linked evidence must preserve vocabulary."""
    config = _alembic_config()
    definitions = tuple(
        item for item in ACTION_DEFINITIONS if item.owner in _PROJECT_MUTATION_OWNERS
    )
    assert len(definitions) == 18
    event_id = ""
    linked_event_id = ""
    record_id = str(uuid4())
    actor_id = str(uuid4())
    target_id = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            definition = definitions[0]
            event_id = asyncio.run(
                _insert_authorization_action_event_for(
                    isolated_database_env,
                    definition.action_id.value,
                    definition.permission_id.value,
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade non-empty project-mutation action evidence",
            ):
                command.downgrade(config, "0040_guide_materialization")
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=event_id))
            event_id = ""

            definition = definitions[-1]
            asyncio.run(
                _insert_committed_authority_idempotency(
                    isolated_database_env, record_id, actor_id, target_id
                )
            )
            linked_event_id = asyncio.run(
                _insert_linked_authorization_action_event(
                    isolated_database_env,
                    record_id=record_id,
                    actor_id=actor_id,
                    action_id=definition.action_id.value,
                    permission_id=definition.permission_id.value,
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade non-empty project-mutation action evidence",
            ):
                command.downgrade(config, "0040_guide_materialization")
            assert asyncio.run(_current_revision(isolated_database_env)) == HEAD_REVISION
        finally:
            if event_id:
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )
            if linked_event_id:
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=linked_event_id)
                )
            asyncio.run(
                _remove_authority_idempotency_fixture(
                    isolated_database_env, record_id, orphan_event=None
                )
            )
            command.downgrade(config, "base")


def test_0043_project_setup_service_round_trip_and_seeds_no_authority(
    isolated_database_env: str, migration_lock
) -> None:
    """0043 alone admits the eighth identity without creating actor authority."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0042_guide_extraction")
            prior = asyncio.run(_project_setup_service_state(isolated_database_env))
            assert not prior["constraint_admits_identity"]
            assert prior["authority_rows"] == (0, 0, 0, 0)

            command.upgrade(config, "head")
            upgraded = asyncio.run(_project_setup_service_state(isolated_database_env))
            assert upgraded["constraint_admits_identity"]
            assert upgraded["authority_rows"] == (0, 0, 0, 0)

            command.downgrade(config, "0042_guide_extraction")
            restored = asyncio.run(_project_setup_service_state(isolated_database_env))
            assert not restored["constraint_admits_identity"]
            assert restored["authority_rows"] == (0, 0, 0, 0)

            command.upgrade(config, "head")
            assert asyncio.run(_project_setup_service_state(isolated_database_env)) == upgraded
        finally:
            command.downgrade(config, "base")


def test_0043_project_setup_service_refuses_in_use_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """An exact project-setup profile prevents removal of its closed identity."""
    config = _alembic_config()
    actor_profile_id = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(
                _insert_project_setup_service_actor(
                    isolated_database_env,
                    actor_profile_id=actor_profile_id,
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade project setup service identity",
            ):
                command.downgrade(config, "0042_guide_extraction")
            assert asyncio.run(_current_revision(isolated_database_env)) == (HEAD_REVISION)
            asyncio.run(_remove_fixed_service_actor(isolated_database_env, actor_profile_id))
            actor_profile_id = ""
            command.downgrade(config, "0042_guide_extraction")
        finally:
            if actor_profile_id:
                asyncio.run(_remove_fixed_service_actor(isolated_database_env, actor_profile_id))
            command.downgrade(config, "base")


async def _project_create_authority_schema_state(database_url: str) -> tuple[bool, bool, bool]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            table_exists = bool(
                await connection.scalar(
                    text(
                        "select to_regclass('public.project_create_idempotency_records') "
                        "is not null"
                    )
                )
            )
            provenance_exists = bool(
                await connection.scalar(
                    text(
                        "select exists(select 1 from information_schema.columns "
                        "where table_schema='public' and table_name='projects' "
                        "and column_name='authorization_decision_event_id')"
                    )
                )
            )
            privacy = (
                await connection.scalar(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint "
                        "where conrelid='audit_events'::regclass "
                        "and conname='ck_audit_events_authority_privacy_bounds'"
                    )
                )
                or ""
            )
            return (
                table_exists,
                provenance_exists,
                "project_create_operation" in privacy and "target_ref_kind" in privacy,
            )
    finally:
        await engine.dispose()


def test_0044_project_create_authority_round_trip(
    isolated_database_env: str, migration_lock
) -> None:
    """0044 alone installs and exactly removes project-create persistence."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0043_project_setup_service")
            assert asyncio.run(_project_create_authority_schema_state(isolated_database_env)) == (
                False,
                False,
                False,
            )
            command.upgrade(config, "head")
            assert asyncio.run(_project_create_authority_schema_state(isolated_database_env)) == (
                True,
                True,
                True,
            )
            command.downgrade(config, "0043_project_setup_service")
            assert asyncio.run(_project_create_authority_schema_state(isolated_database_env)) == (
                False,
                False,
                False,
            )
            command.upgrade(config, "head")
        finally:
            command.downgrade(config, "base")


async def _assert_0044_rejects_new_unattributed_project(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(
                text(
                    "insert into projects (id,name,slug,status) "
                    "values (:id,'Unattributed','unattributed','draft')"
                ),
                {"id": str(uuid4())},
            )
            with pytest.raises(IntegrityError):
                await transaction.commit()
            if transaction.is_active:
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_0044_rejects_new_unattributed_project(isolated_database_env: str, migration_lock) -> None:
    """Historical null provenance survives, but new null-provenance rows deny."""
    config = _alembic_config()
    historical_id = str(uuid4())
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0043_project_setup_service")

            async def seed_historical() -> None:
                engine = create_async_engine(isolated_database_env)
                try:
                    async with engine.begin() as connection:
                        await connection.execute(
                            text(
                                "insert into projects (id,name,slug,status) "
                                "values (:id,'Historical','historical','draft')"
                            ),
                            {"id": historical_id},
                        )
                finally:
                    await engine.dispose()

            asyncio.run(seed_historical())
            command.upgrade(config, "head")
            asyncio.run(_assert_0044_rejects_new_unattributed_project(isolated_database_env))

            async def remove_historical() -> None:
                engine = create_async_engine(isolated_database_env)
                try:
                    async with engine.begin() as connection:
                        await connection.execute(
                            text("delete from projects where id=:id"), {"id": historical_id}
                        )
                finally:
                    await engine.dispose()

            asyncio.run(remove_historical())
        finally:
            command.downgrade(config, "base")


def test_0044_refuses_populated_project_create_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """A committed project custody chain prevents destructive downgrade."""
    config = _alembic_config()

    async def seed() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                await seed_authorized_project(
                    session,
                    project_id=str(uuid4()),
                    name="Downgrade custody",
                    slug=f"downgrade-custody-{uuid4()}",
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def reset_schema() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("drop schema public cascade"))
                await connection.execute(text("create schema public"))
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(seed())
            with pytest.raises(
                RuntimeError, match="cannot downgrade non-empty project creation authority"
            ):
                command.downgrade(config, "0043_project_setup_service")
        finally:
            asyncio.run(reset_schema())


async def _guide_metadata_authority_schema_state(
    database_url: str,
) -> tuple[bool, bool, bool, bool]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return (
                bool(
                    await connection.scalar(
                        text(
                            "select to_regclass('public.guide_mutation_idempotency_records') "
                            "is not null"
                        )
                    )
                ),
                bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from information_schema.columns "
                            "where table_schema='public' and table_name='project_guides' "
                            "and column_name='mutation_generation')"
                        )
                    )
                ),
                bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from information_schema.columns "
                            "where table_schema='public' and table_name='guide_source_snapshots' "
                            "and column_name='creation_generation')"
                        )
                    )
                ),
                bool(
                    await connection.scalar(
                        text(
                            "select exists(select 1 from pg_trigger "
                            "where tgname='guide_mutation_reservation_custody')"
                        )
                    )
                ),
            )
    finally:
        await engine.dispose()


def test_0045_guide_source_metadata_authority_round_trip(
    isolated_database_env: str, migration_lock
) -> None:
    """0045 installs and exactly removes the guide-mutation custody seam."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0044_project_create_authority")
            assert asyncio.run(_guide_metadata_authority_schema_state(isolated_database_env)) == (
                False,
                False,
                False,
                False,
            )
            command.upgrade(config, "head")
            assert asyncio.run(_guide_metadata_authority_schema_state(isolated_database_env)) == (
                True,
                True,
                True,
                True,
            )
            command.downgrade(config, "0044_project_create_authority")
            assert asyncio.run(_guide_metadata_authority_schema_state(isolated_database_env)) == (
                False,
                False,
                False,
                False,
            )
            command.upgrade(config, "head")
        finally:
            command.downgrade(config, "base")


def test_0045_preserves_historical_guide_rows(isolated_database_env: str, migration_lock) -> None:
    """0045 preserves historical rows while the later v2 clean cut refuses them."""
    config = _alembic_config()
    project_id, guide_id, snapshot_id, setup_run_id = (str(uuid4()) for _ in range(4))
    snapshot_hash = "sha256:" + "0" * 64

    async def seed_and_read(*, seed: bool) -> tuple | None:
        engine = create_async_engine(isolated_database_env)
        try:
            if seed:
                factory = async_sessionmaker(engine, expire_on_commit=False)
                async with factory() as session:
                    await insert_historical_project(
                        session,
                        project_id=project_id,
                        name="Historical guide project",
                        slug=f"historical-guide-{uuid4()}",
                    )
                    await session.execute(
                        text(
                            "insert into project_guides "
                            "(id,project_id,version,status,content_markdown,created_by) "
                            "values (:id,:project_id,'v1','draft','# Historical','legacy')"
                        ),
                        {"id": guide_id, "project_id": project_id},
                    )
                    await session.execute(
                        text(
                            "insert into guide_source_snapshots "
                            "(id,project_id,guide_id,guide_version,manifest_schema_version,"
                            "manifest_json,bundle_hash,captured_by) values "
                            "(:id,:project_id,:guide_id,'v1','guide_source_snapshot.v1',"
                            "cast(:manifest as jsonb),:hash,'legacy')"
                        ),
                        {
                            "id": snapshot_id,
                            "project_id": project_id,
                            "guide_id": guide_id,
                            "manifest": '{"schema_version":"guide_source_snapshot.v1","items":[]}',
                            "hash": snapshot_hash,
                        },
                    )
                    await session.execute(
                        text(
                            "insert into project_setup_runs "
                            "(id,project_id,guide_id,guide_version,source_snapshot_id,"
                            "source_snapshot_hash,setup_generation,status,current_step,created_by) "
                            "values (:id,:project_id,:guide_id,'v1',:snapshot_id,:hash,1,"
                            "'queued','queued','legacy')"
                        ),
                        {
                            "id": setup_run_id,
                            "project_id": project_id,
                            "guide_id": guide_id,
                            "snapshot_id": snapshot_id,
                            "hash": snapshot_hash,
                        },
                    )
                    await session.commit()
                return None
            async with engine.connect() as connection:
                guide_result = await connection.execute(
                    text(
                        "select mutation_generation,last_mutated_by_actor_profile_id,"
                        "last_authorization_decision_event_id from project_guides where id=:id"
                    ),
                    {"id": guide_id},
                )
                snapshot_result = await connection.execute(
                    text(
                        "select creation_generation,created_by_actor_profile_id,"
                        "authorization_decision_event_id from guide_source_snapshots where id=:id"
                    ),
                    {"id": snapshot_id},
                )
                setup_result = await connection.execute(
                    text(
                        "select authorized_by_actor_profile_id,authorized_via_identity_link_id,"
                        "authorization_decision_event_id from project_setup_runs where id=:id"
                    ),
                    {"id": setup_run_id},
                )
                return (*guide_result.one(), *snapshot_result.one(), *setup_result.one())
        finally:
            await engine.dispose()

    async def reset_schema() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("drop schema public cascade"))
                await connection.execute(text("create schema public"))
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0044_project_create_authority")
            asyncio.run(seed_and_read(seed=True))
            command.upgrade(config, "0045_guide_metadata_authority")
            assert asyncio.run(seed_and_read(seed=False)) == (None,) * 9
            command.downgrade(config, "0044_project_create_authority")
            command.upgrade(config, "0045_guide_metadata_authority")
            assert asyncio.run(seed_and_read(seed=False)) == (None,) * 9
            with pytest.raises(
                RuntimeError,
                match="guide source v2 requires an empty guide-source namespace",
            ):
                command.upgrade(config, "0050_guide_source_v2")
        finally:
            asyncio.run(reset_schema())


def test_0045_refuses_populated_guide_authority_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """Committed 12D custody prevents destructive downgrade."""
    config = _alembic_config()

    async def seed() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                project_id, guide_id = str(uuid4()), str(uuid4())
                await seed_authorized_project(
                    session,
                    project_id=project_id,
                    name="Guide downgrade custody",
                    slug=f"guide-downgrade-{uuid4()}",
                )
                project_record = await session.scalar(
                    select(ProjectCreateIdempotencyRecord).where(
                        ProjectCreateIdempotencyRecord.project_id == project_id
                    )
                )
                assert project_record is not None
                operation_id, decision_id = uuid4(), uuid4()
                resource = ProjectGuideMutationResourceContext(
                    resource_type="project_guide_mutation",
                    resource_id=UUID(guide_id),
                    operation_id=operation_id,
                    scope_project_id=UUID(project_id),
                    guide_id=UUID(guide_id),
                    target_kind="create",
                    guide_exists=False,
                    operation_generation=1,
                )
                resource_digest = authorization_resource_digest(resource)
                audit_row = (
                    await session.execute(
                        text(
                            "select id,matched_grant_id::uuid from audit_events "
                            "where action_id='project.create' and target_ref_id=:project_id"
                        ),
                        {"project_id": project_id},
                    )
                ).one()
                grant_id = audit_row[1]
                assert grant_id is not None
                await AuditService(session).add_authority_event(
                    AuthorityAuditEventInput(
                        event_id=decision_id,
                        event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
                        entity_type="authorization_decision",
                        entity_id=str(decision_id),
                        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                        actor_ref=project_record.actor_profile_id,
                        request_id=uuid4(),
                        correlation_id=uuid4(),
                        matched_grant_id=str(grant_id),
                        permission_id=PermissionId.PROJECT_GUIDE_MANAGE,
                        action_id=ActionId.PROJECT_GUIDE_CREATE,
                        project_id=project_id,
                        resource_type="project",
                        resource_id=project_id,
                        target_ref_kind="project",
                        target_ref_id=project_id,
                        reason="authorization_evaluation",
                        after_facts={
                            "allowed": True,
                            "resource_context_digest": resource_digest,
                        },
                    )
                )
                reservation = GuideMutationIdempotencyRecord(
                    id=uuid4(),
                    actor_profile_id=project_record.actor_profile_id,
                    identity_link_id=project_record.identity_link_id,
                    action_id=ActionId.PROJECT_GUIDE_CREATE.value,
                    idempotency_key=uuid4(),
                    request_digest=canonical_json_hash(
                        {"domain": "workstream.test.guide_create", "guide_id": guide_id}
                    ),
                    resource_context_digest=resource_digest,
                    operation_id=operation_id,
                    project_id=project_id,
                    resource_id=guide_id,
                    operation_generation=1,
                    status="pending",
                )
                session.add(reservation)
                session.add(
                    ProjectGuide(
                        id=guide_id,
                        project_id=project_id,
                        version="v1",
                        status="draft",
                        content_markdown="# Custodied",
                        created_by=project_record.actor_profile_id,
                        mutation_generation=1,
                        last_mutated_by_actor_profile_id=project_record.actor_profile_id,
                        last_mutated_via_identity_link_id=project_record.identity_link_id,
                        last_mutated_by_admin_role_grant_id=grant_id,
                        last_mutation_scope_type="system",
                        last_mutation_action_id=ActionId.PROJECT_GUIDE_CREATE.value,
                        last_authorization_decision_event_id=str(decision_id),
                    )
                )
                await session.flush()
                reservation.status = "committed"
                reservation.response_json = {"id": guide_id}
                reservation.committed_at = datetime.now(UTC)
                await session.commit()
                with pytest.raises(DBAPIError, match="activation authority"):
                    await session.execute(
                        text("update project_guides set status='active' where id=:id"),
                        {"id": guide_id},
                    )
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    async def reset_schema() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("drop schema public cascade"))
                await connection.execute(text("create schema public"))
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(seed())
            with pytest.raises(
                RuntimeError, match="cannot downgrade used guide source-metadata authority"
            ):
                command.downgrade(config, "0044_project_create_authority")
        finally:
            asyncio.run(reset_schema())


def test_0036_art_auth_catalogue_round_trip(isolated_database_env: str, migration_lock) -> None:
    """Prove the three replacement pairs and review permission round-trip exactly."""
    config = _alembic_config()
    definitions = tuple(
        definition
        for definition in ACTION_DEFINITIONS
        if definition.owner in {ActionOwner.XINT_002_05A, ActionOwner.XINT_002_07}
    )
    assert len(definitions) == 3
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=definitions
                )
            )
            asyncio.run(_assert_removed_art_authority_rejected(isolated_database_env))
            command.downgrade(config, "0033_authorization_read_rate")
            command.upgrade(config, "head")
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=definitions
                )
            )
            asyncio.run(_assert_removed_art_authority_rejected(isolated_database_env))
        finally:
            command.downgrade(config, "base")


def test_0036_art_auth_catalogue_refuses_obsolete_evidence(
    isolated_database_env: str, migration_lock
) -> None:
    """Obsolete upload evidence must block catalogue deletion without mutation."""
    config = _alembic_config()
    event_ids: list[str] = []
    record_id = str(uuid4())
    actor_id = str(uuid4())
    target_id = str(uuid4())
    obsolete = _OBSOLETE_ART_UPLOAD_IDS
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0035_project_read_evidence")
            event_ids.extend(
                asyncio.run(
                    _insert_authorization_action_event_for(
                        isolated_database_env, identifier, identifier
                    )
                )
                for identifier in obsolete
            )
            event_ids.append(
                asyncio.run(
                    _insert_forward_permission_reference(
                        isolated_database_env,
                        event_ids[0],
                        reference_field="target",
                        permission=obsolete[0],
                    )
                )
            )
            event_ids.append(
                asyncio.run(
                    _insert_forward_permission_reference(
                        isolated_database_env,
                        event_ids[1],
                        reference_field="invalidation",
                        permission=obsolete[1],
                    )
                )
            )
            asyncio.run(
                _insert_committed_authority_idempotency(
                    isolated_database_env, record_id, actor_id, target_id
                )
            )
            event_ids.append(
                asyncio.run(
                    _insert_linked_authorization_action_event(
                        isolated_database_env,
                        record_id=record_id,
                        actor_id=actor_id,
                        action_id=obsolete[2],
                        permission_id=obsolete[2],
                    )
                )
            )
            before = asyncio.run(
                _art_catalogue_migration_state(
                    isolated_database_env, actions=obsolete, permissions=obsolete
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot remove non-empty obsolete artifact authority evidence",
            ):
                command.upgrade(config, "head")
            assert (
                asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env, actions=obsolete, permissions=obsolete
                    )
                )
                == before
            )
            for event_id in reversed(event_ids):
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )
            event_ids.clear()
            asyncio.run(
                _remove_authority_idempotency_fixture(
                    isolated_database_env, record_id, orphan_event=None
                )
            )
            record_id = ""
            command.upgrade(config, "head")
            assert asyncio.run(_current_revision(isolated_database_env)) == (HEAD_REVISION)
        finally:
            for event_id in reversed(event_ids):
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )
            if record_id:
                asyncio.run(
                    _remove_authority_idempotency_fixture(
                        isolated_database_env, record_id, orphan_event=None
                    )
                )
            command.downgrade(config, "base")


def test_0036_art_auth_catalogue_refuses_new_evidence_downgrade(
    isolated_database_env: str, migration_lock
) -> None:
    """Committed replacement-action evidence must block restoration of old authority."""
    config = _alembic_config()
    definitions = tuple(
        item
        for item in ACTION_DEFINITIONS
        if item.owner in {ActionOwner.XINT_002_05A, ActionOwner.XINT_002_07}
    )
    event_ids: list[str] = []
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            event_ids.extend(
                asyncio.run(
                    _insert_authorization_action_event_for(
                        isolated_database_env,
                        definition.action_id.value,
                        definition.permission_id.value,
                    )
                )
                for definition in definitions
            )
            review_permission = PermissionId.ARTIFACT_REVIEW_PACKET_MATERIALIZE.value
            event_ids.append(
                asyncio.run(
                    _insert_forward_permission_reference(
                        isolated_database_env,
                        event_ids[0],
                        reference_field="target",
                        permission=review_permission,
                    )
                )
            )
            before = asyncio.run(
                _art_catalogue_migration_state(
                    isolated_database_env,
                    actions=tuple(item.action_id.value for item in definitions),
                    permissions=(review_permission,),
                )
            )
            with pytest.raises(
                RuntimeError, match="cannot downgrade non-empty ART authorization evidence"
            ):
                command.downgrade(config, "0035_project_read_evidence")
            assert (
                asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=tuple(item.action_id.value for item in definitions),
                        permissions=(review_permission,),
                    )
                )
                == before
            )
        finally:
            for event_id in reversed(event_ids):
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )
            command.downgrade(config, "base")


def test_0036_art_auth_catalogue_refuses_each_obsolete_evidence_shape(
    isolated_database_env: str, migration_lock
) -> None:
    """Prove every removal predicate independently blocks the clean-cut upgrade."""
    config = _alembic_config()
    obsolete = _OBSOLETE_ART_UPLOAD_IDS
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0035_project_read_evidence")
            for identifier in obsolete:
                event_id = asyncio.run(
                    _insert_authorization_action_event_for(
                        isolated_database_env, identifier, identifier
                    )
                )
                before = asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=(identifier,),
                        permissions=(identifier,),
                    )
                )
                with pytest.raises(
                    RuntimeError,
                    match="cannot remove non-empty obsolete artifact authority evidence",
                ):
                    command.upgrade(config, "head")
                assert (
                    asyncio.run(
                        _art_catalogue_migration_state(
                            isolated_database_env,
                            actions=(identifier,),
                            permissions=(identifier,),
                        )
                    )
                    == before
                )
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )

            cause_id = asyncio.run(
                _insert_authorization_action_event_for(
                    isolated_database_env,
                    "actor.profile.read_self",
                    "actor.profile.read_self",
                )
            )
            for reference_field, permission in (
                ("target", obsolete[0]),
                ("invalidation", obsolete[1]),
            ):
                event_id = asyncio.run(
                    _insert_forward_permission_reference(
                        isolated_database_env,
                        cause_id,
                        reference_field=reference_field,
                        permission=permission,
                    )
                )
                before = asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env, actions=(), permissions=(permission,)
                    )
                )
                with pytest.raises(
                    RuntimeError,
                    match="cannot remove non-empty obsolete artifact authority evidence",
                ):
                    command.upgrade(config, "head")
                assert (
                    asyncio.run(
                        _art_catalogue_migration_state(
                            isolated_database_env, actions=(), permissions=(permission,)
                        )
                    )
                    == before
                )
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=cause_id))

            record_id, actor_id, target_id = str(uuid4()), str(uuid4()), str(uuid4())
            asyncio.run(
                _insert_committed_authority_idempotency(
                    isolated_database_env, record_id, actor_id, target_id
                )
            )
            event_id = asyncio.run(
                _insert_linked_authorization_action_event(
                    isolated_database_env,
                    record_id=record_id,
                    actor_id=actor_id,
                    action_id=obsolete[2],
                    permission_id=obsolete[2],
                )
            )
            before = asyncio.run(
                _art_catalogue_migration_state(
                    isolated_database_env,
                    actions=(obsolete[2],),
                    permissions=(obsolete[2],),
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot remove non-empty obsolete artifact authority evidence",
            ):
                command.upgrade(config, "head")
            assert (
                asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=(obsolete[2],),
                        permissions=(obsolete[2],),
                    )
                )
                == before
            )
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=event_id))
            asyncio.run(
                _remove_authority_idempotency_fixture(
                    isolated_database_env, record_id, orphan_event=None
                )
            )

            orphan_event_id = asyncio.run(
                _insert_orphan_linked_authorization_action_event(
                    isolated_database_env,
                    action_id=obsolete[3],
                    permission_id=obsolete[3],
                )
            )
            before = asyncio.run(
                _art_catalogue_migration_state(
                    isolated_database_env,
                    actions=(obsolete[3],),
                    permissions=(obsolete[3],),
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot remove non-empty obsolete artifact authority evidence",
            ):
                command.upgrade(config, "head")
            assert (
                asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=(obsolete[3],),
                        permissions=(obsolete[3],),
                    )
                )
                == before
            )
            asyncio.run(
                _remove_authority_audit_fixture(isolated_database_env, event_id=orphan_event_id)
            )
        finally:
            command.downgrade(config, "base")


def test_0036_art_auth_catalogue_refuses_each_new_evidence_shape(
    isolated_database_env: str, migration_lock
) -> None:
    """Prove each added action and permission independently blocks downgrade."""
    config = _alembic_config()
    definitions = tuple(
        item
        for item in ACTION_DEFINITIONS
        if item.owner in {ActionOwner.XINT_002_05A, ActionOwner.XINT_002_07}
    )
    review_permission = PermissionId.ARTIFACT_REVIEW_PACKET_MATERIALIZE.value
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            for definition in definitions:
                event_id = asyncio.run(
                    _insert_authorization_action_event_for(
                        isolated_database_env,
                        definition.action_id.value,
                        definition.permission_id.value,
                    )
                )
                before = asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=(definition.action_id.value,),
                        permissions=(definition.permission_id.value,),
                    )
                )
                with pytest.raises(
                    RuntimeError,
                    match="cannot downgrade non-empty ART authorization evidence",
                ):
                    command.downgrade(config, "0035_project_read_evidence")
                assert (
                    asyncio.run(
                        _art_catalogue_migration_state(
                            isolated_database_env,
                            actions=(definition.action_id.value,),
                            permissions=(definition.permission_id.value,),
                        )
                    )
                    == before
                )
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )

            cause_id = asyncio.run(
                _insert_authorization_action_event_for(
                    isolated_database_env,
                    "actor.profile.read_self",
                    "actor.profile.read_self",
                )
            )
            for reference_field in ("target", "invalidation"):
                event_id = asyncio.run(
                    _insert_forward_permission_reference(
                        isolated_database_env,
                        cause_id,
                        reference_field=reference_field,
                        permission=review_permission,
                    )
                )
                before = asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=(),
                        permissions=(review_permission,),
                    )
                )
                with pytest.raises(
                    RuntimeError,
                    match="cannot downgrade non-empty ART authorization evidence",
                ):
                    command.downgrade(config, "0035_project_read_evidence")
                assert (
                    asyncio.run(
                        _art_catalogue_migration_state(
                            isolated_database_env,
                            actions=(),
                            permissions=(review_permission,),
                        )
                    )
                    == before
                )
                asyncio.run(
                    _remove_authority_audit_fixture(isolated_database_env, event_id=event_id)
                )
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=cause_id))

            record_id, actor_id, target_id = str(uuid4()), str(uuid4()), str(uuid4())
            asyncio.run(
                _insert_committed_authority_idempotency(
                    isolated_database_env, record_id, actor_id, target_id
                )
            )
            linked_definition = definitions[0]
            event_id = asyncio.run(
                _insert_linked_authorization_action_event(
                    isolated_database_env,
                    record_id=record_id,
                    actor_id=actor_id,
                    action_id=linked_definition.action_id.value,
                    permission_id=linked_definition.permission_id.value,
                )
            )
            before = asyncio.run(
                _art_catalogue_migration_state(
                    isolated_database_env,
                    actions=(linked_definition.action_id.value,),
                    permissions=(linked_definition.permission_id.value,),
                )
            )
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade non-empty ART authorization evidence",
            ):
                command.downgrade(config, "0035_project_read_evidence")
            assert (
                asyncio.run(
                    _art_catalogue_migration_state(
                        isolated_database_env,
                        actions=(linked_definition.action_id.value,),
                        permissions=(linked_definition.permission_id.value,),
                    )
                )
                == before
            )
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=event_id))
            asyncio.run(
                _remove_authority_idempotency_fixture(
                    isolated_database_env, record_id, orphan_event=None
                )
            )
        finally:
            command.downgrade(config, "base")


def test_project_role_migration_constraints_and_immutable_history(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0031 exact-role coexistence, evidence bounds, and lifecycle custody."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            result = asyncio.run(_exercise_project_role_migration(isolated_database_env))
            assert result == {
                "revision": HEAD_REVISION,
                "role_count": 3,
                "invalid_availability": "23514",
                "duplicate_role": "23505",
                "snapshot_update": "55000",
                "snapshot_delete": "55000",
                "snapshot_truncate": "55000",
                "issuance_update": "23514",
                "grant_delete": "55000",
                "grant_truncate": "55000",
                "database_timestamps": True,
                "snapshot_constraint_rejections": {
                    "extra_key": "23514",
                    "available_empty": "23514",
                    "unavailable_with_reference": "23514",
                    "url_reference": "23514",
                    "too_many_references": "23514",
                    "invalid_prior_uuid": "23514",
                },
                "grant_constraint_rejections": {
                    "automated_method": "23514",
                    "combined_role": "23514",
                    "leading_space_reason": "23514",
                    "control_reason": "23514",
                    "oversize_reason": "23514",
                    "snapshot_mismatch": "23503",
                    "invalid_active_version": "23514",
                },
                "valid_revoke": ("revoked", 2),
                "second_revoke": "23514",
            }
            project_definitions = tuple(
                definition
                for definition in ACTION_DEFINITIONS
                if definition.owner in {ActionOwner.AUTH_10B, ActionOwner.AUTH_10C}
            )
            assert len(project_definitions) == 5
            asyncio.run(
                _assert_authorization_action_sql_pairs(
                    isolated_database_env, definitions=project_definitions
                )
            )
            asyncio.run(_assert_project_role_denial_sql(isolated_database_env))
        finally:
            command.downgrade(config, "base")


def test_project_role_upgrade_refuses_each_legacy_predicate_before_ddl(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Every obsolete storage predicate leaves 0030 and its schema untouched."""
    config = _alembic_config()
    cases = (
        {"before_facts": {"role": "both"}},
        {"after_facts": {"role": "both"}},
        {"before_facts": {"replaced_grant_id": str(uuid4())}},
        {"after_facts": {"replaced_grant_id": str(uuid4())}},
        {"event_type": "ProjectRoleGrantReplaced"},
        {"reason": "authority_replacement"},
        {
            "before_facts": {"role": "both", "replaced_grant_id": str(uuid4())},
            "after_facts": {"role": "both", "replaced_grant_id": str(uuid4())},
            "event_type": "ProjectRoleGrantReplaced",
            "reason": "authority_replacement",
        },
    )
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0030_artifact_verification")
            for patch in cases:
                event_id, constraints, triggers = asyncio.run(
                    _install_legacy_project_role_blocker(
                        isolated_database_env, patch, bypass_constraints=True
                    )
                )
                before_event = asyncio.run(_project_role_audit_row(isolated_database_env, event_id))
                with pytest.raises(
                    RuntimeError,
                    match="cannot safely upgrade replacement-era project-role evidence",
                ):
                    command.upgrade(config, "head")
                assert asyncio.run(_project_role_refusal_state(isolated_database_env)) == (
                    "0030_artifact_verification",
                    False,
                    False,
                    1,
                )
                assert (
                    asyncio.run(_project_role_audit_row(isolated_database_env, event_id))
                    == before_event
                )
                asyncio.run(
                    _remove_legacy_project_role_blocker(
                        isolated_database_env, event_id, constraints, triggers
                    )
                )

            for operation in ("project_role_grant.issue", "project_role_grant.revoke"):
                record_id = asyncio.run(
                    _insert_project_role_idempotency_blocker(isolated_database_env, operation)
                )
                before_record = asyncio.run(
                    _project_role_idempotency_row(isolated_database_env, record_id)
                )
                with pytest.raises(
                    RuntimeError,
                    match="cannot safely upgrade replacement-era project-role evidence",
                ):
                    command.upgrade(config, "head")
                assert asyncio.run(_project_role_refusal_state(isolated_database_env))[:3] == (
                    "0030_artifact_verification",
                    False,
                    False,
                )
                assert (
                    asyncio.run(_project_role_idempotency_row(isolated_database_env, record_id))
                    == before_record
                )
                asyncio.run(
                    _remove_project_role_idempotency_blocker(isolated_database_env, record_id)
                )

            event_id, constraints, triggers = asyncio.run(
                _install_legacy_project_role_blocker(
                    isolated_database_env,
                    {"after_facts": {"role": "both"}},
                    bypass_constraints=True,
                )
            )
            record_id = asyncio.run(
                _insert_project_role_idempotency_blocker(
                    isolated_database_env, "project_role_grant.revoke"
                )
            )
            before_record = asyncio.run(
                _project_role_idempotency_row(isolated_database_env, record_id)
            )
            with pytest.raises(
                RuntimeError,
                match="cannot safely upgrade replacement-era project-role evidence",
            ):
                command.upgrade(config, "head")
            assert (
                asyncio.run(_project_role_idempotency_row(isolated_database_env, record_id))
                == before_record
            )
            asyncio.run(_remove_project_role_idempotency_blocker(isolated_database_env, record_id))
            asyncio.run(
                _remove_legacy_project_role_blocker(
                    isolated_database_env, event_id, constraints, triggers
                )
            )
            unrelated_event_id = asyncio.run(
                _insert_authorization_action_event(isolated_database_env)
            )
            unrelated_before = asyncio.run(
                _project_role_audit_row(isolated_database_env, unrelated_event_id)
            )
            command.upgrade(config, "head")
            assert (
                asyncio.run(_project_role_audit_row(isolated_database_env, unrelated_event_id))
                == unrelated_before
            )
            asyncio.run(
                _remove_authorization_action_events(isolated_database_env, [unrelated_event_id])
            )
        finally:
            command.downgrade(config, "base")


def test_project_role_downgrade_refuses_each_reserved_evidence_predicate(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Every representable 10A audit predicate leaves head and row untouched."""
    config = _alembic_config()
    cases = (
        *(
            {"action_id": action}
            for action in (
                "project.contributor_candidate.list",
                "project_role_grant.list",
                "project_role_grant.read",
                "project_role_grant.issue",
                "project_role_grant.revoke",
            )
        ),
        {"denial_code": "project_role_grant_already_revoked"},
        {"denial_code": "project_role_grant_replay_state_changed"},
        {
            "action_id": "project_role_grant.issue",
            "denial_code": "project_role_grant_replay_state_changed",
        },
    )
    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            for patch in cases:
                event_id, constraints, triggers = asyncio.run(
                    _install_legacy_project_role_blocker(
                        isolated_database_env, patch, bypass_constraints=False
                    )
                )
                before_event = asyncio.run(_project_role_audit_row(isolated_database_env, event_id))
                with pytest.raises(
                    RuntimeError, match="cannot downgrade project-role grant evidence"
                ):
                    command.downgrade(config, "0030_artifact_verification")
                assert asyncio.run(_project_role_refusal_state(isolated_database_env))[:3] == (
                    HEAD_REVISION,
                    True,
                    True,
                )
                assert (
                    asyncio.run(_project_role_audit_row(isolated_database_env, event_id))
                    == before_event
                )
                asyncio.run(
                    _remove_legacy_project_role_blocker(
                        isolated_database_env, event_id, constraints, triggers
                    )
                )
            for include_grant in (False, True):
                table_ids = asyncio.run(
                    _install_project_role_table_blockers(
                        isolated_database_env, include_grant=include_grant
                    )
                )
                before_tables = asyncio.run(
                    _project_role_table_rows(isolated_database_env, table_ids)
                )
                with pytest.raises(
                    RuntimeError, match="cannot downgrade project-role grant evidence"
                ):
                    command.downgrade(config, "0030_artifact_verification")
                assert asyncio.run(_project_role_refusal_state(isolated_database_env))[:3] == (
                    HEAD_REVISION,
                    True,
                    True,
                )
                assert (
                    asyncio.run(_project_role_table_rows(isolated_database_env, table_ids))
                    == before_tables
                )
                asyncio.run(_remove_project_role_table_blockers(isolated_database_env, table_ids))
            command.downgrade(config, "0030_artifact_verification")
        finally:
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
                "revision": HEAD_REVISION,
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
            assert asyncio.run(_current_revision(isolated_database_env)) == (HEAD_REVISION)
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
                            ActionOwner.AUTH_10B,
                            ActionOwner.AUTH_10C,
                            ActionOwner.AUTH_11B,
                            ActionOwner.AUTH_11C1,
                            ActionOwner.AUTH_11C2,
                            *_PROJECT_MUTATION_OWNERS,
                            ActionOwner.XINT_002_05A,
                            ActionOwner.XINT_002_07,
                            ActionOwner.XINT_003_08A,
                            ActionOwner.XINT_003_08B,
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
    expected_historical = {
        "event_type": "SensitiveAuthorizationAllowed",
        "permission_id": "actor.profile.read_any",
        "action_id": None,
    }
    assert historical_before == expected_historical
    assert historical_upgraded == expected_historical
    assert historical_downgraded == expected_historical
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
                            ActionOwner.AUTH_10B,
                            ActionOwner.AUTH_10C,
                            ActionOwner.AUTH_11B,
                            ActionOwner.AUTH_11C1,
                            ActionOwner.AUTH_11C2,
                            *_PROJECT_MUTATION_OWNERS,
                            ActionOwner.XINT_002_05A,
                            ActionOwner.XINT_002_07,
                            ActionOwner.XINT_003_08A,
                            ActionOwner.XINT_003_08B,
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
    service_id = actor_id_from_external_identity("https://identity.test", "auth09-legacy-service")
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
            for digest_key in ("source_digest", "manifest_digest", "envelope_digest"):
                digest = mapped[digest_key]
                assert isinstance(digest, str)
                assert len(digest) == 64
            assert mapped["private_evidence_columns"] is False
            assert asyncio.run(_service_identity_guards(isolated_database_env, service_id)) == {
                "identity_update_rejected": True,
                "kind_update_rejected": True,
                "human_identity_rejected": True,
                "unknown_identity_rejected": True,
                "duplicate_identity_rejected": True,
            }
            assert asyncio.run(_service_identity_evidence_guards(isolated_database_env)) == {
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
                asyncio.run(_remove_authorization_action_events(isolated_database_env, [event_id]))
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
                        "select last_verified_at is not null from actor_identity_links where id=:id"
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
                        "delete from actor_profiles where id in (:human,:rejected_human,:service)"
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
            refused_namespace_count = asyncio.run(_artifact_namespace_count(isolated_database_env))
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
            prior_shape = ("0025_artifact_store_v2", False, False)
            lifecycle_shape = ("0026_actor_profile_lifecycle", True, True)
            assert asyncio.run(shape()) == prior_shape
            command.upgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(shape()) == lifecycle_shape
            command.downgrade(config, "0025_artifact_store_v2")
            assert asyncio.run(shape()) == prior_shape
            command.upgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(shape()) == lifecycle_shape
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
                code_point for code_point in range(0x110000) if chr(code_point).isspace()
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
            "update actor_identity_links set reactivated_by=:actor where actor_profile_id=:actor",
            "update actor_identity_links set reactivated_by=null where actor_profile_id=:actor",
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
            assert (
                asyncio.run(_current_revision(isolated_database_env))
                == "0026_actor_profile_lifecycle"
            )
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
                    await connection.execute(
                        text("alter table actor_profiles disable trigger user")
                    )
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
                    text("select id from actor_identity_links where actor_profile_id=:actor"),
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
                    reason = (
                        "administrative_correction" if is_profile else "identity_lifecycle_change"
                    )
                    before_facts = (
                        '{"status":"suspended"}' if is_profile else '{"status":"revoked"}'
                    )
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
                            '\'{"status":"active"}\'::json)'
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
                        "alter table audit_events disable trigger audit_events_reject_update_delete"
                    )
                )
                await connection.execute(
                    text("delete from audit_events where id=:id"), {"id": event_id}
                )
                await connection.execute(
                    text(
                        "alter table audit_events enable trigger audit_events_reject_update_delete"
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
            worker_column = ("worker_id", 100)
            contributor_column = ("contributor_id", 36)
            assert before["revision"] == "0026_actor_profile_lifecycle"
            assert before["assignment_column"] == worker_column
            assert before["submission_column"] == worker_column

            command.upgrade(config, "0027_contributor_foundation")
            upgraded = asyncio.run(_contributor_foundation_shape(isolated_database_env))
            expected_upgraded = {
                "revision": "0027_contributor_foundation",
                "assignment_column": contributor_column,
                "submission_column": contributor_column,
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
            assert upgraded == expected_upgraded
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
                _exercise_contributor_lineage_function_contract(isolated_database_env)
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
            assert restored["assignment_column"] == worker_column
            assert restored["submission_column"] == worker_column
            assert restored["assignment_index"] == "ix_task_assignments_worker_id"
            assert restored["submission_index"] == "ix_submissions_worker_id"
            assignment_values = restored["assignment_values"]
            assert isinstance(assignment_values, tuple)
            assert human_id in assignment_values
            expected_submission_values = (human_id,)
            assert restored["submission_values"] == expected_submission_values

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
    assignment_malformed = tuple(f"private.person.{index}@example.test" for index in range(22))
    submission_malformed = tuple(
        f"eyJhbGciOiJSUzI1NiJ9.secret-token-material-{index}" for index in range(22)
    )

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0026_actor_profile_lifecycle")
            fixture = asyncio.run(
                _seed_contributor_prior_head(
                    isolated_database_env,
                    assignment_values=assignment_malformed + (missing_ids[0], "service"),
                    submission_values=submission_malformed + (missing_ids[1], "service"),
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
                assert all(row[1] == "<redacted-malformed>" for row in malformed["rows"])
            assert all(
                value not in message for value in assignment_malformed + submission_malformed
            )
            assert all(
                row_id in message
                for row_id in (
                    tuple(fixture["assignment_ids"])[-2:] + tuple(fixture["submission_ids"])[-2:]
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


def test_authorization_read_rate_scope_upgrade_and_downgrade_refusal(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0033 preserves counters and refuses a live new-scope downgrade."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    async def insert(scope: str, marker: int) -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "insert into api_rate_control_counters "
                        "(control_scope,key_digest,window_started_at,window_expires_at,"
                        "request_count,updated_at) values "
                        "(:scope,:digest,statement_timestamp(),"
                        "statement_timestamp()+interval '1 minute',1,statement_timestamp())"
                    ),
                    {"scope": scope, "digest": bytes([marker]) * 32},
                )
        finally:
            await engine.dispose()

    async def scopes() -> list[str]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                return list(
                    (
                        await connection.execute(
                            text(
                                "select control_scope from api_rate_control_counters "
                                "order by control_scope"
                            )
                        )
                    ).scalars()
                )
        finally:
            await engine.dispose()

    async def clear_new_scope() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "delete from api_rate_control_counters "
                        "where control_scope='authorization_read'"
                    )
                )
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0032_artifact_recovery")
            asyncio.run(insert("first_access", 41))
            asyncio.run(insert("admin_mutation", 42))
            command.upgrade(config, "0033_authorization_read_rate")
            assert asyncio.run(scopes()) == ["admin_mutation", "first_access"]
            asyncio.run(insert("authorization_read", 43))
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade live authorization-read rate controls",
            ):
                command.downgrade(config, "0032_artifact_recovery")
            assert asyncio.run(scopes()) == [
                "admin_mutation",
                "authorization_read",
                "first_access",
            ]
            asyncio.run(clear_new_scope())

            inserted = threading.Event()
            release_insert = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as pool:
                insert_future = pool.submit(
                    asyncio.run,
                    _insert_rate_control_until_released(
                        isolated_database_env,
                        bytes([45]) * 32,
                        inserted,
                        release_insert,
                        scope="authorization_read",
                    ),
                )
                assert inserted.wait(timeout=5)
                downgrade_future = pool.submit(
                    command.downgrade,
                    config,
                    "0032_artifact_recovery",
                )
                asyncio.run(_wait_for_rate_control_table_lock(isolated_database_env))
                release_insert.set()
                insert_future.result(timeout=5)
                with pytest.raises(
                    RuntimeError,
                    match="cannot downgrade live authorization-read rate controls",
                ):
                    downgrade_future.result(timeout=5)

            asyncio.run(clear_new_scope())
            command.downgrade(config, "0032_artifact_recovery")
            assert asyncio.run(scopes()) == ["admin_mutation", "first_access"]
            with pytest.raises(IntegrityError):
                asyncio.run(insert("authorization_read", 43))
            command.upgrade(config, "0033_authorization_read_rate")
            asyncio.run(insert("authorization_read", 44))
        finally:
            asyncio.run(_clear_api_rate_controls(isolated_database_env))
            command.upgrade(config, "head")


def test_authorization_read_rate_scope_migration_refuses_constraint_drift(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Keep revision and counter state unchanged when the known constraint drifted."""
    config = _alembic_config()

    async def replace_constraint(definition: str) -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "alter table api_rate_control_counters drop constraint "
                        "ck_api_rate_control_counters_scope_token"
                    )
                )
                await connection.execute(
                    text(
                        "alter table api_rate_control_counters add constraint "
                        "ck_api_rate_control_counters_scope_token check "
                        f"({definition})"
                    )
                )
        finally:
            await engine.dispose()

    async def state() -> tuple[str, str, int]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                revision = str(
                    await connection.scalar(text("select version_num from alembic_version"))
                )
                definition = str(
                    await connection.scalar(
                        text(
                            "select pg_get_expr(conbin,conrelid) from pg_constraint "
                            "where conrelid='api_rate_control_counters'::regclass "
                            "and conname='ck_api_rate_control_counters_scope_token'"
                        )
                    )
                )
                rows = int(
                    await connection.scalar(text("select count(*) from api_rate_control_counters"))
                )
                return revision, definition, rows
        finally:
            await engine.dispose()

    old_definition = "control_scope in ('first_access', 'admin_mutation')"
    new_definition = "control_scope in ('first_access', 'admin_mutation', 'authorization_read')"
    drifted_definition = "control_scope in ('first_access')"

    with migration_lock():
        try:
            command.downgrade(config, "base")
            command.upgrade(config, "0032_artifact_recovery")
            asyncio.run(replace_constraint(drifted_definition))
            before_upgrade = asyncio.run(state())
            with pytest.raises(RuntimeError, match="unexpected API rate-control scope constraint"):
                command.upgrade(config, "0033_authorization_read_rate")
            assert asyncio.run(state()) == before_upgrade

            asyncio.run(replace_constraint(old_definition))
            command.upgrade(config, "0033_authorization_read_rate")
            asyncio.run(replace_constraint(drifted_definition))
            before_downgrade = asyncio.run(state())
            with pytest.raises(RuntimeError, match="unexpected API rate-control scope constraint"):
                command.downgrade(config, "0032_artifact_recovery")
            assert asyncio.run(state()) == before_downgrade

            asyncio.run(replace_constraint(new_definition))
        finally:
            command.upgrade(config, "head")


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
                "nullable": {row.column_name for row in column_rows if row.is_nullable == "YES"},
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
        async with engine.begin() as setup_connection:
            await insert_historical_project(
                setup_connection,
                project_id=project_id,
                name="Outbox migration",
                slug=f"outbox-migration-{project_id}",
                status="active",
            )
        async with engine.connect() as connection:
            transaction = await connection.begin()
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
                with pytest.raises(
                    RuntimeError, match="cannot downgrade with shared outbox events"
                ):
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
                    text("alter table actor_profiles disable trigger actor_profile_history_guard")
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
                await connection.execute(text("truncate table artifact_storage_namespaces cascade"))
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
            content_count = await connection.scalar(text("select count(*) from artifact_contents"))
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
    *,
    scope: str = "first_access",
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
                    "(:scope, :digest, statement_timestamp(), "
                    "statement_timestamp() + interval '1 minute', 1, statement_timestamp())"
                ),
                {"scope": scope, "digest": digest},
            )
            inserted.set()
            assert await asyncio.to_thread(release.wait, 5)
    finally:
        await engine.dispose()


async def _wait_for_rate_control_table_lock(database_url: str) -> None:
    """Wait until downgrade is queued for the table's access-exclusive lock."""
    engine = create_async_engine(database_url)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            async with engine.connect() as connection:
                waiting = await connection.scalar(
                    text(
                        "select exists(select 1 from pg_locks "
                        "where relation='api_rate_control_counters'::regclass "
                        "and mode='AccessExclusiveLock' and not granted)"
                    )
                )
            if waiting:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("downgrade did not request the table lock")
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


async def _assert_removed_art_authority_rejected(database_url: str) -> None:
    """Prove current SQL rejects every deleted pair and permission reference."""
    removed = _OBSOLETE_ART_UPLOAD_IDS
    engine = create_async_engine(database_url)
    try:
        for identifier in removed:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        _ACTION_EVIDENCE_INSERT,
                        _action_evidence_values(identifier, identifier),
                    )
                await transaction.rollback()

            async with engine.connect() as connection:
                transaction = await connection.begin()
                values = {
                    "id": str(uuid4()),
                    "request": str(uuid4()),
                    "correlation": str(uuid4()),
                    "permission": identifier,
                }
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            "insert into audit_events "
                            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,"
                            "claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                            "event_version,actor_ref_kind,request_id,correlation_id,permission_id,"
                            "target_ref_kind,target_ref_id,reason,after_facts) values "
                            "(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',"
                            "'workstream:system:bootstrap','[]'::json,'{}'::json,"
                            "'local_authority',false,'{}'::json,'authority',1,"
                            "'system_principal',:request,:correlation,'actor.profile.read_any',"
                            "'permission_registry',:permission,'authorization_evaluation',"
                            "'{\"allowed\": true}'::json)"
                        ),
                        values,
                    )
                await transaction.rollback()

            async with engine.connect() as connection:
                transaction = await connection.begin()
                cause = _action_evidence_values(
                    "actor.profile.read_self", "actor.profile.read_self"
                )
                await connection.execute(_ACTION_EVIDENCE_INSERT, cause)
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger audit_events_validate_idempotency"
                    )
                )
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            "insert into audit_events "
                            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,"
                            "claim_snapshot,auth_source,is_dev_auth,event_payload,event_domain,"
                            "event_version,actor_ref_kind,request_id,correlation_id,"
                            "invalidation_cause_event_id,invalidation_target_kind,"
                            "invalidation_target_ref,reason,before_facts,after_facts) values "
                            "(:id,'authority_invalidation',:id,"
                            "'AuthorityInvalidationRequested','workstream:system:bootstrap',"
                            "'[]'::json,'{}'::json,'local_authority',false,'{}'::json,"
                            "'authority',1,'system_principal',:request,:correlation,:cause,"
                            "'permission_registry',:permission,'authority_state_changed',"
                            "'{\"effective\": true}'::json,"
                            "'{\"effective\": false}'::json)"
                        ),
                        {
                            "id": str(uuid4()),
                            "request": str(uuid4()),
                            "correlation": str(uuid4()),
                            "cause": cause["id"],
                            "permission": identifier,
                        },
                    )
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _insert_authorization_action_event(database_url: str) -> str:
    """Commit one valid planned-action denial fixture."""
    values = _action_evidence_values("artifact.binding.read", "artifact.binding.read")
    event_id = values["id"]
    assert event_id is not None
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(_ACTION_EVIDENCE_INSERT, values)
        return event_id
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
    permission: str = "artifact.binding.read",
) -> str:
    """Commit one new permission-registry reference without an action ID."""
    event_id = str(uuid4())
    values = {
        "id": event_id,
        "request_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "permission": permission,
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
    event_id = values["id"]
    assert event_id is not None

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
            return False, event_id
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
        return observed, event_id


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
                    "reason": "authorization_policy_denial"
                    if denied
                    else "initial_access_bootstrap",
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
                        text(f"select {immutable_columns} from admin_role_grants where id=:id"),
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
                    text("update admin_role_grants set status='revoked',version=2 where id=:id"),
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
                    "select service_identity from actor_profiles where actor_kind='service' limit 1"
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
                        text("alter table actor_profile_migration_state disable trigger user")
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


async def _project_setup_service_state(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='actor_profiles'::regclass "
                    "and conname='ck_actor_profiles_kind_service_identity'"
                )
            )
            counts = tuple(
                (
                    await connection.execute(
                        text(
                            "select "
                            "(select count(*) from actor_profiles where service_identity=:identity),"
                            "(select count(*) from actor_identity_links as links join "
                            "actor_profiles as profiles on profiles.id=links.actor_profile_id "
                            "where profiles.service_identity=:identity),"
                            "(select count(*) from admin_role_grants as grants join "
                            "actor_profiles as profiles on profiles.id=grants.target_actor_profile_id "
                            "where profiles.service_identity=:identity),"
                            "(select count(*) from project_role_grants as grants join "
                            "actor_profiles as profiles on profiles.id=grants.actor_profile_id "
                            "where profiles.service_identity=:identity)"
                        ),
                        {"identity": ServiceIdentity.PROJECT_SETUP.value},
                    )
                ).one()
            )
            return {
                "constraint_admits_identity": (
                    ServiceIdentity.PROJECT_SETUP.value in str(definition)
                ),
                "authority_rows": counts,
            }
    finally:
        await engine.dispose()


async def _insert_project_setup_service_actor(
    database_url: str,
    *,
    actor_profile_id: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                    "values (:id,'service','active','manual_service_provisioning',"
                    ":identity,:id)"
                ),
                {
                    "id": actor_profile_id,
                    "identity": ServiceIdentity.PROJECT_SETUP.value,
                },
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links "
                    "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                    "values (:link,:actor,'https://identity.test',:subject,'service',"
                    "'active',:actor)"
                ),
                {
                    "link": str(uuid4()),
                    "actor": actor_profile_id,
                    "subject": ServiceIdentity.PROJECT_SETUP.value,
                },
            )
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
                service_id if value == "service" else value for value in assignment_values
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
            await connection.execute(text("alter table actor_identity_links disable trigger user"))
            await connection.execute(text("alter table actor_profiles disable trigger user"))
            await connection.execute(text("delete from actor_identity_links"))
            await connection.execute(text("delete from actor_profiles"))
            await connection.execute(text("alter table actor_profiles enable trigger user"))
            await connection.execute(text("alter table actor_identity_links enable trigger user"))
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
                await connection.scalar(text("select count(*) from lineage_nullable")) == 1
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
                text("drop trigger task_assignments_contributor_dependency on task_assignments")
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


async def _insert_linked_authorization_action_event(
    database_url: str,
    *,
    record_id: str,
    actor_id: str,
    action_id: str,
    permission_id: str,
) -> str:
    """Seed one constraint-valid linked denial while bypassing only link policy."""
    event_id = str(uuid4())
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_validate_idempotency")
            )
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                    "auth_source,is_dev_auth,event_payload,event_domain,event_version,"
                    "actor_ref_kind,request_id,correlation_id,permission_id,action_id,reason,"
                    "idempotency_reference,after_facts) values "
                    "(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',"
                    ":actor,'[]'::json,'{}'::json,'local_authority',false,'{}'::json,"
                    "'authority',1,'actor_profile',:request,:correlation,:permission,:action,"
                    "'authorization_evaluation',:record,'{\"allowed\": true}'::json)"
                ),
                {
                    "id": event_id,
                    "actor": actor_id,
                    "request": str(uuid4()),
                    "correlation": str(uuid4()),
                    "permission": permission_id,
                    "action": action_id,
                    "record": record_id,
                },
            )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_validate_idempotency")
            )
        return event_id
    finally:
        await engine.dispose()


async def _insert_orphan_linked_authorization_action_event(
    database_url: str,
    *,
    action_id: str,
    permission_id: str,
) -> str:
    """Seed historical action evidence whose non-null idempotency link is orphaned."""
    event_id = str(uuid4())
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "alter table audit_events drop constraint fk_audit_events_authority_idempotency"
                )
            )
            await connection.execute(
                text("alter table audit_events disable trigger audit_events_validate_idempotency")
            )
            await connection.execute(
                text(
                    "insert into audit_events "
                    "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
                    "auth_source,is_dev_auth,event_payload,event_domain,event_version,"
                    "actor_ref_kind,request_id,correlation_id,permission_id,action_id,reason,"
                    "idempotency_reference,after_facts) values "
                    "(:id,'authorization_decision',:id,'SensitiveAuthorizationAllowed',"
                    ":actor,'[]'::json,'{}'::json,'local_authority',false,'{}'::json,"
                    "'authority',1,'actor_profile',:request,:correlation,:permission,:action,"
                    "'authorization_evaluation',:record,'{\"allowed\": true}'::json)"
                ),
                {
                    "id": event_id,
                    "actor": str(uuid4()),
                    "request": str(uuid4()),
                    "correlation": str(uuid4()),
                    "permission": permission_id,
                    "action": action_id,
                    "record": str(uuid4()),
                },
            )
            await connection.execute(
                text(
                    "alter table audit_events add constraint "
                    "fk_audit_events_authority_idempotency foreign key "
                    "(idempotency_reference,actor_ref_kind,actor_id) references "
                    "authority_idempotency_records (id,actor_ref_kind,actor_ref) not valid"
                )
            )
            await connection.execute(
                text("alter table audit_events enable trigger audit_events_validate_idempotency")
            )
        return event_id
    finally:
        await engine.dispose()


async def _art_catalogue_migration_state(
    database_url: str,
    *,
    actions: tuple[str, ...],
    permissions: tuple[str, ...],
) -> dict[str, object]:
    """Snapshot revision, rewritten constraints, and all protected evidence counts."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            constraints = dict(
                (
                    await connection.execute(
                        text(
                            "select conname,pg_get_constraintdef(oid) from pg_constraint "
                            "where conrelid='audit_events'::regclass and conname in "
                            "('ck_audit_events_authority_registries',"
                            "'ck_audit_events_authority_privacy_bounds',"
                            "'ck_audit_events_authorization_action_evidence') order by conname"
                        )
                    )
                ).all()
            )
            direct_count = await connection.scalar(
                text(
                    "select count(*) from audit_events where action_id=any(:actions) or "
                    "permission_id=any(:permissions) or "
                    "(target_ref_kind='permission_registry' and target_ref_id=any(:permissions)) "
                    "or (invalidation_target_kind='permission_registry' and "
                    "invalidation_target_ref=any(:permissions))"
                ),
                {"actions": list(actions), "permissions": list(permissions)},
            )
            linked_count = await connection.scalar(
                text(
                    "select count(*) from authority_idempotency_records record join "
                    "audit_events event on event.idempotency_reference=record.id where "
                    "event.action_id=any(:actions) or event.permission_id=any(:permissions)"
                ),
                {"actions": list(actions), "permissions": list(permissions)},
            )
            return {
                "revision": await connection.scalar(
                    text("select version_num from alembic_version")
                ),
                "constraints": constraints,
                "direct_count": direct_count,
                "linked_count": linked_count,
            }
    finally:
        await engine.dispose()


async def _exercise_project_role_migration(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    actor_id = actor_id_from_external_identity("https://identity.test", "auth10a-actor")
    project_id, admin_grant_id = str(uuid4()), str(uuid4())
    snapshot_ids = [str(uuid4()) for _ in range(3)]
    grant_ids = [str(uuid4()) for _ in range(3)]
    results: dict[str, object] = {}
    supplied_at = datetime(2000, 1, 1, tzinfo=UTC)

    async def rejected(connection, statement: str, values: dict[str, object]) -> str | None:
        try:
            async with connection.begin_nested():
                await connection.execute(text(statement), values)
        except DBAPIError as error:
            return _database_error_sqlstate(error)
        return None

    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await _insert_canonical_actor(connection, actor_id, "auth10a-actor", "human")
                await connection.execute(
                    text(
                        "insert into projects(id,name,slug,status) values (:id,'AUTH 10A',:slug,'active')"
                    ),
                    {"id": project_id, "slug": f"auth-10a-{project_id}"},
                )
                await connection.execute(
                    text(
                        "insert into admin_role_grants "
                        "(id,target_actor_profile_id,role,scope_type,status,version,"
                        "granted_by_system_principal,grant_reason) values "
                        "(:id,:actor,'access_administrator','system','active',1,"
                        "'workstream:system:bootstrap','AUTH 10A migration proof')"
                    ),
                    {"id": admin_grant_id, "actor": actor_id},
                )
                await connection.execute(
                    text(
                        "update authority_control set bootstrap_completed=true,"
                        "bootstrap_grant_id=:grant,version=1 where id=1"
                    ),
                    {"grant": admin_grant_id},
                )
                snapshot_insert = text(
                    "insert into project_role_qualification_snapshots "
                    "(id,project_id,actor_profile_id,requested_role,skills_snapshot,"
                    "reputation_snapshot,prior_project_work_refs,external_expertise_refs,"
                    "captured_by_actor_profile_id,captured_by_admin_role_grant_id,captured_at) values "
                    "(:id,:project,:actor,:role,cast(:skills as jsonb),cast(:reputation as jsonb),"
                    "cast(:prior as jsonb),cast(:external as jsonb),:actor,:admin,"
                    "cast(:supplied_at as timestamptz))"
                )
                available = json.dumps(
                    {
                        "availability": "available",
                        "reference_ids": ["opaque:1"],
                        "unavailable_reason": None,
                    }
                )
                unavailable = json.dumps(
                    {
                        "availability": "unavailable",
                        "reference_ids": [],
                        "unavailable_reason": "no_record",
                    }
                )
                for role, snapshot_id in zip(
                    ("submitter", "reviewer", "adjudicator"), snapshot_ids, strict=True
                ):
                    await connection.execute(
                        snapshot_insert,
                        {
                            "id": snapshot_id,
                            "project": project_id,
                            "actor": actor_id,
                            "role": role,
                            "skills": available,
                            "reputation": unavailable,
                            "prior": "[]",
                            "external": "[]",
                            "admin": admin_grant_id,
                            "supplied_at": supplied_at,
                        },
                    )
                results["invalid_availability"] = await rejected(
                    connection,
                    str(snapshot_insert),
                    {
                        "id": str(uuid4()),
                        "project": project_id,
                        "actor": actor_id,
                        "role": "submitter",
                        "skills": json.dumps(
                            {
                                "availability": "available",
                                "reference_ids": [],
                                "unavailable_reason": None,
                            }
                        ),
                        "reputation": unavailable,
                        "prior": "[]",
                        "external": "[]",
                        "admin": admin_grant_id,
                        "supplied_at": supplied_at,
                    },
                )
                snapshot_rejections: dict[str, str | None] = {}
                snapshot_variants = {
                    "extra_key": {
                        "availability": "available",
                        "reference_ids": ["opaque:1"],
                        "unavailable_reason": None,
                        "extra": True,
                    },
                    "available_empty": {
                        "availability": "available",
                        "reference_ids": [],
                        "unavailable_reason": None,
                    },
                    "unavailable_with_reference": {
                        "availability": "unavailable",
                        "reference_ids": ["opaque:1"],
                        "unavailable_reason": "no_record",
                    },
                    "url_reference": {
                        "availability": "available",
                        "reference_ids": ["https://unsafe.example"],
                        "unavailable_reason": None,
                    },
                    "too_many_references": {
                        "availability": "available",
                        "reference_ids": [f"opaque:{index}" for index in range(21)],
                        "unavailable_reason": None,
                    },
                }
                for name, skills in snapshot_variants.items():
                    snapshot_rejections[name] = await rejected(
                        connection,
                        str(snapshot_insert),
                        {
                            "id": str(uuid4()),
                            "project": project_id,
                            "actor": actor_id,
                            "role": "submitter",
                            "skills": json.dumps(skills),
                            "reputation": unavailable,
                            "prior": "[]",
                            "external": "[]",
                            "admin": admin_grant_id,
                            "supplied_at": supplied_at,
                        },
                    )
                snapshot_rejections["invalid_prior_uuid"] = await rejected(
                    connection,
                    str(snapshot_insert),
                    {
                        "id": str(uuid4()),
                        "project": project_id,
                        "actor": actor_id,
                        "role": "submitter",
                        "skills": available,
                        "reputation": unavailable,
                        "prior": json.dumps(["not-a-uuid"]),
                        "external": "[]",
                        "admin": admin_grant_id,
                        "supplied_at": supplied_at,
                    },
                )
                results["snapshot_constraint_rejections"] = snapshot_rejections
                results["snapshot_truncate"] = await rejected(
                    connection,
                    "truncate project_role_qualification_snapshots, project_role_grants",
                    {},
                )
                raw_grant_insert = (
                    "insert into project_role_grants "
                    "(id,project_id,actor_profile_id,role,status,version,grant_method,"
                    "qualification_snapshot_id,granted_by_actor_profile_id,"
                    "granted_by_admin_role_grant_id,grant_reason) values "
                    "(:id,:project,:actor,:role,:status,:version,:method,:snapshot,:actor,:admin,:reason)"
                )
                base_grant = {
                    "project": project_id,
                    "actor": actor_id,
                    "role": "submitter",
                    "status": "active",
                    "version": 1,
                    "method": "manual",
                    "snapshot": snapshot_ids[0],
                    "admin": admin_grant_id,
                    "reason": "Qualified",
                }
                grant_variants = {
                    "automated_method": {"method": "automated"},
                    "combined_role": {"role": "both"},
                    "leading_space_reason": {"reason": " Qualified"},
                    "control_reason": {"reason": "bad\u200bcontrol"},
                    "oversize_reason": {"reason": "é" * 251},
                    "snapshot_mismatch": {"snapshot": snapshot_ids[1]},
                    "invalid_active_version": {"version": 2},
                }
                results["grant_constraint_rejections"] = {
                    name: await rejected(
                        connection, raw_grant_insert, base_grant | patch | {"id": str(uuid4())}
                    )
                    for name, patch in grant_variants.items()
                }
                grant_insert = text(
                    "insert into project_role_grants "
                    "(id,project_id,actor_profile_id,role,qualification_snapshot_id,"
                    "granted_by_actor_profile_id,granted_by_admin_role_grant_id,grant_reason,granted_at) "
                    "values (:id,:project,:actor,:role,:snapshot,:actor,:admin,"
                    "'Qualified manually',cast(:supplied_at as timestamptz))"
                )
                for role, snapshot_id, grant_id in zip(
                    ("submitter", "reviewer", "adjudicator"), snapshot_ids, grant_ids, strict=True
                ):
                    await connection.execute(
                        grant_insert,
                        {
                            "id": grant_id,
                            "project": project_id,
                            "actor": actor_id,
                            "role": role,
                            "snapshot": snapshot_id,
                            "admin": admin_grant_id,
                            "supplied_at": supplied_at,
                        },
                    )
                results["revision"] = await connection.scalar(
                    text("select version_num from alembic_version")
                )
                results["role_count"] = await connection.scalar(
                    text("select count(*) from project_role_grants where project_id=:project"),
                    {"project": project_id},
                )
                results["duplicate_role"] = await rejected(
                    connection,
                    str(grant_insert),
                    {
                        "id": str(uuid4()),
                        "project": project_id,
                        "actor": actor_id,
                        "role": "submitter",
                        "snapshot": snapshot_ids[0],
                        "admin": admin_grant_id,
                        "supplied_at": supplied_at,
                    },
                )
                results["snapshot_update"] = await rejected(
                    connection,
                    "update project_role_qualification_snapshots set external_expertise_refs='[]'::jsonb where id=:id",
                    {"id": snapshot_ids[0]},
                )
                results["snapshot_delete"] = await rejected(
                    connection,
                    "delete from project_role_qualification_snapshots where id=:id",
                    {"id": snapshot_ids[0]},
                )
                results["issuance_update"] = await rejected(
                    connection,
                    "update project_role_grants set grant_reason='Changed' where id=:id",
                    {"id": grant_ids[0]},
                )
                results["grant_delete"] = await rejected(
                    connection, "delete from project_role_grants where id=:id", {"id": grant_ids[0]}
                )
                results["grant_truncate"] = await rejected(
                    connection, "truncate project_role_grants", {}
                )
                await connection.execute(
                    text(
                        "update project_role_grants set status='revoked',version=2,"
                        "revoked_by_actor_profile_id=:actor,revoked_by_admin_role_grant_id=:admin,"
                        "revoked_reason='No longer assigned',revoked_at='2000-01-01T00:00:00+00:00' where id=:id"
                    ),
                    {"id": grant_ids[0], "actor": actor_id, "admin": admin_grant_id},
                )
                results["valid_revoke"] = tuple(
                    (
                        await connection.execute(
                            text("select status,version from project_role_grants where id=:id"),
                            {"id": grant_ids[0]},
                        )
                    ).one()
                )
                results["database_timestamps"] = bool(
                    await connection.scalar(
                        text(
                            "select captured_at > '2026-01-01'::timestamptz from "
                            "project_role_qualification_snapshots where id=:id"
                        ),
                        {"id": snapshot_ids[0]},
                    )
                ) and bool(
                    await connection.scalar(
                        text(
                            "select granted_at > '2026-01-01'::timestamptz and "
                            "revoked_at > '2026-01-01'::timestamptz from project_role_grants where id=:id"
                        ),
                        {"id": grant_ids[0]},
                    )
                )
                results["second_revoke"] = await rejected(
                    connection,
                    "update project_role_grants set revoked_reason='Again' where id=:id",
                    {"id": grant_ids[0]},
                )
            finally:
                await transaction.rollback()
        return results
    finally:
        await engine.dispose()


async def _install_legacy_project_role_blocker(
    database_url: str,
    patch: dict[str, object],
    *,
    bypass_constraints: bool,
) -> tuple[str, list[tuple[str, str]], tuple[tuple[object, ...], ...]]:
    event_id = await _insert_authorization_action_event(database_url)
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            triggers = tuple(
                tuple(row)
                for row in (
                    await connection.execute(
                        text(
                            "select tgrelid::regclass::text,tgname,tgenabled "
                            "from pg_trigger where tgrelid='audit_events'::regclass "
                            "and not tgisinternal order by tgname"
                        )
                    )
                ).all()
            )
            constraints: list[tuple[str, str]] = []
            if bypass_constraints:
                constraints = [
                    tuple(row)
                    for row in (
                        await connection.execute(
                            text(
                                "select conname,pg_get_constraintdef(oid) from pg_constraint "
                                "where conrelid='audit_events'::regclass and contype='c' "
                                "order by conname"
                            )
                        )
                    ).all()
                ]
                await connection.execute(text("alter table audit_events disable trigger user"))
                for name, _definition in constraints:
                    await connection.execute(
                        text(f'alter table audit_events drop constraint "{name}"')
                    )
            else:
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger audit_events_reject_update_delete"
                    )
                )
            assignments = []
            values: dict[str, object] = {"id": event_id}
            for key, value in patch.items():
                if key == "action_id":
                    definition = next(
                        item for item in ACTION_DEFINITIONS if item.action_id.value == value
                    )
                    assignments.append("permission_id=:permission_id")
                    values["permission_id"] = definition.permission_id.value
                if key in {"before_facts", "after_facts"}:
                    assignments.append(f"{key}=cast(:{key} as json)")
                    values[key] = json.dumps(value)
                else:
                    assignments.append(f"{key}=:{key}")
                    values[key] = value
            await connection.execute(
                text(f"update audit_events set {','.join(assignments)} where id=:id"), values
            )
            if not bypass_constraints:
                await _restore_0034_trigger_states(connection, triggers)
        return event_id, constraints, triggers
    finally:
        await engine.dispose()


async def _remove_legacy_project_role_blocker(
    database_url: str,
    event_id: str,
    constraints: list[tuple[str, str]],
    triggers: tuple[tuple[object, ...], ...],
) -> None:
    engine = create_async_engine(database_url)
    try:
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "alter table audit_events disable trigger audit_events_reject_update_delete"
                    )
                )
                await connection.execute(
                    text("delete from audit_events where id=:id"), {"id": event_id}
                )
                for name, definition in constraints:
                    if name == "ck_audit_events_authority_privacy_bounds":
                        await _restore_0034_privacy_constraint(
                            connection,
                            definition,
                            not definition.endswith(" NOT VALID"),
                        )
                    else:
                        await connection.execute(
                            text(f'alter table audit_events add constraint "{name}" {definition}')
                        )
        finally:
            async with engine.begin() as connection:
                await _restore_0034_trigger_states(connection, triggers)
    finally:
        await engine.dispose()


async def _project_role_refusal_state(database_url: str) -> tuple[str, bool, bool, int]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return (
                str(await connection.scalar(text("select version_num from alembic_version"))),
                bool(
                    await connection.scalar(
                        text("select to_regclass('project_role_grants') is not null")
                    )
                ),
                bool(
                    await connection.scalar(
                        text(
                            "select to_regclass('project_role_qualification_snapshots') is not null"
                        )
                    )
                ),
                int(
                    await connection.scalar(
                        text(
                            "select count(*) from audit_events where event_domain='authority' and "
                            "(before_facts->>'role'='both' or after_facts->>'role'='both' or "
                            "before_facts::jsonb ? 'replaced_grant_id' or "
                            "after_facts::jsonb ? 'replaced_grant_id' or "
                            "event_type='ProjectRoleGrantReplaced' or reason='authority_replacement')"
                        )
                    )
                ),
            )
    finally:
        await engine.dispose()


async def _project_role_audit_row(database_url: str, event_id: str) -> tuple:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return tuple(
                (
                    await connection.execute(
                        text(
                            "select id,event_type,reason,action_id,denial_code,before_facts,"
                            "after_facts from audit_events where id=:id"
                        ),
                        {"id": event_id},
                    )
                ).one()
            )
    finally:
        await engine.dispose()


async def _insert_project_role_idempotency_blocker(database_url: str, operation: str) -> str:
    record_id = str(uuid4())
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
                    "values (:id,:key,'system_principal','workstream:system:bootstrap',"
                    ":operation,:digest,'pending')"
                ),
                {
                    "id": record_id,
                    "key": str(uuid4()),
                    "operation": operation,
                    "digest": "sha256:" + "0" * 64,
                },
            )
        return record_id
    finally:
        await engine.dispose()


async def _project_role_idempotency_row(database_url: str, record_id: str) -> tuple:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return tuple(
                (
                    await connection.execute(
                        text(
                            "select id,idempotency_key,actor_ref_kind,actor_ref,operation,"
                            "request_digest,status from authority_idempotency_records where id=:id"
                        ),
                        {"id": record_id},
                    )
                ).one()
            )
    finally:
        await engine.dispose()


async def _remove_project_role_idempotency_blocker(database_url: str, record_id: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from authority_idempotency_records where id=:id"), {"id": record_id}
            )
            await connection.execute(
                text("alter table authority_idempotency_records enable trigger user")
            )
    finally:
        await engine.dispose()


async def _assert_project_role_denial_sql(database_url: str) -> None:
    engine = create_async_engine(database_url)
    insert = text(str(_ACTION_EVIDENCE_INSERT).replace("'permission_not_granted'", ":denial_code"))
    try:
        for denial_code in (
            "project_role_grant_already_revoked",
            "project_role_grant_replay_state_changed",
        ):
            values = _action_evidence_values("project_role_grant.read", "project.role_grant.read")
            values["denial_code"] = denial_code
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(insert, values)
                await transaction.rollback()
        invalid = _action_evidence_values("project_role_grant.read", "project.role_grant.read")
        invalid["denial_code"] = "project_role_grant_neighboring_unknown"
        async with engine.connect() as connection:
            transaction = await connection.begin()
            with pytest.raises(IntegrityError):
                await connection.execute(insert, invalid)
            await transaction.rollback()
    finally:
        await engine.dispose()


async def _install_project_role_table_blockers(
    database_url: str, *, include_grant: bool
) -> dict[str, str]:
    ids = {
        "actor": actor_id_from_external_identity("https://identity.test", "auth10a-blocker"),
        "project": str(uuid4()),
        "admin": str(uuid4()),
        "snapshot": str(uuid4()),
        "grant": str(uuid4()),
    }
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await _insert_canonical_actor(connection, ids["actor"], "auth10a-blocker", "human")
            await insert_historical_project(
                connection,
                project_id=ids["project"],
                name="AUTH 10A blocker",
                slug=f"auth-10a-blocker-{ids['project']}",
                status="active",
            )
            await connection.execute(
                text(
                    "insert into admin_role_grants "
                    "(id,target_actor_profile_id,role,scope_type,status,version,"
                    "granted_by_system_principal,grant_reason) values "
                    "(:admin,:actor,'access_administrator','system','active',1,"
                    "'workstream:system:bootstrap','AUTH 10A downgrade blocker')"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "update authority_control set bootstrap_completed=true,"
                    "bootstrap_grant_id=:admin,version=1 where id=1"
                ),
                ids,
            )
            availability = json.dumps(
                {
                    "availability": "available",
                    "reference_ids": ["opaque:1"],
                    "unavailable_reason": None,
                }
            )
            unavailable = json.dumps(
                {
                    "availability": "unavailable",
                    "reference_ids": [],
                    "unavailable_reason": "no_record",
                }
            )
            await connection.execute(
                text(
                    "insert into project_role_qualification_snapshots "
                    "(id,project_id,actor_profile_id,requested_role,skills_snapshot,"
                    "reputation_snapshot,prior_project_work_refs,external_expertise_refs,"
                    "captured_by_actor_profile_id,captured_by_admin_role_grant_id) values "
                    "(:snapshot,:project,:actor,'submitter',cast(:available as jsonb),"
                    "cast(:unavailable as jsonb),'[]'::jsonb,'[]'::jsonb,:actor,:admin)"
                ),
                ids | {"available": availability, "unavailable": unavailable},
            )
            if include_grant:
                await connection.execute(
                    text(
                        "insert into project_role_grants "
                        "(id,project_id,actor_profile_id,role,qualification_snapshot_id,"
                        "granted_by_actor_profile_id,granted_by_admin_role_grant_id,grant_reason) "
                        "values (:grant,:project,:actor,'submitter',:snapshot,:actor,:admin,'Qualified')"
                    ),
                    ids,
                )
        return ids
    finally:
        await engine.dispose()


async def _project_role_table_rows(
    database_url: str, ids: dict[str, str]
) -> tuple[tuple | None, tuple | None]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            snapshot = (
                await connection.execute(
                    text(
                        "select id,project_id,actor_profile_id,requested_role,skills_snapshot,"
                        "reputation_snapshot,prior_project_work_refs,external_expertise_refs,"
                        "captured_by_actor_profile_id,captured_by_admin_role_grant_id,captured_at "
                        "from project_role_qualification_snapshots where id=:snapshot"
                    ),
                    ids,
                )
            ).one_or_none()
            grant = (
                await connection.execute(
                    text(
                        "select id,project_id,actor_profile_id,role,status,version,grant_method,"
                        "qualification_snapshot_id,granted_by_actor_profile_id,"
                        "granted_by_admin_role_grant_id,grant_reason,granted_at from "
                        "project_role_grants where id=:grant"
                    ),
                    ids,
                )
            ).one_or_none()
            return (
                tuple(snapshot) if snapshot is not None else None,
                tuple(grant) if grant is not None else None,
            )
    finally:
        await engine.dispose()


async def _remove_project_role_table_blockers(database_url: str, ids: dict[str, str]) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for table in (
                "project_role_grants",
                "project_role_qualification_snapshots",
                "admin_role_grants",
                "authority_control",
                "actor_identity_links",
                "actor_profiles",
            ):
                await connection.execute(text(f"alter table {table} disable trigger user"))
            await connection.execute(text("delete from project_role_grants where id=:grant"), ids)
            await connection.execute(
                text("delete from project_role_qualification_snapshots where id=:snapshot"),
                ids,
            )
            await connection.execute(
                text(
                    "update authority_control set bootstrap_completed=false,"
                    "bootstrap_grant_id=null,version=0 where id=1"
                )
            )
            await connection.execute(text("delete from admin_role_grants where id=:admin"), ids)
            await connection.execute(
                text("delete from actor_identity_links where actor_profile_id=:actor"), ids
            )
            await connection.execute(text("delete from actor_profiles where id=:actor"), ids)
            await connection.execute(text("delete from projects where id=:project"), ids)
            for table in reversed(
                (
                    "project_role_grants",
                    "project_role_qualification_snapshots",
                    "admin_role_grants",
                    "authority_control",
                    "actor_identity_links",
                    "actor_profiles",
                )
            ):
                await connection.execute(text(f"alter table {table} enable trigger user"))
    finally:
        await engine.dispose()


def test_xint003_02a_policy_lineage_backfill_immutability_and_roundtrip(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove historical policies get exact identity without invented semantics."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    ids = {
        "project": str(uuid4()),
        "guide": str(uuid4()),
        "review": str(uuid4()),
        "revision": str(uuid4()),
    }

    with migration_lock():
        try:
            command.downgrade(config, "0045_guide_metadata_authority")
            asyncio.run(_seed_xint003_02a_legacy_policies(isolated_database_env, ids))
            command.upgrade(config, "0047_policy_identity_lineage")
            state = asyncio.run(_xint003_02a_policy_state(isolated_database_env, ids))
            immutable = asyncio.run(
                _xint003_02a_policy_immutable_writes(isolated_database_env, ids)
            )
            with pytest.raises(
                RuntimeError, match="cannot downgrade populated immutable policy lineage"
            ):
                command.downgrade(config, "0045_guide_metadata_authority")
            refused_state = asyncio.run(_xint003_02a_policy_state(isolated_database_env, ids))
        finally:
            asyncio.run(_remove_xint003_02a_immutable_policies(isolated_database_env, ids))
            command.downgrade(config, "0045_guide_metadata_authority")
            command.upgrade(config, "head")

    assert state["review"][0:3] == (ids["review"], 1, "legacy_incomplete")
    assert state["revision"][0:3] == (ids["revision"], 1, "legacy_incomplete")
    assert state["review"][3].startswith("sha256:")
    assert state["revision"][3].startswith("sha256:")
    assert state["guide"] == (
        ids["review"],
        1,
        state["review"][3],
        ids["revision"],
        1,
        state["revision"][3],
    )
    assert immutable == {
        "partial_selection",
        "active_selection_change",
        "review_update",
        "review_delete",
        "review_truncate",
        "revision_update",
        "revision_delete",
        "revision_truncate",
    }
    assert refused_state == state


def test_xint003_02b_policy_authority_schema_and_roundtrip(
    isolated_database_env: str,
    migration_lock,
) -> None:
    """Prove 0048 installs only the closed policy mutation custody boundary."""
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))

    with migration_lock():
        try:
            command.downgrade(config, "0047_policy_identity_lineage")
            command.upgrade(config, "0048_policy_authority")
            shape = asyncio.run(_xint003_02b_authority_shape(isolated_database_env))
            command.downgrade(config, "0047_policy_identity_lineage")
            absent = asyncio.run(_xint003_02b_authority_shape(isolated_database_env))
        finally:
            command.upgrade(config, "head")

    assert shape == {
        "ledger": True,
        "review_provenance": 8,
        "revision_provenance": 8,
        "custody_triggers": 3,
        "selector_constraint": True,
        "review_only_selector": True,
        "revision_only_selector": True,
        "partial_review_selector": False,
        "partial_revision_selector": False,
        "selector_custody": True,
        "predecessor_custody": True,
    }
    assert absent == {
        "ledger": False,
        "review_provenance": 0,
        "revision_provenance": 0,
        "custody_triggers": 0,
        "selector_constraint": True,
        "review_only_selector": False,
        "revision_only_selector": False,
        "partial_review_selector": False,
        "partial_revision_selector": False,
        "selector_custody": False,
        "predecessor_custody": False,
    }


_XINT003_02C_ACTIONS = (
    ("review.revision_context.repair", "project.task.manage"),
    ("review.revision_obligation.close", "project.task.manage"),
    ("review.revision_context.legacy_close", "operations.reconcile.run"),
    ("review.lifecycle.activation.manage", "operations.reconcile.run"),
)
_XINT003_02C_IDENTITIES = tuple(
    identity.value
    for identity in (
        ServiceIdentity.REVIEW_PREFERENCE_EXPIRY,
        ServiceIdentity.REVIEW_LEASE_EXPIRY,
        ServiceIdentity.REVIEW_AUTHORITY_INVALIDATION_RECONCILIATION,
        ServiceIdentity.REVIEW_RECONCILIATION,
        ServiceIdentity.REVIEW_ARTIFACT_REFERENCE_RECONCILIATION,
        ServiceIdentity.REVIEW_PROJECTION,
    )
)


def test_xint003_02c_rev_auth_readiness_schema_and_roundtrip(
    isolated_database_env: str, migration_lock
) -> None:
    """0049 admits exact planned evidence and principals without seeding authority."""
    config = _alembic_config()
    with migration_lock():
        try:
            command.downgrade(config, "0048_policy_authority")
            prior = asyncio.run(_xint003_02c_readiness_state(isolated_database_env))
            command.upgrade(config, "head")
            upgraded = asyncio.run(_xint003_02c_readiness_state(isolated_database_env))
            command.downgrade(config, "0048_policy_authority")
            restored = asyncio.run(_xint003_02c_readiness_state(isolated_database_env))
            command.upgrade(config, "head")
            repeated = asyncio.run(_xint003_02c_readiness_state(isolated_database_env))
        finally:
            command.upgrade(config, "head")

    additions = " OR " + " OR ".join(
        _xint003_02c_pair_token(action, permission) for action, permission in _XINT003_02C_ACTIONS
    )
    assert prior["profiles"] == upgraded["profiles"] == 0
    assert upgraded["action_definition"].count(additions) == 2
    assert upgraded["action_definition"].replace(additions, "") == prior["action_definition"]
    historical_identities = (*FROZEN_SERVICE_IDENTITY_VALUES, ServiceIdentity.PROJECT_SETUP.value)
    assert prior["identity_values"] == historical_identities
    assert upgraded["identity_values"] == (*historical_identities, *_XINT003_02C_IDENTITIES)
    assert restored == prior
    assert repeated == upgraded


@pytest.mark.parametrize(("action_id", "permission_id"), _XINT003_02C_ACTIONS)
@pytest.mark.parametrize("evidence_shape", ("direct", "idempotency_linked"))
def test_xint003_02c_rev_auth_readiness_guarded_action_evidence_downgrade(
    isolated_database_env: str,
    migration_lock,
    action_id: str,
    permission_id: str,
    evidence_shape: str,
) -> None:
    """Every newly admitted action pair blocks vocabulary removal once used."""
    config = _alembic_config()
    event_id = ""
    record_id = str(uuid4())
    with migration_lock():
        try:
            command.upgrade(config, "head")
            if evidence_shape == "direct":
                event_id = asyncio.run(
                    _insert_authorization_action_event_for(
                        isolated_database_env, action_id, permission_id
                    )
                )
            else:
                actor_id, target_id = str(uuid4()), str(uuid4())
                asyncio.run(
                    _insert_committed_authority_idempotency(
                        isolated_database_env, record_id, actor_id, target_id
                    )
                )
                event_id = asyncio.run(
                    _insert_linked_authorization_action_event(
                        isolated_database_env,
                        record_id=record_id,
                        actor_id=actor_id,
                        action_id=action_id,
                        permission_id=permission_id,
                    )
                )
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade non-empty REV authorization action evidence",
            ):
                command.downgrade(config, "0048_policy_authority")
            assert asyncio.run(_current_revision(isolated_database_env)) == HEAD_REVISION
        finally:
            asyncio.run(_remove_authority_audit_fixture(isolated_database_env, event_id=event_id))
            if evidence_shape == "idempotency_linked":
                asyncio.run(
                    _remove_authority_idempotency_fixture(
                        isolated_database_env, record_id, orphan_event=None
                    )
                )
            command.upgrade(config, "head")


@pytest.mark.parametrize("service_identity", _XINT003_02C_IDENTITIES)
def test_xint003_02c_rev_auth_readiness_guarded_identity_downgrade(
    isolated_database_env: str, migration_lock, service_identity: str
) -> None:
    """Every newly admitted fixed principal blocks removal while in use."""
    config = _alembic_config()
    actor_id = str(uuid4())
    with migration_lock():
        try:
            command.upgrade(config, "head")
            asyncio.run(
                _insert_rev_service_actor(
                    isolated_database_env,
                    actor_id=actor_id,
                    service_identity=service_identity,
                )
            )
            with pytest.raises(
                RuntimeError, match="cannot downgrade in-use REV service identities"
            ):
                command.downgrade(config, "0048_policy_authority")
            assert asyncio.run(_current_revision(isolated_database_env)) == HEAD_REVISION
        finally:
            asyncio.run(_remove_fixed_service_actor(isolated_database_env, actor_id))
            command.upgrade(config, "head")


async def _xint003_02c_readiness_state(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            action_definition = str(
                await connection.scalar(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint where "
                        "conname='ck_audit_events_authorization_action_evidence'"
                    )
                )
            )
            identity_definition = str(
                await connection.scalar(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint where "
                        "conname='ck_actor_profiles_kind_service_identity'"
                    )
                )
            )
            profiles = int(
                await connection.scalar(
                    text(
                        "select count(*) from actor_profiles where "
                        "service_identity=any(:identities)"
                    ),
                    {"identities": list(_XINT003_02C_IDENTITIES)},
                )
                or 0
            )
            return {
                "action_definition": action_definition,
                "identity_values": tuple(
                    re.findall(r"'([^']+)'::character varying", identity_definition)
                ),
                "profiles": profiles,
            }
    finally:
        await engine.dispose()


def _xint003_02c_pair_token(action: str, permission: str) -> str:
    return (
        f"(((action_id)::text = '{action}'::text) AND "
        f"((permission_id)::text = '{permission}'::text))"
    )


async def _insert_rev_service_actor(
    database_url: str, *, actor_id: str, service_identity: str
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                    "values (:id,'service','active','manual_service_provisioning',"
                    ":identity,:id)"
                ),
                {"id": actor_id, "identity": service_identity},
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links "
                    "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                    "values (:id,:actor,'https://identity.test',:subject,'service',"
                    "'active',:actor)"
                ),
                {
                    "id": str(uuid4()),
                    "actor": actor_id,
                    "subject": service_identity,
                },
            )
    finally:
        await engine.dispose()


async def _xint003_02b_authority_shape(database_url: str) -> dict[str, int | bool]:
    engine = create_async_engine(database_url)
    provenance = {
        "predecessor_policy_hash",
        "created_by_actor_profile_id",
        "created_via_identity_link_id",
        "created_by_admin_role_grant_id",
        "creation_scope_type",
        "creation_scope_project_id",
        "creation_action_id",
        "authorization_decision_event_id",
    }
    try:
        async with engine.connect() as connection:
            tables = set(
                (
                    await connection.execute(
                        text(
                            "select table_name from information_schema.tables "
                            "where table_schema='public'"
                        )
                    )
                ).scalars()
            )
            columns = {}
            for table in ("review_policies", "revision_policies"):
                columns[table] = set(
                    (
                        await connection.execute(
                            text(
                                "select column_name from information_schema.columns "
                                "where table_schema='public' and table_name=:table"
                            ),
                            {"table": table},
                        )
                    ).scalars()
                )
            triggers = int(
                await connection.scalar(
                    text(
                        "select count(*) from pg_trigger where not tgisinternal and tgname in "
                        "('review_policy_mutation_custody',"
                        "'revision_policy_mutation_custody',"
                        "'policy_mutation_replay_custody')"
                    )
                )
                or 0
            )
            selector = bool(
                await connection.scalar(
                    text(
                        "select exists(select 1 from pg_constraint where "
                        "conname='ck_project_guides_policy_selection_shape')"
                    )
                )
            )
            selector_definition = str(
                await connection.scalar(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint "
                        "where conname='ck_project_guides_policy_selection_shape'"
                    )
                )
                or ""
            )
            selector_behavior = await _policy_selector_constraint_behavior(
                connection, selector_definition
            )
            custody_definition = str(
                await connection.scalar(
                    text(
                        "select pg_get_functiondef(p.oid) from pg_proc p "
                        "where p.proname='validate_policy_mutation_custody'"
                    )
                )
                or ""
            )
            return {
                "ledger": "policy_mutation_idempotency_records" in tables,
                "review_provenance": len(columns["review_policies"] & provenance),
                "revision_provenance": len(columns["revision_policies"] & provenance),
                "custody_triggers": triggers,
                "selector_constraint": selector,
                **selector_behavior,
                "selector_custody": "selected_review_policy_id" in custody_definition
                and "selected_revision_policy_id" in custody_definition,
                "predecessor_custody": "prior.policy_generation=product_generation-1"
                in custody_definition,
            }
    finally:
        await engine.dispose()


async def _policy_selector_constraint_behavior(
    connection: AsyncConnection, definition: str
) -> dict[str, bool]:
    """Exercise the installed selector expression without product trigger noise."""
    await connection.execute(
        text(
            "create temporary table policy_selector_probe ("
            "selected_review_policy_id text, selected_review_policy_generation integer, "
            "selected_review_policy_hash text, selected_revision_policy_id text, "
            "selected_revision_policy_generation integer, "
            "selected_revision_policy_hash text, constraint selector_probe "
            f"{definition}) on commit drop"
        )
    )
    cases = {
        "review_only_selector": ("review", 1, "sha256:" + "1" * 64, None, None, None),
        "revision_only_selector": (None, None, None, "revision", 1, "sha256:" + "2" * 64),
        "partial_review_selector": ("review", None, None, None, None, None),
        "partial_revision_selector": (None, None, None, "revision", None, None),
    }
    accepted: dict[str, bool] = {}
    for name, values in cases.items():
        savepoint = await connection.begin_nested()
        try:
            await connection.execute(
                text(
                    "insert into policy_selector_probe values "
                    "(:r_id,:r_generation,:r_hash,:v_id,:v_generation,:v_hash)"
                ),
                dict(
                    zip(
                        ("r_id", "r_generation", "r_hash", "v_id", "v_generation", "v_hash"),
                        values,
                        strict=True,
                    )
                ),
            )
            accepted[name] = True
        except IntegrityError:
            accepted[name] = False
        finally:
            await savepoint.rollback()
    return accepted


async def _seed_xint003_02a_legacy_policies(database_url: str, ids: dict[str, str]) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for table in ("projects", "project_guides"):
                await connection.execute(text(f"alter table {table} disable trigger user"))
            await connection.execute(
                text(
                    "insert into projects (id,name,slug,status) values "
                    "(:project,'XINT 003 02A','xint-003-02a','draft')"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "insert into project_guides "
                    "(id,project_id,version,status,content_markdown,created_by) values "
                    "(:guide,:project,'v1','draft','# Legacy guide','migration-test')"
                ),
                ids,
            )
            for table in reversed(("projects", "project_guides")):
                await connection.execute(text(f"alter table {table} enable trigger user"))
            await connection.execute(
                text(
                    "insert into review_policies "
                    "(id,project_id,guide_version,requires_second_review,allowed_decisions,"
                    "minimum_finding_fields,sla_hours) values "
                    '(:review,:project,\'v1\',false,\'["accept","needs_revision",'
                    "\"reject\"]'::json,'[]'::json,24)"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "insert into revision_policies "
                    "(id,project_id,guide_version,max_revision_rounds,revision_deadline_hours,"
                    "auto_reject_after_limit,allowed_resubmission_states) values "
                    "(:revision,:project,'v1',3,48,false,'[\"needs_revision\"]'::json)"
                ),
                ids,
            )
    finally:
        await engine.dispose()


async def _xint003_02a_policy_state(database_url: str, ids: dict[str, str]) -> dict[str, tuple]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            review = tuple(
                (
                    await connection.execute(
                        text(
                            "select id,policy_generation,semantics_status,policy_hash "
                            "from review_policies where id=:review"
                        ),
                        ids,
                    )
                ).one()
            )
            revision = tuple(
                (
                    await connection.execute(
                        text(
                            "select id,policy_generation,semantics_status,policy_hash "
                            "from revision_policies where id=:revision"
                        ),
                        ids,
                    )
                ).one()
            )
            guide = tuple(
                (
                    await connection.execute(
                        text(
                            "select selected_review_policy_id,selected_review_policy_generation,"
                            "selected_review_policy_hash,selected_revision_policy_id,"
                            "selected_revision_policy_generation,selected_revision_policy_hash "
                            "from project_guides where id=:guide"
                        ),
                        ids,
                    )
                ).one()
            )
            return {"review": review, "revision": revision, "guide": guide}
    finally:
        await engine.dispose()


async def _xint003_02a_policy_immutable_writes(database_url: str, ids: dict[str, str]) -> set[str]:
    engine = create_async_engine(database_url)
    refused: set[str] = set()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            with pytest.raises(IntegrityError):
                await connection.execute(
                    text(
                        "update project_guides set selected_review_policy_hash=null where id=:guide"
                    ),
                    ids,
                )
            refused.add("partial_selection")
            await transaction.rollback()
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table project_guides disable trigger guide_mutation_product_custody")
            )
            await connection.execute(
                text("alter table project_guides disable trigger guide_lineage_lifecycle_guard")
            )
            await connection.execute(
                text("update project_guides set status='active' where id=:guide"), ids
            )
            await connection.execute(
                text("alter table project_guides enable trigger guide_mutation_product_custody")
            )
            await connection.execute(
                text("alter table project_guides enable trigger guide_lineage_lifecycle_guard")
            )
        async with engine.connect() as connection:
            transaction = await connection.begin()
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "update project_guides set selected_review_policy_hash=:hash "
                        "where id=:guide"
                    ),
                    ids | {"hash": "sha256:" + "f" * 64},
                )
            refused.add("active_selection_change")
            await transaction.rollback()
        statements = {
            "review_update": (
                "update review_policies set requires_second_review=true where id=:review",
                ids,
            ),
            "review_delete": ("delete from review_policies where id=:review", ids),
            "review_truncate": ("truncate review_policies", {}),
            "revision_update": (
                "update revision_policies set max_revision_rounds=4 where id=:revision",
                ids,
            ),
            "revision_delete": ("delete from revision_policies where id=:revision", ids),
            "revision_truncate": ("truncate revision_policies", {}),
        }
        for operation, (sql, params) in statements.items():
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(DBAPIError):
                    await connection.execute(text(sql), params)
                refused.add(operation)
                await transaction.rollback()
        return refused
    finally:
        await engine.dispose()


async def _remove_xint003_02a_immutable_policies(database_url: str, ids: dict[str, str]) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            has_lineage = bool(
                await connection.scalar(
                    text(
                        "select exists(select 1 from information_schema.columns "
                        "where table_schema='public' and table_name='project_guides' "
                        "and column_name='selected_review_policy_id')"
                    )
                )
            )
            for table in (
                "projects",
                "project_guides",
                "review_policies",
                "revision_policies",
            ):
                await connection.execute(text(f"alter table {table} disable trigger user"))
            if has_lineage:
                await connection.execute(
                    text(
                        "update project_guides set status='draft',selected_review_policy_id=null,"
                        "selected_review_policy_generation=null,selected_review_policy_hash=null,"
                        "selected_revision_policy_id=null,"
                        "selected_revision_policy_generation=null,"
                        "selected_revision_policy_hash=null where id=:guide"
                    ),
                    ids,
                )
            await connection.execute(text("delete from review_policies where id=:review"), ids)
            await connection.execute(text("delete from revision_policies where id=:revision"), ids)
            await connection.execute(text("delete from project_guides where id=:guide"), ids)
            await connection.execute(text("delete from projects where id=:project"), ids)
            for table in reversed(
                (
                    "projects",
                    "project_guides",
                    "review_policies",
                    "revision_policies",
                )
            ):
                await connection.execute(text(f"alter table {table} enable trigger user"))
    finally:
        await engine.dispose()
