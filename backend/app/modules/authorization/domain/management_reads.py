"""Project-wide Project Manager and Finance reads under a grant covering the project."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId, PermissionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
_DIGEST = r"^sha256:[0-9a-f]{64}$"

ProjectManagementResourceType = Literal[
    "project_guide_collection", "project_guide_read", "project_guide_activation_readiness",
    "project_guide_document_read", "project_submission_collection", "project_assignment_collection",
    "project_work_summary", "project_task_import_batch_collection",
    "project_submission_bundle_preparation_collection", "contribution_policy_collection",
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
_PROJECT_MEMBER_RESOURCES = frozenset({
    "project_guide_read", "project_guide_activation_readiness", "project_guide_document_read",
})
_FINANCE_ACTIONS = frozenset({ActionId.CONTRIBUTION_POLICY_LIST})


class ProjectManagementReadResourceContext(BaseModel):
    """One exact project, or one guide or document inside it; the digest binds the page."""

    model_config = _STRICT
    resource_type: ProjectManagementResourceType
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=_DIGEST)
    # Set only by the evaluator on a summary it allows: the exact-project
    # Finance grant it locked, so the recorded decision digest binds the
    # award-total disclosure. Callers never supply it.
    award_totals_grant_id: UUID | None = None

    @model_validator(mode="after")
    def exact_project(self):
        """Project collections and summaries name the project itself."""
        if self.resource_type not in _PROJECT_MEMBER_RESOURCES and self.resource_id != self.scope_project_id:
            raise ValueError("project management read differs from its project")
        if self.award_totals_grant_id is not None and self.resource_type != "project_work_summary":
            raise ValueError("only the project summary discloses award totals")
        return self


async def management_read_denial(action, resource, context, repository, refresh, lifecycle):
    """Lock actor, the matched grant(s) covering the project, then Project, until commit.

    Project Manager reads accept a system or exact-project Project Manager
    grant; the policy version list accepts the same scopes for Finance
    Authority. No contributor or other administrative role is admitted. The
    summary also resolves an exact-project Finance Authority grant (the
    PILOT-10 precedent; a system Finance grant does not disclose) and returns
    the evaluated resource naming it, which the kernel records. Every result
    ends with the resource the decision records.
    """
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext, PreparedAuthorizationUnsupported,
    )

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if (not isinstance(context, HumanAuthorizationContext)
            or type(resource) is not ProjectManagementReadResourceContext):
        return refused, context, None, None, None, False, resource
    try:
        resource = ProjectManagementReadResourceContext.model_validate(resource)
    except ValidationError:
        return refused, context, None, None, None, False, resource
    if (resource.actor_profile_id != context.actor_profile_id
            or resource.award_totals_grant_id is not None
            or MANAGEMENT_RESOURCE_BY_ACTION.get(action.action_id) != resource.resource_type):
        return refused, context, None, None, None, False, resource
    if action.availability is not ActionAvailability.ACTIVE:
        return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False, resource
    locked = await repository.lock_request_actor(context.identity_link_id, context.actor_profile_id)
    try:
        context = refresh(locked, context)
    except PreparedAuthorizationUnsupported as exc:
        return exc.denial_code, context, None, None, None, True, resource
    denial = lifecycle(context)
    if denial is not None:
        return denial, context, None, None, None, True, resource
    role = (AdminRole.FINANCE_AUTHORITY if action.action_id in _FINANCE_ACTIONS
            else AdminRole.PROJECT_MANAGER)
    grant = await repository.find_effective_grant(
        context.actor_profile_id, action.permission_id, scope_project_id=resource.scope_project_id,
        for_update=True, allowed_roles=frozenset({role}),
    )
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True, resource
    evaluated = resource
    if action.action_id is ActionId.PROJECT_SUMMARY_READ:
        finance = await repository.find_effective_grant(
            context.actor_profile_id, PermissionId.COMPENSATION_AWARD_READ,
            scope_project_id=resource.scope_project_id, exact_project_scope=True, for_update=True,
            allowed_roles=frozenset({AdminRole.FINANCE_AUTHORITY}),
        )
        if finance is not None:
            evaluated = ProjectManagementReadResourceContext.model_validate(
                {**resource.model_dump(), "award_totals_grant_id": UUID(str(finance.id))},
            )
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True, resource
    return (None, context, MatchedAuthorityKind.ADMIN_ROLE_GRANT, UUID(str(grant.id)),
            resource.scope_project_id, True, evaluated)
