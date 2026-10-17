"""Read exact selected awards; canonical disclosure authority belongs to CON."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.compensation.api.awards import CompensationAwardFacts


class ContributionAwardReadPort(Protocol):
    """Read all retained awards for a bounded already-authorized contribution set."""

    async def read_contribution_awards(
        self, contribution_ids: tuple[UUID, ...]
    ) -> tuple[CompensationAwardFacts, ...]:
        """Return exact complete owner facts, including no rows for unpaid records."""
        ...


@dataclass(frozen=True, slots=True)
class ContributorAwardTotal:
    """The exact sum of immutable awards in one instrument and unit; not a payment claim."""

    instrument_type: str
    unit_code: str
    quantity: Decimal


class ContributorAwardTotalsPort(Protocol):
    """Sum a contributor's awards in an already authorized project set."""

    async def read_award_totals(
        self, contributor_id: UUID, project_ids: frozenset[UUID],
    ) -> tuple[ContributorAwardTotal, ...]: ...


class ProjectAwardTotalsPort(Protocol):
    """Sum every contributor's awards in one project whose totals the caller may see."""

    async def read_project_award_totals(self, project_id: UUID) -> tuple[ContributorAwardTotal, ...]:
        """Exact Decimal sums per instrument and unit, in a stable order."""
        ...
