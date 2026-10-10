"""Strict public contract and hidden-construction proof."""

from inspect import iscoroutinefunction

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.tasks import api as task_api
from app.modules.tasks.api import accepted_effects
from app.modules.tasks.api import (
    TaskAcceptedEffectsFence,
    TaskAcceptedEffectsPort,
    TaskAcceptedEffectsRequest,
    TaskAcceptedEffectsResult,
    TaskAcceptedEffectsUnavailable,
    TaskAcceptedPreparation,
)

SHA = "sha256:" + "a" * 64


def values(**changes):
    result = {
        "project_id": new_record_id(),
        "task_id": new_record_id(),
        "assignment_id": new_record_id(),
        "submission_id": new_record_id(),
        "submission_version": 1,
        "contributor_id": new_record_id(),
        "contribution_policy_version_id": new_record_id(),
        "content_id": new_record_id(),
        "content_sha256": SHA,
        "final_acceptance_id": new_record_id(),
        "expected_task_status": "evaluation_pending",
    }
    result.update(changes)
    return result


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("project_id", str(new_record_id())),
        ("submission_version", "1"),
        ("submission_version", True),
        ("content_sha256", "sha256:" + "A" * 64),
        ("expected_task_status", "accepted"),
        ("routing_manifest_id", new_record_id()),
    ),
)
def test_request_is_strict(field, value):
    with pytest.raises(ValidationError):
        TaskAcceptedEffectsRequest(**values(**{field: value}))


def test_two_phase_contract_is_exact_and_concrete_participant_is_hidden():
    request = TaskAcceptedEffectsRequest(**values())
    preparation = TaskAcceptedPreparation(
        disposition="new", locked_review_policy_id=new_record_id()
    )
    result = TaskAcceptedEffectsResult(
        request=request, task_status="accepted", assignment_status="completed"
    )

    assert preparation.disposition == "new"
    assert result.request == request
    assert set(TaskAcceptedEffectsRequest.model_fields) == set(values())
    assert set(TaskAcceptedEffectsResult.model_fields) == {
        "request", "task_status", "assignment_status",
    }
    assert set(TaskAcceptedPreparation.model_fields) == {
        "disposition", "locked_review_policy_id",
    }
    for model, field, value in (
        (request, "expected_task_status", "review_pending"),
        (result, "task_status", "review_pending"),
        (preparation, "disposition", "replay"),
    ):
        with pytest.raises(ValidationError, match="frozen_instance"):
            setattr(model, field, value)
    for change in (
        {"task_status": "review_pending"},
        {"assignment_status": "accepted"},
        {"review_id": new_record_id()},
    ):
        with pytest.raises(ValidationError):
            TaskAcceptedEffectsResult(**(result.model_dump() | change))
    assert accepted_effects.__all__ == (
        "TaskAcceptedEffectsPort", "TaskAcceptedEffectsFence", "TaskAcceptedPreparation",
        "TaskAcceptedEffectsRequest", "TaskAcceptedEffectsResult", "TaskAcceptedEffectsUnavailable",
    )
    for name in accepted_effects.__all__:
        assert getattr(task_api, name) is getattr(accepted_effects, name)
    assert iscoroutinefunction(TaskAcceptedEffectsPort.lock_accepted_effects)
    assert iscoroutinefunction(TaskAcceptedEffectsPort.apply_accepted_effects)
    assert iscoroutinefunction(TaskAcceptedEffectsPort.require_routing_source)
    assert iscoroutinefunction(TaskAcceptedEffectsFence.acquire)
    assert issubclass(TaskAcceptedEffectsUnavailable, RuntimeError)
    assert not hasattr(task_api, "TaskAcceptedEffectsParticipant")
    for value in (
        {"disposition": "pending", "locked_review_policy_id": new_record_id()},
        {"disposition": "new", "locked_review_policy_id": str(new_record_id())},
    ):
        with pytest.raises(ValidationError):
            TaskAcceptedPreparation(**value)


def test_nested_request_instances_are_revalidated():
    request = TaskAcceptedEffectsRequest(**values())
    object.__setattr__(request, "expected_task_status", "accepted")

    with pytest.raises(ValidationError):
        TaskAcceptedEffectsResult(
            request=request,
            task_status="accepted",
            assignment_status="completed",
        )
