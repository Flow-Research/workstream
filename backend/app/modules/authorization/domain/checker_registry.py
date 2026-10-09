"""AUTH-private resource facts for external-checker registry publication."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.schemas import AdminRole


class ExternalCheckerRegistryResourceContext(BaseModel):
    """Exact system-scoped immutable registry entry and request identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["external_checker_registry_entry"]
    resource_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    entry_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


CHECKER_REGISTRY_ACTIONS = frozenset({ActionId.CHECKER_REGISTRY_REGISTER})
CHECKER_REGISTRY_RESOURCE_BY_ACTION = {
    ActionId.CHECKER_REGISTRY_REGISTER: ExternalCheckerRegistryResourceContext,
}


def checker_registry_grant_filters(action_id: ActionId) -> dict[str, object]:
    """Confine external checker registration to a system Operator grant."""
    if action_id not in CHECKER_REGISTRY_ACTIONS:
        return {}
    return {"allowed_roles": frozenset({AdminRole.OPERATOR})}

