"""Closed detached result values and pre-owner envelope rejection."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.outbox.api import OutboxClaim, OutboxEventEnvelope, HandlerOutcome
from app.modules.checkers.api.execution import COMPLETION_EVENT
from app.modules.tasks.api.routing_outcome import TaskRoutingOutcome, RoutingEconomicFacts
from app.modules.tasks.evaluation_completion_delivery import EvaluationCompletionHandler
from tests.tasks.post_submit_routing.test_requests import untrusted_completion


def result():
    return TaskRoutingOutcome(**{key: new_record_id() for key in (
        "project_id", "task_id", "submission_id", "completion_event_id", "routing_manifest_id",
        "authorization_decision_id", "outcome_event_id",
    )}, final_acceptance_id=None, economic=None, replayed=False)


def test_result_is_closed_and_immutable():
    value = result()
    assert TaskRoutingOutcome.model_validate(value.model_dump()) == value
    with pytest.raises(ValidationError, match="frozen"):
        value.replayed = True
    for key, replacement in (("task_id", str(value.task_id)), ("replayed", 1), ("extra", "private")):
        with pytest.raises(ValidationError):
            TaskRoutingOutcome.model_validate(value.model_dump() | {key: replacement})


def test_result_binds_branch_and_completion():
    value = result()
    acceptance = new_record_id()
    economic = RoutingEconomicFacts(final_acceptance_id=acceptance, contribution_record_id=new_record_id(), award_ids=())
    valid = value.model_dump() | {"final_acceptance_id": acceptance, "economic": economic.model_dump()}
    assert TaskRoutingOutcome.model_validate(valid).economic == economic
    for changes in ({"economic": None}, {"final_acceptance_id": None}, {"final_acceptance_id": new_record_id()}):
        with pytest.raises(ValidationError, match="routing outcome"):
            TaskRoutingOutcome.model_validate(valid | changes)


def envelope():
    event_id, completion = untrusted_completion()
    now = datetime.now(timezone.utc)
    return OutboxEventEnvelope(
        claim=OutboxClaim(event_id=event_id, project_id=completion.project_id,
                          payload_digest=canonical_json_hash(completion.model_dump(mode="json")),
                          claim_generation=1, claim_owner="contract", claimed_at=now,
                          claim_expires_at=now + timedelta(minutes=5)),
        event_type=COMPLETION_EVENT, event_version=1, aggregate_type="checker_run",
        aggregate_id=completion.reference.attempt_id, correlation_id="contract",
        causation_event_id=None, idempotency_key="contract", occurred_at=now,
        payload_json=completion.model_dump_json(),
    ), completion


async def test_completion_handler_rejects_crossed_or_non_success_completion():
    valid, completion = envelope()
    reached = []

    class Observer:
        async def observe_invocation(self, value):
            reached.append(value)
            return None

    def forbidden(*args):
        pytest.fail("intrinsic invalidity reached outcome/session")

    handler = EvaluationCompletionHandler(forbidden, observer=Observer(), outcomes=forbidden)
    altered = [valid.model_copy(update={key: replacement}) for key, replacement in (
        ("event_type", "AnotherEvent"), ("event_version", 2), ("aggregate_type", "task"),
        ("aggregate_id", new_record_id()), ("payload_json", "{"),
        ("claim", valid.claim.model_copy(update={"project_id": new_record_id()})),
        ("event_version", "1"),
    )]
    altered += [valid.model_copy(update={"payload_json": completion.model_copy(update={
        "routing_recommendation": recommendation,
    }).model_dump_json()}) for recommendation in ("needs_revision", "task_setup_blocked")]
    for invalid in altered:
        assert await handler(invalid) is HandlerOutcome.REJECT
    assert not reached
    assert await handler(valid) is HandlerOutcome.REJECT
    assert reached == [valid]
