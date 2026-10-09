"""Closed authority facts for the three project-scoped task queue reads."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole

TASK_QUEUE_ACTIONS = frozenset({
    ActionId.TASK_QUEUE_READ, ActionId.PROJECT_TASK_QUEUE_READ, ActionId.OPERATIONS_TASK_QUEUE_READ,
})


class QueueReadResourceContext(BaseModel):
    """Bind project scope and the exact page request without storing raw cursors."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["project"] = "project"
    resource_id: UUID
    scope_project_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_project(self):
        """A queue resource is the selected project, never another scope."""
        if self.resource_id != self.scope_project_id:
            raise ValueError("queue project scope differs")
        return self


async def queue_read_denial(action, resource, context, repository, refresh, lifecycle):
    """Lock actor, matched grant, then Project; never acquire a TASK row lock."""
    from app.modules.authorization.runtime import PreparedAuthorizationUnsupported

    if type(resource) is not QueueReadResourceContext or resource.resource_id != resource.scope_project_id:
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, False
    if action.availability is not ActionAvailability.ACTIVE:
        return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False
    locked = await repository.lock_request_actor(context.identity_link_id, context.actor_profile_id)
    try:
        context = refresh(locked, context)
    except PreparedAuthorizationUnsupported as exc:
        return exc.denial_code, context, None, None, None, True
    denial = lifecycle(context)
    if denial is not None:
        return denial, context, None, None, None, True
    if action.action_id is ActionId.TASK_QUEUE_READ:
        grant = await repository.find_active_project_role_any(
            project_id=resource.scope_project_id, actor_profile_id=context.actor_profile_id,
            for_update=True,
        )
        kind = MatchedAuthorityKind.PROJECT_ROLE_GRANT
    else:
        operational = action.action_id is ActionId.OPERATIONS_TASK_QUEUE_READ
        grant = await repository.find_effective_grant(
            context.actor_profile_id, action.permission_id, scope_project_id=resource.scope_project_id,
            system_scope_only=operational, for_update=True,
            allowed_roles=frozenset({AdminRole.OPERATOR if operational else AdminRole.PROJECT_MANAGER}),
        )
        kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    if action.action_id is ActionId.TASK_QUEUE_READ and project.status != "active":
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, True
    return None, context, kind, UUID(str(grant.id)), resource.scope_project_id, True
