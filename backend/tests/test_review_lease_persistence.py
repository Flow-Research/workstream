"""Focused PostgreSQL proof for hidden ReviewLease persistence."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.contributions.models import (
    ContributionPolicy,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.reviews.models import ReviewLease, ReviewQueueEntry
from app.modules.reviews.repository import ReviewQueueRepository
from app.modules.reviews.schemas import ReviewLeaseInput
from project_create_fixtures import grant_system_project_manager
from tests.test_review_queue_persistence import (
    _additional_reviewable_submission,
    _queue_input,
    _reviewable_lineage,
)
from tests.test_tasks import auth_headers, set_dev_actor


@pytest.fixture
def review_lease_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    """Bind lease tests to one runner-owned migrated PostgreSQL database."""
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
async def review_lease_client(
    review_lease_database_env: str,
) -> AsyncIterator[AsyncClient]:
    """Create only canonical upstream facts through existing test helpers."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/auth/me", headers=auth_headers())
        assert response.status_code == 200, response.text
        async with db_session.get_session_factory()() as session:
            await grant_system_project_manager(
                session,
                issuer="flow-test",
                subject="project-manager-subject",
            )
            await session.commit()
        yield client


async def _human_actor(session, *, label: str) -> str:
    actor_id = str(uuid4())
    session.add(
        ActorProfile(
            id=actor_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by=actor_id,
        )
    )
    await session.flush()
    session.add(
        ActorIdentityLink(
            id=str(uuid4()),
            actor_profile_id=actor_id,
            issuer="https://review-lease.test",
            subject=f"{label}-{actor_id}",
            subject_kind="human",
            status="active",
            linked_by=actor_id,
            last_verified_at=datetime.now(UTC),
        )
    )
    return actor_id


async def _service_actor(session) -> str:
    actor_id = str(uuid4())
    session.add(
        ActorProfile(
            id=actor_id,
            actor_kind="service",
            status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.REVIEW_LEASE_EXPIRY.value,
            created_by="workstream:test",
        )
    )
    await session.flush()
    session.add(
        ActorIdentityLink(
            id=str(uuid4()),
            actor_profile_id=actor_id,
            issuer="https://review-lease.test",
            subject=f"service-{actor_id}",
            subject_kind="service",
            status="active",
            linked_by="workstream:test",
        )
    )
    await session.flush()
    return actor_id


