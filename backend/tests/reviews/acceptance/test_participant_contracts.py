"""Closed shared effects and structural exclusion from production composition."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.reviews.api.acceptance import FinalAcceptanceInput
from app.modules.reviews.api.acceptance import FinalAcceptanceRequest
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest
from tests.reviews.acceptance.test_contracts import values


def request():
    source = FinalAcceptanceInput(**values())
    return FinalAcceptanceRequest(
        acceptance=source,
        task_effects=TaskAcceptedEffectsRequest(
            project_id=source.project_id, task_id=source.task_id,
            assignment_id=new_record_id(), submission_id=source.submission_id,
            submission_version=1, contributor_id=source.accepted_submitter_id,
            contribution_policy_version_id=new_record_id(), content_id=new_record_id(),
            content_sha256="sha256:" + "a" * 64, final_acceptance_id=source.id,
            expected_task_status="review_pending",
        ), correlation_id=new_record_id(), expected_generation=0,
    )


@pytest.mark.parametrize(
    "field",
    [
        "project_id",
        "task_id",
        "submission_id",
        "contributor_id",
        "final_acceptance_id",
        "expected_task_status",
        "submission_version",
        "content_sha256",
    ],
)
async def test_inconsistent_nested_effects_reject_before_any_owner(field):
    original = request()
    replacement = {
        "expected_task_status": "evaluation_pending", "submission_version": True,
        "content_sha256": "not-a-hash",
    }.get(field, new_record_id())
    forged = original.model_copy(update={
        "task_effects": original.task_effects.model_copy(update={field: replacement}),
    })
    with pytest.raises(ValidationError):
        FinalAcceptanceRequest.model_validate(forged)
    # Closed request validation is pure. Live prepared-capability rejection and
    # absence of effects are proved through the PostgreSQL outcome operation.


@pytest.mark.parametrize(
    "change",
    [
        {"expected_generation": True},
        {"expected_generation": -1},
        {"correlation_id": str(new_record_id())},
        {"authorized": True},
    ],
)
def test_shared_request_rejects_coercion_and_extra_authority(change):
    with pytest.raises(ValidationError):
        FinalAcceptanceRequest(**(request().model_dump() | change))


def test_automated_source_transport_requires_evaluation_prestate_without_review():
    original = request()
    source = original.acceptance.model_copy(update={
        "acceptance_source": "task_post_submit_route",
        "source_review_id": None,
        "source_routing_manifest_id": new_record_id(),
    })
    automated = FinalAcceptanceRequest.model_validate(original.model_copy(update={
        "acceptance": source,
        "task_effects": original.task_effects.model_copy(update={
            "expected_task_status": "evaluation_pending",
        }),
    }))
    assert automated.acceptance.source_review_id is None
    with pytest.raises(ValidationError, match="acceptance effect lineage differs"):
        FinalAcceptanceRequest.model_validate(automated.model_copy(update={
            "task_effects": original.task_effects,
        }))


def test_acceptance_composition_is_confined_to_routing_adapter():
    app_root = Path(__file__).resolve().parents[3] / "app"
    participant_path = app_root / "modules/reviews/acceptance/participant.py"
    found_definition = False
    for path in app_root.rglob("*.py"):
        if path == app_root / "adapters/reviews/__init__.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "FinalAcceptanceParticipant":
                assert path == participant_path
                found_definition = True
            if isinstance(node, ast.ImportFrom):
                assert node.module != "app.modules.reviews.acceptance.participant", str(path)
                assert all(alias.name != "FinalAcceptanceParticipant" for alias in node.names), str(path)
                if node.level and node.module in {"participant", "acceptance.participant"}:
                    assert "reviews" not in path.parts, str(path)
            if isinstance(node, ast.Import):
                assert all(
                    alias.name != "app.modules.reviews.acceptance.participant"
                    for alias in node.names
                ), str(path)
            if isinstance(node, ast.Call):
                called = node.func
                assert not (
                    isinstance(called, ast.Name) and called.id == "FinalAcceptanceParticipant"
                    or isinstance(called, ast.Attribute) and called.attr == "FinalAcceptanceParticipant"
                ), str(path)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in {
                    "app.modules.reviews.acceptance.participant",
                    "app.modules.reviews.acceptance.participant.FinalAcceptanceParticipant",
                }, str(path)
    assert found_definition
    assert ACTION_BY_ID[ActionId.REVIEW_DECISION].availability is ActionAvailability.PLANNED
    assert ACTION_BY_ID[ActionId.TASK_POST_SUBMIT_ROUTE].availability is ActionAvailability.ACTIVE
