"""Internal resource contexts for compensation adapter-binding authority."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionId

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class AdapterBindingReadResourceContext(BaseModel):
    """Exact project-scoped binding disclosure target."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["compensation_adapter_binding"]
    resource_id: UUID
    scope_project_id: UUID
    resource_facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AdapterBindingMutationResourceContext(BaseModel):
    """Exact immutable facts for one adapter-binding mutation."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["compensation_adapter_binding"]
    resource_id: UUID
    scope_project_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    instrument_type: Literal["money", "project_points"]
    adapter_actor_id: UUID
    route_key: str
    expected_status: Literal["active", "suspended"] | None
    expected_lifecycle_version: int | None = Field(default=None, ge=1)
    resource_facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_transition_pair(self):
        """Require status and lifecycle version together for transitions only."""
        if (self.expected_status is None) != (self.expected_lifecycle_version is None):
            raise ValueError("adapter-binding transition facts must be complete")
        return self


AdapterBindingResourceContext = (
    AdapterBindingReadResourceContext | AdapterBindingMutationResourceContext
)

ADAPTER_BINDING_RESOURCE_BY_ACTION = {
    ActionId.COMPENSATION_ADAPTER_BINDING_READ: AdapterBindingReadResourceContext,
    ActionId.COMPENSATION_ADAPTER_BINDING_CREATE: AdapterBindingMutationResourceContext,
    ActionId.COMPENSATION_ADAPTER_BINDING_SUSPEND: AdapterBindingMutationResourceContext,
    ActionId.COMPENSATION_ADAPTER_BINDING_RESUME: AdapterBindingMutationResourceContext,
}
ADAPTER_BINDING_READ_ACTIONS = frozenset(
    {ActionId.COMPENSATION_ADAPTER_BINDING_READ}
)
ADAPTER_BINDING_MUTATION_ACTIONS = frozenset(
    {
        ActionId.COMPENSATION_ADAPTER_BINDING_CREATE,
        ActionId.COMPENSATION_ADAPTER_BINDING_SUSPEND,
        ActionId.COMPENSATION_ADAPTER_BINDING_RESUME,
    }
)
ADAPTER_BINDING_ACTIONS = ADAPTER_BINDING_READ_ACTIONS | ADAPTER_BINDING_MUTATION_ACTIONS


def finance_authority_grant_filters(action_id: ActionId) -> dict[str, object]:
    """Confine binding actions to the exact Finance Authority role."""
    if action_id not in ADAPTER_BINDING_ACTIONS:
        return {}
    from app.modules.authorization.schemas import AdminRole

    return {"allowed_roles": frozenset({AdminRole.FINANCE_AUTHORITY})}
