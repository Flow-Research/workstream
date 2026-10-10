"""Exact inert source projection and detached receipt substitution boundaries."""

from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.authorization.acceptance_source_contracts import routing_source_commitment
from app.modules.authorization.api.acceptance_source import (
    AcceptanceSourceReceiptFacts,
    acceptance_source_commitment_digest,
)
from app.modules.authorization.review_contracts import ReviewDecisionContract, ReviewDecisionValue
from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitManifestFacts,
    task_post_submit_source_digest,
)
from tests.authorization.review_contract_fixtures import _decision_values
from tests.tasks.post_submit_routing.contract_fixtures import _source_values, SHA_A, SHA_B


def _source(kind):
    if kind == "human":
        return ReviewDecisionContract(**_decision_values()).source_commitment()
    return routing_source_commitment(
        TaskPostSubmitManifestFacts(**_source_values(human_review_required=kind == "route_true")),
        route_operation_id=new_record_id(),
        route_request_digest=SHA_B,
    )


def _receipt_values(source):
    human = source.source == "human_review"
    operation = source.operation_id if human else source.route_operation_id
    action = "review.decision" if human else "task.post_submit.route"
    return dict(
        authorization_decision_event_id=new_record_id(),
        action_id=action,
        permission_id=action,
        actor_profile_id=source.reviewer_id if human else new_record_id(),
        actor_identity_link_id=new_record_id(),
        service_identity=None if human else "workstream.task.post_submit_router",
        matched_grant_id=new_record_id() if human else None,
        project_id=source.project_id,
        resource_type="review" if human else "task_post_submit_routing_manifest",
        resource_id=source.review_id if human else source.routing_manifest_id,
        request_id=operation,
        correlation_id=operation,
        resource_context_digest=SHA_A,
        source=source,
        source_commitment_digest=acceptance_source_commitment_digest(source),
    )


def test_human_projection_matches_retained_source_fields():
    values = _decision_values()
    source = ReviewDecisionContract(**values).source_commitment()
    mapping = {
        "review_queue_entry_id": "queue_entry_id",
        "reviewer_id": "reviewer_actor_profile_id",
        "locked_review_policy_id": "review_policy_id",
        "locked_review_policy_generation": "review_policy_generation",
        "locked_review_policy_hash": "review_policy_digest",
        "operation_id": "review_operation_id",
    }
    assert source.model_dump(exclude={"source"}) == {
        name: values[mapping.get(name, name)]
        for name in type(source).model_fields
        if name != "source"
    }
    original = acceptance_source_commitment_digest(source)
    rejected = ReviewDecisionContract(
        **(values | {"decision": ReviewDecisionValue.REJECT})
    ).source_commitment()
    assert rejected.decision == "reject"
    assert acceptance_source_commitment_digest(rejected) != original
    for name in type(source).model_fields:
        if name in {"source", "decision"}:
            continue
        input_name = mapping.get(name, name)
        value = values[input_name]
        changed = (
            new_record_id() if type(value) is UUID else value + 1 if type(value) is int else SHA_B
        )
        projected = ReviewDecisionContract(**(values | {input_name: changed})).source_commitment()
        assert acceptance_source_commitment_digest(projected) != original, name


