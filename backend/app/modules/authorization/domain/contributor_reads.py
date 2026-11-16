"""Caller-owned grant and work reads; nothing here names a second contributor."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
_DIGEST = r"^sha256:[0-9a-f]{64}$"


class ActorProjectListResourceContext(BaseModel):
    """The caller's own grants; the digest binds the page request."""

    model_config = _STRICT
    resource_type: Literal["actor_project_collection"] = "actor_project_collection"
    resource_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def exact_actor(self):
        """A grant list cannot select another actor."""
        if self.resource_id != self.actor_profile_id:
            raise ValueError("actor project list differs from caller")
        return self


ContributorWorkResourceType = Literal[
    "actor_assignment_collection", "actor_submission_collection", "actor_work_summary",
    "task_submission_bundle_preparation_collection", "submission_bundle_preparation_read",
]
_ACTOR_WIDE = frozenset({
    "actor_assignment_collection", "actor_submission_collection", "actor_work_summary",
})
WORK_RESOURCE_BY_ACTION = {
    ActionId.ACTOR_ASSIGNMENT_LIST: "actor_assignment_collection",
    ActionId.ACTOR_SUBMISSION_LIST: "actor_submission_collection",
    ActionId.ACTOR_WORK_SUMMARY_READ: "actor_work_summary",
    ActionId.TASK_SUBMISSION_BUNDLE_PREPARATION_LIST: "task_submission_bundle_preparation_collection",
    ActionId.TASK_SUBMISSION_BUNDLE_PREPARATION_READ: "submission_bundle_preparation_read",
}


class ContributorWorkReadResourceContext(BaseModel):
    """Own work across Submitter projects, or within one exact task's project."""

    model_config = _STRICT
    resource_type: ContributorWorkResourceType
    resource_id: UUID
    actor_profile_id: UUID
    scope_project_id: UUID | None
    request_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def exact_scope(self):
        """Actor-wide reads name the caller; task reads name their resolved project."""
        if self.resource_type in _ACTOR_WIDE:
            if self.resource_id != self.actor_profile_id:
                raise ValueError("contributor work read differs from caller")
        elif self.scope_project_id is None:
            raise ValueError("task work read requires its project")
        return self


async def contributor_read_denial(action, resource, context, repository, refresh, lifecycle):
    """Lock actor, then any selected Submitter grant and Project, until commit.

    An actor-wide read without a project filter is a self read; its caller
    narrows rows to projects where the actor currently holds a Submitter grant.
    """
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext, PreparedAuthorizationUnsupported,
    )

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    project_list = action.action_id is ActionId.ACTOR_PROJECT_LIST
    expected = ActorProjectListResourceContext if project_list else ContributorWorkReadResourceContext
    if not isinstance(context, HumanAuthorizationContext) or type(resource) is not expected:
        return refused, context, None, None, None, False
    try:
        resource = expected.model_validate(resource)
    except ValidationError:
        return refused, context, None, None, None, False
    if resource.actor_profile_id != context.actor_profile_id or (
        not project_list and WORK_RESOURCE_BY_ACTION.get(action.action_id) != resource.resource_type
    ):
        return refused, context, None, None, None, False
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
    if project_list or resource.scope_project_id is None:
        return None, context, MatchedAuthorityKind.ACTOR_SELF, None, None, True
    grant = await repository.find_active_project_role(
        project_id=resource.scope_project_id, actor_profile_id=context.actor_profile_id,
        role="submitter", for_update=True,
    )
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    return (None, context, MatchedAuthorityKind.PROJECT_ROLE_GRANT, UUID(str(grant.id)),
            resource.scope_project_id, True)
