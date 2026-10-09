"""Fresh fixed-router custody verifies the original immutable routing allow."""

from app.modules.authorization.domain.post_submit_routing import (
    ROUTE,
    post_submit_routing_resource_digest,
)
from app.modules.authorization.domain.prepared_service import fixed_service_resource_matches
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    ServiceAuthorizationContext,
)


async def validate_routing_replay(owner, issuance, action, caller_input, resource, decision_id):
    owner._validate_consumption(issuance, action, caller_input, resource)
    authority = issuance.authority
    if (
        action is not ROUTE
        or type(authority.context) is not ServiceAuthorizationContext
        or authority.action_id is not ROUTE
        or not fixed_service_resource_matches(
            action, resource, authority.scope_project_id, None, None, None
        )
    ):
        raise PreparedAuthorizationHandleInvalid("invalid routing replay authority")
    event = await owner._authorization._audit.get_authority_event(decision_id)
    expected = {
        "id": str(decision_id),
        "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed",
        "actor_ref_kind": "actor_profile",
        "actor_id": str(authority.context.actor_profile_id),
        "action_id": ROUTE.value,
        "permission_id": ROUTE.value,
        "project_id": str(resource.scope_project_id),
        "resource_type": resource.resource_type,
        "resource_id": str(resource.resource_id),
        "target_ref_kind": "project",
        "target_ref_id": str(resource.scope_project_id),
        "denial_code": None,
        "matched_grant_id": None,
        "request_id": str(resource.request.route_operation_id),
        "correlation_id": str(resource.request.route_operation_id),
        "after_facts": {
            "allowed": True,
            "resource_context_digest": post_submit_routing_resource_digest(resource),
        },
    }
    if event is None or any(
        getattr(event, key, object()) != value for key, value in expected.items()
    ):
        raise PreparedAuthorizationHandleInvalid("invalid retained routing receipt")