@pytest.mark.parametrize("human_review_required", (True, False))
def test_route_projection_and_digest_bind_complete_reconstructed_source(human_review_required):
    values = _source_values(
        human_review_required=human_review_required,
        submission_version=2,
        predecessor_submission_id=new_record_id(),
        predecessor_submission_version=1,
    )
    facts = TaskPostSubmitManifestFacts(**values)
    digest = task_post_submit_source_digest(facts)
    assert digest == canonical_json_hash(
        {
            "domain": "workstream.task_post_submit_source.v0.1",
            "source": facts.model_dump(mode="json", exclude={"created_at"}),
        }
    )
    assert (
        task_post_submit_source_digest(
            TaskPostSubmitManifestFacts(
                **(
                    values
                    | {
                        "created_at": values["created_at"] + timedelta(days=1),
                    }
                )
            )
        )
        == digest
    )
    operation = new_record_id()
    source = routing_source_commitment(
        facts, route_operation_id=operation, route_request_digest=SHA_B
    )
    mapping = {"routing_manifest_id": "id"}
    policy = facts.locked_policy.model_dump()
    for name in type(source).model_fields:
        if name in {
            "source",
            "routing_source_digest",
            "route_operation_id",
            "route_request_digest",
        }:
            continue
        expected = (
            policy[name]
            if name.startswith("locked_review_policy_")
            else values[mapping.get(name, name)]
        )
        assert getattr(source, name) == expected, name
    assert source.routing_source_digest == digest
    for name, value in values.items():
        if name == "created_at":
            continue
        if name == "locked_policy":
            changed = value.model_copy(update={"locked_review_policy_hash": SHA_B})
        elif type(value) is UUID:
            changed = new_record_id()
        elif type(value) is bool:
            changed = not value
        elif type(value) is int:
            changed = value + 1
        elif value == "allow_review":
            # This closed field has no second valid value.
            with pytest.raises(ValidationError):
                TaskPostSubmitManifestFacts(**(values | {name: "accept"}))
            continue
        else:
            changed = SHA_B if value == SHA_A else SHA_A
        altered = values | {name: changed}
        if name == "contribution_policy_version_id":
            altered["locked_policy"] = facts.locked_policy.model_copy(
                update={"locked_contribution_policy_version_id": changed}
            )
        if name == "submission_version":
            altered["predecessor_submission_version"] = changed - 1
        if name == "predecessor_submission_version":
            altered["submission_version"] = changed + 1
        assert task_post_submit_source_digest(TaskPostSubmitManifestFacts(**altered)) != digest, (
            name
        )
    with pytest.raises(ValidationError, match="routing operation must differ"):
        routing_source_commitment(
            facts, route_operation_id=facts.evaluation_request_id, route_request_digest=SHA_B
        )
    with pytest.raises(ValueError, match="routing request digest must differ"):
        routing_source_commitment(
            facts,
            route_operation_id=operation,
            route_request_digest=facts.request_digest,
        )
    for changes in (
        {"route_operation_id": new_record_id()},
        {"route_request_digest": "sha256:" + "c" * 64},
    ):
        other = routing_source_commitment(
            facts, **({"route_operation_id": operation, "route_request_digest": SHA_B} | changes)
        )
        assert acceptance_source_commitment_digest(other) != acceptance_source_commitment_digest(
            source
        )


@pytest.mark.parametrize("kind", ("human", "route_true", "route_false"))
@pytest.mark.parametrize(
    "field",
    (
        "action_id",
        "permission_id",
        "project_id",
        "resource_type",
        "resource_id",
        "request_id",
        "correlation_id",
        "source_commitment_digest",
        "service_identity",
        "matched_grant_id",
    ),
)
def test_receipt_rejects_independent_envelope_substitution(kind, field):
    source = _source(kind)
    values = _receipt_values(source)
    control = AcceptanceSourceReceiptFacts(**values)
    assert control.source == source
    changes = {
        "action_id": "task.post_submit.route" if kind == "human" else "review.decision",
        "permission_id": "task.post_submit.route" if kind == "human" else "review.decision",
        "resource_type": "task_post_submit_routing_manifest" if kind == "human" else "review",
        "source_commitment_digest": SHA_B,
        "service_identity": "workstream.task.post_submit_router" if kind == "human" else None,
        "matched_grant_id": None if kind == "human" else new_record_id(),
    }
    with pytest.raises(ValidationError, match="acceptance source receipt commitment differs"):
        AcceptanceSourceReceiptFacts(**(values | {field: changes.get(field, new_record_id())}))


def test_human_receipt_rejects_another_reviewer():
    values = _receipt_values(_source("human"))
    AcceptanceSourceReceiptFacts(**values)
    with pytest.raises(ValidationError, match="receipt commitment differs"):
        AcceptanceSourceReceiptFacts(**(values | {"actor_profile_id": new_record_id()}))


@pytest.mark.parametrize("kind", ("human", "route_true", "route_false"))
def test_receipt_revalidates_nested_source_and_rejects_changed_source_digest(kind):
    source = _source(kind)
    values = _receipt_values(source)
    with pytest.raises(ValidationError):
        AcceptanceSourceReceiptFacts(
            **(values | {"source": source.model_copy(update={"submission_id": "not-a-uuid"})})
        )
    changed = source.model_copy(update={"submission_id": new_record_id()})
    with pytest.raises(ValidationError, match="receipt commitment differs"):
        AcceptanceSourceReceiptFacts(**(values | {"source": changed}))
    with pytest.raises(ValidationError):
        acceptance_source_commitment_digest(
            source.model_copy(update={"submission_id": str(new_record_id())})
        )
    with pytest.raises(ValidationError):
        AcceptanceSourceReceiptFacts(**(values | {"authorized": True}))
    with pytest.raises(ValidationError):
        AcceptanceSourceReceiptFacts(**(values | {"request_id": str(values["request_id"])}))


@pytest.mark.parametrize("kind", ("human", "route_false"))
def test_receipt_does_not_claim_administrative_idempotency_reference(kind):
    """Routing/review operation binding is not an AUTH admin-mutation receipt."""
    values = _receipt_values(_source(kind))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AcceptanceSourceReceiptFacts(**(values | {"idempotency_reference": new_record_id()}))
