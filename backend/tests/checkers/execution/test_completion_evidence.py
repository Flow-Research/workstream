"""Current stored failure evidence without TASK routing or mutation authority."""

import json
from uuid import UUID

import pytest

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, VerifiedMaterialFacts
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationResult
from app.modules.checkers.models import CheckerSubmissionFence
from tests.checkers.post_submit.support import change_request
from .completion_fixture import completed_evidence, evidence_snapshot
from .support import reserve


async def verify(session, h, *, completion=None, event_id=None):
    return await evaluation_coordinator(session).require_current_completion(
        event_id or h.source["completion_event_id"], completion or h.completion,
    )


@pytest.mark.parametrize("recommendation", ["allow_review", "needs_revision", "task_setup_blocked"])
async def test_current_completion_returns_exact_stored_result(tmp_path, isolated_database_env, recommendation):
    async with completed_evidence(tmp_path, isolated_database_env, recommendation) as h:
        async with h.factory() as session:
            await session.begin()
            before = await evidence_snapshot(session)
            actual = await verify(session, h)
            assert actual.result == h.result == PostSubmissionEvaluationResult.model_validate_json(
                json.dumps(json.loads(h.run.result_json) | {"result_digest": h.run.result_digest})
            )
            assert actual.completion == h.completion
            assert actual.submission_version == h.request.submission_version
            assert actual.material == VerifiedMaterialFacts.model_validate_json(json.dumps(h.run.material_custody))
            assert actual.input_materialization_evidence_id == UUID(h.run.input_materialization_evidence_id)
            assert actual.completion.execute_evidence_id == UUID(h.run.execute_evidence_id)
            assert actual.completion.finalize_evidence_id == UUID(h.run.finalize_evidence_id)
            assert await evidence_snapshot(session) == before
            await session.rollback()
        async with h.factory() as session, session.begin():
            assert await verify(session, h) == actual
            assert await evidence_snapshot(session) == before


async def test_current_completion_preserves_nonempty_stored_counters(tmp_path, isolated_database_env):
    async with completed_evidence(tmp_path, isolated_database_env, counters=True) as h:
        async with h.factory() as session, session.begin():
            actual = await verify(session, h)
            stored = PostSubmissionEvaluationResult.model_validate_json(
                json.dumps(json.loads(h.run.result_json) | {"result_digest": h.run.result_digest})
            )
            assert any(m.counters for m in stored.member_results), "fixture must discriminate dropped counters"
            assert actual.result == stored == h.result
            failed = next(m for m in actual.result.member_results if m.status == "failed")
            assert [(c.key, c.value) for c in failed.counters] == [("missing_count", 2)]


@pytest.mark.parametrize("recommendation", ["allow_review", "needs_revision", "task_setup_blocked"])
async def test_current_completion_rejects_wrong_derived_recommendation(tmp_path, isolated_database_env, recommendation):
    async with completed_evidence(tmp_path, isolated_database_env, recommendation) as h:
        async with h.factory() as session, session.begin():
            await verify(session, h)
            before = await evidence_snapshot(session)
            for wrong in {"allow_review", "needs_revision", "task_setup_blocked"} - {recommendation}:
                altered = h.completion.model_copy(update={"routing_recommendation": wrong})
                with pytest.raises(CheckerExecutionUnavailable, match="checker_current_completion_unavailable"):
                    await verify(session, h, completion=altered)
                assert await evidence_snapshot(session) == before


async def test_failure_completion_rejects_foreign_owner_and_receipts(tmp_path, isolated_database_env):
    async with completed_evidence(tmp_path / "one", isolated_database_env) as h:
        async with completed_evidence(tmp_path / "two", isolated_database_env,
                                      provision_services=False, storage_settings=h.settings) as foreign:
            async with h.factory() as session, session.begin():
                await verify(session, h)
                await verify(session, foreign)
                before = await evidence_snapshot(session)
                for field in ("event_id", "project_id", "task_id", "submission_id", "reference",
                              "execute_evidence_id", "finalize_evidence_id"):
                    kwargs = (
                        {"event_id": foreign.source["completion_event_id"]} if field == "event_id" else
                        {"completion": h.completion.model_copy(update={field: getattr(foreign.completion, field)})}
                    )
                    with pytest.raises(CheckerExecutionUnavailable, match="checker_current_completion_unavailable"):
                        await verify(session, h, **kwargs)
                    assert await evidence_snapshot(session) == before


async def test_failure_completion_loses_currentness_to_successor(tmp_path, isolated_database_env):
    async with completed_evidence(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            await verify(session, h)
        successor = change_request(h.request, evaluation_request_id=new_record_id(), evaluation_generation=2)
        reserved = await reserve(h, successor)
        async with h.factory() as session, session.begin():
            before = await evidence_snapshot(session)
            with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
                await verify(session, h)
            assert await evidence_snapshot(session) == before
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(reserved.attempt_id)
