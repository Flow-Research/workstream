"""Real PostgreSQL proof of pre-handoff custody, not upload or acceptance authority."""

import asyncio
import json

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import (
    SubmissionIntakeMetadata, SubmissionSourceCapacityLimits, SubmissionSourceCompletion,
    SubmissionSourcePart, SubmissionSourceUpload,
)
from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceUploadReceipt
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository
from app.modules.tasks.api.submission_context import TaskSubmissionContextUnavailable
from app.modules.tasks.intake_custody import IntakeTaskCustody
from tests.selected_policy_fixtures import approved_selected_policy_fixture
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_artifact_admission import _context, _namespace, _seed_human_actor, _settings

SHA = "sha256:" + "a" * 64


def repository(session):
    return SubmissionIntakeRepository(
        session, IntakeTaskCustody(session, task_submission_context_port(session)),
    )


@pytest.fixture
def capacity_limits(request):
    return getattr(request, "param", SubmissionSourceCapacityLimits(maximum_total_bytes=1_000_000))


@pytest.fixture
async def intake(tmp_path, isolated_database_env, capacity_limits, request):
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        from tests.checkers.external.support import pre_registry_spec
        plan, _ = await approved_selected_policy_fixture(
            factory, _namespace(_settings(tmp_path)), guide_version="v1",
            pre_submit_registry_spec=pre_registry_spec() if getattr(request, "param", False) else None,
        )
        actor = _context()
        async with factory.begin() as session:
            await _seed_human_actor(session, actor)
        task, assignment = new_record_id(), new_record_id()
        async with engine.begin() as connection:
            await seed_started_task_for_artifact_test(connection, dict(
                task=str(task), assignment=str(assignment),
                project=str(plan.lineage.project_id), actor=str(actor.actor_profile_id),
            ))
        yield SimpleNamespace(engine=engine, factory=factory, actor=actor, task=task, assignment=assignment,
                              capacity_limits=capacity_limits, durable_root=tmp_path / "durable")
    finally:
        await engine.dispose()


async def reserve(intake, session, *, key=None, declared_raw_bytes=None, with_upload=True,
                  lease_seconds=60, upload_seconds=300):
    now = datetime.now(UTC)
    row = await repository(session).reserve(
        operation_id=new_record_id(),
        metadata=SubmissionIntakeMetadata(task_id=intake.task, assignment_id=intake.assignment),
        actor_id=intake.actor.actor_profile_id, identity_link_id=intake.actor.identity_link_id,
        idempotency_key=key or new_record_id(), maximum_raw_bytes=1024,
        capacity_limits=intake.capacity_limits, declared_raw_bytes=declared_raw_bytes,
        upload_deadline_at=now + timedelta(seconds=upload_seconds),
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )
    if not with_upload:
        return row
    intent = await repository(session).prepare_upload(
        UUID(row.id), UUID(row.lease_id), 1, part_bytes=5 * 1024 * 1024, idle_timeout_seconds=20.0,
    )
    await repository(session).record_upload(
        UUID(row.id), UUID(row.lease_id), 1,
        upload=SubmissionSourceUpload(intent=intent, provider_upload_id="fixture-upload"),
    )
    return row


async def record_eof(session, operation, lease, generation, *, raw_sha256, raw_byte_count):
    """Database-only fixture: build a completed provider receipt, never claim byte I/O."""
    row = await session.get(SubmissionIntakeOperation, str(operation))
    receipt = await session.get(SubmissionSourceUploadReceipt, str(operation))
    repo = repository(session)
    upload = SubmissionSourceUpload(
        intent=await repo._upload_intent(row, receipt), provider_upload_id=receipt.provider_upload_id,
    )
    await repo.record_eof(operation, lease, generation, completion=SubmissionSourceCompletion(
        upload=upload, parts=(SubmissionSourcePart(number=1, byte_count=raw_byte_count, provider_etag="part-etag"),),
        raw_sha256=raw_sha256, raw_byte_count=raw_byte_count,
    ))


async def test_upload_intent_and_handle_commit_before_parts_and_cannot_be_replaced(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        intent = await repository(session).prepare_upload(
            operation, lease, 1, part_bytes=5 * 1024 * 1024, idle_timeout_seconds=20.0,
        )
    with pytest.raises(IntakeCustodyConflict, match="already_initiated"):
        async with intake.factory.begin() as session:
            await repository(session).prepare_upload(
                operation, lease, 1, part_bytes=5 * 1024 * 1024, idle_timeout_seconds=20.0,
            )
    wrong = intent.model_copy(update={"location": intent.location.model_copy(update={"operation_id": new_record_id()})})
    with pytest.raises(IntakeCustodyConflict, match="receipt_mismatch"):
        async with intake.factory.begin() as session:
            await repository(session).record_upload(
                operation, lease, 1, upload=SubmissionSourceUpload(intent=wrong, provider_upload_id="handle"),
            )
    upload = SubmissionSourceUpload(intent=intent, provider_upload_id="handle")
    for _ in range(2):
        async with intake.factory.begin() as session:
            await repository(session).record_upload(operation, lease, 1, upload=upload)
    with pytest.raises(IntakeCustodyConflict, match="handle_immutable"):
        async with intake.factory.begin() as session:
            await repository(session).record_upload(
                operation, lease, 1, upload=upload.model_copy(update={"provider_upload_id": "replacement"}),
            )
    async with intake.factory.begin() as session:
        await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="upload_failed")
    with pytest.raises(IntakeCustodyConflict, match="owner_stale"):
        async with intake.factory.begin() as session:
            await repository(session).record_upload(operation, lease, 1, upload=upload)


