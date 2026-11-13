"""Real database cleanup fencing; historical fixture timestamps are setup only."""
from dataclasses import replace
import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.adapters.tasks import intake_task_custody_port
from app.core.identifiers import new_record_id
from app.modules.artifacts.intake.cleanup import SealedSourceCleanup
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from tests.artifacts.test_submission_intake_custody import (
    SHA, reserve, record_eof, repository,
    intake as intake, capacity_limits as capacity_limits,
)

pytestmark = pytest.mark.asyncio


def owner(session):
    """Use the same TASK custody adapter as foreground and finalization."""
    return SealedSourceCleanup(session, intake_task_custody_port(session))


async def terminal_source(intake):
    """Create a real sealed rejected operation through existing owners."""
    from datetime import UTC, datetime
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        await repository(session).seal(operation, lease, 1, provider_generation="exact-generation",
                                      pre_deadline_at=deadline, lease_expires_at=deadline)
    async with intake.factory.begin() as session:
        await repository(session).terminalize(operation, lease, 1, state="rejected", failure_code="pre_failed")
    return operation


async def age_fixture(intake, operation):
    """Seed historical timestamps in an isolated test DB; all cleanup guards stay enabled."""
    database = intake.engine.url.database
    assert database.startswith("workstream_test_")
    # The isolated runner's restricted role owns only this test database. It can
    # prepare history without exposing the runner's server administrator secret.
    async with intake.engine.begin() as connection:
        # Only timestamp fixture setup bypasses the immutable foreground
        # history guard, restored in this transaction before cleanup runs.
        await connection.execute(text("ALTER TABLE submission_intake_operations DISABLE TRIGGER submission_intake_mutation"))
        await connection.execute(text("UPDATE submission_intake_operations SET " + ",".join(
            f"{column}={column}-interval '3 hours'" for column in (
                "created_at", "upload_deadline_at", "lease_expires_at", "pre_deadline_at",
                "eof_at", "sealed_at", "terminal_at",
            )
        ) + " WHERE id=:id"), {"id": operation})
        await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await connection.execute(text("ALTER TABLE submission_intake_operations ENABLE TRIGGER submission_intake_mutation"))

