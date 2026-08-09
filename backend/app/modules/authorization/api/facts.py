"""Dependency-free immutable facts accepted by public authorization ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Mapping, TypeAlias
from uuid import UUID

JsonScalar: TypeAlias = str | int | float | bool | None
ResourceValue: TypeAlias = JsonScalar | UUID | tuple[JsonScalar | UUID, ...]


def _is_immutable_resource_value(value: object) -> bool:
    """Return whether a resource fact is deeply immutable and finite."""
    if value is None or isinstance(value, UUID) or type(value) in {str, int, bool}:
        return True
    if type(value) is float:
        return math.isfinite(value)
    return isinstance(value, tuple) and all(
        item is None
        or isinstance(item, UUID)
        or type(item) in {str, int, bool}
        or (type(item) is float and math.isfinite(item))
        for item in value
    )


class ActorKind(StrEnum):
    """Actor kinds understood by the authorization boundary."""

    HUMAN = "human"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class ActorIdentityFacts:
    """Exact active actor and identity-link references for one decision."""

    actor_profile_id: UUID
    identity_link_id: UUID
    actor_kind: ActorKind
    service_identity: str | None = None

    def __post_init__(self) -> None:
        """Require service identity only for service actors."""
        normalized = self.service_identity.strip() if self.service_identity is not None else None
        has_service_identity = bool(normalized)
        if has_service_identity != (self.actor_kind is ActorKind.SERVICE):
            raise ValueError("service identity must match actor kind")
        object.__setattr__(self, "service_identity", normalized)


@dataclass(frozen=True, slots=True)
class ResourceFacts:
    """Canonical resource kind, identifier, and server-owned decision facts."""

    resource_type: str
    resource_id: UUID | str
    values: Mapping[str, ResourceValue]

    def __post_init__(self) -> None:
        """Freeze a sorted copy so callers cannot mutate facts after preparation."""
        resource_type = self.resource_type.strip()
        if not resource_type:
            raise ValueError("resource type must not be empty")
        if isinstance(self.resource_id, str) and not self.resource_id.strip():
            raise ValueError("resource identifier must not be empty")
        if not all(isinstance(key, str) and key.strip() for key in self.values):
            raise ValueError("resource fact keys must be non-empty strings")
        if not all(_is_immutable_resource_value(value) for value in self.values.values()):
            raise ValueError("resource fact values must be deeply immutable and finite")
        object.__setattr__(self, "resource_type", resource_type)
        if isinstance(self.resource_id, str):
            object.__setattr__(self, "resource_id", self.resource_id.strip())
        object.__setattr__(self, "values", MappingProxyType(dict(sorted(self.values.items()))))
