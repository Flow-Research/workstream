"""Exact fixed-service post-submit resources over CHECKERS' public phase contracts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.execution import (
    ExecuteFacts, FinalizeAuthorityFacts, execution_authority_digest,
)
from app.modules.checkers.api.materialization import MaterializationFacts, materialization_authority_digest

EXECUTE = ActionId.CHECKER_POST_SUBMIT_EXECUTE
FINALIZE = ActionId.CHECKER_POST_SUBMIT_FINALIZE
MATERIALIZE = ActionId.ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE
POST_SUBMIT_ACTIONS = frozenset({EXECUTE, FINALIZE, MATERIALIZE})
_TYPES = {EXECUTE: ExecuteFacts, FINALIZE: FinalizeAuthorityFacts, MATERIALIZE: MaterializationFacts}


def post_submit_request(facts):
    """Project the exact CHECKERS request from the closed phase facts."""
    return facts.execution.request if type(facts) is MaterializationFacts else facts.request


def post_submit_digest(facts):
    """Delegate canonical phase commitments to the consumer-owned public contract."""
    if type(facts) is MaterializationFacts:
        return materialization_authority_digest(facts)
    return execution_authority_digest(facts)


class PostSubmitResourceContext(BaseModel):
    """A single phase and exact project/attempt, never a generic artifact permission."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["checker_run"] = "checker_run"
    resource_id: UUID
    scope_project_id: UUID
    action_id: ActionId
    facts: ExecuteFacts | FinalizeAuthorityFacts | MaterializationFacts

    @model_validator(mode="after")
    def validate_identity(self):
        expected = _TYPES.get(self.action_id)
        if expected is None or type(self.facts) is not expected:
            raise ValueError("invalid post-submit authority phase")
        checked = expected.model_validate_json(self.facts.model_dump_json())
        request = post_submit_request(checked)
        execution = checked.execution if type(checked) is MaterializationFacts else checked
        if self.resource_id != execution.lease.reservation.attempt_id or self.scope_project_id != request.project_id:
            raise ValueError("invalid post-submit authority resource")
        post_submit_digest(checked)
        return self


def post_submit_resource(action, facts):
    """Build a typed owner-verified resource; no provider coordinates enter AUTH."""
    execution = facts.execution if type(facts) is MaterializationFacts else facts
    return PostSubmitResourceContext(
        action_id=action, resource_id=execution.lease.reservation.attempt_id,
        scope_project_id=execution.request.project_id, facts=facts,
    )


def post_submit_prepare_values(action, request, execution=None):
    """Bind immutable request selectors; materialization additionally binds its existing lease."""
    values = {
        "project_id": str(request.project_id), "request_id": str(request.evaluation_request_id),
        "request_digest": request.request_sha256,
    }
    if action == MATERIALIZE:
        values["execution_digest"] = execution_authority_digest(execution)
    return values


def parse_post_submit_prepare(action, values, invalid_error):
    """Reject malformed or extra prepare selectors before locking product rows."""
    if action not in POST_SUBMIT_ACTIONS:
        return None
    import re
    expected = {"project_id", "request_id", "request_digest"}
    if action == MATERIALIZE:
        expected.add("execution_digest")
    try:
        if set(values) != expected:
            raise ValueError("invalid keys")
        for key in ("project_id", "request_id"):
            if type(values[key]) is not str or str(UUID(values[key])) != values[key]:
                raise ValueError("invalid identity")
        for key in expected - {"project_id", "request_id"}:
            if type(values[key]) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", values[key]) is None:
                raise ValueError("invalid digest")
    except (ValueError, TypeError, KeyError) as error:
        raise invalid_error("invalid prepared post-submit authority") from error
    return dict(values)


def post_submit_prepare_matches(action, prepared, resource):
    """Match final facts to the exact preparation and forbid phase substitution."""
    if type(resource) is not PostSubmitResourceContext or resource.action_id is not action:
        return False
    resource.validate_identity()
    facts = resource.facts
    return prepared == post_submit_prepare_values(
        action, post_submit_request(facts), facts.execution if type(facts) is MaterializationFacts else None,
    )
