"""Validate retained phase receipts under the same fresh transaction-bound PREP."""

from app.modules.authorization.catalogue import ACTION_BY_ID
from app.modules.authorization.domain.post_submit import post_submit_digest, post_submit_request
from app.modules.authorization.domain.prepared_service import fixed_service_resource_matches
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid, ServiceAuthorizationContext


async def validate_post_submit_replay(owner, issuance, action, caller_input, resource, decision_id):
    """Require the exact original allow; never insert another audit event for replay."""
    owner._validate_consumption(issuance, action, caller_input, resource)
    authority = issuance.authority
    if (
        type(authority.context) is not ServiceAuthorizationContext
        or authority.action_id is not action
        or not fixed_service_resource_matches(action, resource, authority.scope_project_id, None, None, None)
    ):
        raise PreparedAuthorizationHandleInvalid("invalid post-submit replay authority")
    event = await owner._authorization._audit.get_authority_event(decision_id)
    request = post_submit_request(resource.facts)
    expected = {
        "id": str(decision_id), "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed", "actor_ref_kind": "actor_profile",
        "actor_id": str(authority.context.actor_profile_id), "action_id": action.value,
        "permission_id": ACTION_BY_ID[action].permission_id.value,
        "project_id": str(resource.scope_project_id), "resource_type": "checker_run",
        "resource_id": str(resource.resource_id), "target_ref_kind": "project",
        "target_ref_id": str(resource.scope_project_id), "denial_code": None,
        "matched_grant_id": None, "request_id": str(request.evaluation_request_id),
        "correlation_id": str(request.evaluation_request_id),
        "after_facts": {"allowed": True, "resource_context_digest": post_submit_digest(resource.facts)},
    }
    if event is None or any(getattr(event, key, object()) != value for key, value in expected.items()):
        raise PreparedAuthorizationHandleInvalid("invalid retained post-submit receipt")
