"""Atomicity, concurrency, conflicting identity, and partial replay proof."""

import asyncio
from contextlib import suppress

import pytest

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.contributions.records.repository import SubmitterContributionRepository
from app.modules.reviews.api.acceptance import FinalAcceptanceConflict
from tests.contributions.records.support import (
    award_values,
    contribution_source,
    insert_award,
    insert_record,
    rows,
)
from tests.reviews.acceptance.support import insert_acceptance
from tests.reviews.packet.test_repository import wait_for_blocker

from .participation_support import (
    participant,
    prepare_review_pending,
    request_for,
    stage_terminal_task,
    stored_effects,
)

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


async def test_caller_rollback_and_late_sql_failure_discard_every_new_effect(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path,
        isolated_database_env,
        paid=True,
        persist_acceptance=False,
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())

        async with h.factory() as session:
            await session.begin()
            result = await participant(session).participate(request)
            assert len(result.participation.awards) == 2
            await session.rollback()

        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="division by zero"):
                async with session.begin():
                    result = await participant(session).participate(request)
                    assert len(result.participation.awards) == 2
                    await session.execute(text("SELECT 1 / 0"))
            await session.rollback()

        async with h.factory() as session:
            assert await stored_effects(session, request.task_effects.task_id) == {
                "task_status": "review_pending",
                "assignment_status": "active",
                "acceptances": 0,
                "contributions": 0,
                "reviewer_contributions": 0,
                "awards": 0,
            }


