"""TASK-owned source labels selected by immutable contribution identities."""

from uuid import UUID

from app.modules.tasks.api.contribution_evidence import ContributionTaskEvidencePort
from app.modules.contributions.api.source_reads import (
    ContributionTaskSourceFacts,
)


class ContributionTaskSourceReadAdapter:
    """Translate TASK's readonly owner reply without making CON depend on TASK."""

    def __init__(self, source: ContributionTaskEvidencePort) -> None:
        """Require the selected TASK owner port on the caller's export session."""
        self._source = source

    async def read_contribution_tasks(
        self, selectors: tuple[tuple[UUID, UUID, UUID], ...],
    ) -> tuple[ContributionTaskSourceFacts, ...]:
        """Preserve each actual selected source value; CON verifies the selector set."""
        return tuple(ContributionTaskSourceFacts.model_validate(row.model_dump())
                     for row in await self._source.read_contribution_tasks(selectors))
