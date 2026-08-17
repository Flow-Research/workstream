"""Database custody for immutable policy lifecycle events."""

from uuid import uuid4

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
    _policy_database_env as _policy_database_env_fixture,  # noqa: F401
)


@pytest.mark.asyncio
async def test_event_update_is_rejected(policy_database_env: str) -> None:
    del policy_database_env
    _, event_id, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ContributionPolicyLifecycleEvent)
                .where(ContributionPolicyLifecycleEvent.id == event_id)
                .values(request_digest="sha256:" + "0" * 64)
            )


@pytest.mark.asyncio
async def test_event_delete_is_rejected(policy_database_env: str) -> None:
    del policy_database_env
    _, event_id, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                delete(ContributionPolicyLifecycleEvent).where(
                    ContributionPolicyLifecycleEvent.id == event_id
                )
            )


@pytest.mark.asyncio
async def test_event_matches_immutable_mutation_result(policy_database_env: str) -> None:
    del policy_database_env
    project_id, event_id, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        event = await session.get(ContributionPolicyLifecycleEvent, event_id)
        assert event is not None
        assert event.project_id == str(project_id)
        assert event.event_type == "draft_created"
        assert event.version_number == 1
        assert event.occurred_at is not None


@pytest.mark.asyncio
async def test_event_actor_matches_authorized_actor(policy_database_env: str) -> None:
    del policy_database_env
    _, event_id, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        event = await session.get(ContributionPolicyLifecycleEvent, event_id)
        assert event is not None
        version = await session.get(
            ContributionPolicyVersion, event.contribution_policy_version_id
        )
        assert version is not None
        assert event.actor_profile_id == version.created_by


@pytest.mark.asyncio
async def test_event_rejects_invalid_transition_shape(
    policy_database_env: str,
) -> None:
    del policy_database_env
    _, event_id, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, event_id)
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
    _, event_id, _ = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        source = await session.get(ContributionPolicyLifecycleEvent, event_id)
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
async def test_event_truncate_is_rejected(policy_database_env: str) -> None:
    del policy_database_env
    await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(text("TRUNCATE contribution_policy_lifecycle_events"))
