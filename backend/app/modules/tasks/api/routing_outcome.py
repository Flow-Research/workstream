"""Detached immutable routing decision and economic identities; no authority."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, model_validator

SUBMISSION_FEEDBACK_EMAIL_EVENT = "SubmissionFeedbackEmailRequested"


class TaskRoutingLifecycleDeferred(RuntimeError):
    """Known pre-effect REV enablement refusal; the caller may retry after rollback."""


class RoutingAuthorityFacts(BaseModel):
    """Actual decision identity and the exact resource context retained by TASK."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision_id: UUID
    actor_id: UUID
    identity_link_id: UUID
    context_json: str


class RoutingEconomicFacts(BaseModel):
    """Immutable identities returned by shared acceptance and CON participation."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    final_acceptance_id: UUID
    contribution_record_id: UUID
    award_ids: tuple[UUID, ...]


class TaskRoutingOutcome(BaseModel):
    """Exact staged outcome identities; successful transaction exit still owns commit."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: UUID
    task_id: UUID
    submission_id: UUID
    completion_event_id: UUID
    routing_manifest_id: UUID
    authorization_decision_id: UUID
    outcome_event_id: UUID
    routing_recommendation: Literal["allow_review", "needs_revision"]
    final_acceptance_id: UUID | None
    economic: RoutingEconomicFacts | None
    replayed: bool

    @model_validator(mode="after")
    def coherent_economics(self):
        """A human handoff has no economics; acceptance has one exact identity."""
        if (self.final_acceptance_id is None) != (self.economic is None):
            raise ValueError("routing outcome economics are inconsistent")
        if self.economic is not None and self.economic.final_acceptance_id != self.final_acceptance_id:
            raise ValueError("routing outcome acceptance identity differs")
        if self.routing_recommendation == "needs_revision" and self.economic is not None:
            raise ValueError("remediation outcome cannot contain acceptance economics")
        return self
