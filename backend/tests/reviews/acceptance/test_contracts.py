"""Closed acceptance source shapes do not imply authority."""

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.reviews.api.acceptance import FinalAcceptanceInput


def values(source="human_review"):
    return dict(
        **{
            name: new_record_id()
            for name in (
                "id",
                "project_id",
                "task_id",
                "submission_id",
                "accepted_submitter_id",
                "recorded_by",
                "policy_context_ref",
                "source_authorization_decision_id",
            )
        },
        acceptance_source=source,
        source_review_id=new_record_id() if source == "human_review" else None,
        source_routing_manifest_id=new_record_id() if source == "task_post_submit_route" else None,
    )


@pytest.mark.parametrize("source", ["human_review", "task_post_submit_route"])
def test_closed_source_contract(source):
    expected = values(source)
    actual = FinalAcceptanceInput(**expected)
    assert actual.model_dump() == expected
    with pytest.raises(ValidationError, match="frozen_instance"):
        actual.task_id = new_record_id()
    for field in ("authority", "authorization_decision_event_id", "accepted_at", "reviewer_id"):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            FinalAcceptanceInput(**expected, **{field: new_record_id()})
    for field, value in expected.items():
        if field == "acceptance_source" or value is None:
            continue
        with pytest.raises(ValidationError):
            FinalAcceptanceInput(**{**expected, field: str(value)})


@pytest.mark.parametrize("source", ["human_review", "task_post_submit_route"])
@pytest.mark.parametrize("shape", ["missing", "both", "opposite", "unknown"])
def test_exclusive_source_contract(source, shape):
    data = values(source)
    if shape == "unknown":
        data["acceptance_source"] = "unknown"
    elif shape == "opposite":
        data["acceptance_source"] = (
            "human_review" if source == "task_post_submit_route" else "task_post_submit_route"
        )
    else:
        data["source_review_id"] = new_record_id() if shape == "both" else None
        data["source_routing_manifest_id"] = new_record_id() if shape == "both" else None
    with pytest.raises(ValidationError):
        FinalAcceptanceInput(**data)
