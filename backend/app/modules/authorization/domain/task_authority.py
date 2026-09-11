"""Exact resource and prepared rules for the bounded task-authority cutover."""

import json
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind


TASK_SUBMITTER_ACTIONS = frozenset(
    {
        ActionId.TASK_CLAIM,
        ActionId.TASK_START,
        ActionId.TASK_WORK_CONTEXT_READ,
    }
)
TASK_ACTIONS = TASK_SUBMITTER_ACTIONS | {
    ActionId.OPERATIONS_TASK_START_OVERRIDE,
    ActionId.PROJECT_TASK_WORK_CONTEXT_READ,
}


class TaskAuthorityResourceContext(BaseModel):
    """TASK-locked facts remain exact through AUTH preparation and consumption."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["task_authority"] = "task_authority"
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    task_status: str
    assigned_to: UUID | None
    assignment_id: UUID | None
    assignment_contributor_id: UUID | None
    locked_context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str | None


def parse_task_authority_binding(
    action: ActionId, request: Mapping[str, object], invalid_error: type[Exception],
) -> TaskAuthorityResourceContext | None:
    """Keep the complete task commitment typed and immutable through consumption."""
    if action not in TASK_ACTIONS:
        return None
    try:
        return TaskAuthorityResourceContext.model_validate_json(json.dumps(dict(request)))
    except (TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared authorization handle") from exc


def task_resource_guard(action: ActionId, resource: TaskAuthorityResourceContext) -> bool:
    """No authority allow may substitute for assignment and task currentness."""
    own_assignment = (
        resource.assignment_id is not None
        and resource.assignment_contributor_id == resource.actor_profile_id
        and resource.assigned_to == resource.actor_profile_id
    )
    unassigned_ready = (
        resource.task_status == "ready"
        and resource.assigned_to is None
        and resource.assignment_id is None
        and resource.assignment_contributor_id is None
    )
    if action is ActionId.TASK_CLAIM:
        return unassigned_ready
    if action is ActionId.TASK_START:
        return resource.task_status == "claimed" and own_assignment
    if action is ActionId.OPERATIONS_TASK_START_OVERRIDE:
        return (
            resource.task_status == "claimed"
            and resource.assignment_id is not None
            and resource.assignment_contributor_id is not None
            and resource.assignment_contributor_id == resource.assigned_to
            and resource.assigned_to != resource.actor_profile_id
            and bool(resource.reason and resource.reason.strip())
        )
    if action is ActionId.TASK_WORK_CONTEXT_READ:
        return unassigned_ready or own_assignment
    return action is ActionId.PROJECT_TASK_WORK_CONTEXT_READ


def evaluate_task_authority(action, context, authority, resource, lifecycle_denial):
    """Evaluate exact TASK facts against the authority already locked by AUTH."""
    denial = lifecycle_denial
    if denial is None and action.availability is not ActionAvailability.ACTIVE:
        denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
    if denial is None and (
        not isinstance(resource, TaskAuthorityResourceContext)
        or resource.scope_project_id != authority.scope_project_id
        or resource.actor_profile_id != context.actor_profile_id
        or resource.identity_link_id != context.identity_link_id
        or not task_resource_guard(action.action_id, resource)
    ):
        denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if denial is None and (
        authority.matched_grant_id is None or authority.matched_grant_status != "active"
    ):
        denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    if denial is not None:
        return denial, None, None, None
    matched_kind = (
        MatchedAuthorityKind.PROJECT_ROLE_GRANT if action.action_id in TASK_SUBMITTER_ACTIONS
        else MatchedAuthorityKind.ADMIN_ROLE_GRANT
    )
    return None, matched_kind, authority.matched_grant_id, authority.scope_project_id
