"""Strict complete award-set contract for accepted-submission contributions."""

from decimal import Decimal
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.modules.compensation.api.instruments import CompensationInstrumentType

_STRICT_FROZEN = ConfigDict(
    extra="forbid", frozen=True, strict=True, revalidate_instances="always"
)
_Quantity = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class CompensationAwardConflict(RuntimeError):
    """The requested complete award set differs from immutable stored facts."""


class AwardDefinitionFacts(BaseModel):
    """One exact frozen definition selected by the contribution owner."""

    model_config = _STRICT_FROZEN

    id: UUID
    project_id: UUID
    contribution_policy_version_id: UUID
    contribution_type: Literal["accepted_submission"]
    instrument_type: CompensationInstrumentType
    unit_code: str = Field(min_length=1, max_length=32)
    quantity: _Quantity
    adapter_binding_id: UUID


class AwardContributionFacts(BaseModel):
    """Exact immutable contribution lineage needed to copy award facts."""

    model_config = _STRICT_FROZEN

    id: UUID
    project_id: UUID
    contributor_id: UUID
    contribution_policy_version_id: UUID
    contribution_type: Literal["accepted_submission"]


class CompleteAwardSetRequest(BaseModel):
    """Create a new set or validate replay of an already complete set."""

    model_config = _STRICT_FROZEN

    disposition: Literal["new", "replay"]
    compensation_mode: Literal["unpaid", "compensated"]
    contribution: AwardContributionFacts
    definitions: tuple[AwardDefinitionFacts, ...] = Field(max_length=2)
    correlation_id: UUID

    @model_validator(mode="after")
    def validate_complete_definition_set(self) -> Self:
        """Reject incomplete, duplicate, or crossed frozen definition facts."""
        definitions = self.definitions
        instruments = {item.instrument_type for item in definitions}
        expected = (
            self.compensation_mode == "unpaid" and not definitions
        ) or (
            self.compensation_mode == "compensated"
            and 1 <= len(definitions) <= 2
            and len(instruments) == len(definitions)
        )
        if not expected or any(
            item.project_id != self.contribution.project_id
            or item.contribution_policy_version_id
            != self.contribution.contribution_policy_version_id
            or item.contribution_type != self.contribution.contribution_type
            for item in definitions
        ):
            raise ValueError("award definitions differ from contribution lineage")
        return self


class CompensationAwardFacts(BaseModel):
    """Exact immutable award facts persisted by the compensation owner."""

    model_config = _STRICT_FROZEN

    id: UUID
    reward_model_version: Annotated[StrictInt, Field(ge=1, le=2)]
    project_id: UUID
    contribution_record_id: UUID
    contributor_id: UUID
    contribution_policy_version_id: UUID
    award_definition_id: UUID
    adapter_binding_id: UUID
    instrument_type: CompensationInstrumentType
    unit_code: str = Field(min_length=1, max_length=32)
    quantity: _Quantity
    created_at: AwareDatetime
    correlation_id: UUID


class CompleteAwardSetResult(BaseModel):
    """The exact complete stored set, ordered by instrument identity."""

    model_config = _STRICT_FROZEN

    awards: tuple[CompensationAwardFacts, ...] = Field(max_length=2)

    @model_validator(mode="after")
    def validate_unique_instruments(self) -> Self:
        """A returned complete set cannot contain duplicate instruments."""
        instruments = {item.instrument_type for item in self.awards}
        if len(instruments) != len(self.awards):
            raise ValueError("award result contains duplicate instruments")
        return self


class CompleteAwardSetPort(Protocol):
    """Write or exactly replay awards in the caller's current transaction."""

    async def complete_award_set(
        self, request: CompleteAwardSetRequest
    ) -> CompleteAwardSetResult:
        """Create every new award or validate an existing complete set."""
        ...


__all__ = (
    "AwardContributionFacts",
    "AwardDefinitionFacts",
    "CompleteAwardSetPort",
    "CompleteAwardSetRequest",
    "CompleteAwardSetResult",
    "CompensationAwardConflict",
    "CompensationAwardFacts",
)
