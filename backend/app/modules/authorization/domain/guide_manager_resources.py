"""Exact resource matching for the shared human project-guide authority path."""

from app.modules.authorization.catalogue import GUIDE_PROPOSAL_ACTION_IDS

from app.modules.authorization.domain.guide_compilation import COMPILATION_RESOURCE_BY_ACTION
from app.modules.authorization.domain.guide_proposals import GUIDE_PROPOSAL_RESOURCE_BY_ACTION
from app.modules.authorization.runtime import (
    PROJECT_MUTATION_RESOURCE_BY_ACTION,
    PROJECT_GUIDE_TARGET_KIND_BY_ACTION,
    PROJECT_SUFFICIENCY_TARGET_KIND_BY_ACTION,
    PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    AuthorizationDenialCode,
)


def guide_manager_resource_denial(action, resource, project_id):
    """Keep family-specific type, scope and execution checks out of kernel control flow."""
    expected = (
        PROJECT_MUTATION_RESOURCE_BY_ACTION.get(action)
        or COMPILATION_RESOURCE_BY_ACTION.get(action)
        or GUIDE_PROPOSAL_RESOURCE_BY_ACTION.get(action)
    )
    if expected is None or not isinstance(resource, expected):
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if resource.scope_project_id != project_id:
        return AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
    if action in GUIDE_PROPOSAL_ACTION_IDS and resource.facts.locator.action_id != action:
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    guide_kind = PROJECT_GUIDE_TARGET_KIND_BY_ACTION.get(action)
    if guide_kind is not None and resource.target_kind != guide_kind:
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    for mapping in (
        PROJECT_SUFFICIENCY_TARGET_KIND_BY_ACTION,
        PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    ):
        kind = mapping.get(action)
        if kind is not None and (
            resource.target_kind != kind or resource.execution_kind != "human"
        ):
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    return None
