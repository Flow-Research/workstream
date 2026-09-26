"""Phase delegation and removed JSON precheck; no fake post execution custody."""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError

from app.adapters.artifacts import CheckerPhaseService
from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidencePersistenceResult
from app.modules.checkers.api import (
    PostSubmissionExecutionUnavailable, UnavailablePostSubmissionExecution,
)
from tests.checkers.post_submit.support import OTHER_HASH, request
from tests.checkers.post_submit.test_result_contract import result


def phases(pre=None, post=None):
    return CheckerPhaseService(
        pre_submission=pre if pre is not None else SimpleNamespace(execute_reserved=AsyncMock()),
        post_submission=post if post is not None else UnavailablePostSubmissionExecution(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("replay", (False, True))
async def test_pre_phase_preserves_owner_result_and_pass_capability(replay):
    capability = None if replay else object()
    canonical = PreSubmitEvidencePersistenceResult(
        evidence=object(), execution=object(), pass_capability=capability, failure_audit=None,
    )
    owner = SimpleNamespace(execute_reserved=AsyncMock(return_value=canonical))
    material = SimpleNamespace(prepared_authorization=None)
    preparation = object()
    selection = canonical if replay else object()
    actual = await phases(pre=owner).evaluate_pre_submission(
        material, selection, preparation_request=preparation,
    )
    assert actual is canonical
    assert actual.pass_capability is capability
    if replay:
        owner.execute_reserved.assert_not_awaited()
    else:
        owner.execute_reserved.assert_awaited_once_with(
            material, selection, preparation_request=preparation,
        )


@pytest.mark.asyncio
async def test_pre_phase_rejects_authorization_handle_and_propagates_owner_failure():
    owner = SimpleNamespace(execute_reserved=AsyncMock(side_effect=RuntimeError("unresolved")))
    service = phases(pre=owner)
    with pytest.raises(ValueError, match="requires_consumed_authorization"):
        await service.evaluate_pre_submission(
            SimpleNamespace(prepared_authorization=object()), object(), preparation_request=object(),
        )
    owner.execute_reserved.assert_not_awaited()
    with pytest.raises(RuntimeError, match="^unresolved$"):
        await service.evaluate_pre_submission(
            SimpleNamespace(prepared_authorization=None), object(), preparation_request=object(),
        )
    owner.execute_reserved.assert_awaited_once()


@pytest.mark.asyncio
async def test_valid_post_phase_stays_unavailable_without_invoking_pre_owner():
    owner = SimpleNamespace(execute_reserved=AsyncMock())
    with pytest.raises(PostSubmissionExecutionUnavailable, match="^post_submit_execution_unavailable$"):
        await phases(pre=owner).evaluate_post_submission(request())
    owner.execute_reserved.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", (None, "request", "digest", "generation", "members"))
async def test_post_phase_validates_exact_delegated_result(damage):
    source = request()
    changes = {}
    if damage == "request":
        changes["request_id"] = new_record_id()
    elif damage == "digest":
        changes["request_digest"] = OTHER_HASH
    elif damage == "generation":
        changes["evaluation_generation"] = 2
    elif damage == "members":
        changes["member_results"] = result(source).member_results[:-1]
    completed = result(source, **changes)
    executor = SimpleNamespace(evaluate_post_submission=AsyncMock(return_value=completed))
    service = phases(post=executor)
    if damage is None:
        assert await service.evaluate_post_submission(source) == completed
    else:
        with pytest.raises(ValueError, match="post-submit result .* mismatch"):
            await service.evaluate_post_submission(source)
    executor.evaluate_post_submission.assert_awaited_once_with(source)


@pytest.mark.asyncio
async def test_invalid_post_request_never_reaches_executor():
    executor = SimpleNamespace(evaluate_post_submission=AsyncMock())
    source = request().model_copy(update={"project_id": new_record_id()})
    with pytest.raises(ValidationError, match="project mismatch"):
        await phases(post=executor).evaluate_post_submission(source)
    executor.evaluate_post_submission.assert_not_awaited()


def test_two_phase_commands_and_no_draft_packet_precheck_route():
    from app.main import create_app
    from app.modules.checkers import runner

    assert [name for name, method in inspect.getmembers(CheckerPhaseService, inspect.isfunction)
            if not name.startswith("_")] == ["evaluate_post_submission", "evaluate_pre_submission"]
    app = create_app()
    assert all("submission-precheck" not in getattr(route, "path", "") for route in app.routes)
    schema = app.openapi()
    assert all("submission-precheck" not in path for path in schema["paths"])
    for name in ("PreSubmitCheckRequest", "PreSubmitCheckResponse", "CheckerFeedbackItem"):
        assert name not in schema["components"]["schemas"]
    assert not hasattr(runner, "pre_submit_static_feedback")