async def test_eof_cannot_commit_without_exact_bounded_completion_receipts(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation = UUID(row.id)
    valid_part = {"number": 1, "byte_count": 100, "provider_etag": "opaque-part"}
    for parts, error in (
        (None, "requires exact completion"),
        ([dict(valid_part, number="1")], "invalid submission completion part"),
        ([dict(valid_part, number=2)], "invalid submission completion part"),
        ([dict(valid_part, byte_count=99)], "byte count mismatch"),
        ([dict(valid_part, provider_etag="")], "invalid submission completion part"),
        ([dict(valid_part, unexpected="field")], "invalid submission completion part"),
        ([dict(valid_part, byte_count=50), dict(valid_part, number=2, byte_count=50)], "part size"),
    ):
        with pytest.raises(DBAPIError, match=error):
            async with intake.factory.begin() as session:
                await session.execute(text(
                    "UPDATE submission_intake_operations SET raw_sha256=:sha,raw_byte_count=100,"
                    "eof_at=clock_timestamp() WHERE id=:id"
                ), {"sha": SHA, "id": operation})
                if parts is not None:
                    await session.execute(text(
                        "UPDATE submission_source_upload_receipts SET completion_parts=CAST(:parts AS jsonb),"
                        "completion_recorded_at=clock_timestamp() WHERE operation_id=:id"
                    ), {"parts": json.dumps(parts), "id": operation})
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT raw_sha256 FROM submission_intake_operations")) is None
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges")) == 1024


async def test_recorded_upload_and_completion_are_immutable_custody(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
    for assignment in (
        "provider_upload_id='replacement'", "part_bytes=8388608", "idle_timeout_seconds=99",
        "completion_parts='[]'::jsonb", "completion_recorded_at=clock_timestamp()",
    ):
        with pytest.raises(DBAPIError, match="receipt is immutable"):
            async with intake.factory.begin() as session:
                await session.execute(text("UPDATE submission_source_upload_receipts SET " + assignment))
    for statement in ("DELETE FROM submission_source_upload_receipts", "TRUNCATE submission_source_upload_receipts"):
        with pytest.raises(DBAPIError, match="custody cannot be deleted"):
            async with intake.factory.begin() as session:
                await session.execute(text(statement))


async def test_foreground_eof_seal_terminal_and_stale_fence(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
    async with intake.factory.begin() as session:
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        source = await repository(session).seal(
            operation, lease, 1, provider_generation="exact-generation",
            pre_deadline_at=deadline, lease_expires_at=deadline,
        )
        assert source.raw_byte_count == 100
        assert source.sealed_upload_fence == 1
    async with intake.factory.begin() as session:
        await repository(session).terminalize(operation, lease, 1, state="rejected", failure_code="pre_failed")
    async with intake.factory() as session:
        stored = (await session.execute(text(
            "SELECT o.state,o.lease_generation,o.sealed_upload_fence,t.active_submission_operation_id "
            "FROM submission_intake_operations o JOIN workstream_tasks t ON t.id=o.task_id WHERE o.id=:id"
        ), {"id": operation})).one()
        assert tuple(stored) == ("rejected", 2, 1, None)
    with pytest.raises(IntakeCustodyConflict, match="intake_owner_stale"):
        async with intake.factory.begin() as session:
            await repository(session).heartbeat(operation, lease, 1, lease_duration=timedelta(seconds=30))


async def test_reservation_rollback_leaves_no_pointer_or_operation(intake):
    async with intake.factory() as session:
        await session.begin()
        await reserve(intake, session)
        await session.rollback()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_source_upload_receipts")) == 0
        assert await session.scalar(text(
            "SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"
        ), {"id": intake.task}) is None


@pytest.mark.parametrize("mutation", [
    "raw_sha256='" + SHA + "',raw_byte_count=NULL,eof_at=clock_timestamp()",
    "state='pre_checking'",
    "state='finalization_pending'",
    "metadata_sha256='sha256:'||repeat('b',64)",
    "object_ref='submission-source/v1/other/bundle.zip'",
    "lease_generation=2",
])
async def test_database_rejects_incomplete_or_rebound_custody(intake, mutation):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
    with pytest.raises(DBAPIError):
        async with intake.factory.begin() as session:
            await session.execute(text(
                f"UPDATE submission_intake_operations SET {mutation} WHERE id=:id"
            ), {"id": UUID(row.id)})


async def test_database_requires_matching_task_pointer_at_commit(intake):
    async with intake.factory.begin() as session:
        await reserve(intake, session)
    with pytest.raises(DBAPIError, match="intake task custody mismatch"):
        async with intake.factory.begin() as session:
            await session.execute(text(
                "UPDATE workstream_tasks SET active_submission_operation_id=NULL WHERE id=:id"
            ), {"id": intake.task})


async def test_expiry_can_only_abandon_and_cannot_resume(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        # Move the still-live lease into the past without sleeping or changing DB time.
        await session.execute(text(
            "UPDATE submission_intake_operations SET lease_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE id=:id"
        ), {"id": operation})
    with pytest.raises(IntakeCustodyConflict, match="intake_owner_stale"):
        async with intake.factory.begin() as session:
            await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
    async with intake.factory.begin() as session:
        assert await repository(session).abandon_expired(operation)
    async with intake.factory.begin() as session:
        assert not await repository(session).abandon_expired(operation)
        assert await session.scalar(text("SELECT sum(accounted_bytes) FROM submission_source_charges")) == 1024
        replacement = await reserve(intake, session)
        assert replacement.id != str(operation)
    with pytest.raises(DBAPIError, match="terminal intake is immutable"):
        async with intake.factory.begin() as session:
            await session.execute(text(
                "UPDATE submission_intake_operations SET state='receiving' WHERE id=:id"
            ), {"id": operation})


async def test_actor_key_stays_reserved_after_terminal_outcome(intake):
    key = new_record_id()
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, key=key)
    async with intake.factory.begin() as session:
        await repository(session).terminalize(UUID(row.id), UUID(row.lease_id), 1,
                                             state="failed", failure_code="upload_failed")
    with pytest.raises(DBAPIError, match="uq_submission_intake_actor_key"):
        async with intake.factory.begin() as session:
            await reserve(intake, session, key=key)
    async with intake.factory() as session:
        assert await session.scalar(text(
            "SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"
        ), {"id": intake.task}) is None


async def test_two_requests_serialize_on_task_and_only_one_claims(intake):
    async with intake.factory() as first, intake.factory() as second:
        await first.begin()
        await second.begin()
        winner = await reserve(intake, first)
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
        contender = asyncio.create_task(reserve(intake, second))
        try:
            async with intake.factory() as observer:
                async with asyncio.timeout(10):
                    while not await observer.scalar(text(
                        "SELECT cardinality(pg_blocking_pids(:pid))>0"
                    ), {"pid": second_pid}):
                        if contender.done():
                            await contender
                            pytest.fail("contender bypassed the TASK lock")
                        await asyncio.sleep(0.02)
            await first.commit()
            with pytest.raises(TaskSubmissionContextUnavailable):
                await contender
        finally:
            if not contender.done():
                contender.cancel()
                await asyncio.gather(contender, return_exceptions=True)
            await first.rollback()
            await second.rollback()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 1
        assert str(await session.scalar(text(
            "SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"
        ), {"id": intake.task})) == winner.id


async def test_recorded_source_identity_is_immutable(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
    with pytest.raises(DBAPIError, match="sealed_identity"):
        async with intake.factory.begin() as session:
            await session.execute(text(
                "UPDATE submission_intake_operations SET state='pre_checking',"
                "provider_generation='generation-without-deadline' WHERE id=:id"
            ), {"id": operation})
    with pytest.raises(DBAPIError, match="intake EOF identity is immutable"):
        async with intake.factory.begin() as session:
            await session.execute(text(
                "UPDATE submission_intake_operations SET raw_byte_count=101 WHERE id=:id"
            ), {"id": operation})
    async with intake.factory.begin() as session:
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        await repository(session).seal(operation, lease, 1, provider_generation="generation-a",
                                       pre_deadline_at=deadline, lease_expires_at=deadline)
    with pytest.raises(DBAPIError, match="intake sealed source is immutable"):
        async with intake.factory.begin() as session:
            await session.execute(text(
                "UPDATE submission_intake_operations SET provider_generation='generation-b' WHERE id=:id"
            ), {"id": operation})


async def test_intake_model_matches_installed_schema(isolated_database_env):
    from sqlalchemy import inspect
    from app.modules.artifacts.intake.models import (
        SubmissionIntakeOperation, SubmissionSourceCapacityProfile, SubmissionSourceCharge,
    )

    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            def compare(sync):
                inspector = inspect(sync)
                for owner in (SubmissionIntakeOperation, SubmissionSourceCapacityProfile, SubmissionSourceCharge,
                              SubmissionSourceUploadReceipt):
                    table = owner.__table__
                    assert {
                        (c["name"], str(c["type"].compile(dialect=sync.dialect)), c["nullable"])
                        for c in inspector.get_columns(table.name)
                    } == {
                        (c.name, str(c.type.compile(dialect=sync.dialect)), c.nullable)
                        for c in table.columns
                    }
                    assert {
                        (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]))
                        for f in inspector.get_foreign_keys(table.name)
                    } == {
                        (tuple(f.column_keys), f.referred_table.name, tuple(e.column.name for e in f.elements))
                        for f in table.foreign_key_constraints
                    }
                    assert {c["name"] for c in inspector.get_check_constraints(table.name)} == {
                        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
                    }
                    assert {i["name"] for i in inspector.get_indexes(table.name) if not i.get("duplicates_constraint")} == {
                        i.name for i in table.indexes
                    }
            await connection.run_sync(compare)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(("field", "constraint"), [
    ("project_id", "fk_submission_intake_task"),
    ("identity_link_id", "fk_submission_intake_identity"),
    ("assignment_id", "fk_submission_intake_assignment"),
    ("namespace_fingerprint", "intake namespace mismatch"),
])
async def test_sql_insert_cannot_substitute_bound_parents(intake, field, constraint):
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation

    # Capture a legitimate command, then roll back both participants. The probe
    # inserts through SQLAlchemy Core, bypassing the owner repository entirely.
    async with intake.factory() as session:
        await session.begin()
        row = await reserve(intake, session)
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        await session.rollback()
    values[field] = "sha256:" + "f" * 64 if field == "namespace_fingerprint" else str(new_record_id())
    if field == "identity_link_id":
        foreign = _context()
        async with intake.factory.begin() as session:
            await _seed_human_actor(session, foreign)
        values[field] = str(foreign.identity_link_id)
    if field == "assignment_id":
        async with intake.engine.begin() as connection:
            await seed_started_task_for_artifact_test(connection, dict(
                task=str(new_record_id()), assignment=values[field],
                project=values["project_id"], actor=str(intake.actor.actor_profile_id),
            ))
        metadata = SubmissionIntakeMetadata(task_id=intake.task, assignment_id=UUID(values[field]))
        values["command_metadata"] = metadata.model_dump(mode="json")
        values["metadata_sha256"] = metadata.metadata_sha256()
    with pytest.raises(DBAPIError, match=constraint):
        async with intake.factory.begin() as session:
            await session.execute(SubmissionIntakeOperation.__table__.insert().values(**values))
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_sql_rejects_malformed_command_selectors_even_with_matching_digest(intake):
    from app.core.hashing import canonical_json_hash
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation

    async with intake.factory() as session:
        await session.begin()
        row = await reserve(intake, session)
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        await session.rollback()
    cases = [
        {"predecessor_submission_id": value}
        for value in (42, True, {}, [], "not-a-uuid", str(new_record_id()).upper())
    ] + [
        {"predecessor_submission_id": str(new_record_id()),
         "revision_preparation_id": value, "revision_preparation_sha256": SHA}
        for value in (42, {}, "not-a-uuid")
    ]
    for selectors in cases:
        metadata = {**values["command_metadata"], **selectors}
        candidate = {**values, "command_metadata": metadata,
                     "metadata_sha256": canonical_json_hash({
                         "schema_version": "workstream.submission_intake_metadata.v1", **metadata,
                     })}
        with pytest.raises(DBAPIError, match="invalid intake metadata"):
            async with intake.factory.begin() as session:
                await session.execute(text(
                    "UPDATE workstream_tasks SET active_submission_operation_id=:operation WHERE id=:task"
                ), {"operation": UUID(row.id), "task": intake.task})
                await session.execute(SubmissionIntakeOperation.__table__.insert().values(**candidate))
                from app.modules.artifacts.intake.capacity import SubmissionSourceCapacity
                stored = await session.get(SubmissionIntakeOperation, values["id"])
                await SubmissionSourceCapacity(session).reserve(
                    stored, limits=intake.capacity_limits, declared_raw_bytes=None,
                )


@pytest.mark.parametrize("declared", [None, 100])
async def test_source_reservation_becomes_exact_bytes_only_after_sealing(intake, declared):
    from app.modules.artifacts.intake.capacity import SubmissionSourceCapacity
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge

    async with intake.factory.begin() as session:
        row = await reserve(intake, session, declared_raw_bytes=declared)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        charge = await session.get(SubmissionSourceCharge, row.id)
        assert charge.accounted_bytes == (1024 if declared is None else 100)
    async with intake.factory.begin() as session:
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
    async with intake.factory.begin() as session:
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        await repository(session).seal(operation, lease, 1, provider_generation="exact-source",
                                       pre_deadline_at=deadline, lease_expires_at=deadline)
    async with intake.factory.begin() as session:
        stored = await session.get(SubmissionIntakeOperation, str(operation))
        charge = await SubmissionSourceCapacity(session).reserve(
            stored, limits=intake.capacity_limits, declared_raw_bytes=declared,
        )
        assert (charge.state, charge.accounted_bytes) == ("sealed", 100)
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 1


async def test_declared_length_mismatch_cannot_record_eof_or_free_its_charge(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, declared_raw_bytes=101)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    with pytest.raises(DBAPIError, match="declared size mismatch"):
        async with intake.factory.begin() as session:
            await session.execute(text(
                "UPDATE submission_intake_operations SET raw_sha256=:sha,raw_byte_count=100,"
                "eof_at=clock_timestamp() WHERE id=:id"
            ), {"sha": SHA, "id": operation})
    async with intake.factory.begin() as session:
        await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="length_mismatch")
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT sum(accounted_bytes) FROM submission_source_charges")) == 101
        assert await session.scalar(text("SELECT raw_sha256 FROM submission_intake_operations")) is None
    for statement in ("DELETE FROM submission_source_charges", "TRUNCATE submission_source_charges"):
        with pytest.raises(DBAPIError, match="require confirmed cleanup"):
            async with intake.factory.begin() as session:
                await session.execute(text(statement))


@pytest.mark.parametrize("capacity_limits", [
    SubmissionSourceCapacityLimits(maximum_total_bytes=150),
    SubmissionSourceCapacityLimits(maximum_total_bytes=2000, maximum_project_bytes=150),
    SubmissionSourceCapacityLimits(maximum_total_bytes=2000, maximum_producer_bytes=150),
    SubmissionSourceCapacityLimits(maximum_total_bytes=2000, maximum_task_bytes=150),
], indirect=True)
async def test_each_enabled_source_quota_counts_failed_objects(intake):
    from app.modules.artifacts.intake.capacity import SubmissionSourceCapacityConflict

    async with intake.factory.begin() as session:
        row = await reserve(intake, session, declared_raw_bytes=100)
    async with intake.factory.begin() as session:
        await repository(session).terminalize(UUID(row.id), UUID(row.lease_id), 1,
                                             state="failed", failure_code="upload_uncertain")
    with pytest.raises(SubmissionSourceCapacityConflict, match="source_capacity_exhausted"):
        async with intake.factory.begin() as session:
            await reserve(intake, session, declared_raw_bytes=100)
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT sum(accounted_bytes) FROM submission_source_charges")) == 100
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 1


async def test_equal_content_sources_keep_distinct_physical_charges(intake):
    operations = []
    for _ in range(2):
        async with intake.factory.begin() as session:
            row = await reserve(intake, session, declared_raw_bytes=100)
            operation, lease = UUID(row.id), UUID(row.lease_id)
            operations.append(operation)
        async with intake.factory.begin() as session:
            await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        async with intake.factory.begin() as session:
            deadline = datetime.now(UTC) + timedelta(minutes=2)
            await repository(session).seal(operation, lease, 1, provider_generation=f"generation-{operation}",
                                           pre_deadline_at=deadline, lease_expires_at=deadline)
            await repository(session).terminalize(operation, lease, 1, state="rejected", failure_code="pre_failed")
    assert operations[0] != operations[1]
    async with intake.factory() as session:
        counts = (await session.execute(text(
            "SELECT count(*),sum(accounted_bytes) FROM submission_source_charges"
        ))).one()
        assert tuple(counts) == (2, 200)


@pytest.mark.parametrize("capacity_limits", [SubmissionSourceCapacityLimits(maximum_total_bytes=150)], indirect=True)
async def test_source_quota_serializes_distinct_tasks(intake):
    from app.modules.artifacts.intake.capacity import SubmissionSourceCapacityConflict

    async with intake.factory() as session:
        project = await session.scalar(text("SELECT project_id FROM workstream_tasks WHERE id=:id"), {"id": intake.task})
    other = SimpleNamespace(**{**vars(intake), "task": new_record_id(), "assignment": new_record_id()})
    async with intake.engine.begin() as connection:
        await seed_started_task_for_artifact_test(connection, dict(
            task=str(other.task), assignment=str(other.assignment), project=str(project), actor=str(intake.actor.actor_profile_id),
        ))
    async with intake.factory() as first, intake.factory() as second:
        await first.begin()
        await second.begin()
        await reserve(intake, first, declared_raw_bytes=100)
        pid = await second.scalar(text("SELECT pg_backend_pid()"))
        contender = asyncio.create_task(reserve(other, second, declared_raw_bytes=100))
        try:
            async with intake.factory() as observer:
                async with asyncio.timeout(10):
                    while not await observer.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))>0"), {"pid": pid}):
                        if contender.done():
                            await contender
                            pytest.fail("second task bypassed the shared capacity lock")
                        await asyncio.sleep(0.02)
                query = await observer.scalar(text("SELECT query FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid})
                assert "submission_source_capacity_profiles" in query
            await first.commit()
            with pytest.raises(SubmissionSourceCapacityConflict, match="source_capacity_exhausted"):
                await contender
        finally:
            if not contender.done():
                contender.cancel()
                await asyncio.gather(contender, return_exceptions=True)
            await first.rollback()
            await second.rollback()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT sum(accounted_bytes) FROM submission_source_charges")) == 100
        assert await session.scalar(text("SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"), {"id": other.task}) is None


@pytest.mark.parametrize("capacity_limits", [SubmissionSourceCapacityLimits(maximum_total_bytes=150)], indirect=True)
async def test_sql_cannot_bypass_source_quota(intake):
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge

    async with intake.factory.begin() as session:
        row = await reserve(intake, session, declared_raw_bytes=100)
        values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    async with intake.factory.begin() as session:
        await repository(session).terminalize(UUID(row.id), UUID(row.lease_id), 1,
                                             state="failed", failure_code="upload_uncertain")
    new_id = new_record_id()
    values.update(id=str(new_id), lease_id=str(new_record_id()), idempotency_key=str(new_record_id()),
                  object_ref=f"submission-source/v1/{new_id}/bundle.zip")
    with pytest.raises(DBAPIError, match="submission source capacity exhausted"):
        async with intake.factory.begin() as session:
            await session.execute(text("UPDATE workstream_tasks SET active_submission_operation_id=:op WHERE id=:task"),
                                  {"op": new_id, "task": intake.task})
            await session.execute(SubmissionIntakeOperation.__table__.insert().values(**values))
            await session.execute(SubmissionSourceCharge.__table__.insert().values(
                operation_id=str(new_id), declared_raw_bytes=100, reserved_bytes=100, accounted_bytes=100, state="reserved",
            ))


async def test_capacity_configuration_cannot_be_replaced_or_truncated(intake):
    from app.modules.artifacts.intake.capacity import SubmissionSourceCapacity, SubmissionSourceCapacityConflict
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation

    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
    for statement in (
        "UPDATE submission_source_capacity_profiles SET maximum_total_bytes=maximum_total_bytes+1",
        "DELETE FROM submission_source_capacity_profiles",
        "TRUNCATE submission_source_capacity_profiles",
    ):
        with pytest.raises(DBAPIError, match="capacity configuration is immutable"):
            async with intake.factory.begin() as session:
                await session.execute(text(statement))
    with pytest.raises(SubmissionSourceCapacityConflict, match="configuration_mismatch"):
        async with intake.factory.begin() as session:
            operation = await session.get(SubmissionIntakeOperation, row.id)
            await SubmissionSourceCapacity(session).reserve(
                operation, limits=SubmissionSourceCapacityLimits(maximum_total_bytes=2_000_000), declared_raw_bytes=None,
            )


@pytest.mark.parametrize("declared", [True, 0, -1, 1025])
async def test_invalid_declared_size_rolls_back_all_custody(intake, declared):
    from app.modules.artifacts.intake.capacity import SubmissionSourceCapacityConflict

    with pytest.raises(SubmissionSourceCapacityConflict, match="source_declared_size_invalid"):
        async with intake.factory.begin() as session:
            await reserve(intake, session, declared_raw_bytes=declared)
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 0
        assert await session.scalar(text("SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"), {"id": intake.task}) is None


def foreground_upload(intake, store):
    from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
    return ForegroundSourceUpload(intake.factory,
        lambda session: IntakeTaskCustody(session, task_submission_context_port(session)), store)


async def foreground_bytes():
    yield b"original source bytes"


def foreground_limits():
    """Explicit fixture limits, never approved production settings."""
    return dict(part_bytes=5 * 1024 * 1024, idle_timeout_seconds=20.0,
                pre_timeout_seconds=60.0, pre_lease_seconds=30.0)


@pytest.mark.parametrize("scenario", ["success", "lost_complete", "lost_begin", "cancel_part", "precondition",
                                     "fence_begin", "fence_part", "fence_complete", "foreign_source"])
async def test_foreground_upload_committed_boundaries_and_retained_uncertainty(intake, monkeypatch, scenario):
    from app.interfaces.artifacts import ArtifactIntegrityError, ArtifactPreconditionFailedError, ArtifactStoreUnavailableError
    from tests.artifact_store_helpers import initialize_local_store
    store = initialize_local_store(root=intake.durable_root, buffer_bytes=7)
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    seen, handles = [], []

    async def committed(stage):
        async with intake.factory.begin() as session:
            # Independent real locks prove SQL locks are not retained during I/O.
            for sql, parameters in (
                ("SELECT id FROM workstream_tasks WHERE id=:id FOR UPDATE NOWAIT", {"id": intake.task}),
                ("SELECT id FROM submission_intake_operations WHERE id=:id FOR UPDATE NOWAIT", {"id": operation}),
                ("SELECT namespace_id FROM submission_source_capacity_profiles WHERE namespace_id=:id FOR UPDATE NOWAIT", {"id": "primary"}),
            ):
                assert (await session.execute(text(sql), parameters)).one()
            stored = await session.get(SubmissionIntakeOperation, str(operation))
            receipt = await session.get(SubmissionSourceUploadReceipt, str(operation))
            assert receipt is not None and stored.state == "receiving"
            if stage == "begin":
                assert receipt.provider_upload_id is None and stored.raw_sha256 is None
            elif stage == "part":
                assert receipt.provider_upload_id and stored.raw_sha256 is None
            else:
                assert stored.raw_byte_count == len(b"original source bytes")
                assert receipt.completion_parts and receipt.completion_recorded_at is not None
        seen.append(stage)

    def checked(stage, original):
        async def call(*args, **kwargs):
            await committed(stage)
            if stage == "observe":
                assert scenario == "lost_complete", "unexpected source observation"
            result = await original(*args, **kwargs)
            if stage == "begin":
                handles.append(result)
            if scenario == "fence_" + stage:
                async with intake.factory.begin() as session:
                    await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="owner_ended")
            if (stage, scenario) in {("begin", "lost_begin"), ("complete", "lost_complete")}:
                raise ArtifactStoreUnavailableError("lost acknowledgement")
            if stage == "part" and scenario == "cancel_part":
                raise asyncio.CancelledError
            if stage == "complete" and scenario == "precondition":
                raise ArtifactPreconditionFailedError("conditional completion conflict")
            if stage == "complete" and scenario == "foreign_source":
                return result.model_copy(update={"location": result.location.model_copy(update={"operation_id": new_record_id()})})
            return result
        return call

    for stage, name in (("begin", "begin_source_upload"), ("part", "upload_source_part"),
                        ("complete", "complete_source_upload"), ("observe", "observe_source_upload")):
        monkeypatch.setattr(store, name, checked(stage, getattr(store, name)))
    failures = dict(lost_begin=ArtifactStoreUnavailableError, cancel_part=asyncio.CancelledError,
                    precondition=ArtifactPreconditionFailedError, foreign_source=ArtifactIntegrityError,
                    fence_begin=IntakeCustodyConflict, fence_part=IntakeCustodyConflict, fence_complete=IntakeCustodyConflict)
    try:
        command = foreground_upload(intake, store).receive(operation, lease, 1,
            foreground_bytes(), **foreground_limits())
        if scenario in failures:
            with pytest.raises(failures[scenario]):
                await command
        else:
            source = await command
            assert seen == ["begin", "part", "complete"] + (["observe"] if scenario == "lost_complete" else [])
            assert b"".join([chunk async for chunk in store.open_source(source)]) == b"original source bytes"
        async with intake.factory() as session:
            stored = await session.get(SubmissionIntakeOperation, str(operation))
            charge = (await session.execute(text(
                "SELECT state,accounted_bytes FROM submission_source_charges WHERE operation_id=:id"
            ), {"id": operation})).one()
            if scenario in failures:
                assert stored.provider_generation is None
                assert stored.state == ("failed" if scenario.startswith("fence_") else "receiving")
                assert charge == ("reserved", 1024)
            else:
                assert stored.state == "pre_checking" and stored.provider_generation == source.provider_generation
                assert stored.raw_sha256 == source.raw_sha256 and stored.sealed_upload_fence == 1
                assert charge == ("sealed", len(b"original source bytes"))
            if scenario in {"lost_begin", "cancel_part", "fence_begin", "fence_part"}:
                assert stored.raw_sha256 is None
        if scenario == "lost_begin":
            assert await store.discover_source_uploads(handles[0].intent) == tuple(handles)
    finally:
        store.close()


async def test_foreground_upload_rolled_back_reservation_cannot_start_provider(intake, monkeypatch):
    from tests.artifact_store_helpers import initialize_local_store
    store = initialize_local_store(root=intake.durable_root)
    async with intake.factory() as session:
        async with session.begin():
            row = await reserve(intake, session, with_upload=False)
            operation, lease = UUID(row.id), UUID(row.lease_id)
            await session.rollback()

    async def forbidden(*args, **kwargs):
        pytest.fail("provider called without committed T1")

    monkeypatch.setattr(store, "begin_source_upload", forbidden)
    try:
        with pytest.raises(IntakeCustodyConflict, match="unavailable"):
            await foreground_upload(intake, store).receive(operation, lease, 1,
                foreground_bytes(), **foreground_limits())
    finally:
        store.close()


def foreground_lease(intake, *, duration=2, interval=0.1):
    from app.modules.artifacts.intake.foreground_lease import ForegroundIntakeLease
    return ForegroundIntakeLease(intake.factory,
        lambda session: IntakeTaskCustody(session, task_submission_context_port(session)),
        lease_duration=timedelta(seconds=duration), heartbeat_interval=timedelta(seconds=interval))


async def test_foreground_lease_delayed_local_upload_and_longer_pre_lease(intake):
    from tests.artifact_store_helpers import initialize_local_store
    store = initialize_local_store(root=intake.durable_root, buffer_bytes=7)
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False, lease_seconds=2)
        operation, lease, initial_expiry = UUID(row.id), UUID(row.lease_id), row.lease_expires_at

    async def delayed_bytes():
        while True:
            async with intake.factory() as session:
                now = await session.scalar(text("SELECT clock_timestamp()"))
            if now > initial_expiry:
                break
            await asyncio.sleep(0.1)
        yield b"original source bytes"

    async def command(op, owner, generation):
        assert (op, owner, generation) == (operation, lease, 1)
        limits = dict(foreground_limits(), pre_lease_seconds=2.0)
        source = await foreground_upload(intake, store).receive(op, owner, generation,
            delayed_bytes(), **limits)
        async with intake.factory() as session:
            sealed = await session.get(SubmissionIntakeOperation, str(op))
            first_pre_expiry, pre_deadline = sealed.lease_expires_at, sealed.pre_deadline_at
        # Keep the same foreground command alive in PRE beyond its first PRE lease.
        while True:
            async with intake.factory() as session:
                now = await session.scalar(text("SELECT clock_timestamp()"))
                observed = await session.get(SubmissionIntakeOperation, str(op))
                assert observed.state == "pre_checking"
                assert (observed.lease_id, observed.lease_generation) == (str(owner), generation)
                assert observed.pre_deadline_at == pre_deadline
            if now > first_pre_expiry:
                assert now < observed.lease_expires_at <= pre_deadline
                break
            await asyncio.sleep(0.1)
        return source

    source = await foreground_lease(intake).run(operation, lease, 1, command)
    async with intake.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(operation))
        pre_expiry = row.lease_expires_at
        assert row.state == "pre_checking" and row.lease_generation == 1 and row.lease_id == str(lease)
        assert row.lease_expires_at > initial_expiry
        assert row.provider_generation == source.provider_generation
        await repository(session).heartbeat(operation, lease, 1, lease_duration=timedelta(milliseconds=10))
    async with intake.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(operation))
        assert row.lease_expires_at == pre_expiry


