"""Upgrade real predecessor cleanup claims without rewriting their authority."""
import asyncio
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from tests.artifacts.test_submission_intake_custody import intake as intake, capacity_limits as capacity_limits, repository
from tests.artifacts.test_submission_source_cleanup import age_fixture, cleanup_decision, owner, terminal_source
from tests.checkers.execution.support import provision_post_submit_service
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config, current_schema_revision

pytestmark = pytest.mark.postgres_schema_contract


@pytest.fixture(autouse=True)
async def predecessor_schema(isolated_database_env, migration_lock):
    """Build the actual predecessor before the ordinary intake fixture runs."""
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        try:
            await asyncio.to_thread(command.upgrade, _config(), "0087_source_cleanup_candidates")
            yield
        finally:
            await db_session.dispose_engine()
            await _drop_test_database_schema(isolated_database_env)
            await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())


async def retained_rows(factory, *, upgraded=False):
    """Compare every retained fact in the owners touched by this migration."""
    tables = (
        "submission_intake_operations", "submission_source_upload_receipts",
        "submission_source_charges", "submission_source_cleanup_claims", "audit_events",
    )
    async with factory() as session:
        result = {}
        for table in tables:
            value = "to_jsonb(r)"
            if upgraded and table == "submission_source_cleanup_claims":
                assert await session.scalar(text("SELECT count(*) FROM submission_source_cleanup_claims "
                    "WHERE observed_source IS NOT NULL OR observed_at IS NOT NULL")) == 0
                value += "-ARRAY['observed_source','observed_at']"
            result[table] = await session.scalar(text(
                f"SELECT jsonb_agg({value} ORDER BY to_jsonb(r)::text) FROM {table} r"))
        return result


async def test_upgrade_preserves_sealed_claims_charges_and_audit_decisions(intake):
    await provision_post_submit_service(intake.factory, ServiceIdentity.ARTIFACT_SOURCE_CLEANUP)
    claims = []
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
        claims.append((operation, claim_id, confirmed))
    before = await retained_rows(intake.factory)
    await intake.engine.dispose()
    await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
    assert await retained_rows(intake.factory, upgraded=True) == before
    for operation, claim_id, confirmed in claims:
        async with intake.factory.begin() as session:
            claim = await owner(session).claim(operation, claim_id, lease_duration=timedelta(minutes=5))
            assert claim.confirmed is confirmed
            assert claim.observed_source is None
            await owner(session).confirm(claim, object_absent=True, writes_settled=True, parts_absent=True)
        async with intake.factory() as session:
            assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                        {"id": operation}) == 0
