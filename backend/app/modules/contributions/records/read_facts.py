"""CON-private stored source/rule facts used by its actual evidence reader."""

from decimal import Decimal
from dataclasses import dataclass
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.contributions.api.records import ContributionReadRequest
from app.modules.contributions.records.schemas import ContributionRecordInput

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class FrozenContributionAward(BaseModel):
    """Exact published terms used to validate the retained award set."""

    model_config = _STRICT
    id: UUID
    instrument: Literal["money", "project_points"]
    unit: str
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)


class ContributionReadFacts(ContributionRecordInput):
    """Stored immutable source and exact frozen rule for complete-set validation."""

    model_config = _STRICT
    recorded_at: AwareDatetime
    policy_version_number: int = Field(gt=0)
    compensation_mode: Literal["unpaid", "compensated"]
    award_definitions: tuple[FrozenContributionAward, ...] = Field(max_length=1)

    @model_validator(mode="after")
    def validate_frozen_set(self) -> Self:
        """An unpaid rule has no definitions; compensated rules have one per instrument."""
        count = len(self.award_definitions)
        if len({item.id for item in self.award_definitions}) != count or len({
            item.instrument for item in self.award_definitions
        }) != count or (
            self.compensation_mode == "unpaid" and count != 0
        ) or (self.compensation_mode == "compensated" and count != 1):
            raise ValueError("stored contribution rule is incomplete")
        return self


class ContributionReadRepositoryPort(Protocol):
    """Load an exact fixed-membership page after caller authorization."""

    async def read(self, request: ContributionReadRequest) -> "ContributionReadPage":
        """Pre-filter a first selection or use only its retained continuation IDs."""
        ...


@dataclass(frozen=True)
class ContributionReadPage:
    """One ordered evidence page and its optional signed continuation."""

    records: tuple[ContributionReadFacts, ...]
    next_cursor: str | None
