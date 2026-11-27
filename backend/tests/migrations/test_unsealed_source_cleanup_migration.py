"""Upgrade real predecessor cleanup claims without rewriting their authority."""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import event, text

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from tests.artifacts.test_submission_intake_custody import (
    intake as intake, capacity_limits as capacity_limits, repository, reserve, record_eof, SHA,
)
from tests.artifacts.test_submission_source_cleanup import age_fixture, cleanup_decision, owner, terminal_source
from tests.checkers.execution.support import provision_post_submit_service
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config, current_schema_revision

pytestmark = pytest.mark.postgres_schema_contract


@asynccontextmanager
async def predecessor_submission_read_projection(intake):
    """Construct old v1 commands and remove both current ORM projections."""
    def bind_old_metadata(_mapper, _connection, row):
        assert row.command_metadata["feedback"] is None
        metadata = {
            "task_id": row.task_id,
            "assignment_id": row.assignment_id,
            "predecessor_submission_id": None,
            "summary": "",
            "contributor_attestation": "",
            "revision_preparation_id": None,
            "revision_preparation_sha256": None,
        }
        row.command_metadata = metadata
        row.metadata_sha256 = canonical_json_hash({
            "schema_version": "workstream.submission_intake_metadata.v1", **metadata,
        })

    async with intake.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE public.submissions ADD COLUMN feedback text"))
    event.listen(SubmissionIntakeOperation, "before_insert", bind_old_metadata)
    try:
        yield
    finally:
        event.remove(SubmissionIntakeOperation, "before_insert", bind_old_metadata)
        async with intake.engine.begin() as connection:
            assert await connection.scalar(text(
                "SELECT count(*) FROM public.submissions WHERE feedback IS NOT NULL"
            )) == 0
            await connection.execute(text("ALTER TABLE public.submissions DROP COLUMN feedback"))
            assert await connection.scalar(text(
                "SELECT count(*) FROM public.actor_identity_links WHERE email_verified IS DISTINCT FROM false"
            )) == 0
            await connection.execute(text("ALTER TABLE public.actor_identity_links DROP COLUMN email_verified"))


@pytest.fixture(autouse=True, params=["0087_source_cleanup_candidates", "0088_unsealed_source_cleanup"])
async def predecessor_schema(isolated_database_env, migration_lock, request):
    """Build the actual predecessor before the ordinary intake fixture runs."""
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        try:
            await asyncio.to_thread(command.upgrade, _config(), request.param)
            # The intake fixture uses the current ORM to create fixture identities.
            async with db_session.get_engine().begin() as connection:
                await connection.execute(text(
                    "ALTER TABLE public.actor_identity_links ADD COLUMN email_verified boolean NOT NULL DEFAULT false"
                ))
            yield request.param
        finally:
            await db_session.dispose_engine()
            await _drop_test_database_schema(isolated_database_env)
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())


async def retained_rows(factory, *, new_columns=()):
    """Compare every retained fact in the owners touched by this migration."""
    tables = (
        "submission_intake_operations", "submission_source_upload_receipts",
        "submission_source_charges", "submission_source_cleanup_claims", "audit_events",
    )
    async with factory() as session:
        result = {}
        for table in tables:
            value = "to_jsonb(r)"
            if new_columns and table == "submission_source_cleanup_claims":
                assert await session.scalar(text("SELECT count(*) FROM submission_source_cleanup_claims "
                    "WHERE " + " OR ".join(f"{column} IS NOT NULL" for column in new_columns))) == 0
                value += "-ARRAY[" + ",".join(f"'{column}'" for column in new_columns) + "]"
            result[table] = await session.scalar(text(
                f"SELECT jsonb_agg({value} ORDER BY to_jsonb(r)::text) FROM {table} r"))
        return result


