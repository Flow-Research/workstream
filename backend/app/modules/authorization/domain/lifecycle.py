"""Exact system Operator resource and PREP binding for REV lifecycle transitions."""

import json

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.reviews.api.lifecycle import LifecycleTransitionCommand, LifecycleTransitionFacts

ACTION = ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE


class ReviewLifecycleActivationContract(BaseModel):
    """Closed REV facts; arbitrary request values cannot become an allow."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    action_id: Literal[ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE] = ACTION
    resource_type: Literal["joint_lifecycle_control"] = "joint_lifecycle_control"
    resource_id: UUID
    facts: LifecycleTransitionFacts

    @model_validator(mode="after")
    def exact_identity(self):
        if self.resource_id != self.facts.command.singleton_id:
            raise ValueError("lifecycle resource mismatch")
        return self


def parse_lifecycle_prepare(action, caller_input, scope, context):
    """Close all request selectors over the authenticated human and system scope."""
    if action != ACTION:
        return None
    command = LifecycleTransitionCommand.model_validate_json(json.dumps(dict(caller_input.request_value)))
    if (
        scope.kind.value != "system" or scope.project_id is not None
        or command.operation_id != caller_input.idempotency_key
        or command.operation_id != context.correlation_id
        or command.actor_profile_id != context.actor_profile_id
        or command.identity_link_id != context.identity_link_id
    ):
        raise ValueError("lifecycle preparation mismatch")
    return command


def lifecycle_matches(binding, resource):
    exact = type(resource) is ReviewLifecycleActivationContract
    if exact != (binding is not None):
        return False
    if not exact:
        return True
    checked = ReviewLifecycleActivationContract.model_validate(resource.model_dump(), strict=True)
    return binding == checked.facts.command
