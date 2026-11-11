"""Real PostgreSQL proof of pre-handoff custody, not upload or acceptance authority."""

import asyncio

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata, SubmissionSourceCapacityLimits
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
async def intake(tmp_path, isolated_database_env, capacity_limits):
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        plan, _ = await approved_selected_policy_fixture(
            factory, _namespace(_settings(tmp_path)), guide_version="v1",
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
                              capacity_limits=capacity_limits)
    finally:
        await engine.dispose()


async def reserve(intake, session, *, key=None, declared_raw_bytes=None):
    now = datetime.now(UTC)
    return await repository(session).reserve(
        metadata=SubmissionIntakeMetadata(task_id=intake.task, assignment_id=intake.assignment),
        actor_id=intake.actor.actor_profile_id, identity_link_id=intake.actor.identity_link_id,
        idempotency_key=key or new_record_id(), maximum_raw_bytes=1024,
        capacity_limits=intake.capacity_limits, declared_raw_bytes=declared_raw_bytes,
        upload_deadline_at=now + timedelta(minutes=5),
        lease_expires_at=now + timedelta(minutes=1),
    )


async def test_foreground_eof_seal_terminal_and_stale_fence(intake):
    async with intake.factory.begin() as session:
        row = await reserve(intake, session)
        operation, lease = UUID(row.id), UUID(row.lease_id)
    async with intake.factory.begin() as session:
        await repository(session).record_eof(operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
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
            await repository(session).heartbeat(operation, lease, 1, lease_expires_at=deadline)


async def test_reservation_rollback_leaves_no_pointer_or_operation(intake):
    async with intake.factory() as session:
        await session.begin()
        await reserve(intake, session)
        await session.rollback()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations")) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges")) == 0
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
            await repository(session).record_eof(operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
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
        await repository(session).record_eof(operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
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
                for owner in (SubmissionIntakeOperation, SubmissionSourceCapacityProfile, SubmissionSourceCharge):
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
        await repository(session).record_eof(operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
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
            await repository(session).record_eof(operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
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
            await repository(session).record_eof(operation, lease, 1, raw_sha256=SHA, raw_byte_count=100)
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
