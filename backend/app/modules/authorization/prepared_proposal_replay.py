"""Fresh shared PREP custody over retained human proposal decision evidence."""
from app.modules.authorization.catalogue import GUIDE_PROPOSAL_ACTION_IDS

from uuid import UUID

from app.modules.authorization.catalogue import ACTION_BY_ID
from app.modules.authorization.domain.guide_proposals import proposal_matches
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid


async def validate_proposal_replay(owner, issuance, action, caller_input, resource, decision_id):
    """Validate the exact original allow under freshly locked project-manager authority."""
    invalid = PreparedAuthorizationHandleInvalid("invalid prepared proposal replay")
    if (
        action not in GUIDE_PROPOSAL_ACTION_IDS
        or issuance.binding.action_id is not action
        or owner._binding(action, caller_input, issuance.binding.scope) != issuance.binding
        or owner._root_transaction() is not issuance.transaction
        or owner._scope_from_resource(action, resource) != issuance.binding.scope
        or not proposal_matches(issuance.binding.proposal_prepare_context, resource)
    ):
        raise invalid
    authority = issuance.authority
    if (
        authority.action_id is not action
        or authority.matched_grant_id is None
        or authority.matched_grant_status != "active"
        or authority.scope_project_id != resource.scope_project_id
        or authority.matched_grant_scope_project_id != resource.scope_project_id
    ):
        raise invalid
    event = await owner._authorization._audit.get_authority_event(decision_id)
    locator = resource.facts.locator
    expected = {
        "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed",
        "actor_ref_kind": "actor_profile",
        "actor_id": str(locator.actor_profile_id),
        "action_id": action.value,
        "permission_id": ACTION_BY_ID[action].permission_id.value,
        "project_id": str(locator.project_id),
        "resource_type": resource.resource_type,
        "resource_id": str(resource.resource_id),
        "correlation_id": str(locator.operation_id),
        "target_ref_kind": "project",
        "target_ref_id": str(locator.project_id),
        "denial_code": None,
        "after_facts": {"allowed": True, "resource_context_digest": resource.facts.digest},
    }
    if event is None or any(
        not hasattr(event, k) or getattr(event, k) != v for k, v in expected.items()
    ):
        raise invalid
    try:
        if UUID(str(event.id)) != decision_id:
            raise ValueError("decision mismatch")
        UUID(str(event.request_id))
        UUID(str(event.matched_grant_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise invalid from exc
