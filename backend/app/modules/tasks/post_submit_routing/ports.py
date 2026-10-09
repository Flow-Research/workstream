"""Consumer-owned boundaries for one authorized TASK outcome transaction."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.routing_outcome import RoutingAuthorityFacts, RoutingEconomicFacts

from app.modules.outbox.api import OutboxClaim
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest
from app.modules.tasks.api.post_submit_routing import (
    TaskRoutingRequestFacts,
    TaskRoutingSourcePreparation,
)


class PreparedRoutingAuthority(Protocol):
    async def consume(
        self,
        source: TaskRoutingSourcePreparation,
        claim: OutboxClaim,
        effects: TaskAcceptedEffectsRequest | None,
        authorized_generation: int | None,
    ) -> RoutingAuthorityFacts: ...

    async def validate_replay(
        self,
        source: TaskRoutingSourcePreparation,
        retained: RoutingAuthorityFacts,
        effects: TaskAcceptedEffectsRequest | None,
        authorized_generation: int | None,
    ) -> None: ...


class RoutingAuthorizationPort(Protocol):
    def prepare(
        self, request: TaskRoutingRequestFacts
    ) -> AbstractAsyncContextManager[PreparedRoutingAuthority]: ...


class PreparedRoutingAcceptance(Protocol):
    async def require_new(self) -> None: ...

    async def participate(
        self,
        source: TaskRoutingSourcePreparation,
        effects: TaskAcceptedEffectsRequest,
        authority: RoutingAuthorityFacts,
        authorized_generation: int,
    ) -> RoutingEconomicFacts: ...


class RoutingAcceptancePort(Protocol):
    def prepare(
        self, current_generation: int
    ) -> AbstractAsyncContextManager[PreparedRoutingAcceptance]: ...


class RoutingAuditPort(Protocol):
    async def record(
        self,
        *,
        audit_event_id: UUID,
        source: TaskRoutingSourcePreparation,
        authority: RoutingAuthorityFacts,
        economic: RoutingEconomicFacts | None,
        replay: bool,
    ) -> None: ...
