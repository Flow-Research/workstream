"""Exact original callback allow under fresh request-local prepared custody."""

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.authorization.domain.fulfillment_evidence import (
    fulfillment_evidence_action_matches, fulfillment_evidence_resource_digest,
)
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid, ServiceAuthorizationContext


async def validate_fulfillment_replay(owner, issuance, action, caller_input, resource, decision_id):
    """Check immutable allow identity without allocating a new authorization row."""
    owner._validate_consumption(issuance, action, caller_input, resource)
    authority = issuance.authority
    context = authority.context
    if (
        action not in {
            ActionId.COMPENSATION_FULFILLMENT_REPORT,
            ActionId.COMPENSATION_FULFILLMENT_EXCEPTION_REPORT,
        }
        or type(context) is not ServiceAuthorizationContext
        or context.service_identity is not ServiceIdentity.COMPENSATION_ADAPTER
        or authority.action_id is not action
        or not fulfillment_evidence_action_matches(
            action, resource, authority.scope_project_id,
            context.actor_profile_id, context.identity_link_id,
        )
    ):
        raise PreparedAuthorizationHandleInvalid("invalid fulfillment replay authority")
    event = await owner._authorization._audit.get_authority_event(decision_id)
    expected = {
        "id": str(decision_id), "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed", "actor_ref_kind": "actor_profile",
        "actor_id": str(context.actor_profile_id), "action_id": action.value,
        "permission_id": ACTION_BY_ID[action].permission_id.value,
        "project_id": str(resource.scope_project_id), "resource_type": resource.resource_type,
        "resource_id": str(resource.resource_id), "target_ref_kind": "project",
        "target_ref_id": str(resource.scope_project_id), "denial_code": None,
        "matched_grant_id": None, "idempotency_reference": None,
        "after_facts": {
            "allowed": True, "resource_context_digest": fulfillment_evidence_resource_digest(resource),
        },
    }
    if event is None or any(getattr(event, key, object()) != value for key, value in expected.items()):
        raise PreparedAuthorizationHandleInvalid("invalid retained fulfillment receipt")
