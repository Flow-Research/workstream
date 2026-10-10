"""A verified checker failure still grants no success routing or acceptance authority."""

import pytest
from sqlalchemy import func, select, text

from app.adapters.checkers import evaluation_coordinator
from app.adapters.tasks import evaluation_completion_handler, routing_source_preparer, task_post_submit_outcome
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest, TaskPostSubmitRoutingManifest
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequests, TaskRoutingRequestUnavailable
from tests.checkers.execution.completion_fixture import completed_evidence, evidence_snapshot
from tests.checkers.execution.test_completion_evidence import verify
from .outcome_support import invoked_completion


@pytest.mark.parametrize("recommendation", ["needs_revision", "task_setup_blocked"])
async def test_stored_failure_cannot_enter_task_routing_or_completion_delivery(tmp_path, isolated_database_env, recommendation):
    async with completed_evidence(tmp_path, isolated_database_env, recommendation) as h:
        async with h.factory() as session, session.begin():
            await session.execute(text("UPDATE public.task_assignments SET accepted_at=clock_timestamp() WHERE id=:id"),
                                  {"id": h.request.assignment_id})
        envelope = await invoked_completion(h)
        async with h.factory() as session, session.begin():
            # The same actual stored failure is valid for CHECKERS observation.
            assert (await verify(session, h)).completion.routing_recommendation == recommendation
            before = await evidence_snapshot(session)
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_request_unavailable"):
                await TaskRoutingRequests(session, evaluation_coordinator(session)).stage(
                    h.source["completion_event_id"], h.completion,
                )
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_request_unavailable"):
                await routing_source_preparer(session).prepare(h.source["completion_event_id"], h.completion)
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing invocation unavailable"):
                await task_post_submit_outcome(session, h.factory).apply(envelope, current_generation=None)
            assert await evidence_snapshot(session) == before
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0
            assert await session.scalar(select(func.count()).select_from(TaskPostSubmitRoutingManifest)) == 0
        assert await evaluation_completion_handler(sessions=h.factory)(envelope) is HandlerOutcome.REJECT
        async with h.factory() as session:
            assert await evidence_snapshot(session) == before
