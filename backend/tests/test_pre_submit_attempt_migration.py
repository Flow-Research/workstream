"""Retained ART evidence and downgrade custody for the attempt migration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migration_fixtures import (
    current_schema_revision, run_guarded_revision_downgrade, run_scoped_revision_upgrade,
)
from tests.test_pre_submit_attempt_recovery import _harness


OWN = "0021_pre_submit_attempts"
pytestmark = pytest.mark.postgres_schema_contract


def _seed_retained_evidence(tmp_path: Path, database_url: str) -> str:
    """Prepare current owners, then insert the actual pre-0021 evidence shape."""
    async def prepare():
        harness = await _harness(tmp_path, database_url)
        await harness.close()
        return harness

    harness = asyncio.run(prepare())
    activation = asyncio.run(_activation_snapshot(database_url))
    asyncio.run(run_guarded_revision_downgrade(database_url, OWN))
    assert asyncio.run(_activation_snapshot(database_url)) == activation
    return asyncio.run(_insert_retained_evidence(harness))


async def _insert_retained_evidence(harness) -> str:
    evidence_id = str(uuid4())
    lineage = harness.request.effective_plan.lineage
    digest = "sha256:" + "a" * 64
    values = {
        "id": evidence_id,
        "operation": "sha256:" + "b" * 64,
        "actor": str(harness.actor_id),
        "link": str(harness.identity_link_id),
        "project": str(lineage.project_id),
        "task": str(harness.request.task_id),
        "assignment": str(harness.request.assignment_id),
        "generation": str(uuid4()),
        "manifest": str(uuid4()),
        "guide": str(lineage.guide_id),
        "guide_version": lineage.guide_version,
        "snapshot": str(lineage.source_snapshot_id),
        "snapshot_hash": lineage.source_snapshot_hash,
        "policy": str(lineage.effective_policy_id),
        "artifact_hash": lineage.effective_policy_hash,
        "checker_policy": str(lineage.pre_submit_policy_id),
        "checker_hash": lineage.pre_submit_policy_bundle_hash,
        "digest": digest,
        "result": str(uuid4()),
    }
    try:
        async with harness.engine.begin() as connection:
            await connection.execute(text("""
                INSERT INTO pre_submit_evidence_sets (
                  id,operation_identity,actor_profile_id,identity_link_id,project_id,
                  task_id,assignment_id,prepared_generation_id,archive_sha256,
                  archive_byte_count,semantic_manifest_id,semantic_manifest_sha256,
                  guide_id,guide_version,source_snapshot_id,source_snapshot_sha256,
                  locked_guide_sha256,effective_policy_id,locked_artifact_policy_sha256,
                  pre_submit_policy_id,locked_checker_policy_sha256,effective_plan_sha256,
                  catalogue_id,catalogue_version,catalogue_manifest_sha256,
                  storage_scheme,terminal_status,eligible,result_count,
                  result_manifest_sha256,locked_policy_context_hash)
                VALUES (
                  :id,:operation,:actor,:link,:project,:task,:assignment,
                  :generation,:digest,17,:manifest,:digest,:guide,:guide_version,
                  :snapshot,:snapshot_hash,:digest,:policy,:artifact_hash,
                  :checker_policy,:checker_hash,:digest,'retained-catalogue','v1',
                  :digest,'local','passed',true,1,:digest,:digest)
            """), values)
            await connection.execute(text("""
                INSERT INTO pre_submit_evidence_results (
                  id,evidence_set_id,result_order,schema_version,dispatch_authority,
                  definition_id,definition_version,public_name,source,phase,
                  classification,severity,status,message_code,effective_plan_sha256,
                  locked_policy_sha256)
                VALUES (:result,:id,0,'v1','retained','retained.check','v1',
                  'Retained check','retained','custody','mandatory_integrity',
                  'blocking','passed','retained.passed',:digest,:digest)
            """), values)
    finally:
        await harness.engine.dispose()
    return evidence_id


async def _snapshot(
    database_url: str, evidence_id: str, *, upgraded: bool, attempt_count: int = 0,
):
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            evidence = (await connection.execute(text(
                "SELECT * FROM pre_submit_evidence_sets WHERE id=:id"
            ), {"id": evidence_id})).mappings().one()
            result = (await connection.execute(text(
                "SELECT * FROM pre_submit_evidence_results WHERE evidence_set_id=:id"
            ), {"id": evidence_id})).mappings().one()
            if upgraded:
                assert evidence["attempt_id"] is None
                assert evidence["attempt_request_digest"] is None
                assert evidence["packet_sha256"] is None
                assert result["checker_order"] is None
                assert result["metadata_json"] is None
                assert await connection.scalar(text(
                    "SELECT count(*) FROM pre_submit_execution_attempts"
                )) == attempt_count
            return (
                {key: value for key, value in evidence.items()
                 if key not in {"attempt_id", "attempt_request_digest", "packet_sha256"}},
                {key: value for key, value in result.items()
                 if key not in {"checker_order", "metadata_json"}},
                await _activation_snapshot(database_url),
            )
    finally:
        await engine.dispose()


async def _activation_snapshot(database_url: str):
    """Keep complete later-owner evidence and the head marker across scoped DDL."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            marker = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert marker == current_schema_revision()
            operations = list(await connection.scalars(text(
                "SELECT to_jsonb(r) FROM guide_mutation_idempotency_records r "
                "WHERE action_id='project.guide.activate' ORDER BY operation_id"
            )))
            events = list(await connection.scalars(text(
                "SELECT to_jsonb(e) FROM audit_events e "
                "WHERE resource_type='project_guide_activation' ORDER BY id"
            )))
            assert operations and events
            return marker, operations, events
    finally:
        await engine.dispose()


