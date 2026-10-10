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
    """Transaction-scoped authority; consumption and replay use the same exact source."""
    async def consume(
        self,
        source: TaskRoutingSourcePreparation,
        claim: OutboxClaim,
        effects: TaskAcceptedEffectsRequest | None,
        authorized_generation: int | None,
    ) -> RoutingAuthorityFacts:
        """Consume genuine route authority over source, delivery claim and consequence."""
        ...

    async def validate_replay(
        self,
        source: TaskRoutingSourcePreparation,
        retained: RoutingAuthorityFacts,
        effects: TaskAcceptedEffectsRequest | None,
        authorized_generation: int | None,
    ) -> None:
        """Revalidate current authority against the retained immutable allow without writing."""
        ...


class RoutingAuthorizationPort(Protocol):
    """Prepare the fixed routing service through the canonical AUTH owner."""
    def prepare(
        self, request: TaskRoutingRequestFacts
    ) -> AbstractAsyncContextManager[PreparedRoutingAuthority]:
        """Hold exact router authority for the lifetime of this caller transaction."""
        ...


class PreparedRoutingAcceptance(Protocol):
    """REV preparation acquired before TASK custody, with no detached fence facts."""
    async def require_new(self) -> None:
        """Reject new effects unless the held lifecycle generation is live."""
        ...

    async def participate(
        self,
        source: TaskRoutingSourcePreparation,
        effects: TaskAcceptedEffectsRequest,
        authority: RoutingAuthorityFacts,
        authorized_generation: int,
    ) -> RoutingEconomicFacts:
        """Stage or exactly replay acceptance, TASK and CON effects without committing."""
        ...


class RoutingAcceptancePort(Protocol):
    """Acquire the shared acceptance fence before false-branch source locking."""
    def prepare(
        self, current_generation: int
    ) -> AbstractAsyncContextManager[PreparedRoutingAcceptance]:
        """Yield a closed acceptance capability for the current lifecycle generation."""
        ...


class RoutingAuditPort(Protocol):
    """Append or verify complete outcome evidence in the caller transaction."""
    async def record(
        self,
        *,
        audit_event_id: UUID,
        source: TaskRoutingSourcePreparation,
        authority: RoutingAuthorityFacts,
        economic: RoutingEconomicFacts | None,
        replay: bool,
    ) -> None:
        """Record TASK and economic facts, or verify every retained fact on replay."""
        ...
