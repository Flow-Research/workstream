"""Read-only validation of an original lifecycle allow under fresh Operator custody."""

from uuid import UUID

from app.modules.authorization.catalogue import ACTION_BY_ID
from app.modules.authorization.domain.lifecycle import ACTION
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid, authorization_resource_digest,
)


async def validate_lifecycle_replay(owner, issuance, action, caller_input, resource, decision_id):
    invalid = PreparedAuthorizationHandleInvalid("invalid lifecycle replay")
    if action is not ACTION:
        raise invalid
    owner._validate_consumption(issuance, action, caller_input, resource)
    authority = issuance.authority
    if (
        authority.scope_project_id is not None
        or authority.matched_grant_id is None
        or authority.matched_grant_status != "active"
    ):
        raise invalid
    command = resource.facts.command
    event = await owner._authorization._audit.get_authority_event(decision_id)
    expected = {
        "event_domain": "authority", "event_type": "SensitiveAuthorizationAllowed",
        "actor_ref_kind": "actor_profile", "actor_id": str(command.actor_profile_id),
        "action_id": action.value, "permission_id": ACTION_BY_ID[action].permission_id.value,
        "project_id": None, "resource_type": resource.resource_type,
        "resource_id": str(command.singleton_id), "correlation_id": str(command.operation_id),
        "target_ref_kind": "joint_lifecycle_control", "target_ref_id": str(command.singleton_id), "denial_code": None,
        "after_facts": {"allowed": True, "resource_context_digest": authorization_resource_digest(resource)},
    }
    if event is None or any(getattr(event, key, object()) != value for key, value in expected.items()):
        raise invalid
    try:
        if UUID(str(event.id)) != decision_id:
            raise ValueError("wrong event")
        UUID(str(event.request_id))
        UUID(str(event.matched_grant_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise invalid from exc
