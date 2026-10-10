"""Atomic authorized acceptance, concurrent replay, and immutable terminal state."""

import asyncio
from contextlib import suppress

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.reviews.packet.test_repository import wait_for_blocker
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
    outcome_snapshot,
)

pytestmark = pytest.mark.usefixtures("live_acceptance_lifecycle")


async def test_paid_rollback_and_late_sql_failure_discard_every_new_effect(
    tmp_path, isolated_database_env
):
    async with authorized_routing_source(
        tmp_path,
        isolated_database_env,
        contribution_awards=("money", "project_points"),
    ) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        for fail_sql in (False, True):
            async with h.factory() as session:
                await session.begin()
                result = await apply_outcome(session, h, 2)
                assert len(result.economic.award_ids) == 2
                if fail_sql:
                    with pytest.raises(DBAPIError, match="division by zero"):
                        await session.execute(text("SELECT 1 / 0"))
                await session.rollback()
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before


@pytest.mark.parametrize("commit_first", [True, False], ids=("commit-wins", "rollback-loses"))
async def test_concurrent_shared_acceptance_converges_on_committed_winner_ids(
    tmp_path,
    isolated_database_env,
    commit_first,
):
    async with authorized_routing_source(
        tmp_path,
        isolated_database_env,
        contribution_awards=("money", "project_points"),
    ) as h:
        ready = asyncio.Future()

        async def competitor():
            async with h.factory() as session, session.begin():
                ready.set_result(await session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
                return await apply_outcome(session, h, 2)

        async with h.factory() as first_session:
            await first_session.begin()
            first = await apply_outcome(first_session, h, 2)
            pending = asyncio.create_task(competitor())
            try:
                await wait_for_blocker(h.factory, await ready)
                await (
                    first_session.commit() if commit_first else first_session.rollback()
                )
                winner = await asyncio.wait_for(pending, 10)
            finally:
                await first_session.rollback()
                if not pending.done():
                    pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
        if commit_first:
            assert winner == first.model_copy(update={"replayed": True})
        else:
            # No routing reservation committed: the winner allocates its own IDs.
            assert winner.routing_manifest_id != first.routing_manifest_id
            assert winner.final_acceptance_id != first.final_acceptance_id
            assert (
                winner.economic.contribution_record_id
                != first.economic.contribution_record_id
            )
            assert set(winner.economic.award_ids).isdisjoint(first.economic.award_ids)
            assert winner.replayed is False
        async with h.factory() as session:
            assert (
                await session.scalar(text("SELECT id FROM public.final_acceptances"))
                == winner.final_acceptance_id
            )
            assert (
                await session.scalar(text("SELECT id FROM public.contribution_records"))
                == winner.economic.contribution_record_id
            )
            assert set(
                await session.scalars(text("SELECT id FROM public.compensation_awards"))
            ) == set(winner.economic.award_ids)


@pytest.mark.parametrize("target", ["task", "assignment"])
async def test_completed_outcome_cannot_be_returned_to_partial_state(
    tmp_path, isolated_database_env, target
):
    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            result = await apply_outcome(session, h, 2)
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        command = (
            "UPDATE public.workstream_tasks SET status='evaluation_pending' WHERE id=:id"
            if target == "task"
            else "UPDATE public.task_assignments SET status='active' WHERE task_id=:id"
        )
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="accepted routing outcome is immutable"):
                async with session.begin():
                    await session.execute(text(command), {"id": h.request.task_id})
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert await apply_outcome(session, h, 2) == result.model_copy(update={"replayed": True})


