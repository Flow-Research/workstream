"""Prepared-capability parsing for adapter-binding mutations."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.adapter_bindings import (
    ADAPTER_BINDING_MUTATION_ACTIONS,
    AdapterBindingMutationResourceContext,
)
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    authorization_resource_digest,
)

def parse_prepared_adapter_binding(
    action_id: ActionId, request_value: Mapping[str, object]
) -> dict[str, object]:
    """Parse exact adapter-binding facts for the three mutation actions."""
    if action_id not in ADAPTER_BINDING_MUTATION_ACTIONS:
        return {}
    try:
        value = dict(request_value)
        for field in (
            "resource_id",
            "scope_project_id",
            "operation_id",
            "adapter_actor_id",
        ):
            value[field] = UUID(str(value[field]))
        resource = AdapterBindingMutationResourceContext.model_validate(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
    return {
        "adapter_binding_context": resource.model_dump(mode="json"),
        "adapter_binding_resource_digest": authorization_resource_digest(resource),
    }


def prepared_adapter_binding_matches(
    context: dict | None,
    digest: str | None,
    resource: object,
) -> bool:
    """Require exact resource facts and digest equality."""
    return isinstance(resource, AdapterBindingMutationResourceContext) and (
        context == resource.model_dump(mode="json")
        and digest == authorization_resource_digest(resource)
    )
