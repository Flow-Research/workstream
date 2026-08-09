"""Typed capability ports forming the sole public authorization seam."""

from __future__ import annotations

from typing import Protocol, TypeVar
from uuid import UUID

from .action_ids import ActionId
from .decisions import AuthorizationDecision
from .facts import ActorIdentityFacts, ResourceFacts

PreparedHandleT = TypeVar("PreparedHandleT", covariant=True)


class AuthorizationPort(Protocol):
    """Make one request-scoped decision from canonical immutable facts."""

    async def authorize(
        self,
        *,
        actor: ActorIdentityFacts,
        action_id: ActionId,
        resource: ResourceFacts,
        request_id: UUID,
    ) -> AuthorizationDecision:
        """Return the exact decision or raise a stable boundary error."""
        ...


class PreparedAuthorizationPort(Protocol[PreparedHandleT]):
    """Issue opaque capabilities; consumption stays owned by an exact adapter."""

    async def prepare(
        self,
        *,
        actor: ActorIdentityFacts,
        action_id: ActionId,
        resource: ResourceFacts,
        request_id: UUID,
        idempotency_key: UUID,
    ) -> PreparedHandleT:
        """Return a process-local opaque handle bound to the supplied facts."""
        ...