@pytest.mark.parametrize("remove_guard", [False, True], ids=("protected", "guard-removal-probe"))
async def test_missing_contribution_cannot_leave_committed_acceptance(
    tmp_path,
    isolated_database_env,
    monkeypatch,
    remove_guard,
):
    """A faulty CON return cannot replace its required stored record."""
    from app.core.identifiers import new_record_id
    from app.modules.contributions.api import SubmitterContributionFacts
    from app.modules.contributions.records.repository import SubmitterContributionRepository

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        calls = []

        async def omitted(repository, request):
            calls.append(request)
            return SubmitterContributionFacts(
                id=new_record_id(),
                project_id=request.project_id,
                task_id=request.task_id,
                submission_id=request.submission_id,
                contributor_id=request.contributor_id,
                source_final_acceptance_id=request.final_acceptance_id,
                source_task_assignment_id=request.task_assignment_id,
                artifact_hash=request.artifact_hash,
                contribution_policy_version_id=request.contribution_policy_version_id,
                created_at=await repository._session.scalar(text("SELECT clock_timestamp()")),
            )

        async with h.factory() as session:
            before = await outcome_snapshot(session)
        with monkeypatch.context() as patch:
            patch.setattr(SubmitterContributionRepository, "apply_acceptance_disposition", omitted)
            async with h.factory() as session:
                await session.begin()
                if remove_guard:
                    definition = await session.scalar(
                        text(
                            "SELECT pg_get_functiondef('public.task_routing_outcome_complete(public.task_post_submit_routing_manifests)'::regprocedure)"
                        )
                    )
                    anchor = "SELECT * INTO c FROM public.contribution_records WHERE source_final_acceptance_id=f.id;"
                    assert definition.count(anchor) == 1
                    await session.execute(
                        text(
                            definition.replace(
                                anchor, anchor + " IF NOT FOUND THEN RETURN true; END IF;"
                            )
                        )
                    )
                await apply_outcome(session, h, 2)
                assert len(calls) == 1
                assert (
                    await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 1
                )
                assert (
                    await session.scalar(text("SELECT count(*) FROM public.contribution_records"))
                    == 0
                )

                async def assert_rejected():
                    with pytest.raises(
                        DBAPIError, match="routing authority requires its complete governed outcome"
                    ):
                        await session.execute(
                            text("SET CONSTRAINTS public.task_routing_complete_outcome IMMEDIATE")
                        )

                if remove_guard:
                    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                        await assert_rejected()
                else:
                    await assert_rejected()
                await session.rollback()
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, 2))[
                "economic"
            ].contribution_record_id is not None


async def test_replay_never_repairs_a_missing_contribution(
    tmp_path, isolated_database_env, monkeypatch
):
    """Corruption is isolated and rolled back; replay must never turn into new work."""
    from app.modules.contributions.records.repository import SubmitterContributionRepository
    from app.modules.reviews.api.acceptance import FinalAcceptanceConflict

    async with authorized_routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            committed = await apply_outcome(session, h, 2)
        async with h.factory() as session:
            retained = await outcome_snapshot(session)
            await session.rollback()
            await session.begin()
            await session.execute(
                text(
                    "ALTER TABLE public.contribution_records DISABLE TRIGGER contribution_record_immutable"
                )
            )
            await session.execute(
                text("DELETE FROM public.contribution_records WHERE id=:id"),
                {"id": committed.economic.contribution_record_id},
            )
            with pytest.raises(FinalAcceptanceConflict, match="final_acceptance_conflict"):
                await apply_outcome(session, h, 2)
            assert (
                await session.scalar(text("SELECT count(*) FROM public.contribution_records")) == 0
            )

            original = SubmitterContributionRepository.apply_acceptance_disposition
            repaired = []

            async def wrong_repair(repository, request):
                assert request.acceptance_disposition == "replay"
                value = await original(
                    repository, request.model_copy(update={"acceptance_disposition": "new"})
                )
                repaired.append(value.id)
                return value

            with monkeypatch.context() as patch:
                patch.setattr(
                    SubmitterContributionRepository, "apply_acceptance_disposition", wrong_repair
                )

                # Stop after the unwanted write: later audit closure is a separate guard.
                class Repaired(RuntimeError):
                    pass

                async def repair_sentinel(repository, request):
                    await wrong_repair(repository, request)
                    raise Repaired("replay attempted to repair retained facts")

                patch.setattr(
                    SubmitterContributionRepository, "apply_acceptance_disposition", repair_sentinel
                )
                with pytest.raises(Repaired, match="replay attempted to repair"):
                    await apply_outcome(session, h, 2)
                assert len(repaired) == 1
                assert (
                    await session.scalar(text("SELECT id FROM public.contribution_records"))
                    == repaired[0]
                )
            await session.rollback()
        async with h.factory() as session:
            assert await outcome_snapshot(session) == retained
        async with h.factory() as session, session.begin():
            assert await apply_outcome(session, h, 2) == committed.model_copy(update={"replayed": True})