async def test_upgrade_preserves_sealed_claims_charges_and_audit_decisions(intake, predecessor_schema):
    claims = []
    async with predecessor_submission_read_projection(intake):
        await provision_post_submit_service(intake.factory, ServiceIdentity.ARTIFACT_SOURCE_CLEANUP)
        for confirmed in (False, True):
            operation = await terminal_source(intake)
            await age_fixture(intake, operation)
            claim_id = new_record_id()
            async with intake.factory.begin() as session:
                row = await session.get(SubmissionIntakeOperation, str(operation))
                source = repository(session)._sealed_source(row).model_dump_json()
                decision = await cleanup_decision(session, operation, claim_id)
                # Use actual 0087 SQL guards and real authority decisions. The new
                # Python cleanup owner cannot run against this predecessor schema.
                await session.execute(text("INSERT INTO submission_source_cleanup_claims "
                    "(operation_id,claim_id,generation,source,claimed_at,lease_expires_at,claim_decision_id) "
                    "VALUES (:id,:claim,1,CAST(:source AS jsonb),statement_timestamp(),"
                    "statement_timestamp()+interval '5 minutes',:decision)"),
                    {"id": operation, "claim": claim_id, "source": source, "decision": decision})
                if confirmed:
                    confirmation = await cleanup_decision(session, operation, claim_id, phase="confirm")
                    await session.execute(text("UPDATE submission_source_cleanup_claims "
                        "SET confirmed_at=clock_timestamp(),confirmation_decision_id=:decision WHERE operation_id=:id"),
                        {"id": operation, "decision": confirmation})
                    await session.execute(text("UPDATE submission_source_charges SET state='released',accounted_bytes=0 "
                        "WHERE operation_id=:id"), {"id": operation})
            claims.append((operation, claim_id, confirmed, None))
        if predecessor_schema == "0088_unsealed_source_cleanup":
            claims.append(await observed_version_claim(intake))
    before = await retained_rows(intake.factory)
    await intake.engine.dispose()
    await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
    columns = ("observed_upload_ids",) if predecessor_schema == "0088_unsealed_source_cleanup" else (
        "observed_source", "observed_at", "observed_upload_ids")
    assert await retained_rows(intake.factory, new_columns=columns) == before
    for operation, claim_id, confirmed, observed in claims:
        async with intake.factory.begin() as session:
            claim = await owner(session).claim(operation, claim_id, lease_duration=timedelta(minutes=5))
            assert claim.confirmed is confirmed
            assert claim.observed_source == observed
            assert claim.observed_upload_ids == ()
            await owner(session).confirm(claim, object_absent=True, writes_settled=True, parts_absent=True)
        async with intake.factory() as session:
            assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                        {"id": operation}) == 0


async def observed_version_claim(intake):
    """Create an actual 0088 claim whose audit binds a recovered completed version."""
    from app.modules.artifacts.api.submission_cleanup import SubmissionSourceCleanupAuthorityFacts, cleanup_target_sha256
    from app.modules.artifacts.api.submission_intake import SealedSubmissionSource
    from app.modules.artifacts.authorization import PreparedSubmissionSourceCleanupAuthorization

    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="upload_interrupted")
    await age_fixture(intake, operation)

    async def decision(session, source, claim_id, generation, observed=None):
        row = await session.get(SubmissionIntakeOperation, str(operation))
        facts = SubmissionSourceCleanupAuthorityFacts(operation_id=operation, project_id=UUID(row.project_id),
            task_id=UUID(row.task_id), source_sha256=cleanup_target_sha256(source, observed),
            claim_id=claim_id, claim_generation=generation, phase="claim")
        authority = PreparedSubmissionSourceCleanupAuthorization(session,
            request_id=new_record_id(), correlation_id=new_record_id())
        prepared = await authority.prepare(facts=facts, idempotency_key=claim_id)
        return await authority.consume(prepared_authorization=prepared, facts=facts)

    claim_id = new_record_id()
    async with intake.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(operation))
        source = await owner(session)._target(row)
        observed = SealedSubmissionSource(location=source.location, provider_generation="retained-observed-version",
            raw_sha256=SHA, raw_byte_count=100, sealed_upload_fence=1)
        authorization = await decision(session, source, claim_id, 1)
        await session.execute(text("INSERT INTO submission_source_cleanup_claims "
            "(operation_id,claim_id,generation,source,claimed_at,lease_expires_at,claim_decision_id) "
            "VALUES (:id,:claim,1,CAST(:source AS jsonb),statement_timestamp(),"
            "statement_timestamp()+interval '5 minutes',:decision)"),
            {"id": operation, "claim": claim_id, "source": source.model_dump_json(), "decision": authorization})
        await session.execute(text("UPDATE submission_source_cleanup_claims "
            "SET observed_source=CAST(:source AS jsonb),observed_at=clock_timestamp() WHERE operation_id=:id"),
            {"id": operation, "source": observed.model_dump_json()})
    assert intake.engine.url.database.startswith("workstream_test_")
    async with intake.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE submission_source_cleanup_claims DISABLE TRIGGER submission_source_cleanup_guard"))
        await connection.execute(text("UPDATE submission_source_cleanup_claims SET observed_at=observed_at-interval '3 hours', "
            "claimed_at=claimed_at-interval '3 hours',lease_expires_at=lease_expires_at-interval '3 hours' WHERE operation_id=:id"),
            {"id": operation})
        await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await connection.execute(text("ALTER TABLE submission_source_cleanup_claims ENABLE TRIGGER submission_source_cleanup_guard"))
    claim_id = new_record_id()
    async with intake.factory.begin() as session:
        authorization = await decision(session, source, claim_id, 2, observed)
        await session.execute(text("UPDATE submission_source_cleanup_claims SET claim_id=:claim,generation=2, "
            "claimed_at=statement_timestamp(),lease_expires_at=statement_timestamp()+interval '5 minutes', "
            "claim_decision_id=:decision WHERE operation_id=:id"),
            {"id": operation, "claim": claim_id, "decision": authorization})
    return operation, claim_id, False, observed
