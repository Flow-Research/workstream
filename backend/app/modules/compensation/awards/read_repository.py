"""Bounded canonical award projection with no fulfillment or policy mutation."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api.award_reads import ContributorAwardTotal
from app.modules.compensation.api.awards import CompensationAwardFacts
from app.modules.compensation.api.instruments import CompensationInstrumentType
from app.modules.compensation.awards.models import CompensationAward


class ContributionAwardReadRepository:
    """Use the caller's snapshot to return only its selected contribution awards."""

    def __init__(self, session: AsyncSession) -> None:
        """Share the export transaction; this owner never commits."""
        self._session = session

    async def read_contribution_awards(
        self, contribution_ids: tuple[UUID, ...]
    ) -> tuple[CompensationAwardFacts, ...]:
        """Preserve original IDs, Decimal quantities and every complete-set member."""
        if len(contribution_ids) > 1_000 or len(set(contribution_ids)) != len(contribution_ids):
            raise ValueError("invalid contribution award selection")
        if not contribution_ids:
            return ()
        rows = (await self._session.scalars(
            select(CompensationAward).where(
                CompensationAward.contribution_record_id.in_(contribution_ids)
            ).order_by(CompensationAward.contribution_record_id, CompensationAward.instrument_type)
        )).all()
        return tuple(CompensationAwardFacts(
            id=row.id, project_id=UUID(row.project_id),
            contribution_record_id=row.contribution_record_id,
            contributor_id=UUID(row.contributor_id),
            contribution_policy_version_id=row.contribution_policy_version_id,
            award_definition_id=row.award_definition_id,
            adapter_binding_id=row.adapter_binding_id,
            instrument_type=CompensationInstrumentType(row.instrument_type),
            unit_code=row.unit_code, quantity=row.quantity,
            created_at=row.created_at, correlation_id=row.correlation_id,
        ) for row in rows)

    async def read_award_totals(
        self, contributor_id: UUID, project_ids: frozenset[UUID],
    ) -> tuple[ContributorAwardTotal, ...]:
        """Exact Decimal sums per instrument and unit, in a stable order."""
        if not project_ids:
            return ()
        return await self._totals(
            CompensationAward.contributor_id == str(contributor_id),
            CompensationAward.project_id.in_([str(item) for item in project_ids]),
        )

    async def read_project_award_totals(self, project_id: UUID) -> tuple[ContributorAwardTotal, ...]:
        """Every contributor's awards in one project, summed per instrument and unit."""
        return await self._totals(CompensationAward.project_id == str(project_id))

    async def _totals(self, *scope) -> tuple[ContributorAwardTotal, ...]:
        """One grouped sum over the selected awards."""
        rows = (await self._session.execute(
            select(
                CompensationAward.instrument_type, CompensationAward.unit_code,
                func.sum(CompensationAward.quantity),
            ).where(*scope).group_by(CompensationAward.instrument_type, CompensationAward.unit_code).order_by(
                CompensationAward.instrument_type, CompensationAward.unit_code,
            )
        )).all()
        return tuple(ContributorAwardTotal(row[0], row[1], row[2]) for row in rows)