@pytest.mark.parametrize("invalid", ["lease", "generation", "terminal", "expired"])
async def test_foreground_lease_invalid_owner_never_invokes_callback(intake, invalid):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    if invalid == "terminal":
        async with intake.factory.begin() as session:
            await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="fixture_failed")
    if invalid == "expired":
        async with intake.factory.begin() as session:
            await session.execute(text("UPDATE submission_intake_operations SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": operation})
    called = False

    def command(*owner):
        nonlocal called
        called = True
        raise AssertionError("stale owner invoked command")

    with pytest.raises(IntakeCustodyConflict, match="owner_stale"):
        await foreground_lease(intake).run(operation, new_record_id() if invalid == "lease" else lease,
                                          2 if invalid == "generation" else 1, command)
    assert not called


@pytest.mark.parametrize("stop", ["caller", "fence", "deadline"])
async def test_foreground_lease_drains_local_write_and_retains_charge(intake, monkeypatch, stop):
    from app.core.cancellation import await_completion_preserving_cancellation
    from app.interfaces.artifacts import ArtifactStoreUnavailableError
    from tests.artifact_store_helpers import initialize_local_store
    store = initialize_local_store(root=intake.durable_root, buffer_bytes=7)
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False,
                            lease_seconds=2, upload_seconds=2 if stop == "deadline" else 60)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    started, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = store.upload_source_part
    writes = []

    async def held_part(*args, **kwargs):
        async def write():
            started.set()
            await release.wait()
            result = await original(*args, **kwargs)
            writes.append(result)
            return result
        try:
            return await await_completion_preserving_cancellation(write())
        finally:
            cancelled.set()

    monkeypatch.setattr(store, "upload_source_part", held_part)

    async def command(op, owner, generation):
        return await foreground_upload(intake, store).receive(op, owner, generation,
            foreground_bytes(), **foreground_limits())

    runner = asyncio.create_task(foreground_lease(intake).run(operation, lease, 1, command))
    try:
        await asyncio.wait_for(started.wait(), 5)
        if stop == "caller":
            runner.cancel()
            await asyncio.sleep(0.05)
            runner.cancel()
        elif stop == "fence":
            async with intake.factory.begin() as session:
                await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="fixture_fenced")
        else:
            await asyncio.sleep(2.1)
        await asyncio.sleep(0.3)
        assert not runner.done() and not cancelled.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError if stop == "caller" else (IntakeCustodyConflict, DBAPIError, ArtifactStoreUnavailableError)):
            await asyncio.wait_for(runner, 5)
        assert cancelled.is_set() and len(writes) == (0 if stop == "deadline" else 1)
        assert not [task for task in asyncio.all_tasks()
                    if task.get_name() in {f"submission-foreground:{operation}", f"submission-lease:{operation}"}]
        async with intake.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(operation))
            expiry = row.lease_expires_at
            assert expiry <= row.upload_deadline_at
            assert row.state == ("failed" if stop == "fence" else "receiving")
            assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges")) == 1024
        await asyncio.sleep(0.2)
        async with intake.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(operation))
            assert row.lease_expires_at == expiry and len(writes) == (0 if stop == "deadline" else 1)
    finally:
        release.set()
        if not runner.done():
            runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