async def _published_reviewer_policy(session, project_id: str, actor_id: str) -> UUID:
    policy_id = uuid4()
    version_id = uuid4()
    policy = ContributionPolicy(
        id=policy_id,
        project_id=project_id,
        name=f"Reviewer policy {policy_id}",
        status="draft",
        created_by=actor_id,
    )
    version = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=project_id,
        version_number=1,
        status="draft",
        created_by=actor_id,
    )
    session.add_all([policy, version])
    await session.flush()
    session.add_all(
        [
            ContributionRule(
                id=uuid4(),
                contribution_policy_version_id=version_id,
                project_id=project_id,
                contribution_type=kind,
                compensation_mode="unpaid",
            )
            for kind in ("accepted_submission", "completed_review")
        ]
    )
    await session.flush()
    await session.execute(
        update(ContributionPolicyVersion)
        .where(ContributionPolicyVersion.id == version_id)
        .values(
            status="published",
            published_by=actor_id,
            published_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return version_id


async def _draft_reviewer_policy(session, project_id: str, actor_id: str) -> UUID:
    policy_id = uuid4()
    version_id = uuid4()
    session.add_all(
        [
            ContributionPolicy(
                id=policy_id,
                project_id=project_id,
                name=f"Draft reviewer policy {policy_id}",
                status="draft",
                created_by=actor_id,
            ),
            ContributionPolicyVersion(
                id=version_id,
                contribution_policy_id=policy_id,
                project_id=project_id,
                version_number=1,
                status="draft",
                created_by=actor_id,
            ),
        ]
    )
    await session.flush()
    return version_id


def _lease_input(
    queue: ReviewQueueEntry,
    reviewer_id: str,
    policy_version_id: UUID,
    *,
    generation: int = 1,
) -> ReviewLeaseInput:
    return ReviewLeaseInput(
        id=uuid4(),
        review_queue_entry_id=queue.id,
        project_id=queue.project_id,
        task_id=queue.task_id,
        submission_id=queue.submission_id,
        submission_version=queue.submission_version,
        reviewer_id=reviewer_id,
        reviewer_contribution_policy_version_id=policy_version_id,
        attempt_generation=generation,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )


async def _seed_queue_and_policy(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict, ReviewQueueEntry, str, UUID]:
    project, task, submission = await _reviewable_lineage(client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        queue = await ReviewQueueRepository(session).add_queue_entry(
            _queue_input(project, task, submission)
        )
        reviewer_id = await _human_actor(session, label="reviewer")
        version_id = await _published_reviewer_policy(session, project["id"], reviewer_id)
        await session.commit()
        return project, queue, reviewer_id, version_id


async def _add_second_queue(
    client: AsyncClient,
    project: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> ReviewQueueEntry:
    task, submission = await _additional_reviewable_submission(client, project, monkeypatch)
    async with db_session.get_session_factory()() as session:
        queue = await ReviewQueueRepository(session).add_queue_entry(
            _queue_input(project, task, submission)
        )
        await session.commit()
        return queue


def test_review_lease_metadata_is_hidden_and_exact() -> None:
    assert "review_leases" in Base.metadata.tables
    assert "active_lease_id" in Base.metadata.tables["review_queue_entries"].columns
    assert set(ReviewLeaseInput.model_fields) == {
        "id",
        "review_queue_entry_id",
        "project_id",
        "task_id",
        "submission_id",
        "submission_version",
        "reviewer_id",
        "reviewer_contribution_policy_version_id",
        "attempt_generation",
        "expires_at",
    }
    assert not any(
        getattr(route, "path", "").startswith("/api/v1/reviews")
        for route in create_app().routes
    )


@pytest.mark.asyncio
async def test_repository_flushes_exact_active_lease_without_committing(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    value = _lease_input(queue, reviewer_id, version_id)
    async with db_session.get_session_factory()() as session:
        lease = await ReviewQueueRepository(session).add_lease(value)
        await session.execute(
            update(ReviewQueueEntry)
            .where(ReviewQueueEntry.id == queue.id)
            .values(queue_state="leased", active_lease_id=lease.id, lifecycle_generation=2)
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        stored = await session.get(ReviewLease, value.id)
        assert stored is not None
        assert stored.status == "active"
        assert stored.claimed_at < stored.expires_at
        assert stored.reviewer_contribution_policy_version_id == version_id


@pytest.mark.asyncio
async def test_active_capacity_and_queue_pointer_are_database_enforced(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    first = _lease_input(queue, reviewer_id, version_id)
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).add_lease(first)
        with pytest.raises(DBAPIError, match="non-leased queue cannot retain an active lease"):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).add_lease(first)
        await session.execute(
            text(
                "update review_queue_entries set queue_state='leased',active_lease_id=:lease,"
                "lifecycle_generation=lifecycle_generation+1 where id=:queue"
            ),
            {"lease": first.id, "queue": queue.id},
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        duplicate = _lease_input(queue, reviewer_id, version_id, generation=2)
        with pytest.raises(IntegrityError, match="uq_review_lease_active_queue"):
            await ReviewQueueRepository(session).add_lease(duplicate)


@pytest.mark.asyncio
async def test_reviewer_policy_lineage_and_human_kind_are_database_enforced(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    async with db_session.get_session_factory()() as session:
        service_id = await _service_actor(session)
        value = _lease_input(queue, service_id, version_id)
        with pytest.raises(DBAPIError, match="review lease reviewer must be human"):
            await ReviewQueueRepository(session).add_lease(value)


@pytest.mark.asyncio
async def test_queue_lineage_policy_project_and_published_status_are_enforced(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    second_queue = await _add_second_queue(review_lease_client, project, monkeypatch)

    crossed = _lease_input(queue, reviewer_id, version_id).model_copy(
        update={"task_id": second_queue.task_id, "submission_id": second_queue.submission_id}
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="fk_review_lease_queue_lineage"):
            await ReviewQueueRepository(session).add_lease(crossed)

    other_project_key = str(uuid4())
    response = await review_lease_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": "Other lease policy project",
            "slug": f"other-lease-policy-{other_project_key}",
            "description": "Cross-project lease policy proof",
        },
    )
    assert response.status_code == 201, response.text
    other_project_id = response.json()["id"]
    async with db_session.get_session_factory()() as session:
        other_policy = await _published_reviewer_policy(
            session, other_project_id, reviewer_id
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="policy version must be published"):
            await ReviewQueueRepository(session).add_lease(
                _lease_input(queue, reviewer_id, other_policy)
            )

    async with db_session.get_session_factory()() as session:
        draft_policy = await _draft_reviewer_policy(session, project["id"], reviewer_id)
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="policy version must be published"):
            await ReviewQueueRepository(session).add_lease(
                _lease_input(queue, reviewer_id, draft_policy)
            )


@pytest.mark.asyncio
async def test_preferred_reviewer_and_global_active_capacity_are_enforced(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    second_queue = await _add_second_queue(review_lease_client, project, monkeypatch)
    async with db_session.get_session_factory()() as session:
        service_id = await _service_actor(session)
        with pytest.raises(DBAPIError, match="preferred reviewer must be human"):
            await session.execute(
                update(ReviewQueueEntry)
                .where(ReviewQueueEntry.id == second_queue.id)
                .values(
                    routing_mode="preferred",
                    routing_reason="revision_return",
                    preferred_reviewer_id=service_id,
                    preference_expires_at=datetime.now(UTC) + timedelta(hours=1),
                    routing_generation=2,
                )
            )

    first = _lease_input(queue, reviewer_id, version_id)
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).add_lease(first)
        await session.execute(
            update(ReviewQueueEntry)
            .where(ReviewQueueEntry.id == queue.id)
            .values(queue_state="leased", active_lease_id=first.id, lifecycle_generation=2)
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="uq_review_lease_active_reviewer"):
            await ReviewQueueRepository(session).add_lease(
                _lease_input(second_queue, reviewer_id, version_id)
            )


@pytest.mark.asyncio
async def test_two_sessions_cannot_race_active_leases_for_one_reviewer(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    second_queue = await _add_second_queue(review_lease_client, project, monkeypatch)
    first = _lease_input(queue, reviewer_id, version_id)
    second = _lease_input(second_queue, reviewer_id, version_id)
    first_flushed = asyncio.Event()
    second_started = asyncio.Event()

    async def winner() -> None:
        async with db_session.get_session_factory()() as session:
            await ReviewQueueRepository(session).add_lease(first)
            await session.execute(
                update(ReviewQueueEntry)
                .where(ReviewQueueEntry.id == queue.id)
                .values(queue_state="leased", active_lease_id=first.id, lifecycle_generation=2)
            )
            first_flushed.set()
            await second_started.wait()
            await session.commit()

    async def loser() -> None:
        await first_flushed.wait()
        async with db_session.get_session_factory()() as session:
            second_started.set()
            with pytest.raises(IntegrityError, match="uq_review_lease_active_reviewer"):
                await ReviewQueueRepository(session).add_lease(second)

    await asyncio.gather(winner(), loser())


@pytest.mark.asyncio
async def test_terminal_attempt_is_immutable_and_cannot_reopen(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    value = _lease_input(queue, reviewer_id, version_id)
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).add_lease(value)
        await session.execute(
            update(ReviewQueueEntry)
            .where(ReviewQueueEntry.id == queue.id)
            .values(queue_state="leased", active_lease_id=value.id, lifecycle_generation=2)
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        await session.execute(
            text(
                "update review_leases set status='released',closed_at=statement_timestamp(),"
                "close_reason='manual_release' where id=:id"
            ),
            {"id": value.id},
        )
        await session.execute(
            update(ReviewQueueEntry)
            .where(ReviewQueueEntry.id == queue.id)
            .values(queue_state="pending", active_lease_id=None, lifecycle_generation=3)
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="terminal review leases are immutable"):
            await session.execute(
                text("update review_leases set status='active' where id=:id"),
                {"id": value.id},
            )


@pytest.mark.postgres_schema_contract
@pytest.mark.asyncio
async def test_populated_lease_persistence_refuses_downgrade(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    migration_lock,
) -> None:
    _, queue, reviewer_id, version_id = await _seed_queue_and_policy(
        review_lease_client, monkeypatch
    )
    value = _lease_input(queue, reviewer_id, version_id)
    async with db_session.get_session_factory()() as session:
        await ReviewQueueRepository(session).add_lease(value)
        await session.execute(
            update(ReviewQueueEntry)
            .where(ReviewQueueEntry.id == queue.id)
            .values(queue_state="leased", active_lease_id=value.id, lifecycle_generation=2)
        )
        await session.commit()
    await db_session.dispose_engine()

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    def downgrade() -> None:
        with migration_lock():
            command.downgrade(config, "0055_contribution_policy")

    with pytest.raises(RuntimeError, match="cannot downgrade populated review lease"):
        await asyncio.to_thread(downgrade)

    async with db_session.get_session_factory()() as session:
        assert await session.scalar(text("select version_num from alembic_version")) == (
            "0056_review_lease_preference"
        )
        assert await session.get(ReviewLease, value.id) is not None


@pytest.mark.postgres_schema_contract
@pytest.mark.asyncio
async def test_upgrade_refuses_preexisting_nonhuman_preference(
    review_lease_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    migration_lock,
) -> None:
    _, queue, _, _ = await _seed_queue_and_policy(review_lease_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        service_id = await _service_actor(session)
        await session.commit()
    await db_session.dispose_engine()

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    def migrate(revision: str) -> None:
        with migration_lock():
            if revision == "0055_contribution_policy":
                command.downgrade(config, revision)
            else:
                command.upgrade(config, revision)

    await asyncio.to_thread(migrate, "0055_contribution_policy")
    async with db_session.get_session_factory()() as session:
        await session.execute(
            text(
                "update review_queue_entries set routing_mode='preferred',"
                "routing_reason='revision_return',preferred_reviewer_id=:reviewer,"
                "preference_expires_at=statement_timestamp()+interval '1 hour',"
                "routing_generation=routing_generation+1 where id=:queue"
            ),
            {"reviewer": service_id, "queue": queue.id},
        )
        await session.commit()
    await db_session.dispose_engine()

    try:
        with pytest.raises(
            RuntimeError, match="cannot add lease persistence with nonhuman reviewer preference"
        ):
            await asyncio.to_thread(migrate, "head")
        async with db_session.get_session_factory()() as session:
            assert await session.scalar(text("select version_num from alembic_version")) == (
                "0055_contribution_policy"
            )
    finally:
        await db_session.dispose_engine()
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text(
                    "update review_queue_entries set routing_mode='open',"
                    "routing_reason='first_submission',preferred_reviewer_id=null,"
                    "preference_expires_at=null,routing_generation=routing_generation+1 "
                    "where id=:queue"
                ),
                {"queue": queue.id},
            )
            await session.commit()
        await db_session.dispose_engine()
        await asyncio.to_thread(migrate, "head")
