"""Hidden submitter participation contract; construction grants no authority."""

from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.modules.compensation.api.awards import CompensationAwardFacts

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
_Digest = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
_Generation = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]


class ContributionParticipationUnavailable(RuntimeError):
    """The exact frozen rule or participant transaction is unavailable."""


class ContributionParticipationConflict(RuntimeError):
    """A replay differs from the immutable contribution or award facts."""


class ParticipationLifecycleFacts(Protocol):
    """Read-only scalar phase facts from the externally owned canonical fence."""

    @property
    def phase(self) -> str:
        ...

    @property
    def generation(self) -> int:
        ...


class ParticipationLifecycleFence(Protocol):
    """Acquire only the canonical lifecycle fence owned by external composition."""

    async def acquire(self, expected_generation: int) -> ParticipationLifecycleFacts:
        """Hold the expected generation through the caller's root transaction."""
        ...


class SubmitterParticipationRequest(BaseModel):
    """Exact scalar FinalAcceptance source lineage selected by its future owner."""

    model_config = _STRICT_FROZEN

    acceptance_disposition: Literal["new", "replay"]
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    final_acceptance_id: UUID
    task_assignment_id: UUID
    contributor_id: UUID
    contribution_policy_version_id: UUID
    artifact_hash: _Digest
    correlation_id: UUID
    expected_generation: _Generation


class SubmitterContributionFacts(BaseModel):
    """Exact accepted-submission contribution persisted for the submitter."""

    model_config = _STRICT_FROZEN

    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    contributor_id: UUID
    source_final_acceptance_id: UUID
    source_task_assignment_id: UUID
    artifact_hash: _Digest
    contribution_policy_version_id: UUID
    created_at: AwareDatetime


class SubmitterParticipationResult(BaseModel):
    """Immutable contribution and its exact complete frozen award set."""

    model_config = _STRICT_FROZEN

    contribution: SubmitterContributionFacts
    awards: tuple[CompensationAwardFacts, ...] = Field(max_length=2)


class SubmitterParticipationPort(Protocol):
    """Create or exactly replay submitter economic facts without committing."""

    async def participate_submitter(
        self, request: SubmitterParticipationRequest
    ) -> SubmitterParticipationResult:
        """Flush exact facts in the caller's fenced root transaction."""
        ...


__all__ = (
    "ContributionParticipationConflict",
    "ContributionParticipationUnavailable",
    "ParticipationLifecycleFence",
    "SubmitterContributionFacts",
    "SubmitterParticipationPort",
    "SubmitterParticipationRequest",
    "SubmitterParticipationResult",
)
