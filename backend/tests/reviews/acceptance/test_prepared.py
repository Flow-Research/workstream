"""Prepared acceptance cannot outlive the root transaction holding its custody."""

import pytest
from sqlalchemy import text

from app.adapters.reviews import final_acceptance_participant
from app.db.session import get_session_factory
from app.modules.reviews.api.acceptance import FinalAcceptanceConflict
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


@pytest.mark.parametrize("boundary", ["commit", "rollback", "savepoint", "closed"])
async def test_prepared_acceptance_requires_original_root(boundary):
    async with get_session_factory()() as session:
        await session.begin()
        async with final_acceptance_participant(session).prepare(2) as prepared:
            await prepared.require_new()
            if boundary in {"commit", "rollback"}:
                await getattr(session, boundary)()
                await session.begin()
                with pytest.raises(JointLifecycleUnavailable, match="held lifecycle custody is unavailable"):
                    await prepared.require_new()
            elif boundary == "savepoint":
                await session.execute(text("SAVEPOINT hidden_scope"))
                assert not session.in_nested_transaction()
                with pytest.raises(JointLifecycleUnavailable, match="requires a root transaction"):
                    await prepared.require_new()
                await session.execute(text("ROLLBACK TO SAVEPOINT hidden_scope"))
                await session.execute(text("RELEASE SAVEPOINT hidden_scope"))
                with pytest.raises(JointLifecycleUnavailable, match="held lifecycle custody is unavailable"):
                    await prepared.require_new()
        with pytest.raises(FinalAcceptanceConflict, match="acceptance preparation is closed"):
            await prepared.require_new()
        await session.rollback()
