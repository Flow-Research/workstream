"""Internal policy selectors; disclosure authority belongs to the caller."""

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias
from uuid import UUID

from app.modules.compensation.api import CompensationInstrumentType


@dataclass(frozen=True, slots=True)
class PublishedContributionPolicySelection:
    """No draft identity, rule body or economic configuration crosses this port."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID


class PublishedContributionPolicyPort(Protocol):
    """The caller owns the project lock and authorization before disclosure."""

    async def published_selection(self, project_id: UUID) -> PublishedContributionPolicySelection | None: ...


@dataclass(frozen=True, slots=True)
class LockedCompensationAward:
    """One exact contributor-visible award definition."""

    instrument: CompensationInstrumentType
    unit: str
    quantity: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.instrument, CompensationInstrumentType)
            or type(self.unit) is not str
            or not self.unit
            or type(self.quantity) is not str
            or not self.quantity
        ):
            raise ValueError("locked compensation award is invalid")


LockedContributionTerms: TypeAlias = Literal["unpaid"] | tuple[LockedCompensationAward, ...]


@dataclass(frozen=True, slots=True)
class LockedCompensationTerms:
    """The complete contributor-visible graph for one immutable policy version."""

    contribution_policy_version_id: UUID
    accepted_submission: LockedContributionTerms
    completed_review: LockedContributionTerms

    def __post_init__(self) -> None:
        if not isinstance(self.contribution_policy_version_id, UUID):
            raise ValueError("locked compensation terms are invalid")
        for value in (self.accepted_submission, self.completed_review):
            if value == "unpaid":
                continue
            if (
                type(value) is not tuple
                or not 1 <= len(value) <= 2
                or any(not isinstance(item, LockedCompensationAward) for item in value)
                or len({item.instrument for item in value}) != len(value)
            ):
                raise ValueError("locked compensation terms are invalid")


class LockedCompensationTermsPort(Protocol):
    """Read complete terms by exact locked version; the caller owns disclosure authority."""

    async def read_locked_compensation_terms(
        self, project_id: UUID, contribution_policy_version_ids: tuple[UUID, ...]
    ) -> tuple[LockedCompensationTerms, ...]: ...
