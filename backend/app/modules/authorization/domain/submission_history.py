"""Closed history-read decisions with live authority and immutable ownership."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorization.catalogue import ActionAvailability, HISTORY_READ_ACTIONS
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole


class HistoryReadResourceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["task_submission_history", "submission_history", "checker_history"]
    resource_id: UUID
    scope_project_id: UUID
    task_id: UUID
    submission_id: UUID
    contributor_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def _valid_target(action, resource, context):
    if type(resource) is not HistoryReadResourceContext or resource.actor_profile_id != context.actor_profile_id:
        return False
    name = action.value.removeprefix("project.")
    if name == "task.submission.list":
        return resource.resource_type == "task_submission_history" and resource.resource_id == resource.task_id
    if name in {"submission.read", "submission.checker_run.list"}:
        return resource.resource_type == "submission_history" and resource.resource_id == resource.submission_id
    return name == "checker_run.read" and resource.resource_type == "checker_history"


async def history_read_denial(action, resource, context, repository, refresh, lifecycle):
    """TASK is already locked; lock actor, matched grant and Project in that order."""
    from app.modules.authorization.runtime import PreparedAuthorizationUnsupported

    if action.action_id not in HISTORY_READ_ACTIONS or not _valid_target(action.action_id, resource, context):
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
    manager = action.action_id.value.startswith("project.")
    if not manager:
        if resource.contributor_id != context.actor_profile_id:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, True
        grant = await repository.find_active_project_role(
            project_id=resource.scope_project_id, actor_profile_id=context.actor_profile_id,
            role="submitter", for_update=True,
        )
        kind = MatchedAuthorityKind.PROJECT_ROLE_GRANT
    else:
        grant = await repository.find_effective_grant(
            context.actor_profile_id, action.permission_id, scope_project_id=resource.scope_project_id,
            for_update=True, allowed_roles=frozenset({AdminRole.PROJECT_MANAGER}),
        )
        kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    return None, context, kind, UUID(str(grant.id)), resource.scope_project_id, True
