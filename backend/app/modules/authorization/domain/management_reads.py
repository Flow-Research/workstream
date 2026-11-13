"""Project-wide Project Manager and Finance reads under a grant covering the project."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
_DIGEST = r"^sha256:[0-9a-f]{64}$"

ProjectManagementResourceType = Literal[
    "project_guide_collection",
    "project_guide_read",
    "project_guide_activation_readiness",
    "project_guide_document_read",
    "project_submission_collection",
    "project_assignment_collection",
    "project_work_summary",
    "project_task_import_batch_collection",
    "project_submission_bundle_preparation_collection",
    "contribution_policy_collection",
]
MANAGEMENT_RESOURCE_BY_ACTION = {
    ActionId.PROJECT_GUIDE_LIST: "project_guide_collection",
    ActionId.PROJECT_GUIDE_READ: "project_guide_read",
    ActionId.PROJECT_GUIDE_ACTIVATION_READINESS_READ: "project_guide_activation_readiness",
    ActionId.PROJECT_GUIDE_DOCUMENT_READ: "project_guide_document_read",
    ActionId.PROJECT_SUBMISSION_LIST: "project_submission_collection",
    ActionId.PROJECT_ASSIGNMENT_LIST: "project_assignment_collection",
    ActionId.PROJECT_SUMMARY_READ: "project_work_summary",
    ActionId.PROJECT_TASK_IMPORT_BATCH_LIST: "project_task_import_batch_collection",
    ActionId.PROJECT_SUBMISSION_BUNDLE_PREPARATION_LIST: "project_submission_bundle_preparation_collection",
    ActionId.CONTRIBUTION_POLICY_LIST: "contribution_policy_collection",
}
# Guide and document reads select one record inside the project.
_PROJECT_MEMBER_RESOURCES = frozenset(
    {
        "project_guide_read",
        "project_guide_activation_readiness",
        "project_guide_document_read",
    }
)
_POLICY_ACTIONS = frozenset({ActionId.CONTRIBUTION_POLICY_LIST})


class ProjectManagementReadResourceContext(BaseModel):
    """One exact project, or one guide or document inside it; the digest binds the page."""

    model_config = _STRICT
    resource_type: ProjectManagementResourceType
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def exact_project(self):
        """Project collections and summaries name the project itself."""
        if (
            self.resource_type not in _PROJECT_MEMBER_RESOURCES
            and self.resource_id != self.scope_project_id
        ):
            raise ValueError("project management read differs from its project")
        return self


async def management_read_denial(action, resource, context, repository, refresh, lifecycle):
    """Lock actor, the matched grant(s) covering the project, then Project, until commit.

    Project Manager reads accept a system or exact-project Project Manager
    grant; the policy version list also accepts Finance Authority grants in
    those scopes. No contributor or other administrative role is admitted; the
    Project Manager role holds ``compensation.award.read``, so the summary's
    award totals need no second grant.
    """
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext,
        PreparedAuthorizationUnsupported,
    )

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if (
        not isinstance(context, HumanAuthorizationContext)
        or type(resource) is not ProjectManagementReadResourceContext
    ):
        return refused, context, None, None, None, False
    try:
        resource = ProjectManagementReadResourceContext.model_validate(resource)
    except ValidationError:
        return refused, context, None, None, None, False
    if (
        resource.actor_profile_id != context.actor_profile_id
        or MANAGEMENT_RESOURCE_BY_ACTION.get(action.action_id) != resource.resource_type
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
    roles = {AdminRole.PROJECT_MANAGER}
    if action.action_id in _POLICY_ACTIONS:
        roles.add(AdminRole.FINANCE_AUTHORITY)
    grant = await repository.find_effective_grant(
        context.actor_profile_id,
        action.permission_id,
        scope_project_id=resource.scope_project_id,
        for_update=True,
        allowed_roles=frozenset(roles),
    )
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    return (
        None,
        context,
        MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        UUID(str(grant.id)),
        resource.scope_project_id,
        True,
    )
