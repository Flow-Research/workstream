"""Flush-only owner of complete immutable compensation award sets."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.compensation.api import (
    CompleteAwardSetRequest,
    CompleteAwardSetResult,
    CompensationAwardConflict,
    CompensationAwardFacts,
    CompensationInstrumentType,
)
from app.modules.compensation.awards.models import CompensationAward


class CompensationAwardParticipant:
    """Create all new awards or exactly validate an existing complete set."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def complete_award_set(
        self, request: CompleteAwardSetRequest
    ) -> CompleteAwardSetResult:
        """Copy frozen facts without committing or repairing a replay."""
        try:
            checked = CompleteAwardSetRequest.model_validate(request)
        except (TypeError, ValueError, ValidationError) as exc:
            raise CompensationAwardConflict("compensation_award_conflict") from exc
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise CompensationAwardConflict("compensation_award_conflict")

        if checked.disposition == "new":
            self._session.add_all(
                [
                    CompensationAward(
                        id=new_record_id(),
                        project_id=str(checked.contribution.project_id),
                        contribution_record_id=checked.contribution.id,
                        contributor_id=str(checked.contribution.contributor_id),
                        contribution_policy_version_id=(
                            checked.contribution.contribution_policy_version_id
                        ),
                        award_definition_id=definition.id,
                        adapter_binding_id=definition.adapter_binding_id,
                        instrument_type=definition.instrument_type.value,
                        unit_code=definition.unit_code,
                        quantity=definition.quantity,
                        correlation_id=checked.correlation_id,
                    )
                    for definition in checked.definitions
                ]
            )
            await self._session.flush()

        awards = await self._load(checked)
        self._require_exact_complete_set(checked, awards)
        return CompleteAwardSetResult(awards=awards)

    async def _load(
        self, request: CompleteAwardSetRequest
    ) -> tuple[CompensationAwardFacts, ...]:
        """Read the stored set after insert or for exact replay validation."""
        rows = (
            await self._session.scalars(
                select(CompensationAward)
                .where(
                    CompensationAward.contribution_record_id
                    == request.contribution.id
                )
                .order_by(CompensationAward.instrument_type)
            )
        ).all()
        try:
            return tuple(
                CompensationAwardFacts(
                    id=row.id,
                    project_id=UUID(row.project_id),
                    contribution_record_id=row.contribution_record_id,
                    contributor_id=UUID(row.contributor_id),
                    contribution_policy_version_id=row.contribution_policy_version_id,
                    award_definition_id=row.award_definition_id,
                    adapter_binding_id=row.adapter_binding_id,
                    instrument_type=CompensationInstrumentType(row.instrument_type),
                    unit_code=row.unit_code,
                    quantity=row.quantity,
                    created_at=row.created_at,
                    correlation_id=row.correlation_id,
                )
                for row in rows
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise CompensationAwardConflict("compensation_award_conflict") from exc

    @staticmethod
    def _require_exact_complete_set(
        request: CompleteAwardSetRequest,
        awards: tuple[CompensationAwardFacts, ...],
    ) -> None:
        """Reject missing, extra, crossed, or correlation-conflicting awards."""
        definitions = {item.instrument_type: item for item in request.definitions}
        if len(awards) != len(definitions):
            raise CompensationAwardConflict("compensation_award_conflict")
        for award in awards:
            definition = definitions.get(award.instrument_type)
            if definition is None or not (
                award.project_id == request.contribution.project_id
                and award.contribution_record_id == request.contribution.id
                and award.contributor_id == request.contribution.contributor_id
                and award.contribution_policy_version_id
                == request.contribution.contribution_policy_version_id
                and award.award_definition_id == definition.id
                and award.adapter_binding_id == definition.adapter_binding_id
                and award.unit_code == definition.unit_code
                and award.quantity == definition.quantity
                and award.correlation_id == request.correlation_id
            ):
                raise CompensationAwardConflict("compensation_award_conflict")
