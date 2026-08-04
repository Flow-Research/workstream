"""Focused PostgreSQL proof for the hidden REV queue foundation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.checkers.models import CheckerRun
from app.modules.reviews.models import (
    ReviewAdmissionIdempotencyRecord,
    ReviewQueueEntry,
)
from app.modules.reviews.repository import (
    ReviewAdmissionIdempotencyConflict,
    ReviewQueueRepository,
)
from app.modules.reviews.schemas import (
    ReviewAdmissionReservationInput,
    ReviewQueueEntryInput,
    ReviewRoutingMode,
    ReviewRoutingReason,
)
from app.modules.tasks.models import Submission
from project_create_fixtures import grant_system_project_manager, insert_historical_project
from tests.test_checkers import get_submission_and_automatic_pre_review_run
from tests.test_tasks import (
    auth_headers,
    complete_submission_payload,
    create_active_project,
    create_started_task,
    set_dev_actor,
)


@pytest.fixture
def review_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    """Bind one test to the runner-owned migrated PostgreSQL database."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def review_client(review_database_env: str) -> AsyncIterator[AsyncClient]:
    """Return an API client used only to create canonical upstream test facts."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        admission = await client.get("/api/v1/auth/me", headers=auth_headers())
        assert admission.status_code == 200, admission.text
        async with db_session.get_session_factory()() as session:
            await grant_system_project_manager(
                session,
                issuer="flow-test",
                subject="project-manager-subject",
            )
            await session.commit()
        yield client


async def _reviewable_lineage(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict, dict, dict]:
    project = await create_active_project(client)
    task = await create_started_task(
        client,
        project["id"],
        monkeypatch,
        subject="review-worker-two",
    )
    submission_response = await client.post(
        f"/api/v1/tasks/{task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert submission_response.status_code == 201, submission_response.text
    submission = submission_response.json()
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, checker = await get_submission_and_automatic_pre_review_run(client, submission["id"])
    assert checker["status"] == "completed"
    assert checker["routing_recommendation"] == "allow_review"
    return project, task, submission | {"checker_run_id": checker["id"]}


async def _additional_reviewable_submission(
    client: AsyncClient,
    project: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict, dict]:
    """Create another exact task/submission/checker lineage in one project."""
    task = await create_started_task(client, project["id"], monkeypatch)
    submission_response = await client.post(
        f"/api/v1/tasks/{task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert submission_response.status_code == 201, submission_response.text
    submission = submission_response.json()
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, checker = await get_submission_and_automatic_pre_review_run(client, submission["id"])
    assert checker["status"] == "completed"
    assert checker["routing_recommendation"] == "allow_review"
    return task, submission | {"checker_run_id": checker["id"]}


def _queue_input(project: dict, task: dict, submission: dict) -> ReviewQueueEntryInput:
    return ReviewQueueEntryInput(
        id=uuid4(),
        project_id=project["id"],
        task_id=task["id"],
        submission_id=submission["id"],
        submission_version=submission["version"],
        admitting_checker_run_id=submission["checker_run_id"],
        routing_mode=ReviewRoutingMode.OPEN,
        routing_reason=ReviewRoutingReason.FIRST_SUBMISSION,
    )


def _reservation_input(
    project: dict,
    task: dict,
    submission: dict,
) -> ReviewAdmissionReservationInput:
    return ReviewAdmissionReservationInput(
        id=uuid4(),
        idempotency_key=uuid4(),
        operation_id=uuid4(),
        request_digest="sha256:" + "a" * 64,
        project_id=project["id"],
        task_id=task["id"],
        submission_id=submission["id"],
        submission_version=submission["version"],
        admitting_checker_run_id=submission["checker_run_id"],
    )


def test_review_models_are_registered_without_routes() -> None:
    """Alembic sees the tables while the application exposes no REV router."""
    assert "review_queue_entries" in Base.metadata.tables
    assert "review_admission_idempotency_records" in Base.metadata.tables
    assert "active_lease_id" not in Base.metadata.tables["review_queue_entries"].columns
    assert "review_lease_id" not in Base.metadata.tables["review_queue_entries"].columns
    assert {
        "queue_state",
        "closed_at",
        "closed_reason",
    }.isdisjoint(ReviewQueueEntryInput.model_fields)
    route_paths = {getattr(route, "path", None) for route in create_app().routes}
    assert not any(path and path.startswith("/api/v1/reviews") for path in route_paths)


@pytest.mark.asyncio
async def test_repository_reserves_and_commits_exact_queue_identity(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    queue_input = _queue_input(project, task, submission)
    reservation_input = _reservation_input(project, task, submission)

    async with db_session.get_session_factory()() as session:
        repository = ReviewQueueRepository(session)
        reservation = await repository.reserve_admission(reservation_input)
        assert reservation.created is True
        assert reservation.record.status == "pending"
        queue = await repository.add_queue_entry(queue_input)
        committed = await repository.commit_admission(
            reservation_id=reservation.record.id,
            queue_entry_id=queue.id,
        )
        assert committed.status == "committed"
        await session.commit()

    async with db_session.get_session_factory()() as session:
        queue = await session.get(ReviewQueueEntry, queue_input.id)
        admission = await session.get(ReviewAdmissionIdempotencyRecord, reservation_input.id)
        assert queue is not None
        assert queue.queue_state == "pending"
        assert queue.routing_generation == queue.lifecycle_generation == 1
        assert admission is not None
        assert admission.review_queue_entry_id == queue_input.id


@pytest.mark.asyncio
async def test_repository_exact_replay_and_conflict(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    value = _reservation_input(project, task, submission)
    async with db_session.get_session_factory()() as session:
        repository = ReviewQueueRepository(session)
        first = await repository.reserve_admission(value)
        replay = await repository.reserve_admission(value.model_copy(update={"id": uuid4()}))
        assert first.created is True
        assert replay.created is False
        assert replay.record.id == first.record.id
        conflict = value.model_copy(update={"request_digest": "sha256:" + "b" * 64})
        with pytest.raises(ReviewAdmissionIdempotencyConflict):
            await repository.reserve_admission(conflict)
        await session.rollback()


@pytest.mark.asyncio
async def test_database_rejects_invalid_admission_state_and_commit(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    reservation_value = _reservation_input(project, task, submission)
    async with db_session.get_session_factory()() as session:
        invalid_digest = ReviewAdmissionIdempotencyRecord(
            **reservation_value.model_dump(exclude={"request_digest"}),
            request_digest="not-a-sha256-digest",
        )
        session.add(invalid_digest)
        with pytest.raises(IntegrityError, match="request_digest"):
            await session.flush()
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        invalid_committed = ReviewAdmissionIdempotencyRecord(
            **reservation_value.model_copy(update={"id": uuid4()}).model_dump(),
            status="committed",
            committed_at=datetime.now(UTC),
        )
        session.add(invalid_committed)
        with pytest.raises(DBAPIError, match="review admission must begin pending"):
            await session.flush()
        await session.rollback()

    queue_value = _queue_input(project, task, submission)
    async with db_session.get_session_factory()() as session:
        repository = ReviewQueueRepository(session)
        reservation = await repository.reserve_admission(reservation_value)
        queue = await repository.add_queue_entry(queue_value)
        checker = await session.get(CheckerRun, submission["checker_run_id"])
        assert checker is not None
        checker.is_current_for_submission = False
        await session.flush()
        with pytest.raises(DBAPIError, match="review admission checker is not admissible"):
            await repository.commit_admission(
                reservation_id=reservation.record.id,
                queue_entry_id=queue.id,
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_database_enforces_admission_replay_and_queue_identity_constraints(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    other_task, other_submission = await _additional_reviewable_submission(
        review_client, project, monkeypatch
    )
    base = _reservation_input(project, task, submission)
    other = _reservation_input(project, other_task, other_submission)
    async with db_session.get_session_factory()() as session:
        session.add(ReviewAdmissionIdempotencyRecord(**base.model_dump()))
        await session.commit()

    pending_lineage_failures = (
        (
            base.model_copy(
                update={
                    "id": uuid4(),
                    "idempotency_key": uuid4(),
                    "operation_id": uuid4(),
                    "project_id": str(uuid4()),
                }
            ),
            "review admission task project mismatch",
        ),
        (
            base.model_copy(
                update={
                    "id": uuid4(),
                    "idempotency_key": uuid4(),
                    "operation_id": uuid4(),
                    "admitting_checker_run_id": other_submission["checker_run_id"],
                }
            ),
            "review admission checker lineage mismatch",
        ),
    )
    for invalid_lineage, error_message in pending_lineage_failures:
        async with db_session.get_session_factory()() as session:
            session.add(ReviewAdmissionIdempotencyRecord(**invalid_lineage.model_dump()))
            with pytest.raises(DBAPIError, match=error_message):
                await session.flush()
            await session.rollback()

    duplicates = (
        (
            other.model_copy(update={"id": uuid4(), "idempotency_key": base.idempotency_key}),
            "uq_review_admission_replay_key",
        ),
        (
            other.model_copy(update={"id": uuid4(), "operation_id": base.operation_id}),
            "uq_review_admission_operation",
        ),
        (
            base.model_copy(
                update={"id": uuid4(), "idempotency_key": uuid4(), "operation_id": uuid4()}
            ),
            "uq_review_admission_checker_run",
        ),
    )
    for duplicate, constraint_name in duplicates:
        async with db_session.get_session_factory()() as session:
            session.add(ReviewAdmissionIdempotencyRecord(**duplicate.model_dump()))
            with pytest.raises(IntegrityError, match=constraint_name):
                await session.flush()
            await session.rollback()

    base_queue = _queue_input(project, task, submission)
    other_queue = _queue_input(project, other_task, other_submission)
    async with db_session.get_session_factory()() as session:
        repository = ReviewQueueRepository(session)
        await repository.add_queue_entry(base_queue)
        await repository.add_queue_entry(other_queue)
        await session.commit()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="fk_review_admission_committed_queue"):
            await session.execute(
                text(
                    "update review_admission_idempotency_records "
                    "set status='committed', review_queue_entry_id=:queue_id, "
                    "committed_at=statement_timestamp() where id=:id"
                ),
                {"queue_id": other_queue.id, "id": base.id},
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_database_rejects_non_admissible_checker_and_project_mismatch(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    for field, invalid_value in (
        ("status", "running"),
        ("routing_recommendation", "needs_revision"),
        ("is_current_for_submission", False),
    ):
        async with db_session.get_session_factory()() as session:
            checker = await session.get(CheckerRun, submission["checker_run_id"])
            assert checker is not None
            setattr(checker, field, invalid_value)
            await session.flush()
            session.add(
                ReviewQueueEntry(
                    **_queue_input(project, task, submission)
                    .model_copy(update={"id": uuid4()})
                    .model_dump()
                )
            )
            with pytest.raises(DBAPIError, match="review queue checker is not admissible"):
                await session.flush()
            await session.rollback()

    other_task, other_submission = await _additional_reviewable_submission(
        review_client, project, monkeypatch
    )
    task_mismatch = _queue_input(project, task, submission).model_copy(
        update={"id": uuid4(), "task_id": other_task["id"]}
    )
    async with db_session.get_session_factory()() as session:
        session.add(ReviewQueueEntry(**task_mismatch.model_dump()))
        with pytest.raises(DBAPIError, match="review queue checker lineage mismatch"):
            await session.flush()
        await session.rollback()

    checker_mismatch = _queue_input(project, task, submission).model_copy(
        update={
            "id": uuid4(),
            "admitting_checker_run_id": other_submission["checker_run_id"],
        }
    )
    async with db_session.get_session_factory()() as session:
        session.add(ReviewQueueEntry(**checker_mismatch.model_dump()))
        with pytest.raises(DBAPIError, match="review queue checker lineage mismatch"):
            await session.flush()
        await session.rollback()

    other_project_id = str(uuid4())
    async with db_session.get_session_factory()() as session:
        await insert_historical_project(
            session,
            project_id=other_project_id,
            name="Other review project",
            slug=f"other-review-{other_project_id[:8]}",
        )
        await session.commit()
    mismatched = _queue_input(project, task, submission).model_copy(
        update={"id": uuid4(), "project_id": other_project_id}
    )
    async with db_session.get_session_factory()() as session:
        session.add(ReviewQueueEntry(**mismatched.model_dump()))
        with pytest.raises(DBAPIError, match="review queue task project mismatch"):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_database_enforces_routing_uniqueness_and_immutable_lineage(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    value = _queue_input(project, task, submission)
    async with db_session.get_session_factory()() as session:
        queue = ReviewQueueEntry(**value.model_dump())
        session.add(queue)
        await session.commit()

    async with db_session.get_session_factory()() as session:
        duplicate = ReviewQueueEntry(**value.model_copy(update={"id": uuid4()}).model_dump())
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        await session.execute(
            text("update review_queue_entries set routing_generation=2 where id=:id"),
            {"id": value.id},
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="review queue generations cannot decrease"):
            await session.execute(
                text("update review_queue_entries set routing_generation=1 where id=:id"),
                {"id": value.id},
            )
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        await session.execute(
            text("update review_queue_entries set lifecycle_generation=2 where id=:id"),
            {"id": value.id},
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="review queue generations cannot decrease"):
            await session.execute(
                text("update review_queue_entries set lifecycle_generation=1 where id=:id"),
                {"id": value.id},
            )
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        await session.execute(
            text(
                "update review_queue_entries set queue_state='closed', "
                "closed_at=statement_timestamp(), closed_reason='admin_cancelled', "
                "lifecycle_generation=2 where id=:id"
            ),
            {"id": value.id},
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="closed review queue entries cannot reopen"):
            await session.execute(
                text(
                    "update review_queue_entries set queue_state='pending', "
                    "closed_at=null, closed_reason=null, lifecycle_generation=3 where id=:id"
                ),
                {"id": value.id},
            )
        await session.rollback()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="review queue identity is immutable"):
            await session.execute(
                text(
                    "update review_queue_entries set first_queued_at=:changed where id=:id"
                ),
                {"changed": datetime.now(UTC) + timedelta(seconds=5), "id": value.id},
            )
        await session.rollback()
        with pytest.raises(DBAPIError, match="review queue identity is immutable"):
            await session.execute(
                text("update review_queue_entries set project_id=:changed where id=:id"),
                {"changed": str(uuid4()), "id": value.id},
            )
        await session.rollback()
        with pytest.raises(DBAPIError, match="review queue entries cannot be deleted"):
            await session.execute(
                text("delete from review_queue_entries where id=:id"),
                {"id": value.id},
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_preferred_shape_is_storage_only_and_lease_shape_is_impossible(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        contributor_id = await session.scalar(
            select(Submission.contributor_id).where(Submission.id == submission["id"])
        )
        assert contributor_id is not None
        preferred = _queue_input(project, task, submission).model_copy(
            update={
                "routing_mode": ReviewRoutingMode.PREFERRED,
                "routing_reason": ReviewRoutingReason.REVISION_RETURN,
                "preferred_reviewer_id": contributor_id,
                "preference_expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        )
        await ReviewQueueRepository(session).add_queue_entry(preferred)
        await session.commit()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            IntegrityError,
            match=r"ck_review_queue_entries_(queue_state|lifecycle_shape)",
        ):
            await session.execute(
                text("update review_queue_entries set queue_state='leased' where id=:id"),
                {"id": preferred.id},
            )
        await session.rollback()


@pytest.mark.postgres_schema_contract
@pytest.mark.asyncio
async def test_later_authority_preserves_populated_review_admission_on_downgrade(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    migration_lock,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    reservation_value = _reservation_input(project, task, submission)
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).reserve_admission(reservation_value)
        await session.commit()
    await db_session.dispose_engine()

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    def downgrade() -> None:
        with migration_lock():
            command.downgrade(config, "0050_guide_source_v2")

    with pytest.raises(RuntimeError, match="cannot downgrade guide sufficiency authority"):
        await asyncio.to_thread(downgrade)

    async with db_session.get_session_factory()() as session:
        assert await session.scalar(text("select version_num from alembic_version")) == (
            "0053_guide_sufficiency_authority"
        )
        assert await session.scalar(
            select(ReviewAdmissionIdempotencyRecord.id).where(
                ReviewAdmissionIdempotencyRecord.id == reservation_value.id
            )
        ) == reservation_value.id


@pytest.mark.postgres_schema_contract
@pytest.mark.asyncio
async def test_later_authority_preserves_populated_review_queue_on_downgrade(
    review_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    migration_lock,
) -> None:
    project, task, submission = await _reviewable_lineage(review_client, monkeypatch)
    queue_value = _queue_input(project, task, submission)
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).add_queue_entry(queue_value)
        await session.commit()
    await db_session.dispose_engine()

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    def downgrade() -> None:
        with migration_lock():
            command.downgrade(config, "0050_guide_source_v2")

    with pytest.raises(RuntimeError, match="cannot downgrade guide sufficiency authority"):
        await asyncio.to_thread(downgrade)

    async with db_session.get_session_factory()() as session:
        assert await session.scalar(text("select version_num from alembic_version")) == (
            "0053_guide_sufficiency_authority"
        )
        assert await session.get(ReviewQueueEntry, queue_value.id) is not None
