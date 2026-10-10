"""Actual outbox finalization and the authorized outcome retain one invocation order."""

import asyncio

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.outbox.api import FinalizationCause
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from app.modules.tasks.post_submit_routing.source import TaskRoutingSourcePreparer
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.tasks.post_submit_routing.outcome_support import apply_outcome, authorized_routing_source, outcome_snapshot

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


async def test_outcome_holds_invocation_until_commit(tmp_path, isolated_database_env, monkeypatch):
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        name = "outcome-finalize-" + new_record_id().hex
        original = DeliveryRepository.event

        async def named(owner, *args, **kwargs):
            if asyncio.current_task().get_name() == name:
                await owner.session.execute(text("SELECT set_config('application_name',:name,true)"), {"name": name})
            return await original(owner, *args, **kwargs)

        monkeypatch.setattr(DeliveryRepository, "event", named)
        pending = None
        try:
            async with h.factory() as session, session.begin():
                blocker = await session.scalar(text("SELECT pg_backend_pid()"))
                result = await apply_outcome(session, h, 2)
                pending = asyncio.create_task(h.completion_delivery.finalize(h.envelope.claim, FinalizationCause.ACKNOWLEDGE), name=name)
                await asyncio.wait_for(wait_for_named_database_lock(isolated_database_env, name, expected_blocker_pid=blocker), 10)
                assert not pending.done()
            receipt = await asyncio.wait_for(pending, 10)
            assert receipt.claim == h.envelope.claim
            async with h.factory() as session:
                assert await session.scalar(text("SELECT id FROM public.final_acceptances")) == result["final_acceptance_id"]
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_finalization_between_observation_and_fence_denies_outcome(tmp_path, isolated_database_env, monkeypatch):
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        entered, release = asyncio.Event(), asyncio.Event()
        original = TaskRoutingSourcePreparer.prepare

        async def paused(owner, *args, **kwargs):
            entered.set()
            await asyncio.wait_for(release.wait(), 10)
            return await original(owner, *args, **kwargs)

        monkeypatch.setattr(TaskRoutingSourcePreparer, "prepare", paused)

        async def apply():
            async with h.factory() as session, session.begin():
                return await apply_outcome(session, h, 2)

        pending = asyncio.create_task(apply())
        try:
            await asyncio.wait_for(entered.wait(), 10)
            receipt = await h.completion_delivery.finalize(h.envelope.claim, FinalizationCause.ACKNOWLEDGE)
            assert receipt.claim == h.envelope.claim
            async with h.factory() as session:
                after_finalization = await outcome_snapshot(session)
            release.set()
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing invocation changed"):
                await asyncio.wait_for(pending, 10)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == after_finalization
                assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)
