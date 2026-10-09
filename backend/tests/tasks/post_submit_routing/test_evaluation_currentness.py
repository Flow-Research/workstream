"""Real shared acceptance and successor reservations serialize through TASK custody."""

import asyncio

import pytest
from sqlalchemy import select, text

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, CheckerRequestConflict
from app.modules.checkers.models import CheckerSubmissionFence
from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequests
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.checkers.post_submit.support import change_request
from tests.contributions.records.support import contribution_source
from tests.reviews.acceptance.participation_support import participant, prepare_review_pending, request_for
from .support import completed_source, completion_for


async def _counts(session):
    return (await session.execute(text("""
        SELECT (SELECT count(*) FROM public.checker_runs),
               (SELECT count(*) FROM public.task_post_submit_routing_requests),
               (SELECT count(*) FROM public.final_acceptances),
               (SELECT count(*) FROM public.contribution_records),
               (SELECT count(*) FROM public.compensation_awards)
    """))).one()


async def _acceptance_wins(tmp_path, database_url):
    async with contribution_source(tmp_path, database_url, persist_acceptance=False) as h:
        await prepare_review_pending(h)
        acceptance = await request_for(h)
        successor = change_request(h.request, evaluation_request_id=new_record_id(), evaluation_generation=2)
        async with h.factory() as session, session.begin():
            original = await evaluation_coordinator(session).reserve_current_evaluation(h.request)
        name = "acceptance-successor-" + new_record_id().hex

        async def compete():
            async with h.factory() as session:
                try:
                    async with session.begin():
                        await session.execute(text("select set_config('application_name',:name,true)"), {"name": name})
                        return await evaluation_coordinator(session).reserve_current_evaluation(successor)
                except CheckerExecutionUnavailable as error:
                    return error

        pending = None
        try:
            async with h.factory() as winner, winner.begin():
                blocker = await winner.scalar(text("select pg_backend_pid()"))
                accepted = await participant(winner).participate(acceptance)
                pending = asyncio.create_task(compete())
                await asyncio.wait_for(wait_for_named_database_lock(
                    database_url, name, expected_blocker_pid=blocker,
                ), 10)
                assert not pending.done()
            outcome = await asyncio.wait_for(pending, 10)
            assert isinstance(outcome, CheckerExecutionUnavailable), "terminal reservation was not rejected"
            assert str(outcome) == "checker_reservation_scope_unavailable"
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

        async with h.factory() as session, session.begin():
            before = await _counts(session)
            assert before == (1, 0, 1, 1, 0)
            assert accepted.task_effects.task_status == "accepted"
            assert accepted.task_effects.assignment_status == "completed"
            async with h.factory() as blocker, blocker.begin():
                await blocker.execute(text("select pg_advisory_xact_lock(hashtextextended(:key,0))"),
                                      {"key": "checkers:submission:" + str(h.request.submission_id)})
                await blocker.execute(text(
                    "SELECT submission_id FROM public.checker_submission_fences "
                    "WHERE submission_id=:id FOR UPDATE"
                ), {"id": h.request.submission_id})
                await blocker.execute(text("SELECT id FROM public.checker_runs WHERE id=:id FOR UPDATE"),
                                      {"id": original.attempt_id})
                await session.execute(text("SET LOCAL lock_timeout='250ms'"))
                assert await evaluation_coordinator(session).reserve_current_evaluation(h.request) == original
            changed = change_request(h.request, structural_input=h.request.structural_input.model_copy(
                update={"summary": "Changed envelope, unchanged immutable TASK lineage."},
            ))
            with pytest.raises(CheckerRequestConflict, match="checker_request_conflict"):
                await evaluation_coordinator(session).reserve_current_evaluation(changed)
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(original.attempt_id)
            assert await _counts(session) == before


@pytest.mark.usefixtures("live_acceptance_lifecycle")
async def test_acceptance_blocks_successor_and_retains_exact_replay(tmp_path, isolated_database_env):
    await _acceptance_wins(tmp_path, isolated_database_env)


@pytest.mark.usefixtures("live_acceptance_lifecycle")
async def test_terminal_guard_removal_is_detected(tmp_path, isolated_database_env, monkeypatch):
    original = TaskEvaluationGuard.lock_evaluation_scope

    async def ignore_terminal(self, request):
        await original(self, request)
        return True

    monkeypatch.setattr(TaskEvaluationGuard, "lock_evaluation_scope", ignore_terminal)
    with pytest.raises(AssertionError, match="terminal reservation was not rejected"):
        await _acceptance_wins(tmp_path, isolated_database_env)


async def test_successor_blocks_then_invalidates_old_routing_completion(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        completion = completion_for(h)
        successor = change_request(h.request, evaluation_request_id=new_record_id(), evaluation_generation=2)
        name = "successor-routing-" + new_record_id().hex

        async def route():
            async with h.factory() as session, session.begin():
                await session.execute(text("select set_config('application_name',:name,true)"), {"name": name})
                return await TaskRoutingRequests(session, evaluation_coordinator(session)).stage(
                    h.source["completion_event_id"], completion,
                )

        pending = None
        try:
            async with h.factory() as winner, winner.begin():
                blocker = await winner.scalar(text("select pg_backend_pid()"))
                before = await _counts(winner)
                reserved = await evaluation_coordinator(winner).reserve_current_evaluation(successor)
                pending = asyncio.create_task(route())
                await asyncio.wait_for(wait_for_named_database_lock(
                    isolated_database_env, name, expected_blocker_pid=blocker,
                ), 10)
                assert not pending.done()
            with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
                await asyncio.wait_for(pending, 10)
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        async with h.factory() as session, session.begin():
            assert await _counts(session) == (before[0] + 1, *before[1:])
            current = await session.scalar(select(CheckerSubmissionFence.current_run_id).where(
                CheckerSubmissionFence.submission_id == str(h.request.submission_id),
            ))
            assert current == str(reserved.attempt_id)
            # Old reservation replay never restores the previous current fence.
            old = await evaluation_coordinator(session).reserve_current_evaluation(h.request)
            assert old.attempt_id == h.result.attempt_id
            assert await session.scalar(select(CheckerSubmissionFence.current_run_id).where(
                CheckerSubmissionFence.submission_id == str(h.request.submission_id),
            )) == str(reserved.attempt_id)