async def _audit_privacy_constraint(database_url: str) -> str:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return str(await connection.scalar(text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='audit_events'::regclass "
                "AND conname='ck_audit_events_authority_privacy_bounds'"
            )))
    finally:
        await engine.dispose()


def test_retained_evidence_round_trip_does_not_invent_attempt_or_result_details(
    tmp_path: Path, isolated_database_env: str, migration_lock, migration_schema_at,
) -> None:
    with migration_lock():
        migration_schema_at("head")
        evidence_id = _seed_retained_evidence(tmp_path, isolated_database_env)
        original = asyncio.run(_snapshot(isolated_database_env, evidence_id, upgraded=False))
        old_audit = asyncio.run(_audit_privacy_constraint(isolated_database_env))
        assert "pre_submit_checker_input" not in old_audit
        assert "compensation_adapter_binding" in old_audit
        assert "project_guide_activation" in old_audit
        asyncio.run(run_scoped_revision_upgrade(isolated_database_env, OWN))
        assert asyncio.run(_snapshot(isolated_database_env, evidence_id, upgraded=True)) == original
        new_audit = asyncio.run(_audit_privacy_constraint(isolated_database_env))
        assert new_audit.count("pre_submit_checker_input") == 1
        asyncio.run(run_guarded_revision_downgrade(isolated_database_env, OWN))
        assert asyncio.run(_snapshot(isolated_database_env, evidence_id, upgraded=False)) == original
        assert asyncio.run(_audit_privacy_constraint(isolated_database_env)) == old_audit
        asyncio.run(run_scoped_revision_upgrade(isolated_database_env, OWN))
        assert asyncio.run(_snapshot(isolated_database_env, evidence_id, upgraded=True)) == original
        assert asyncio.run(_audit_privacy_constraint(isolated_database_env)) == new_audit


def test_retained_reservation_refuses_downgrade_without_mutation(
    tmp_path: Path, isolated_database_env: str, migration_lock, migration_schema_at,
) -> None:
    with migration_lock():
        migration_schema_at("head")
        evidence_id = _seed_retained_evidence(tmp_path, isolated_database_env)
        asyncio.run(run_scoped_revision_upgrade(isolated_database_env, OWN))

    async def reserve() -> str:
        engine = create_async_engine(isolated_database_env)
        attempt_id = str(uuid4())
        try:
            async with engine.begin() as connection:
                await connection.execute(text("""
                    INSERT INTO pre_submit_execution_attempts (
                      id,idempotency_key,actor_profile_id,identity_link_id,task_id,
                      assignment_id,prepared_generation_id,claim_nonce,request_json,
                      request_digest,status)
                    SELECT :attempt,:key,e.actor_profile_id,e.identity_link_id,e.task_id,
                      e.assignment_id,e.prepared_generation_id,:nonce,
                      json_build_object('actor_profile_id',e.actor_profile_id,
                        'identity_link_id',e.identity_link_id,'task_id',e.task_id,
                        'assignment_id',e.assignment_id),
                      'sha256:' || encode(sha256(convert_to(
                        project_guide_projection_canonical_json(jsonb_build_object(
                          'actor_profile_id',e.actor_profile_id,
                          'identity_link_id',e.identity_link_id,'task_id',e.task_id,
                          'assignment_id',e.assignment_id)), 'UTF8')), 'hex'),
                      'reserved'
                    FROM pre_submit_evidence_sets e WHERE e.id=:evidence
                """), {"attempt": attempt_id, "key": str(uuid4()),
                       "nonce": str(uuid4()), "evidence": evidence_id})
            return attempt_id
        finally:
            await engine.dispose()

    attempt_id = asyncio.run(reserve())
    before = asyncio.run(_snapshot(
        isolated_database_env, evidence_id, upgraded=True, attempt_count=1,
    ))
    with pytest.raises(RuntimeError, match="retained pre-submit attempts prevent downgrade"):
        asyncio.run(run_guarded_revision_downgrade(isolated_database_env, OWN))
    after = asyncio.run(_snapshot(
        isolated_database_env, evidence_id, upgraded=True, attempt_count=1,
    ))
    assert after == before

    async def still_reserved() -> bool:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                return bool(await connection.scalar(text(
                    "SELECT status='reserved' AND evidence_set_id IS NULL "
                    "FROM pre_submit_execution_attempts WHERE id=:id"
                ), {"id": attempt_id}))
        finally:
            await engine.dispose()

    assert asyncio.run(still_reserved())


