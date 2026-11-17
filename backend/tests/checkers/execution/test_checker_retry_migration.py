"""0035 preserves retained checker custody and installs terminal retry closure."""

import asyncio
import json
from uuid import UUID

import asyncpg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.historical_submission_fixtures import restore_archived_snapshot
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
PREDECESSOR = "0034_checker_replacement"
SUCCESSOR = "0035_checker_retry"
RETAINED_TABLES = (
    "submissions",
    "submission_dispatches",
    "submission_binding_receipts",
    "checker_runs",
    "checker_results",
    "checker_submission_fences",
    "audit_events",
    "outbox_events",
    "outbox_delivery_attempts",
    "task_post_submit_routing_manifests",
    "workstream_tasks",
    "task_assignments",
    "pre_submit_evidence_sets",
    "pre_submit_evidence_results",
    "pre_submit_execution_attempts",
    "submission_bundle_admissions",
    "submission_bundle_durable_intents",
    "artifact_bindings",
    "artifact_contents",
    "artifact_put_attempts",
    "artifact_operation_receipts",
    "artifact_verification_receipts",
    "artifact_replicas",
)


async def _connection(database_url):
    return await asyncpg.connect(database_url.replace("+asyncpg", ""))


async def _reset_to_predecessor(database_url):
    await db_session.dispose_engine()
    connection = await _connection(database_url)
    try:
        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    finally:
        await connection.close()
    await asyncio.to_thread(command.upgrade, _config(), PREDECESSOR)


async def _retained_rows(connection):
    return {
        table: tuple(
            row["value"]
            for row in await connection.fetch(
                f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY value"
            )
        )
        for table in RETAINED_TABLES
    }


async def _source_custody(connection, submission_id):
    return await connection.fetchrow(
        """
        SELECT r.id AS run_id, r.status, r.failure_code, r.result_digest,
          r.finalize_evidence_id IS NOT NULL AS finalized,
          fin.action_id='checker.post_submit.finalize' AS finalize_authority_valid,
          fin.event_type='SensitiveAuthorizationAllowed' AS finalize_allowed,
          r.completion_event_id IS NULL AS no_completion_event,
          f.current_run_id=r.id AS current_run,
          public.submission_dispatch_valid(d) AS dispatch_valid,
          public.submission_binding_receipt_valid(br) AS binding_valid,
          public.submission_authority_receipt_valid(
            d.creation_decision_id, public.submission_creation_resource(d.submission_id), true
          ) AS creation_authority_valid,
          public.submission_authority_receipt_valid(
            d.binding_decision_id, public.submission_binding_resource(d.admission_id), false
          ) AS binding_authority_valid
        FROM public.submission_dispatches d
        JOIN public.submission_binding_receipts br ON br.admission_id=d.admission_id
        JOIN public.checker_runs r ON r.id=d.evaluation_attempt_id
        JOIN public.audit_events fin ON fin.id=r.finalize_evidence_id
        JOIN public.checker_submission_fences f ON f.submission_id=d.submission_id
        WHERE d.submission_id=$1
    """,
        submission_id,
    )


async def _predecessor_evidence(connection, submission_id):
    """Verify the complete archived source before comparing its upgrade."""
    assert await connection.fetchval("SELECT version_num FROM public.alembic_version") == PREDECESSOR
    assert await connection.fetchval(
        "SELECT to_regclass('public.checker_retry_receipts') IS NULL"
    ) is True
    before = await _retained_rows(connection)
    assert all(before[table] for table in (
        "submissions", "submission_dispatches", "checker_runs",
        "checker_submission_fences", "audit_events", "outbox_events",
        "pre_submit_evidence_sets", "submission_bundle_admissions", "artifact_bindings",
    ))
    assert await connection.fetchval("""
        SELECT count(*) FROM public.audit_events
        WHERE action_id='checker.post_submit.finalize'
    """) == 1
    source = await _source_custody(connection, submission_id)
    assert source["status"] == "infrastructure_failed"
    assert source["failure_code"] == "material_unavailable"
    assert source["result_digest"].startswith("sha256:")
    assert all(source[key] is True for key in (
        "finalized", "finalize_authority_valid", "finalize_allowed",
        "no_completion_event", "current_run", "dispatch_valid", "binding_valid",
        "creation_authority_valid", "binding_authority_valid",
    ))
    return before, source


