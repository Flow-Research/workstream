"""Database custody for immutable policy lifecycle events."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.contributions.models import (
    ContributionPolicyLifecycleEvent,
    ContributionPolicyVersion,
)
from tests.contributions.test_policy_integration_postgresql import (
    _exercise_policy,
    _seed_project_only,
    _policy_database_env as _policy_database_env_fixture,  # noqa: F401
)


@pytest.mark.asyncio
async def test_event_update_is_rejected(policy_database_env: str) -> None:
    del policy_database_env
    _, created, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ContributionPolicyLifecycleEvent)
                .where(ContributionPolicyLifecycleEvent.id == created.event_id)
                .values(request_digest="sha256:" + "0" * 64)
            )


@pytest.mark.asyncio
async def test_event_delete_is_rejected(policy_database_env: str) -> None:
    del policy_database_env
    _, created, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                delete(ContributionPolicyLifecycleEvent).where(
                    ContributionPolicyLifecycleEvent.id == created.event_id
                )
            )


@pytest.mark.asyncio
async def test_event_matches_immutable_mutation_result(policy_database_env: str) -> None:
    del policy_database_env
    project_id, created, updated = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        for result in (created, updated):
            event = await session.get(ContributionPolicyLifecycleEvent, result.event_id)
            assert event is not None
            assert result.operation_id == event.operation_id
            assert result.request_digest == event.request_digest
            assert result.event_type == event.event_type
            assert str(result.actor_profile_id) == event.actor_profile_id
            assert result.project_id == project_id == UUID(event.project_id)
            assert result.contribution_policy_id == event.contribution_policy_id
            assert result.contribution_policy_version_id == event.contribution_policy_version_id
            assert result.version_number == event.version_number
            assert result.prior_current_version_id == event.prior_current_version_id
            assert result.prior_current_version_number == event.prior_current_version_number
            assert result.from_policy_status == event.from_policy_status
            assert result.to_policy_status == event.to_policy_status
            assert result.from_version_status == event.from_version_status
            assert result.to_version_status == event.to_version_status
            assert result.occurred_at == event.occurred_at


@pytest.mark.asyncio
async def test_event_actor_matches_authorized_actor(policy_database_env: str) -> None:
    del policy_database_env
    _, created, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        event = await session.get(ContributionPolicyLifecycleEvent, created.event_id)
        assert event is not None
        version = await session.get(ContributionPolicyVersion, event.contribution_policy_version_id)
        assert version is not None
        assert event.actor_profile_id == version.created_by


@pytest.mark.asyncio
async def test_event_rejects_invalid_transition_shape(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, created, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, created.event_id)
        assert source is not None
        session.add(
            ContributionPolicyLifecycleEvent(
                id=uuid4(),
                operation_id=uuid4(),
                request_digest="sha256:" + "1" * 64,
                event_type="published",
                actor_profile_id=source.actor_profile_id,
                project_id=source.project_id,
                contribution_policy_id=source.contribution_policy_id,
                contribution_policy_version_id=source.contribution_policy_version_id,
                version_number=source.version_number,
                prior_current_version_id=None,
                prior_current_version_number=None,
                from_policy_status="draft",
                to_policy_status="active",
                from_version_status="draft",
                to_version_status="published",
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_event_rejects_duplicate_operation_id(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, created, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, created.event_id)
        assert source is not None
        session.add(
            ContributionPolicyLifecycleEvent(
                id=uuid4(),
                operation_id=source.operation_id,
                request_digest=source.request_digest,
                event_type=source.event_type,
                actor_profile_id=source.actor_profile_id,
                project_id=source.project_id,
                contribution_policy_id=source.contribution_policy_id,
                contribution_policy_version_id=source.contribution_policy_version_id,
                version_number=source.version_number,
                prior_current_version_id=source.prior_current_version_id,
                prior_current_version_number=source.prior_current_version_number,
                from_policy_status=source.from_policy_status,
                to_policy_status=source.to_policy_status,
                from_version_status=source.from_version_status,
                to_version_status=source.to_version_status,
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_event_rejects_null_prior_policy_status(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, updated = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, updated.event_id)
        assert source is not None
        session.add(
            ContributionPolicyLifecycleEvent(
                id=uuid4(),
                operation_id=uuid4(),
                request_digest="sha256:" + "2" * 64,
                event_type="draft_updated",
                actor_profile_id=source.actor_profile_id,
                project_id=source.project_id,
                contribution_policy_id=source.contribution_policy_id,
                contribution_policy_version_id=source.contribution_policy_version_id,
                version_number=source.version_number,
                prior_current_version_id=source.prior_current_version_id,
                prior_current_version_number=source.prior_current_version_number,
                from_policy_status=None,
                to_policy_status=source.to_policy_status,
                from_version_status="draft",
                to_version_status="draft",
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_event_rejects_null_mutation_actor_anchor(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, _, updated = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, updated.event_id)
        assert source is not None
        await session.execute(
            update(ContributionPolicyVersion)
            .where(ContributionPolicyVersion.id == source.contribution_policy_version_id)
            .values(last_updated_by=None)
        )
        session.add(
            ContributionPolicyLifecycleEvent(
                id=uuid4(),
                operation_id=uuid4(),
                request_digest="sha256:" + "3" * 64,
                event_type="draft_updated",
                actor_profile_id=source.actor_profile_id,
                project_id=source.project_id,
                contribution_policy_id=source.contribution_policy_id,
                contribution_policy_version_id=source.contribution_policy_version_id,
                version_number=source.version_number,
                prior_current_version_id=source.prior_current_version_id,
                prior_current_version_number=source.prior_current_version_number,
                from_policy_status=source.from_policy_status,
                to_policy_status=source.to_policy_status,
                from_version_status="draft",
                to_version_status="draft",
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_event_schema_has_composite_ownership_constraints(
    policy_database_env: str,
) -> None:
    del policy_database_env
    async with db_session.get_session_factory()() as session:
        names = set(
            await session.scalars(
                text(
                    "select conname from pg_constraint "
                    "where conrelid='contribution_policy_lifecycle_events'::regclass"
                )
            )
        )
    assert "fk_contribution_policy_event_policy_ownership" in names
    assert "fk_contribution_policy_event_version_ownership" in names


@pytest.mark.asyncio
async def test_event_rejects_cross_project_policy_version_ownership(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, created, _ = await _exercise_policy()
    foreign_project = await _seed_project_only()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, created.event_id)
        assert source is not None
        session.add(
            ContributionPolicyLifecycleEvent(
                id=uuid4(),
                operation_id=uuid4(),
                request_digest="sha256:" + "4" * 64,
                event_type=source.event_type,
                actor_profile_id=source.actor_profile_id,
                project_id=foreign_project,
                contribution_policy_id=source.contribution_policy_id,
                contribution_policy_version_id=source.contribution_policy_version_id,
                version_number=source.version_number,
                prior_current_version_id=source.prior_current_version_id,
                prior_current_version_number=source.prior_current_version_number,
                from_policy_status=source.from_policy_status,
                to_policy_status=source.to_policy_status,
                from_version_status=source.from_version_status,
                to_version_status=source.to_version_status,
            )
        )
        with pytest.raises(DBAPIError):
            await session.flush()


@pytest.mark.asyncio
async def test_event_truncate_is_rejected(policy_database_env: str) -> None:
    del policy_database_env
    await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(text("TRUNCATE contribution_policy_lifecycle_events"))
