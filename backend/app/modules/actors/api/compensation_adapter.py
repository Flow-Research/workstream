"""Public ACTORS capability for compensation-adapter eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class CompensationAdapterActorUnavailable(RuntimeError):
    """Conceal missing, inactive, or ineligible adapter actors."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CompensationAdapterActorEligibilityFacts:
    """Exact active service actor retained under an ACTORS-owned fence."""

    adapter_actor_id: UUID


class CompensationAdapterActorEligibilityPort(Protocol):
    """Lock and validate one exact compensation-adapter actor."""

    async def lock_compensation_adapter_actor(
        self, adapter_actor_id: UUID
    ) -> CompensationAdapterActorEligibilityFacts:
        """Retain the ACTORS eligibility fence through the caller transaction."""
