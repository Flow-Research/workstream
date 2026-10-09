"""Detached immutable routing decision and economic identities; no authority."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict


class RoutingAuthorityFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision_id: UUID
    actor_id: UUID
    identity_link_id: UUID
    context_json: str


class RoutingEconomicFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    final_acceptance_id: UUID
    contribution_record_id: UUID
    award_ids: tuple[UUID, ...]
