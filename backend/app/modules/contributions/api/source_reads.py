"""Minimal source-read facts consumed by CON without reversing owner dependencies."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class ContributionTaskSourceFacts(BaseModel):
    """Exact selected task identity and source labels, with no lifecycle authority."""

    model_config = _STRICT
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    task_size: Literal["small", "medium", "large"]
    contribution_policy_version_id: UUID
    contribution_award_definition_id: UUID | None
    title: str
    source_type: str
    source_ref: str | None
    external_task_id: str | None


class ContributionAcceptanceSourceFacts(BaseModel):
    """Actual FinalAcceptance identity, accepted actor and database-owned source time."""

    model_config = _STRICT
    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    accepted_submitter_id: UUID
    accepted_at: AwareDatetime
    acceptance_source: Literal["human_review", "task_post_submit_route"]
    source_review_id: UUID | None
    source_routing_manifest_id: UUID | None

    @model_validator(mode="after")
    def exclusive_source(self):
        """Retain the exact human Review or automatic routing manifest reference."""
        human = self.acceptance_source == "human_review"
        if (self.source_review_id is not None) != human or (
            self.source_routing_manifest_id is not None
        ) == human:
            raise ValueError("contribution acceptance source is incomplete")
        return self


class ContributionTaskSourceReadPort(Protocol):
    """The selected CON set fixes every project/task selector before owner reads."""

    async def read_contribution_tasks(
        self, selectors: tuple[tuple[UUID, UUID, UUID], ...],
    ) -> tuple[ContributionTaskSourceFacts, ...]:
        """Return only the exact selected source labels in the caller's snapshot."""
        ...


class ContributionAcceptanceSourceReadPort(Protocol):
    """Read source times only for exact FinalAcceptance identities already in CON."""

    async def read_final_acceptances(
        self, selectors: tuple[tuple[UUID, UUID], ...],
    ) -> tuple[ContributionAcceptanceSourceFacts, ...]:
        """Preserve actual acceptance time and lineage without creating acceptance."""
        ...
