"""Actual acceptance effects against authorized controller changes and shutdown."""

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, text

from app.db.session import get_session_factory
from app.modules.reviews.acceptance.repository import FinalAcceptanceRepository
from app.modules.reviews.api.acceptance import FinalAcceptanceConflict
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl
from tests.contributions.records.support import contribution_source
from tests.reviews.acceptance.participation_support import (
    participant, prepare_review_pending, request_for, stored_effects,
)
from tests.reviews.lifecycle.test_fence import observe_advisory_wait
from tests.reviews.lifecycle.transition_support import command_for, controller, transition


@pytest.mark.parametrize("instruments", [(), ("money",), ("money", "project_points")])
async def test_stopped_terminal_replay_is_select_only(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, instruments,
):
    access = live_acceptance_lifecycle
    async with contribution_source(
        tmp_path, isolated_database_env, contribution_awards=instruments, persist_acceptance=False,
    ) as h:
        await prepare_review_pending(h)
        request = await request_for(h)
        async with h.factory() as session, session.begin():
            original = await participant(session).participate(request)
        for phase in ("draining", "disabled"):
            receipt = await transition(await command_for(access.target.id, phase))
            engine = h.factory.kw["bind"].sync_engine
            writes = []

            def observe(_connection, _cursor, statement, _parameters, _context, _many):
                if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                    writes.append(statement)

            event.listen(engine, "before_cursor_execute", observe)
            try:
                async with h.factory() as session, session.begin():
                    replay = await participant(session).participate(
                        request.model_copy(update={"expected_generation": receipt.generation}),
                    )
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert replay == original
            assert writes == []
        # Source receipts are not implemented by this manifest. Preserve its
        # mechanically retained rows, and refuse to certify them for reactivation.
        await transition(await command_for(access.target.id, "shadow"))
        with pytest.raises(JointLifecycleUnavailable, match="pre-authority acceptance"):
            await transition(await command_for(access.target.id, "live"))
        async with h.factory() as session:
            facts = await stored_effects(session, h.acceptance.task_id)
            assert facts["acceptances"] == facts["contributions"] == 1
            assert facts["awards"] == len(instruments)


