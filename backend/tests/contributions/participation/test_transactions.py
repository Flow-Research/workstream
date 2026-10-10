"""The CON participant cannot bypass the canonical caller-owned fence."""

import pytest
from sqlalchemy import text

from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from tests.contributions.records.support import authorized_submitter_source
from tests.tasks.post_submit_routing.outcome_support import outcome_snapshot
from .support import participant, request_for

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


async def test_canonical_fence_rejects_missing_and_savepoint_transactions(
    tmp_path, isolated_database_env
):
    async with authorized_submitter_source(tmp_path, isolated_database_env) as h:
        request = request_for(h, acceptance_disposition="replay")
        async with h.factory() as session:
            before = await outcome_snapshot(session)
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
            assert await participant(session).participate_submitter(request) == h.participation
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
