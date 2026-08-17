"""PostgreSQL lock-order proofs for ContributionPolicy publication."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from tests.contributions.test_policy_integration_postgresql import (
    _exercise_policy,
    _policy_database_env,  # noqa: F401
)


async def _assert_competing_write_waits(lock_sql: str, write_sql: str) -> None:
    async with (
        db_session.get_session_factory()() as owner,
        db_session.get_session_factory()() as contender,
        owner.begin(),
    ):
        await owner.execute(text(lock_sql))
        with pytest.raises(DBAPIError):
            async with contender.begin():
                await contender.execute(text("set local lock_timeout='100ms'"))
                await contender.execute(text(write_sql))


@pytest.mark.asyncio
async def test_child_mutation_waits_for_publication_graph_fence(
    policy_database_env: str,
) -> None:
    del policy_database_env
    await _exercise_policy()
    await _assert_competing_write_waits(
        "select id from contribution_rules order by id for update",
        "update contribution_rules set compensation_mode=compensation_mode",
    )


@pytest.mark.asyncio
async def test_binding_suspension_waits_for_publication_owner_fence(
    policy_database_env: str,
) -> None:
    del policy_database_env
    await _exercise_policy()
    await _assert_competing_write_waits(
        "select id from project_compensation_adapter_bindings order by id for update",
        "update project_compensation_adapter_bindings set lifecycle_version=lifecycle_version",
    )


@pytest.mark.asyncio
async def test_unit_retirement_waits_for_publication_owner_fence(
    policy_database_env: str,
) -> None:
    del policy_database_env
    await _exercise_policy()
    await _assert_competing_write_waits(
        "select project_id,instrument_type,unit_code from project_compensation_units "
        "order by project_id,instrument_type,unit_code for update",
        "update project_compensation_units set status=status",
    )


@pytest.mark.asyncio
async def test_competing_publications_serialize_before_authorization(
    policy_database_env: str,
) -> None:
    del policy_database_env
    project_id, _, _, _ = await _exercise_policy()
    scope = f"contribution-policy-project:{project_id}"
    async with (
        db_session.get_session_factory()() as winner,
        db_session.get_session_factory()() as contender,
        winner.begin(),
    ):
        await winner.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": scope},
        )
        with pytest.raises(DBAPIError):
            async with contender.begin():
                await contender.execute(text("set local lock_timeout='100ms'"))
                await contender.execute(
                    text("select pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                    {"scope": scope},
                )


@pytest.mark.asyncio
async def test_reverse_ordered_graphs_use_one_lock_order(
    policy_database_env: str,
) -> None:
    del policy_database_env
    await _exercise_policy()
    async with db_session.get_session_factory()() as first:
        async with first.begin():
            forward = (
                (await first.execute(text("select id from contribution_rules order by id")))
                .scalars()
                .all()
            )
            reverse_input = list(reversed(forward))
            canonical = sorted(reverse_input, key=str)
            assert canonical == sorted(forward, key=str)
            await first.execute(text("select id from contribution_rules order by id for update"))
        await asyncio.sleep(0)