async def test_current_generation_cannot_admit_new_effects_when_stopped(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    access = live_acceptance_lifecycle
    async with contribution_source(tmp_path, isolated_database_env, persist_acceptance=False) as h:
        await prepare_review_pending(h)
        async with h.factory() as session:
            before = await stored_effects(session, h.acceptance.task_id)
        for phase in ("draining", "disabled", "shadow"):
            receipt = await transition(await command_for(access.target.id, phase))
            request = await request_for(h, expected_generation=receipt.generation)
            async with h.factory() as session:
                with pytest.raises(FinalAcceptanceConflict):
                    async with session.begin():
                        await participant(session).participate(request)
            async with h.factory() as session:
                assert await stored_effects(session, h.acceptance.task_id) == before, phase


async def test_operator_who_is_submitter_does_not_deadlock_prior_acceptance(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, monkeypatch,
):
    access = live_acceptance_lifecycle
    async with contribution_source(tmp_path, isolated_database_env, persist_acceptance=False) as h:
        await prepare_review_pending(h)
        await access.signed.grant(
            access.admin, SimpleNamespace(id=h.acceptance.accepted_submitter_id),
        )
        command = await command_for(h.acceptance.accepted_submitter_id, "draining")
        request = await request_for(h)
        reached, proceed = asyncio.Event(), asyncio.Event()
        original = FinalAcceptanceRepository.persist

        async def pause(owner, source, **kwargs):
            reached.set()
            await proceed.wait()
            return await original(owner, source, **kwargs)

        monkeypatch.setattr(FinalAcceptanceRepository, "persist", pause)

        async def accept():
            async with h.factory() as session, session.begin():
                return await participant(session).participate(request)

        pids = asyncio.Queue()

        async def stop():
            async with h.factory() as session, session.begin():
                await pids.put(await session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
                return await controller(session, command).transition(command)

        writer = asyncio.create_task(accept())
        stopper = None
        try:
            await asyncio.wait_for(reached.wait(), 10)
            stopper = asyncio.create_task(stop())
            pid = await asyncio.wait_for(pids.get(), 10)
            await observe_advisory_wait(h.factory, pid, stopper)
            proceed.set()
            accepted, stopped = await asyncio.wait_for(asyncio.gather(writer, stopper), 15)
            assert accepted.acceptance.id == h.acceptance.id
            assert stopped.phase == "draining"
        finally:
            proceed.set()
            pending = [task for task in (writer, stopper) if task is not None]
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        async with get_session_factory()() as session:
            control = await session.scalar(select(JointLifecycleReleaseControl))
            assert control.phase == "draining" and control.generation == 3
            facts = await stored_effects(session, h.acceptance.task_id)
            assert facts["acceptances"] == facts["contributions"] == 1


async def test_committed_transition_fences_waiting_acceptance(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    access = live_acceptance_lifecycle
    async with contribution_source(tmp_path, isolated_database_env, persist_acceptance=False) as h:
        await prepare_review_pending(h)
        request = await request_for(h)
        command = await command_for(access.target.id, "draining")
        async with h.factory() as session:
            before = await stored_effects(session, h.acceptance.task_id)
        async with h.factory() as stopper:
            await stopper.begin()
            stopped = await controller(stopper, command).transition(command)
            pids = asyncio.Queue()

            async def accept():
                async with h.factory() as session, session.begin():
                    await pids.put(await session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
                    return await participant(session).participate(request)

            writer = asyncio.create_task(accept())
            try:
                await observe_advisory_wait(h.factory, await pids.get(), writer)
                await stopper.commit()
                with pytest.raises(JointLifecycleUnavailable, match="generation changed"):
                    await asyncio.wait_for(writer, 10)
                # A fresh generation is still not permission for stopped effects.
                async with h.factory() as session, session.begin():
                    with pytest.raises(FinalAcceptanceConflict):
                        await participant(session).participate(request.model_copy(update={
                            "expected_generation": stopped.generation,
                        }))
            finally:
                await stopper.rollback()
                if not writer.done():
                    writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)
        async with h.factory() as session:
            assert await stored_effects(session, h.acceptance.task_id) == before


async def test_generation_zero_cannot_create_acceptance(tmp_path, isolated_database_env):
    async with contribution_source(tmp_path, isolated_database_env, persist_acceptance=False) as h:
        await prepare_review_pending(h)
        request = await request_for(h, expected_generation=0)
        async with h.factory() as session:
            before = await stored_effects(session, h.acceptance.task_id)
        async with h.factory() as session, session.begin():
            with pytest.raises(FinalAcceptanceConflict):
                await participant(session).participate(request)
        async with h.factory() as session:
            assert await stored_effects(session, h.acceptance.task_id) == before


@pytest.mark.parametrize("sequence", ["genesis", "stopped"])
async def test_each_owner_independently_rejects_new_effects(
    tmp_path, isolated_database_env, admin_access, sequence,
):
    from unittest.mock import AsyncMock

    from app.modules.contributions.api import ContributionParticipationUnavailable
    from app.modules.reviews.acceptance.participant import FinalAcceptanceParticipant
    from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
    from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
    from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsUnavailable, TaskAcceptedPreparation
    from tests.contributions.participation.support import participant as contribution_participant
    from tests.contributions.participation.support import request_for as contribution_request

    await admin_access.signed.grant(admin_access.admin, admin_access.target)
    generation = 0
    if sequence == "stopped":
        await transition(await command_for(admin_access.target.id, "shadow"))
        await transition(await command_for(admin_access.target.id, "live"))
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        await prepare_review_pending(h)
        phases = ("disabled", "shadow") if sequence == "genesis" else ("draining", "disabled", "shadow")
        for phase in phases:
            if not (sequence == "genesis" and phase == "disabled"):
                generation = (await transition(await command_for(admin_access.target.id, phase))).generation
            request = await request_for(h, expected_generation=generation)
            async with h.factory() as session:
                before = await stored_effects(session, h.acceptance.task_id)
            async with h.factory() as session, session.begin():
                task = TaskAcceptedEffectsParticipant(session, fence=PostgresJointLifecycleMutationFence(session))
                with pytest.raises(TaskAcceptedEffectsUnavailable, match="lifecycle is not live"):
                    await task.lock_accepted_effects(request.task_effects, expected_generation=generation)
            async with h.factory() as session, session.begin():
                with pytest.raises(ContributionParticipationUnavailable, match="lifecycle is not live"):
                    await contribution_participant(session).participate_submitter(contribution_request(
                        h, acceptance_disposition="new", expected_generation=generation,
                    ))
            async with h.factory() as session, session.begin():
                # Isolate REV's own check: TASK supplies a correctly shaped new
                # preparation; neither TASK nor CON can mask a missing REV gate.
                tasks = SimpleNamespace(lock_accepted_effects=AsyncMock(return_value=TaskAcceptedPreparation(
                    disposition="new", locked_review_policy_id=request.acceptance.policy_context_ref,
                )))
                owner = FinalAcceptanceParticipant(
                    session, fence=PostgresJointLifecycleMutationFence(session),
                    tasks=tasks, contributions=AsyncMock(),
                )
                owner._repository.persist = AsyncMock(side_effect=AssertionError("REV reached persistence"))
                with pytest.raises(FinalAcceptanceConflict, match="lifecycle is not live"):
                    await owner.participate(request)
                owner._repository.persist.assert_not_awaited()
            async with h.factory() as session:
                assert await stored_effects(session, h.acceptance.task_id) == before