async def test_cleanup_requires_age_then_confirms_charge_once(intake):
    operation = await terminal_source(intake)
    claim_id = new_record_id()
    with pytest.raises(DBAPIError, match="cleanup is protected"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, claim_id, lease_duration=timedelta(minutes=5))
    await age_fixture(intake, operation)
    async with intake.factory.begin() as session:
        claim = await owner(session).claim(operation, claim_id, lease_duration=timedelta(minutes=5))
    with pytest.raises(IntakeCustodyConflict, match="cleanup_busy"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
    for field in ("object_absent", "writes_settled", "parts_absent"):
        facts = dict(object_absent=True, writes_settled=True, parts_absent=True)
        facts[field] = False
        with pytest.raises(IntakeCustodyConflict, match="cleanup_unresolved"):
            async with intake.factory.begin() as session:
                await owner(session).confirm(claim, **facts)
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"), {"id": operation}) == 100
    with pytest.raises(IntakeCustodyConflict, match="cleanup_stale"):
        async with intake.factory.begin() as session:
            await owner(session).confirm(replace(claim, generation=claim.generation+1),
                                         object_absent=True, writes_settled=True, parts_absent=True)
    for _ in range(2):
        async with intake.factory.begin() as session:
            await owner(session).confirm(claim, object_absent=True, writes_settled=True, parts_absent=True)
    async with intake.factory() as session:
        row = (await session.execute(text("SELECT state,accounted_bytes FROM submission_source_charges WHERE operation_id=:id"), {"id": operation})).one()
        assert tuple(row) == ("released", 0)
    with pytest.raises(DBAPIError, match="tombstone is retained"):
        async with intake.factory.begin() as session:
            await session.execute(text("DELETE FROM submission_source_cleanup_claims WHERE operation_id=:id"), {"id": operation})


async def test_cleanup_sql_rejects_release_without_confirmation_and_target_substitution(intake):
    operation = await terminal_source(intake)
    await age_fixture(intake, operation)
    async with intake.factory.begin() as session:
        claim = await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
    for sql, error in (
        ("UPDATE submission_source_charges SET state='released',accounted_bytes=0 WHERE operation_id=:id", "confirmed cleanup"),
        ("UPDATE submission_source_cleanup_claims SET source=jsonb_set(source,'{provider_generation}','\"foreign\"') WHERE operation_id=:id", "target differs"),
        ("UPDATE submission_source_cleanup_claims SET confirmed_at=clock_timestamp() WHERE operation_id=:id", "release must be atomic"),
    ):
        with pytest.raises(DBAPIError, match=error):
            async with intake.factory.begin() as session:
                await session.execute(text(sql), {"id": operation})
    async with intake.factory.begin() as session:
        replay = await owner(session).claim(operation, claim.claim_id, lease_duration=timedelta(minutes=5))
        assert replay == claim


async def test_cleanup_rejects_live_input_and_serializes_competing_claims(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation = UUID(row.id)
    with pytest.raises(DBAPIError, match="cleanup is protected"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
    async with intake.factory.begin() as session:
        await repository(session).terminalize(operation, UUID(row.lease_id), 1, state="failed", failure_code="upload_failed")
    # Unsealed terminal input cannot enter the sealed cleanup/release path.
    await age_fixture(intake, operation)
    with pytest.raises(DBAPIError, match="cleanup is protected"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
    operation = await terminal_source(intake)
    await age_fixture(intake, operation)

    async def claim():
        try:
            async with intake.factory.begin() as session:
                return await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
        except IntakeCustodyConflict as exc:
            return str(exc)

    results = await asyncio.gather(claim(), claim())
    assert sum(result == "source_cleanup_busy" for result in results) == 1
    assert sum(not isinstance(result, str) for result in results) == 1


async def test_expired_cleanup_claim_cannot_confirm_after_takeover(intake):
    operation = await terminal_source(intake)
    await age_fixture(intake, operation)
    async with intake.factory.begin() as session:
        first = await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(seconds=3))
    await asyncio.sleep(3.1)
    with pytest.raises(IntakeCustodyConflict, match="cleanup_stale"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, first.claim_id, lease_duration=timedelta(minutes=5))
    async with intake.factory.begin() as session:
        second = await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
        assert second.generation == first.generation + 1
        assert second.source == first.source
    with pytest.raises(IntakeCustodyConflict, match="cleanup_stale"):
        async with intake.factory.begin() as session:
            await owner(session).confirm(first, object_absent=True, writes_settled=True, parts_absent=True)
    async with intake.factory.begin() as session:
        await owner(session).confirm(second, object_absent=True, writes_settled=True, parts_absent=True)


async def test_cleanup_lease_bound_is_enforced_by_owner_and_database(intake):
    operation = await terminal_source(intake)
    await age_fixture(intake, operation)
    with pytest.raises(ValueError, match="lease is invalid"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(days=3650))
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    async with intake.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(operation))
        source = repository(session)._sealed_source(row).model_dump_json()
    with pytest.raises(DBAPIError, match="claim_bounds"):
        async with intake.factory.begin() as session:
            await session.execute(text("INSERT INTO submission_source_cleanup_claims "
                "(operation_id,claim_id,generation,source,claimed_at,lease_expires_at) "
                "VALUES (:id,:claim,1,CAST(:source AS jsonb),clock_timestamp(),clock_timestamp()+interval '10 years')"),
                {"id": operation, "claim": new_record_id(), "source": source})


async def retain_exact_key(session, operation):
    """Create an ordinary generic replica referencing the managed key, without bypassing guards."""
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from app.modules.artifacts.models import ArtifactContent, ArtifactReplica, ArtifactStorageNamespace
    from app.modules.artifacts.repository import ArtifactRepository
    row = await session.get(SubmissionIntakeOperation, str(operation))
    namespace = await session.get(ArtifactStorageNamespace, row.namespace_id)
    content = await ArtifactRepository(session).get_or_create_content(ArtifactContent(
        id=str(new_record_id()), sha256=row.raw_sha256, byte_count=row.raw_byte_count,
        media_type="application/zip", normalized_display_name="submission.zip"))
    session.add(ArtifactReplica(id=str(new_record_id()), content_id=content.id, source_operation_id=None,
        storage_namespace_id=row.namespace_id, namespace_fingerprint=row.namespace_fingerprint,
        adapter=namespace.adapter, provider_profile=row.provider_profile, provider_object_ref=row.object_ref,
        verification_state="pending", availability_state="unknown", integrity_state="unknown"))
    await session.flush()


async def test_retained_key_blocks_claim_and_claim_blocks_new_retention(intake):
    operation = await terminal_source(intake)
    await age_fixture(intake, operation)
    async with intake.factory.begin() as session:
        await retain_exact_key(session, operation)
    with pytest.raises(DBAPIError, match="cleanup is protected"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
    other = await terminal_source(intake)
    await age_fixture(intake, other)
    async with intake.factory.begin() as session:
        await owner(session).claim(other, new_record_id(), lease_duration=timedelta(minutes=5))
    with pytest.raises(DBAPIError, match="claimed source cannot become retained"):
        async with intake.factory.begin() as session:
            await retain_exact_key(session, other)
