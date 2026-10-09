"""Pure contract proof for the detached post-submit routing source."""

from inspect import isclass

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import (ActionId, PermissionId, ActionAvailability, ACTION_BY_ID, SERVICE_ACTIONS_BY_IDENTITY, resolve_executable_action)
from app.modules.tasks import api as task_api
from app.modules.tasks.api import post_submit_routing
from app.modules.tasks.api.post_submit_routing import TaskPostSubmitManifestFacts
from tests.tasks.post_submit_routing.contract_fixtures import _lineage, _source_values


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("id", str(new_record_id())),
        ("created_at", "2026-01-02T00:00:00Z"),
        ("submission_version", "1"),
        ("evaluation_generation", True),
        ("request_digest", "a" * 64),
        ("human_review_required", 1),
        ("byte_count", False),
        ("routing_recommendation", "needs_revision"),
    ),
)
def test_source_contract_is_strict_and_detached(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        TaskPostSubmitManifestFacts(**_source_values(**{field: value}))

    valid = _source_values()
    valid["private_provider_key"] = "must-not-cross-owner-boundary"
    with pytest.raises(ValidationError):
        TaskPostSubmitManifestFacts(**valid)


def test_source_contract_is_an_exact_frozen_value() -> None:
    source = TaskPostSubmitManifestFacts(**_source_values())

    with pytest.raises(ValidationError):
        source.human_review_required = False

    assert set(TaskPostSubmitManifestFacts.model_fields) == {
        "id",
        "created_at",
        "project_id",
        "task_id",
        "submission_id",
        "submission_version",
        "assignment_id",
        "contributor_id",
        "contribution_policy_version_id",
        "checker_run_id",
        "evaluation_request_id",
        "request_digest",
        "evaluation_generation",
        "result_id",
        "result_digest",
        "completion_event_id",
        "creation_decision_id",
        "binding_decision_id",
        "input_materialization_evidence_id",
        "execute_evidence_id",
        "finalize_evidence_id",
        "human_review_required",
        "replica_id",
        "content_sha256",
        "byte_count",
        "semantic_manifest_sha256",
        "predecessor_submission_id",
        "predecessor_submission_version",
        "admission_id",
        "binding_id",
        "content_id",
        "locked_policy",
        "routing_recommendation",
    }


def test_source_rejects_nested_lineage_mismatch() -> None:
    with pytest.raises(ValidationError, match="contribution policy lineage differs"):
        TaskPostSubmitManifestFacts(
            **_source_values(locked_policy=_lineage(contribution_policy_version_id=new_record_id()))
        )


@pytest.mark.parametrize("successor", (False, True))
def test_source_rejects_equal_phase_receipts(successor: bool) -> None:
    receipt_id = new_record_id()
    changes: dict[str, object] = {
        "execute_evidence_id": receipt_id,
        "finalize_evidence_id": receipt_id,
    }
    if successor:
        changes.update(
            submission_version=2,
            predecessor_submission_id=new_record_id(),
            predecessor_submission_version=1,
        )

    with pytest.raises(ValidationError, match="phase receipts are not distinct"):
        TaskPostSubmitManifestFacts(**_source_values(**changes))


@pytest.mark.parametrize(
    "changes",
    (
        {"predecessor_submission_id": new_record_id()},
        {"predecessor_submission_version": 1},
        {
            "submission_version": 1,
            "predecessor_submission_id": new_record_id(),
            "predecessor_submission_version": 1,
        },
        {"submission_version": 2},
        {
            "submission_version": 3,
            "predecessor_submission_id": new_record_id(),
            "predecessor_submission_version": 1,
        },
    ),
)
def test_source_rejects_inconsistent_predecessor_shape(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="predecessor"):
        TaskPostSubmitManifestFacts(**_source_values(**changes))


def test_source_accepts_exact_immediate_predecessor() -> None:
    predecessor_id = new_record_id()
    source = TaskPostSubmitManifestFacts(
        **_source_values(
            submission_version=2,
            predecessor_submission_id=predecessor_id,
            predecessor_submission_version=1,
        )
    )

    assert source.predecessor_submission_id == predecessor_id
    assert source.predecessor_submission_version == source.submission_version - 1


def test_source_rejects_its_own_submission_as_predecessor() -> None:
    submission_id = new_record_id()
    with pytest.raises(ValidationError, match="predecessor equals submission"):
        TaskPostSubmitManifestFacts(
            **_source_values(
                submission_id=submission_id,
                submission_version=2,
                predecessor_submission_id=submission_id,
                predecessor_submission_version=1,
            )
        )


def test_false_source_value_is_transport_only() -> None:
    source = TaskPostSubmitManifestFacts(**_source_values(human_review_required=False))

    assert source.human_review_required is False
    assert source.model_dump(mode="json")["human_review_required"] is False


def test_routing_authority_has_no_public_or_delivery_entry() -> None:
    assert post_submit_routing.__all__ == (
        "TaskPostSubmitSourceProposal", "TaskPostSubmitManifestFacts", "task_post_submit_source_digest",
        "TaskRoutingSelection", "TaskRoutingRequestFacts", "task_routing_request_digest",
        "TaskRoutingSourcePreparation",
    )
    for name in post_submit_routing.__all__:
        assert getattr(task_api, name) is getattr(post_submit_routing, name)

    assert {
        name
        for name, value in vars(post_submit_routing).items()
        if isclass(value) and value.__module__ == post_submit_routing.__name__
    } == {"TaskPostSubmitSourceProposal", "TaskPostSubmitManifestFacts", "TaskRoutingSelection", "TaskRoutingRequestFacts", "TaskRoutingSourcePreparation"}
    assert not hasattr(task_api, "TaskRoutingRequests")
    action = ActionId.TASK_POST_SUBMIT_ROUTE
    assert ACTION_BY_ID[action].permission_id is PermissionId.TASK_POST_SUBMIT_ROUTE
    assert ACTION_BY_ID[action].availability is ActionAvailability.ACTIVE
    assert SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.TASK_POST_SUBMIT_ROUTER] == {action}
    assert resolve_executable_action(action).action_id is action


@pytest.mark.parametrize("human_review_required", [True, False])
def test_proposal_has_no_persisted_timestamp(human_review_required):
    values = _source_values(human_review_required=human_review_required)
    source = post_submit_routing.TaskPostSubmitSourceProposal(
        **{key: value for key, value in values.items() if key != "created_at"}
    )
    assert source.human_review_required is human_review_required
    assert "created_at" not in source.model_dump()
    with pytest.raises(ValidationError, match="Extra inputs"):
        post_submit_routing.TaskPostSubmitSourceProposal(**values)
    with pytest.raises(ValidationError, match="created_at"):
        TaskPostSubmitManifestFacts(**source.model_dump())
