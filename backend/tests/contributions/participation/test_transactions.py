"""Caller transaction, rollback, and canonical fence proof."""

import pytest

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from tests.contributions.records.support import contribution_source, rows
from tests.reviews.acceptance.support import insert_acceptance

from .support import participant, request_for

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


async def test_later_sql_failure_rolls_back_acceptance_contribution_and_awards(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, paid=True, persist_acceptance=False
    ) as h:
        request = request_for(h, acceptance_disposition="new", correlation_id=new_record_id())
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="division by zero"):
                async with session.begin():
                    await PostgresJointLifecycleMutationFence(session).acquire(2)
                    await insert_acceptance(session, h.acceptance)
                    result = await participant(session).participate_submitter(request)
                    assert len(result.awards) == 2
                    await session.execute(text("SELECT 1 / 0"))
            await session.rollback()
        async with h.factory() as session:
            assert await rows(session, "final_acceptances") == []
            assert await rows(session, "contribution_records") == []
            assert await rows(session, "compensation_awards") == []


async def test_canonical_fence_rejects_missing_and_savepoint_transactions(
    tmp_path, isolated_database_env
):
    async with contribution_source(tmp_path, isolated_database_env) as h:
        request = request_for(h, acceptance_disposition="new", correlation_id=new_record_id())
        async with h.factory() as session:
            with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                await participant(session).participate_submitter(request)
            assert not session.in_transaction()

        async with h.factory() as session, session.begin():
            async with session.begin_nested():
                with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                    await participant(session).participate_submitter(request)

        async with h.factory() as session:
            await session.begin()
            await session.execute(text("SAVEPOINT caller_raw_savepoint"))
            with pytest.raises(JointLifecycleUnavailable, match="root database transaction"):
                await participant(session).participate_submitter(request)
            await session.rollback()

        async with h.factory() as session, session.begin():
            result = await participant(session).participate_submitter(request)
            assert result.awards == ()
