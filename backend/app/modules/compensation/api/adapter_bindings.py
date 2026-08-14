"""Public CON contracts for hidden compensation adapter-binding behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, TypeAlias
from uuid import UUID

from app.modules.actors.api import CompensationAdapterActorEligibilityPort
from app.modules.projects.api import ProjectCompensationBindingEligibilityPort

AdapterBindingAction = Literal[
    "compensation.adapter_binding.create",
    "compensation.adapter_binding.suspend",
    "compensation.adapter_binding.resume",
]
AdapterBindingEventType = Literal["created", "suspended", "resumed"]
AdapterBindingStatus = Literal["active", "suspended"]


class AdapterBindingUnavailable(RuntimeError):
    """Fail closed when hidden binding behavior has no authority."""


class AdapterBindingConflict(RuntimeError):
    """Conceal absence, mismatch, stale state, or unauthorized recovery."""


def _require_positive_version(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("expected_lifecycle_version must be a positive integer")


def _require_uuids(**values: object) -> None:
    invalid = next((name for name, value in values.items() if type(value) is not UUID), None)
    if invalid is not None:
        raise ValueError(f"{invalid} must be a UUID")


def validate_adapter_route_key(value: str) -> str:
    """Return one canonical, bounded, traversal-free adapter route key."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 120
        or not value[0].isascii()
        or not value[0].isalpha()
        or any(
            not (character.isascii() and (character.isalnum() or character in "._:-"))
            for character in value
        )
        or ".." in value
    ):
        raise ValueError("route_key must be canonical and traversal-free")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingCreateRequest:
    operation_id: UUID
    actor_profile_id: UUID
    project_id: UUID
    instrument_type: Literal["money", "project_points"]
    adapter_actor_id: UUID
    route_key: str

    def __post_init__(self) -> None:
        _require_uuids(
            operation_id=self.operation_id,
            actor_profile_id=self.actor_profile_id,
            project_id=self.project_id,
            adapter_actor_id=self.adapter_actor_id,
        )
        if self.instrument_type not in {"money", "project_points"}:
            raise ValueError("instrument_type must be money or project_points")
        validate_adapter_route_key(self.route_key)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingReadRequest:
    actor_profile_id: UUID
    project_id: UUID
    adapter_binding_id: UUID

    def __post_init__(self) -> None:
        _require_uuids(
            actor_profile_id=self.actor_profile_id,
            project_id=self.project_id,
            adapter_binding_id=self.adapter_binding_id,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingSuspendRequest:
    operation_id: UUID
    actor_profile_id: UUID
    project_id: UUID
    adapter_binding_id: UUID
    expected_lifecycle_version: int

    def __post_init__(self) -> None:
        _require_uuids(
            operation_id=self.operation_id,
            actor_profile_id=self.actor_profile_id,
            project_id=self.project_id,
            adapter_binding_id=self.adapter_binding_id,
        )
        _require_positive_version(self.expected_lifecycle_version)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingResumeRequest:
    operation_id: UUID
    actor_profile_id: UUID
    project_id: UUID
    adapter_binding_id: UUID
    expected_lifecycle_version: int

    def __post_init__(self) -> None:
        _require_uuids(
            operation_id=self.operation_id,
            actor_profile_id=self.actor_profile_id,
            project_id=self.project_id,
            adapter_binding_id=self.adapter_binding_id,
        )
        _require_positive_version(self.expected_lifecycle_version)


AdapterBindingMutationRequest: TypeAlias = (
    AdapterBindingCreateRequest | AdapterBindingSuspendRequest | AdapterBindingResumeRequest
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingView:
    adapter_binding_id: UUID
    project_id: UUID
    instrument_type: str
    adapter_actor_id: UUID
    route_key: str
    status: AdapterBindingStatus
    lifecycle_version: int
    created_by: UUID
    created_at: datetime
    suspended_by: UUID | None
    suspended_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingMutationResult:
    event_id: UUID
    operation_id: UUID
    request_digest: str
    project_id: UUID
    adapter_binding_id: UUID
    event_type: AdapterBindingEventType
    actor_profile_id: UUID
    from_status: AdapterBindingStatus | None
    to_status: AdapterBindingStatus
    from_lifecycle_version: int
    to_lifecycle_version: int
    prior_suspension_event_id: UUID | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterBindingMutationAuthorizationFacts:
    action: AdapterBindingAction
    actor_profile_id: UUID
    operation_id: UUID
    request_digest: str
    project_id: UUID
    adapter_binding_id: UUID
    instrument_type: str
    adapter_actor_id: UUID
    route_key: str
    expected_status: AdapterBindingStatus | None
    expected_lifecycle_version: int | None

    def __post_init__(self) -> None:
        _require_uuids(
            actor_profile_id=self.actor_profile_id,
            operation_id=self.operation_id,
            project_id=self.project_id,
            adapter_binding_id=self.adapter_binding_id,
            adapter_actor_id=self.adapter_actor_id,
        )
        if self.instrument_type not in {"money", "project_points"}:
            raise ValueError("instrument_type must be money or project_points")


class AdapterBindingReadAuthorizationPort(Protocol):
    async def authorize_adapter_binding_read(self, request: AdapterBindingReadRequest) -> None:
        """Authorize disclosure of one exact project/binding pair."""


class AdapterBindingMutationAuthorizationPort(Protocol):
    async def prepare_adapter_binding_mutation(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> object:
        """Prepare opaque transaction-bound mutation authority."""

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        """Consume exact authority and return the bound actor."""

    def close_adapter_binding_mutation(self, prepared: object) -> None:
        """Invalidate one prepared object exactly once."""


class DenyAdapterBindingAuthorization:
    """Production-safe default until CP03 installs real AUTH adapters."""

    async def authorize_adapter_binding_read(self, request: AdapterBindingReadRequest) -> None:
        del request
        raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")

    async def prepare_adapter_binding_mutation(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> object:
        del facts
        raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        del prepared, facts
        raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")

    def close_adapter_binding_mutation(self, prepared: object) -> None:
        del prepared


AdapterBindingProjectEligibilityPort = ProjectCompensationBindingEligibilityPort
AdapterBindingActorEligibilityPort = CompensationAdapterActorEligibilityPort