def test_new_result_rows_require_valid_order_and_bounded_metadata(
    tmp_path: Path, isolated_database_env: str, migration_lock, migration_schema_at,
) -> None:
    with migration_lock():
        migration_schema_at("head")
        retained_id = _seed_retained_evidence(tmp_path, isolated_database_env)
        asyncio.run(run_scoped_revision_upgrade(isolated_database_env, OWN))

    async def probe() -> None:
        engine = create_async_engine(isolated_database_env)
        new_id = str(uuid4())
        attempt_id = str(uuid4())
        packet_sha256 = "sha256:" + "d" * 64
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    # Reserve a complete request body so the transaction-local
                    # parent can satisfy every attempt/evidence binding guard.
                    await connection.execute(text("""
                        INSERT INTO pre_submit_execution_attempts (
                          id,idempotency_key,actor_profile_id,identity_link_id,
                          task_id,assignment_id,prepared_generation_id,claim_nonce,
                          request_json,request_digest,status)
                        SELECT :attempt,:key,e.actor_profile_id,e.identity_link_id,
                          e.task_id,e.assignment_id,e.prepared_generation_id,:nonce,
                          (to_jsonb(e) || jsonb_build_object(
                            'packet_sha256',CAST(:packet_sha256 AS text)))::json,
                          'sha256:' || encode(sha256(convert_to(
                            project_guide_projection_canonical_json(
                              to_jsonb(e) || jsonb_build_object(
                                'packet_sha256',CAST(:packet_sha256 AS text))),
                            'UTF8')), 'hex'),
                          'reserved'
                        FROM pre_submit_evidence_sets e WHERE e.id=:retained
                    """), {
                        "attempt": attempt_id, "key": str(uuid4()),
                        "nonce": str(uuid4()), "packet_sha256": packet_sha256,
                        "retained": retained_id,
                    })
                    await connection.execute(text("""
                        INSERT INTO pre_submit_evidence_sets
                        SELECT (jsonb_populate_record(NULL::pre_submit_evidence_sets,
                          to_jsonb(e) || jsonb_build_object(
                            'id',CAST(:new_id AS text),
                            'operation_identity','sha256:' || repeat('c',64),
                            'packet_sha256',CAST(:packet_sha256 AS text),
                            'attempt_id',CAST(:attempt AS text),
                            'attempt_request_digest',a.request_digest,
                            'created_at',transaction_timestamp()))).*
                        FROM pre_submit_evidence_sets e
                        JOIN pre_submit_execution_attempts a ON a.id=:attempt
                        WHERE e.id=:retained
                    """), {
                        "new_id": new_id, "retained": retained_id,
                        "packet_sha256": packet_sha256, "attempt": attempt_id,
                    })
                    await connection.execute(text(
                        "UPDATE pre_submit_execution_attempts "
                        "SET status='completed',evidence_set_id=:evidence "
                        "WHERE id=:attempt"
                    ), {"evidence": new_id, "attempt": attempt_id})
                    # Flush deferred lineage checks before probing the result
                    # trigger, so a mismatched packet cannot mask its verdict.
                    await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                    insert_result = text("""
                        INSERT INTO pre_submit_evidence_results (
                          id,evidence_set_id,result_order,schema_version,
                          dispatch_authority,definition_id,definition_version,
                          public_name,source,phase,classification,severity,status,
                          message_code,effective_plan_sha256,locked_policy_sha256,
                          checker_order,metadata_json)
                        VALUES (:id,:parent,0,'v1','migration-test','test.check',
                          'v1','Test check','test','custody','mandatory_integrity',
                          'blocking','passed','test.passed',:digest,:digest,
                          :checker_order,CAST(:metadata AS json))
                    """)
                    parameters = {
                        "parent": new_id, "digest": "sha256:" + "a" * 64,
                    }
                    for checker_order, metadata in (
                        (None, "[]"), (-1, "[]"), (0, None),
                        (0, '{"entry_count":1}'),
                        (0, '[["entry_count",-1]]'),
                        (0, '[["entry_count",1],["entry_count",2]]'),
                    ):
                        with pytest.raises(DBAPIError, match="pre-submit result"):
                            async with connection.begin_nested():
                                await connection.execute(insert_result, {
                                    **parameters, "id": str(uuid4()),
                                    "checker_order": checker_order, "metadata": metadata,
                                })
                    await connection.execute(insert_result, {
                        **parameters, "id": str(uuid4()),
                        "checker_order": 0,
                        "metadata": '[["entry_count",1],["finding_count",0]]',
                    })
                    assert await connection.scalar(text(
                        "SELECT count(*) FROM pre_submit_evidence_results "
                        "WHERE evidence_set_id=:id AND checker_order=0"
                    ), {"id": new_id}) == 1
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(probe())