async def test_retry_upgrade_preserves_evidence_and_installs_closure(
    tmp_path,
    isolated_database_env,
    migration_lock,
):
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        seed = await restore_archived_snapshot(
            isolated_database_env, "0034_checker_retry_source"
        )
        submission_id = UUID(seed["submission_id"])
        request = seed["request"]
        assert UUID(request["submission_id"]) == submission_id
        connection = await _connection(isolated_database_env)
        try:
            before, source = await _predecessor_evidence(connection, submission_id)
        finally:
            await connection.close()

        await db_session.dispose_engine()
        await asyncio.to_thread(command.upgrade, _config(), SUCCESSOR)
        connection = await _connection(isolated_database_env)
        try:
            assert (
                await connection.fetchval("SELECT version_num FROM public.alembic_version")
                == SUCCESSOR
            )
            assert await _retained_rows(connection) == before
            assert await _source_custody(connection, submission_id) == source
            assert (
                await connection.fetchval("SELECT count(*) FROM public.checker_retry_receipts")
                == 0
            )
            assert (
                await connection.fetchval("""
                SELECT EXISTS (SELECT 1 FROM pg_trigger t
                JOIN pg_class c ON c.oid=t.tgrelid
                WHERE c.oid='public.checker_submission_fences'::regclass
                  AND t.tgname='checker_failed_supersession_receipt'
                  AND t.tgdeferrable)
            """)
                is True
            )
            assert (
                await connection.fetchval(
                    "SELECT public.checker_retry_receipt_valid($1)", new_record_id()
                )
                is False
            )
        finally:
            await connection.close()

        # This is a raw predecessor SQL invariant, not a current runtime request.
        successor_request = {key: value for key, value in request.items() if key != "request_sha256"}
        successor_request.update(evaluation_request_id=str(new_record_id()), evaluation_generation=2)
        successor_id = new_record_id()
        request_json = json.dumps(successor_request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        successor_row = {
            "id": str(successor_id), "evaluation_request_id": successor_request["evaluation_request_id"],
            "evaluation_generation": 2, "request_json": request_json,
            "request_digest": canonical_json_hash(successor_request), "result_id": str(new_record_id()),
            "supersedes_checker_run_id": str(source["run_id"]),
            "status": "queued", "outcome_source": "none", "routing_recommendation": "not_evaluated",
            "worker_lease_id": None, "worker_lease_generation": 0, "worker_lease_expires_at": None,
            "execute_evidence_id": None, "finalize_evidence_id": None,
            "result_json": None, "result_digest": None, "material_custody": None,
            "input_materialization_evidence_id": None, "completion_event_id": None,
            "started_at": None, "completed_at": None, "failure_code": None,
            "passed_count": 0, "warning_count": 0, "failed_count": 0, "blocking_count": 0,
        }
        with pytest.raises(
            IntegrityError,
            match="terminal checker infrastructure retry requires Operator receipt",
        ):
            async with db_session.get_session_factory().begin() as session:
                await session.execute(text("""
                    INSERT INTO public.checker_runs
                    SELECT (jsonb_populate_record(NULL::public.checker_runs,
                      to_jsonb(r) || CAST(:changes AS jsonb))).*
                    FROM public.checker_runs r WHERE id=:source
                """), {"changes": json.dumps(successor_row), "source": source["run_id"]})
                await session.execute(text("""
                    UPDATE public.checker_submission_fences SET current_run_id=:successor
                    WHERE submission_id=:submission
                """), {"successor": successor_id, "submission": submission_id})
        connection = await _connection(isolated_database_env)
        try:
            assert await _retained_rows(connection) == before
            assert (
                await connection.fetchval("SELECT count(*) FROM public.checker_retry_receipts")
                == 0
            )
        finally:
            await connection.close()

async def test_selected_checker_cutover_refuses_new_archived_pre_submit_lineage(
    isolated_database_env,
    migration_lock,
):
    """The selected-checker migration retains rows and refuses new archived PRE writes."""
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        await restore_archived_snapshot(
            isolated_database_env, "0034_checker_retry_source"
        )
        await db_session.dispose_engine()
        await asyncio.to_thread(command.upgrade, _config(), "0036_selected_checker_flow")
        connection = await _connection(isolated_database_env)
        try:
            before = await _retained_rows(connection)
            intent_id = await connection.fetchval("""
                SELECT id FROM public.submission_bundle_durable_intents
                WHERE pre_submit_evidence_set_id IS NOT NULL
            """)
            admission_id = await connection.fetchval("""
                SELECT id FROM public.submission_bundle_admissions
                WHERE pre_submit_evidence_set_id IS NOT NULL
            """)
            attempt_id = await connection.fetchval(
                "SELECT id FROM public.pre_submit_execution_attempts"
            )
            evidence_id = await connection.fetchval(
                "SELECT id FROM public.pre_submit_evidence_sets"
            )
            result_id = await connection.fetchval(
                "SELECT id FROM public.pre_submit_evidence_results ORDER BY result_order LIMIT 1"
            )
            assert all((intent_id, admission_id, attempt_id, evidence_id, result_id))
            with pytest.raises(
                asyncpg.CheckViolationError,
                match="submission bundle durable intent requires selected PRE lineage",
            ):
                async with connection.transaction():
                    await connection.execute("""
                        INSERT INTO public.submission_bundle_durable_intents
                        SELECT (jsonb_populate_record(
                          NULL::public.submission_bundle_durable_intents,
                          to_jsonb(value) || jsonb_build_object('id',$1::uuid)
                        )).* FROM public.submission_bundle_durable_intents value
                        WHERE value.id=$2::uuid
                    """, new_record_id(), intent_id)
            with pytest.raises(
                asyncpg.CheckViolationError,
                match="submission bundle admission requires selected PRE lineage",
            ):
                async with connection.transaction():
                    await connection.execute("""
                        INSERT INTO public.submission_bundle_admissions
                        SELECT (jsonb_populate_record(
                          NULL::public.submission_bundle_admissions,
                          to_jsonb(value) || jsonb_build_object('id',$1::uuid)
                        )).* FROM public.submission_bundle_admissions value
                        WHERE value.id=$2::uuid
                    """, new_record_id(), admission_id)
            for table, source_id, message in (
                (
                    "pre_submit_execution_attempts",
                    attempt_id,
                    "retained pre-submit attempts are immutable",
                ),
                (
                    "pre_submit_evidence_sets",
                    evidence_id,
                    "retained pre-submit evidence is immutable",
                ),
                (
                    "pre_submit_evidence_results",
                    result_id,
                    "retained pre-submit evidence results are immutable",
                ),
            ):
                with pytest.raises(asyncpg.PostgresError, match=message) as refused:
                    async with connection.transaction():
                        await connection.execute(f"""
                            INSERT INTO public.{table}
                            SELECT (jsonb_populate_record(
                              NULL::public.{table},
                              to_jsonb(value) || jsonb_build_object('id',$1::uuid)
                            )).* FROM public.{table} value WHERE value.id=$2::uuid
                        """, new_record_id(), source_id)
                assert refused.value.sqlstate == "55000"
            with pytest.raises(
                asyncpg.PostgresError,
                match="retained pre-submit attempts are immutable",
            ) as refused:
                async with connection.transaction():
                    await connection.execute("""
                        UPDATE public.pre_submit_execution_attempts
                        SET status=status WHERE id=$1::uuid
                    """, attempt_id)
            assert refused.value.sqlstate == "55000"
            assert await _retained_rows(connection) == before
        finally:
            await connection.close()
