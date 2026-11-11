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
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
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
async def intake(tmp_path, isolated_database_env):
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
        yield SimpleNamespace(engine=engine, factory=factory, actor=actor, task=task, assignment=assignment)
    finally:
        await engine.dispose()


async def reserve(intake, session, *, key=None):
    now = datetime.now(UTC)
    return await repository(session).reserve(
        metadata=SubmissionIntakeMetadata(task_id=intake.task, assignment_id=intake.assignment),
        actor_id=intake.actor.actor_profile_id, identity_link_id=intake.actor.identity_link_id,
        idempotency_key=key or new_record_id(), maximum_raw_bytes=1024,
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
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation

    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            def compare(sync):
                inspector = inspect(sync)
                table = SubmissionIntakeOperation.__table__
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
