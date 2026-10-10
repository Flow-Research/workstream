"""Actual staged effects, root commit failures, closed invocations and observation races."""

import asyncio

import pytest
from sqlalchemy.exc import DBAPIError

from app.adapters.tasks import evaluation_completion_handler
from app.modules.outbox.api import HandlerOutcome, FinalizationCause
from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, outcome_snapshot
from tests.tasks.post_submit_routing.test_source_preparation import routing_source
from .test_completion import completion_delivery, assert_committed
from .support import outcome


async def snapshot(h):
    async with h.factory() as session:
        return await outcome_snapshot(session)


async def test_completion_handler_deferred_constraint_failure_never_acknowledges(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, monkeypatch,
):
    from app.adapters.audit import _TaskRoutingAudit

    original = _TaskRoutingAudit._record
    omitted = []

    async def omit(owner, value, replay):
        if value.event_type.value == "TaskPostSubmitRouted":
            omitted.append(value)
            return
        return await original(owner, value, replay)

    async with authorized_routing_source(tmp_path, isolated_database_env, contribution_awards=("money",)) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        before = await snapshot(h)
        with monkeypatch.context() as patch:
            patch.setattr(_TaskRoutingAudit, "_record", omit)
            with pytest.raises(DBAPIError, match="routing authority requires its complete governed outcome"):
                await handler(h.envelope)
        assert len(omitted) == 1
        assert await snapshot(h) == before
        assert await handler(h.envelope) is HandlerOutcome.ACKNOWLEDGE


@pytest.mark.parametrize("corruption", ["project_id", "task_id", "submission_id", "completion_event_id", "economic"])
async def test_completion_handler_invalid_result_rolls_back(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, monkeypatch, corruption,
):
    from app.core.identifiers import new_record_id
    from pydantic import ValidationError

    original = TaskPostSubmitOutcome.apply
    reached = []

    async def corrupt(owner, *args, **kwargs):
        result = await original(owner, *args, **kwargs)
        reached.append(result)
        object.__setattr__(result, corruption, None if corruption == "economic" else new_record_id())
        return result

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        before = await snapshot(h)
        with monkeypatch.context() as patch:
            patch.setattr(TaskPostSubmitOutcome, "apply", corrupt)
            with pytest.raises((TaskRoutingRequestUnavailable, ValidationError)):
                await handler(h.envelope)
        assert len(reached) == 1
        assert await snapshot(h) == before
        assert await handler(h.envelope) is HandlerOutcome.ACKNOWLEDGE


async def test_completion_handler_cancellation_rolls_back(tmp_path, isolated_database_env, live_acceptance_lifecycle, monkeypatch):
    original = TaskPostSubmitOutcome.apply
    staged = asyncio.Event()

    async def pause(owner, *args, **kwargs):
        result = await original(owner, *args, **kwargs)
        staged.set()
        await asyncio.Event().wait()
        return result

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        before = await snapshot(h)
        with monkeypatch.context() as patch:
            patch.setattr(TaskPostSubmitOutcome, "apply", pause)
            pending = asyncio.create_task(handler(h.envelope))
            try:
                await asyncio.wait_for(staged.wait(), 10)
            finally:
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
        assert await snapshot(h) == before
        assert await handler(h.envelope) is HandlerOutcome.ACKNOWLEDGE


async def test_completion_handler_response_loss_is_unknown_without_duplicate_effects(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    async with routing_source(tmp_path, isolated_database_env, human_review_required=False) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        invoked = []

        async def lose_response(envelope):
            invoked.append(envelope)
            assert await handler(envelope) is HandlerOutcome.ACKNOWLEDGE
            await assert_committed(h, human=False, award_count=0)
            raise RuntimeError("test response loss after commit")

        delivery = await completion_delivery(h, lose_response)
        receipt = await delivery.deliver(h.source["completion_event_id"], h.request.project_id, "lost")
        assert outcome(receipt)["invocation_unknown"] is True
        assert outcome(receipt)["next_attempt_at"] is None
        saved = await snapshot(h)
        assert await handler(invoked[0]) is HandlerOutcome.REJECT
        assert await delivery.deliver(h.source["completion_event_id"], h.request.project_id, "duplicate") is None
        assert len(invoked) == 1
        assert await snapshot(h) == saved


async def test_completion_handler_stale_observed_generation_cannot_commit(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, monkeypatch,
):
    from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
    from tests.reviews.lifecycle.transition_support import command_for, controller

    original = TaskPostSubmitOutcome.observe_delivery_generation
    observed, release = asyncio.Event(), asyncio.Event()

    async def pause(owner, envelope):
        generation = await original(owner, envelope)
        assert generation == 2
        observed.set()
        await release.wait()
        return generation

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        with monkeypatch.context() as patch:
            patch.setattr(TaskPostSubmitOutcome, "observe_delivery_generation", pause)
            pending = asyncio.create_task(handler(h.envelope))
            try:
                await asyncio.wait_for(observed.wait(), 10)
                command = await command_for(live_acceptance_lifecycle.target.id, "draining")
                async with h.factory() as session, session.begin():
                    result = await controller(session, command).transition(command)
                    assert result.generation == 3
                before = await snapshot(h)
                release.set()
                with pytest.raises(JointLifecycleUnavailable, match="generation changed"):
                    await asyncio.wait_for(pending, 10)
                assert await snapshot(h) == before
            finally:
                release.set()
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_completion_handler_finalized_invocation_cannot_commit(tmp_path, isolated_database_env):
    async with authorized_routing_source(tmp_path, isolated_database_env, human_review_required=True) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        original = handler._observer
        observed, release = asyncio.Event(), asyncio.Event()

        class PausedObserver:
            async def observe_invocation(self, envelope):
                result = await original.observe_invocation(envelope)
                assert result is not None
                observed.set()
                await release.wait()
                return result

        handler._observer = PausedObserver()
        pending = asyncio.create_task(handler(h.envelope))
        try:
            await asyncio.wait_for(observed.wait(), 10)
            await h.completion_delivery.finalize(h.envelope.claim, FinalizationCause.UNKNOWN)
            before = await snapshot(h)
            release.set()
            with pytest.raises(TaskRoutingRequestUnavailable, match="invocation unavailable"):
                await asyncio.wait_for(pending, 10)
            assert await snapshot(h) == before
        finally:
            release.set()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
