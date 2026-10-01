"""Caller transactions and exact request identity, including valid foreign facts."""

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, CheckerRequestConflict
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.models import CheckerRun, CheckerSubmissionFence
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture
from .support import reserve, live_executor


async def test_reservation_replay_rejects_changed_envelope(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        first = await reserve(h)
        assert await reserve(h) == first
        changed = change_request(h.request, assignment_id=new_record_id())
        with pytest.raises(CheckerRequestConflict, match="checker_request_conflict"):
            await reserve(h, changed)
        async with h.factory() as session:
            assert list(await session.scalars(select(CheckerRun.id))) == [str(first.attempt_id)]
        async with h.factory() as session, session.begin():
            async with session.begin_nested():
                with pytest.raises(CheckerExecutionUnavailable, match="caller_transaction"):
                    await EvaluationCoordinator(session).reserve_current_evaluation(h.request)
        with pytest.raises(CheckerExecutionUnavailable, match="caller_transaction"):
            async with h.factory() as session:
                await EvaluationCoordinator(session).reserve_current_evaluation(h.request)


async def test_reservation_rollback_and_exact_successor(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        first = await reserve(h)
        next_request = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=2
        )
        async with h.factory() as session:
            await session.begin()
            second = await EvaluationCoordinator(session).reserve_current_evaluation(next_request)
            assert second.attempt_id != first.attempt_id
            await session.rollback()
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(first.attempt_id)
            assert await session.get(CheckerRun, str(second.attempt_id)) is None
        second = await reserve(h, next_request)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(second.attempt_id))
            assert run.supersedes_checker_run_id == str(first.attempt_id)
        # Replaying old reservation does not restore it as current.
        assert await reserve(h) == first
        with pytest.raises(CheckerExecutionUnavailable, match="current_request"):
            await live_executor(h).evaluate_post_submission(h.request)


@pytest.mark.parametrize(
    "field", ["project_id", "task_id", "submission_id", "evaluation_request_id"]
)
async def test_current_result_conceals_foreign_lineage(tmp_path, isolated_database_env, field):
    async with material_fixture(tmp_path / "first", isolated_database_env) as first:
        await reserve(first)
        await live_executor(first).evaluate_post_submission(first.request)
        async with material_fixture(
            tmp_path / "foreign",
            isolated_database_env,
            provision_services=False,
            storage_settings=first.settings,
        ) as foreign:
            await reserve(foreign)
            await live_executor(foreign).evaluate_post_submission(foreign.request)
            if field == "project_id":
                # A project substitution must carry a matching valid policy/context,
                # so validation succeeds and the repository owns the isolation proof.
                bad = change_request(
                    foreign.request,
                    task_id=first.request.task_id,
                    submission_id=first.request.submission_id,
                    evaluation_request_id=first.request.evaluation_request_id,
                )
            else:
                bad = change_request(first.request, **{field: getattr(foreign.request, field)})
            async with first.factory() as session, session.begin():
                valid = await EvaluationCoordinator(session).read_current_result(first.request)
                assert valid.reference.request_id == first.request.evaluation_request_id
                with pytest.raises(CheckerExecutionUnavailable, match="current_request"):
                    await EvaluationCoordinator(session).read_current_result(bad)