@pytest.mark.parametrize("commit_first", [True, False], ids=("commit-wins", "rollback-loses"))
async def test_concurrent_shared_acceptance_converges_on_committed_winner_ids(
    tmp_path, isolated_database_env, commit_first
):
    async with contribution_source(
        tmp_path,
        isolated_database_env,
        paid=True,
        persist_acceptance=False,
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        ready = asyncio.Future()

        async def competitor():
            async with h.factory() as session:
                await session.begin()
                ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
                try:
                    result = await participant(session).participate(request)
                    await session.commit()
                    return result
                except BaseException:
                    await session.rollback()
                    raise

        async with h.factory() as first_session:
            await first_session.begin()
            first = await participant(first_session).participate(request)
            pending = asyncio.create_task(competitor())
            try:
                await wait_for_blocker(h.factory, await ready)
                await (
                    first_session.commit() if commit_first else first_session.rollback()
                )
                winner = await asyncio.wait_for(pending, 10)
            finally:
                if not pending.done():
                    pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending

        if commit_first:
            assert winner == first
        else:
            assert winner.acceptance.id == first.acceptance.id == request.acceptance.id
            assert winner.acceptance.accepted_at != first.acceptance.accepted_at
            assert winner.participation.contribution.id != first.participation.contribution.id
            assert {award.id for award in winner.participation.awards}.isdisjoint(
                {award.id for award in first.participation.awards}
            )
        async with h.factory() as session:
            assert await session.scalar(text("SELECT id FROM public.final_acceptances")) == (
                winner.acceptance.id
            )
            assert await session.scalar(
                text("SELECT id FROM public.contribution_records")
            ) == winner.participation.contribution.id
            assert set(
                await session.scalars(text("SELECT id FROM public.compensation_awards"))
            ) == {award.id for award in winner.participation.awards}


async def test_terminal_replay_rejects_conflicting_preallocated_acceptance_identity(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session, session.begin():
            created = await participant(session).participate(request)

        conflicting_id = new_record_id()
        conflict = request.model_copy(
            update={
                "acceptance": request.acceptance.model_copy(update={"id": conflicting_id}),
                "task_effects": request.task_effects.model_copy(
                    update={"final_acceptance_id": conflicting_id}
                ),
            }
        )
        async with h.factory() as session, session.begin():
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(conflict)

        async with h.factory() as session:
            assert await session.scalar(text("SELECT id FROM public.final_acceptances")) == (
                created.acceptance.id
            )
            assert await session.scalar(
                text("SELECT count(*) FROM public.contribution_records")
            ) == 1


async def test_recorded_acceptance_with_pending_task_rejects_without_terminal_repair(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session, session.begin():
            await insert_acceptance(session, request.acceptance)

        async with h.factory() as session, session.begin():
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(request)

        async with h.factory() as session:
            assert await stored_effects(session, request.task_effects.task_id) == {
                "task_status": "review_pending",
                "assignment_status": "active",
                "acceptances": 1,
                "contributions": 0,
                "reviewer_contributions": 0,
                "awards": 0,
            }


async def test_terminal_task_without_acceptance_rejects_without_source_or_economics(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session, session.begin():
            await stage_terminal_task(session, request)

        async with h.factory() as session, session.begin():
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(request)

        async with h.factory() as session:
            assert await stored_effects(session, request.task_effects.task_id) == {
                "task_status": "accepted",
                "assignment_status": "completed",
                "acceptances": 0,
                "contributions": 0,
                "reviewer_contributions": 0,
                "awards": 0,
            }


@pytest.mark.parametrize(
    ("task_status", "assignment_status"),
    (("accepted", "active"), ("review_pending", "completed")),
)
async def test_mixed_task_assignment_states_reject_without_missing_effects(
    tmp_path, isolated_database_env, task_status, assignment_status
):
    async with contribution_source(
        tmp_path, isolated_database_env, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session, session.begin():
            await session.execute(
                text("UPDATE public.workstream_tasks SET status=:status WHERE id=:id"),
                {"status": task_status, "id": request.task_effects.task_id},
            )
            await session.execute(
                text("UPDATE public.task_assignments SET status=:status WHERE id=:id"),
                {"status": assignment_status, "id": request.task_effects.assignment_id},
            )

        async with h.factory() as session, session.begin():
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(request)

        async with h.factory() as session:
            state = await stored_effects(session, request.task_effects.task_id)
            assert state == {
                "task_status": task_status,
                "assignment_status": assignment_status,
                "acceptances": 0,
                "contributions": 0,
                "reviewer_contributions": 0,
                "awards": 0,
            }


async def test_acceptance_and_terminal_task_without_contribution_rejects_and_commits_no_repair(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, paid=True, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session, session.begin():
            await stage_terminal_task(session, request)
            await insert_acceptance(session, request.acceptance)

        async with h.factory() as session, session.begin():
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(request)

        async with h.factory() as session:
            assert await stored_effects(session, request.task_effects.task_id) == {
                "task_status": "accepted",
                "assignment_status": "completed",
                "acceptances": 1,
                "contributions": 0,
                "reviewer_contributions": 0,
                "awards": 0,
            }


async def test_partial_awards_in_same_transaction_reject_without_backfill(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, paid=True, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session:
            await session.begin()
            await stage_terminal_task(session, request)
            await insert_acceptance(session, request.acceptance)
            await insert_record(session, h.submitter_record)
            expected_awards = await award_values(session, h.submitter_record)
            await insert_award(
                session,
                expected_awards[0],
                correlation_id=request.correlation_id,
            )
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(request)
            assert len(await rows(session, "compensation_awards")) == 1
            assert len(await rows(session, "contribution_records")) == 1
            await session.rollback()

        async with h.factory() as session:
            assert await stored_effects(session, request.task_effects.task_id) == {
                "task_status": "review_pending",
                "assignment_status": "active",
                "acceptances": 0,
                "contributions": 0,
                "reviewer_contributions": 0,
                "awards": 0,
            }


async def test_removing_replay_no_insert_guard_exposes_partial_repair(
    tmp_path, isolated_database_env, monkeypatch
):
    async with contribution_source(
        tmp_path, isolated_database_env, paid=False, persist_acceptance=False
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h, correlation_id=new_record_id())
        async with h.factory() as session, session.begin():
            await stage_terminal_task(session, request)
            await insert_acceptance(session, request.acceptance)

        original = SubmitterContributionRepository.apply_acceptance_disposition

        async def insert_during_replay(repository, participation_request):
            return await original(
                repository,
                participation_request.model_copy(
                    update={"acceptance_disposition": "new"}
                ),
            )

        monkeypatch.setattr(
            SubmitterContributionRepository,
            "apply_acceptance_disposition",
            insert_during_replay,
        )
        async with h.factory() as session:
            await session.begin()
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(FinalAcceptanceConflict):
                    await participant(session).participate(request)
            assert len(await rows(session, "contribution_records")) == 1
            assert await rows(session, "compensation_awards") == []
            state = await stored_effects(session, request.task_effects.task_id)
            assert state["task_status"] == "accepted"
            assert state["assignment_status"] == "completed"
            assert state["acceptances"] == 1
            await session.rollback()
