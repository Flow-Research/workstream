"""Closed detached result values and pre-owner envelope rejection."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.outbox.api import OutboxClaim, OutboxEventEnvelope, HandlerOutcome
from app.modules.checkers.api.execution import COMPLETION_EVENT
from app.modules.tasks.api.routing_outcome import TaskRoutingOutcome, RoutingEconomicFacts
from app.modules.tasks.evaluation_completion_delivery import EvaluationCompletionHandler
from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from tests.tasks.post_submit_routing.test_requests import untrusted_completion


def result():
    return TaskRoutingOutcome(**{key: new_record_id() for key in (
        "project_id", "task_id", "submission_id", "completion_event_id", "routing_manifest_id",
        "authorization_decision_id", "outcome_event_id",
    )}, routing_recommendation="allow_review", final_acceptance_id=None,
       economic=None, replayed=False)


def test_result_is_closed_and_immutable():
    value = result()
    assert TaskRoutingOutcome.model_validate(value.model_dump()) == value
    with pytest.raises(ValidationError, match="frozen"):
        value.replayed = True
    for key, replacement in (
        ("task_id", str(value.task_id)),
        ("routing_recommendation", "task_setup_blocked"),
        ("replayed", 1),
        ("extra", "private"),
    ):
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
    remediation = value.model_copy(update={"routing_recommendation": "needs_revision"})
    assert remediation.economic is remediation.final_acceptance_id is None
    with pytest.raises(ValidationError, match="remediation outcome"):
        TaskRoutingOutcome.model_validate(valid | {"routing_recommendation": "needs_revision"})


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
        "routing_recommendation": "task_setup_blocked",
    }).model_dump_json()})]
    for invalid in altered:
        assert await handler(invalid) is HandlerOutcome.REJECT
    assert not reached
    remediation = valid.model_copy(update={"payload_json": completion.model_copy(update={
        "routing_recommendation": "needs_revision",
    }).model_dump_json()})
    assert await handler(remediation) is HandlerOutcome.REJECT
    assert reached == [remediation]
    assert await handler(valid) is HandlerOutcome.REJECT
    assert reached == [remediation, valid]


async def test_remediation_delivery_bypasses_acceptance_generation_observation():
    value, completion = envelope()
    remediation = value.model_copy(update={"payload_json": completion.model_copy(update={
        "routing_recommendation": "needs_revision",
    }).model_dump_json()})

    class Acceptance:
        async def observe_generation(self):
            pytest.fail("remediation observed REV acceptance generation")

    operation = TaskPostSubmitOutcome(
        None,
        projects=None,
        rewards=None,
        evaluations=None,
        authorization=None,
        acceptance=Acceptance(),
        observer=None,
        invocation_fence=None,
        audit=None,
        outbox=None,
    )

    assert await operation.observe_delivery_generation(remediation) is None


async def test_completion_handler_rejects_substituted_outcome_recommendation():
    value, completion = envelope()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    class Observer:
        async def observe_invocation(self, received):
            return SimpleNamespace(claim=received.claim)

    class Outcome:
        async def observe_delivery_generation(self, _):
            return None

        async def apply(self, _, *, current_generation):
            assert current_generation is None
            return TaskRoutingOutcome(
                project_id=completion.project_id,
                task_id=completion.task_id,
                submission_id=completion.submission_id,
                completion_event_id=value.claim.event_id,
                routing_manifest_id=new_record_id(),
                authorization_decision_id=new_record_id(),
                outcome_event_id=new_record_id(),
                routing_recommendation="needs_revision",
                final_acceptance_id=None,
                economic=None,
                replayed=False,
            )

    handler = EvaluationCompletionHandler(
        Session, observer=Observer(), outcomes=lambda _: Outcome()
    )

    with pytest.raises(
        TaskRoutingRequestUnavailable,
        match="routing outcome recommendation differs",
    ):
        await handler(value)