async def test_foreground_lease_exhausted_commit_response_budget_does_not_start(intake):
    from contextlib import asynccontextmanager
    from app.modules.artifacts.intake.foreground_lease import ForegroundIntakeLease
    async with intake.factory.begin() as session:
        row = await reserve(intake, session, with_upload=False, lease_seconds=2)
        operation, lease = UUID(row.id), UUID(row.lease_id)

    class DelayedCommitResponse:
        @asynccontextmanager
        async def begin(self):
            async with intake.factory.begin() as session:
                yield session
            await asyncio.sleep(2.1)

    runner = ForegroundIntakeLease(DelayedCommitResponse(),
        lambda session: IntakeTaskCustody(session, task_submission_context_port(session)),
        lease_duration=timedelta(seconds=2), heartbeat_interval=timedelta(seconds=0.1))
    called = False

    def command(*owner):
        nonlocal called
        called = True
        raise AssertionError("expired commit budget invoked command")

    with pytest.raises(IntakeCustodyConflict, match="renewal_expired"):
        await runner.run(operation, lease, 1, command)
    assert not called


async def test_pre_source_custody_returns_exact_locked_facts(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        source = await repository(session).seal(
            operation, lease, 1, provider_generation="pre-source-generation",
            pre_deadline_at=deadline, lease_expires_at=deadline,
        )
    async with intake.factory.begin() as session:
        facts = await repository(session).lock_pre_source(source=source, lease_id=lease, generation=1)
        assert facts.source == source
        assert facts.task_id == intake.task and facts.assignment_id == intake.assignment
        assert facts.actor_profile_id == intake.actor.actor_profile_id
        assert facts.identity_link_id == intake.actor.identity_link_id
        assert facts.lease_id == lease and facts.lease_generation == 1
        assert facts.lease_expires_at == facts.pre_deadline_at == deadline
        assert facts.metadata_sha256 == row.metadata_sha256
        assert facts.locked_context_sha256 == row.locked_context_sha256


@pytest.mark.parametrize("changed", [
    "generation", "raw_sha", "raw_count", "namespace", "profile", "lease", "fence",
    "cleared_pointer", "foreign_pointer", "expired", "terminal", "unsealed",
])
async def test_pre_source_custody_rejects_substitution_or_stale_owner(intake, changed):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        if changed == "unsealed":
            from app.modules.artifacts.api.submission_intake import SealedSubmissionSource, SubmissionSourceLocation
            source = SealedSubmissionSource(
                location=SubmissionSourceLocation(
                    operation_id=operation, namespace_id=row.namespace_id,
                    namespace_fingerprint=row.namespace_fingerprint, provider_profile=row.provider_profile,
                ), provider_generation="pre-source-generation", raw_sha256=SHA,
                raw_byte_count=100, sealed_upload_fence=1,
            )
        else:
            source = await repository(session).seal(
                operation, lease, 1, provider_generation="pre-source-generation",
                pre_deadline_at=deadline, lease_expires_at=deadline,
            )
    values = source.model_dump(mode="python")
    if changed == "generation":
        values["provider_generation"] = "another-generation"
    elif changed == "raw_sha":
        values["raw_sha256"] = "sha256:" + "b" * 64
    elif changed == "raw_count":
        values["raw_byte_count"] += 1
    elif changed == "namespace":
        values["location"]["namespace_fingerprint"] = "sha256:" + "b" * 64
    elif changed == "profile":
        values["location"]["provider_profile"] = "unqualified-profile"
    supplied = type(source).model_validate(values)
    async with intake.factory() as session:
        await session.begin()
        try:
            if changed in {"cleared_pointer", "foreign_pointer"}:
                # Deferrable SQL constraints do not replace the in-root owner
                # check before another participant can consume custody.
                await session.execute(text(
                    "UPDATE workstream_tasks SET active_submission_operation_id=:active WHERE id=:task"
                ), {"active": None if changed == "cleared_pointer" else new_record_id(), "task": intake.task})
            elif changed == "expired":
                await session.execute(text(
                    "UPDATE submission_intake_operations SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"
                ), {"id": operation})
            elif changed == "terminal":
                await repository(session).terminalize(operation, lease, 1, state="rejected", failure_code="pre_failed")
            with pytest.raises((IntakeCustodyConflict, TaskSubmissionContextUnavailable)):
                await repository(session).lock_pre_source(
                    source=supplied, lease_id=new_record_id() if changed == "lease" else lease,
                    generation=2 if changed == "fence" else 1,
                )
        finally:
            await session.rollback()


@pytest.mark.parametrize("intake", [True], indirect=True)
@pytest.mark.parametrize("changed", [None, "source", "packet", "policy", "post_policy", "fence", "deadline", "actor", "rules", "predecessor", "predecessor_identity"])
async def test_selected_pre_sql_requires_exact_live_source(intake, changed):
    """Exercise the SQL source participant; not full PRE execution or T4 proof."""
    from dataclasses import replace
    from app.core.hashing import canonical_json_hash
    from app.modules.tasks.api.transition_audit import TaskPolicyLineage
    from app.modules.checkers.api.external_policy import LockedExternalCheckerPolicies
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
        await record_eof(session, operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
        deadline = datetime.now(UTC) + timedelta(minutes=2)
        source = await repository(session).seal(
            operation, lease, 1, provider_generation="pre-source-generation",
            pre_deadline_at=deadline, lease_expires_at=deadline,
        )
        from app.adapters.artifacts import submission_intake_pre_source_port
        guarded = await submission_intake_pre_source_port(session).lock_pre_source(
            source=source, lease_id=lease, generation=1,
        )
        assert guarded.source == source
        policy_body = await session.scalar(text("""
            SELECT a.effective_pre_submit_plan FROM project_guide_proposal_approvals a
            JOIN workstream_tasks t ON t.locked_pre_submit_checker_policy_id=a.pre_submit_policy_id
            WHERE t.id=:task
        """), {"task": intake.task})
        policies = LockedExternalCheckerPolicies.model_validate_json(json.dumps(policy_body))
        base = _source_reservation()
        locked = await session.scalar(text("""
            SELECT jsonb_build_object('task',to_jsonb(t),'guide_id',g.id)
            FROM workstream_tasks t JOIN project_guides g
              ON g.project_id=t.project_id AND g.version=t.locked_guide_version
            WHERE t.id=:task
        """), {"task": intake.task})
        task = locked["task"]
        locked_policy = TaskPolicyLineage.model_validate_json(json.dumps({
            key: task[key] for key in TaskPolicyLineage.model_fields
        }))
        rules = canonical_json_hash({
            "schema_version": "workstream.task_checker_rules.v1",
            "task_policy": locked_policy.model_dump(mode="json"),
            "external_checker_policies_sha256": policies.policies_sha256,
        })
        lineage = replace(
            base.admission_lineage, rules_sha256=rules, effective_plan_sha256=policies.pre_submit.policy_sha256,
            guide_id=UUID(locked["guide_id"]), guide_version=task["locked_guide_version"],
            source_snapshot_id=UUID(task["locked_guide_source_snapshot_id"]),
            source_snapshot_sha256=task["locked_guide_source_snapshot_hash"],
            effective_policy_id=UUID(task["locked_effective_project_submission_artifact_policy_id"]),
            effective_policy_sha256=task["locked_effective_project_submission_artifact_policy_hash"],
            pre_submit_policy_id=UUID(task["locked_pre_submit_checker_policy_id"]),
            pre_submit_policy_sha256=task["locked_pre_submit_checker_bundle_hash"],
            external_checker_policies_sha256=policies.policies_sha256,
            post_submit_policy_body=policies.post_submit.model_dump(mode="json"),
            post_submit_policy_sha256=policies.post_submit.policy_sha256,
        )
        request = replace(
            base, actor_profile_id=UUID(row.actor_profile_id), identity_link_id=UUID(row.identity_link_id),
            project_id=UUID(row.project_id), task_id=intake.task, assignment_id=intake.assignment,
            idempotency_key=UUID(row.idempotency_key), source=source,
            metadata_sha256=row.metadata_sha256, locked_context_sha256=row.locked_context_sha256,
            foreground_lease_id=lease, foreground_lease_generation=1, pre_deadline_at=deadline,
            policy=policies.pre_submit, admission_lineage=lineage,
            default_context=replace(base.default_context, current_rules_sha256=rules),
        )
        body = request.canonical_body()
        if changed == "source":
            body["source"]["provider_generation"] = "substituted"
            body["source_sha256"] = canonical_json_hash({
                "schema_version": "workstream.sealed_submission_source.v1", **body["source"],
            })
        elif changed == "packet":
            body["default_context"]["packet"]["summary"] = "substituted"
            body["admission_lineage"]["packet_sha256"] = canonical_json_hash(body["default_context"]["packet"])
        elif changed == "policy":
            body["policy"]["entries"] = []
        elif changed == "post_policy":
            body["admission_lineage"]["post_submit_policy_body"] = {}
        elif changed == "fence":
            body["foreground_lease_generation"] += 1
        elif changed == "deadline":
            body["pre_deadline_at"] = (deadline + timedelta(seconds=1)).isoformat()
        elif changed == "rules":
            body["default_context"]["current_rules_sha256"] = "sha256:" + "f" * 64
            body["admission_lineage"]["rules_sha256"] = "sha256:" + "f" * 64
        elif changed == "predecessor":
            body["default_context"]["predecessor_exists"] = True
        elif changed == "predecessor_identity":
            body["admission_lineage"]["predecessor_submission_id"] = str(new_record_id())
            body["admission_lineage"]["predecessor_submission_version"] = 1
            body["admission_lineage"]["checker_remediation_manifest_id"] = str(new_record_id())
        value = {
            "source_operation_id": str(operation), "task_id": str(intake.task),
            "project_id": row.project_id, "assignment_id": str(intake.assignment),
            "actor_profile_id": str(new_record_id()) if changed == "actor" else row.actor_profile_id,
            "identity_link_id": row.identity_link_id, "idempotency_key": row.idempotency_key,
            "request_json": body, "archive_sha256": source.raw_sha256,
            "archive_byte_count": source.raw_byte_count, "policy_sha256": request.policy_sha256,
        }
    async with intake.factory.begin() as session:
        statement = text("""SELECT public.require_selected_pre_source(
            jsonb_populate_record(NULL::public.selected_pre_submit_runs, CAST(:value AS jsonb)))""")
        if changed is None:
            await session.execute(statement, {"value": json.dumps(value)})
        else:
            with pytest.raises(DBAPIError, match="selected PRE"):
                await session.execute(statement, {"value": json.dumps(value)})
            await session.rollback()
    from app.modules.checkers.models import SelectedPreSubmitRun
    async with intake.factory.begin() as session:
        session.add(SelectedPreSubmitRun(
            id=str(request.attempt_id), source_operation_id=str(operation),
            actor_profile_id=value["actor_profile_id"], identity_link_id=row.identity_link_id,
            project_id=row.project_id, task_id=str(intake.task), assignment_id=str(intake.assignment),
            idempotency_key=row.idempotency_key, request_json=body,
            request_digest=canonical_json_hash(body), policy_sha256=request.policy_sha256,
            default_behavior_sha256=request.default_behavior_sha256,
            archive_sha256=source.raw_sha256, archive_byte_count=source.raw_byte_count,
            execution_budget_ms=request.execution_budget_ms, status="queued", lease_generation=0,
        ))
        if changed is None:
            await session.flush()
        else:
            with pytest.raises(DBAPIError, match="selected PRE"):
                await session.flush()
            await session.rollback()
    if changed is None:
        await _assert_pre_terminal_guards(intake, request)


@pytest.mark.parametrize("version", ["v1", "v2"])
async def test_selected_pre_sql_audit_digest_keeps_versioned_custody(isolated_database_env, version):
    from app.core.hashing import canonical_json_hash
    from tests.checkers.external.test_selected_pre_submit_coordination import _retained_v1, _source_reservation

    retained = _retained_v1()
    request = retained["request"] if version == "v1" else _source_reservation().canonical_body()
    terminal = retained["terminal"]
    execute = {
        "schema_version": f"workstream.selected_pre_submit_execute.{version}",
        "reservation": request, "lease_id": terminal["lease_id"],
        "lease_generation": terminal["lease_generation"], "lease_expires_at": terminal["lease_expires_at"],
    }
    expected_execute = canonical_json_hash(execute)
    expected_finalize = canonical_json_hash({
        "schema_version": f"workstream.selected_pre_submit_finalize.{version}",
        "execute_facts_digest": expected_execute,
        "execution": terminal["execution"],
        "infrastructure_failure_code": terminal["infrastructure_failure_code"],
    })
    value = {
        "request_json": request, "lease_id": execute["lease_id"],
        "lease_generation": execute["lease_generation"], "lease_expires_at": execute["lease_expires_at"],
        "terminal_json": terminal,
    }
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            for phase, expected in (("execute", expected_execute), ("finalize", expected_finalize)):
                actual = await connection.scalar(text("""SELECT public.selected_pre_submit_facts_digest(
                    jsonb_populate_record(NULL::public.selected_pre_submit_runs, CAST(:value AS jsonb)),
                    :phase)"""), {"value": json.dumps(value), "phase": phase})
                assert actual == expected
    finally:
        await engine.dispose()


async def _assert_pre_terminal_guards(intake, request):
    """Claim with real AUTH, reject rebound terminal updates, then finalize once."""
    from app.adapters.auth import selected_pre_submit_authority
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.core.hashing import canonical_json_hash
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitFinalizeFacts, SelectedPreSubmitTerminalFacts
    from app.modules.checkers.models import SelectedPreSubmitRun

    async with intake.factory.begin() as session:
        async with selected_pre_submit_authority(session).prepare_execution(request) as authority:
            lease = await selected_pre_submit_coordinator(session).claim(
                run_id=request.attempt_id, facts=request, authority=authority,
            )
    finalize = SelectedPreSubmitFinalizeFacts(
        lease=lease, execution=None, infrastructure_failure_code="capacity_exceeded",
    )
    for changed in ("lease_id", "lease_expires_at", "started_at", "execute_evidence_id",
                    "schema_version", "reservation", "request_digest", "outcome", "terminal_digest", "extra"):
        async with intake.factory.begin() as session:
            async with selected_pre_submit_authority(session).prepare_finalization(finalize) as authority:
                evidence = await authority.consume(finalize)
                row = await session.get(SelectedPreSubmitRun, str(request.attempt_id))
                now = await session.scalar(text("select clock_timestamp()"))
                terminal = SelectedPreSubmitTerminalFacts(
                    lease=lease, outcome="infrastructure_failed", execution=None,
                    infrastructure_failure_code="capacity_exceeded", queued_at=row.queued_at,
                    started_at=row.started_at, completed_at=now,
                ).canonical_body()
                values = dict(
                    id=request.attempt_id, lease_id=lease.lease_id,
                    lease_expires_at=lease.lease_expires_at, started_at=row.started_at,
                    execute_evidence_id=UUID(row.execute_evidence_id), completed_at=now,
                    finalize_evidence_id=evidence.evidence_id,
                )
                claim_change = changed in {"lease_id", "lease_expires_at", "started_at", "execute_evidence_id"}
                if changed in {"lease_id", "execute_evidence_id"}:
                    values[changed] = new_record_id()
                    if changed == "lease_id":
                        terminal[changed] = str(values[changed])
                elif changed in {"lease_expires_at", "started_at"}:
                    values[changed] -= timedelta(microseconds=1)
                    terminal[changed] = values[changed].isoformat()
                elif changed == "schema_version":
                    terminal[changed] = "workstream.selected_pre_submit_terminal.v1"
                elif changed == "reservation":
                    terminal[changed] = terminal[changed] | {"metadata_sha256": "sha256:" + "f" * 64}
                elif changed == "request_digest":
                    terminal[changed] = "sha256:" + "f" * 64
                elif changed == "outcome":
                    terminal[changed] = "completed"
                elif changed == "extra":
                    terminal["unexpected"] = True
                values["terminal_json"] = json.dumps(terminal)
                values["terminal_digest"] = ("sha256:" + "f" * 64 if changed == "terminal_digest"
                                             else canonical_json_hash(terminal))
                message = "committed claim is immutable" if claim_change else "terminal binding mismatch"
                with pytest.raises(DBAPIError, match=message):
                    await session.execute(text("""UPDATE selected_pre_submit_runs SET
                        status='infrastructure_failed', lease_id=:lease_id, lease_expires_at=:lease_expires_at,
                        started_at=:started_at, execute_evidence_id=:execute_evidence_id,
                        completed_at=:completed_at, finalize_evidence_id=:finalize_evidence_id,
                        terminal_json=CAST(:terminal_json AS jsonb), terminal_digest=:terminal_digest
                        WHERE id=:id"""), values)
                await session.rollback()
    async with intake.factory.begin() as session:
        async with selected_pre_submit_authority(session).prepare_finalization(finalize) as authority:
            completion = await selected_pre_submit_coordinator(session).finalize(
                run_id=request.attempt_id, lease=lease, authority=authority,
                execution=None, infrastructure_failure_code="capacity_exceeded",
            )
            assert completion.terminal.outcome == "infrastructure_failed"
            assert completion.capability is None
