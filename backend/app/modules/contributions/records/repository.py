"""Persistence for exact accepted-submission contribution participation."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.compensation.api import AwardDefinitionFacts, CompensationInstrumentType
from app.modules.contributions.api import (
    ContributionParticipationConflict,
    ContributionParticipationUnavailable,
    SubmitterContributionFacts,
    SubmitterParticipationRequest,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.records.models import ContributionRecord


@dataclass(frozen=True, slots=True)
class FrozenSubmitterRule:
    """The one accepted-submission rule and its complete definition set."""

    compensation_mode: Literal["unpaid", "compensated"]
    definitions: tuple[AwardDefinitionFacts, ...]


class SubmitterContributionRepository:
    """Read the frozen rule and reserve the source-unique contribution row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_frozen_rule(
        self, project_id: UUID, contribution_policy_version_id: UUID
    ) -> FrozenSubmitterRule:
        """Read only the exact published or retired accepted-submission rule."""
        rule = (
            await self._session.execute(
                select(ContributionRule.id, ContributionRule.compensation_mode)
                .join(
                    ContributionPolicyVersion,
                    ContributionPolicyVersion.id == ContributionRule.contribution_policy_version_id,
                )
                .where(
                    ContributionPolicyVersion.id == contribution_policy_version_id,
                    ContributionPolicyVersion.project_id == str(project_id),
                    ContributionPolicyVersion.status.in_(("published", "retired")),
                    ContributionRule.project_id == str(project_id),
                    ContributionRule.contribution_type == "accepted_submission",
                )
            )
        ).one_or_none()
        if rule is None:
            raise ContributionParticipationUnavailable("contribution_participation_unavailable")

        rows = (
            await self._session.execute(
                select(
                    ContributionAwardDefinition.id,
                    ContributionAwardDefinition.project_id,
                    ContributionAwardDefinition.contribution_policy_version_id,
                    ContributionAwardDefinition.contribution_type,
                    ContributionAwardDefinition.instrument_type,
                    ContributionAwardDefinition.unit_code,
                    ContributionAwardDefinition.quantity,
                    ContributionAwardDefinition.adapter_binding_id,
                )
                .where(
                    ContributionAwardDefinition.contribution_rule_id == rule.id,
                    ContributionAwardDefinition.project_id == str(project_id),
                    ContributionAwardDefinition.contribution_policy_version_id
                    == contribution_policy_version_id,
                    ContributionAwardDefinition.contribution_type == "accepted_submission",
                )
                .order_by(ContributionAwardDefinition.instrument_type)
            )
        ).all()
        try:
            definitions = tuple(
                AwardDefinitionFacts(
                    id=row.id,
                    project_id=UUID(row.project_id),
                    contribution_policy_version_id=row.contribution_policy_version_id,
                    contribution_type=row.contribution_type,
                    instrument_type=CompensationInstrumentType(row.instrument_type),
                    unit_code=row.unit_code,
                    quantity=row.quantity,
                    adapter_binding_id=row.adapter_binding_id,
                )
                for row in rows
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise ContributionParticipationUnavailable(
                "contribution_participation_unavailable"
            ) from exc

        instruments = {item.instrument_type for item in definitions}
        complete = (rule.compensation_mode == "unpaid" and not definitions) or (
            rule.compensation_mode == "compensated"
            and len(definitions) == 1
            and len(instruments) == len(definitions)
        )
        if not complete:
            raise ContributionParticipationUnavailable("contribution_participation_unavailable")
        return FrozenSubmitterRule(
            compensation_mode=rule.compensation_mode,
            definitions=definitions,
        )

    async def apply_acceptance_disposition(
        self, request: SubmitterParticipationRequest
    ) -> SubmitterContributionFacts:
        """Insert new work or read an exact replay without repairing either mode."""
        if request.acceptance_disposition == "replay":
            winner = await self._select_exact_source(request)
            if winner is None or not self._matches(winner, request):
                raise ContributionParticipationConflict("contribution_participation_conflict")
            return self._facts(winner)

        candidate_id = new_record_id()
        inserted_id = await self._session.scalar(
            insert(ContributionRecord)
            .values(
                id=candidate_id,
                project_id=str(request.project_id),
                task_id=str(request.task_id),
                submission_id=str(request.submission_id),
                contribution_type="accepted_submission",
                contributor_id=str(request.contributor_id),
                source_review_id=None,
                source_review_lease_id=None,
                source_final_acceptance_id=request.final_acceptance_id,
                source_task_assignment_id=str(request.task_assignment_id),
                artifact_hash=request.artifact_hash,
                contribution_policy_version_id=request.contribution_policy_version_id,
            )
            .on_conflict_do_nothing(index_elements=[ContributionRecord.source_final_acceptance_id])
            .returning(ContributionRecord.id)
        )
        if inserted_id != candidate_id:
            raise ContributionParticipationConflict("contribution_participation_conflict")
        winner = await self._session.scalar(
            select(ContributionRecord)
            .where(
                ContributionRecord.id == candidate_id,
                ContributionRecord.project_id == str(request.project_id),
            )
            .execution_options(populate_existing=True)
        )
        if winner is None or not self._matches(winner, request):
            raise ContributionParticipationConflict("contribution_participation_conflict")
        return self._facts(winner)

    async def _select_exact_source(
        self, request: SubmitterParticipationRequest
    ) -> ContributionRecord | None:
        """Read the source-unique replay candidate without staging a row."""
        return await self._session.scalar(
            select(ContributionRecord)
            .where(
                ContributionRecord.source_final_acceptance_id == request.final_acceptance_id,
                ContributionRecord.project_id == str(request.project_id),
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _facts(winner: ContributionRecord) -> SubmitterContributionFacts:
        """Validate stored scalar types before returning public immutable facts."""
        try:
            return SubmitterContributionFacts(
                id=winner.id,
                project_id=UUID(winner.project_id),
                task_id=UUID(winner.task_id),
                submission_id=UUID(winner.submission_id),
                contributor_id=UUID(winner.contributor_id),
                source_final_acceptance_id=winner.source_final_acceptance_id,
                source_task_assignment_id=UUID(winner.source_task_assignment_id),
                artifact_hash=winner.artifact_hash,
                contribution_policy_version_id=winner.contribution_policy_version_id,
                created_at=winner.created_at,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise ContributionParticipationConflict("contribution_participation_conflict") from exc

    @staticmethod
    def _matches(winner: ContributionRecord, request: SubmitterParticipationRequest) -> bool:
        """Compare every caller-supplied immutable contribution source fact."""
        return (
            winner.project_id == str(request.project_id)
            and winner.task_id == str(request.task_id)
            and winner.submission_id == str(request.submission_id)
            and winner.contribution_type == "accepted_submission"
            and winner.contributor_id == str(request.contributor_id)
            and winner.source_review_id is None
            and winner.source_review_lease_id is None
            and winner.source_final_acceptance_id == request.final_acceptance_id
            and winner.source_task_assignment_id == str(request.task_assignment_id)
            and winner.artifact_hash == request.artifact_hash
            and winner.contribution_policy_version_id == request.contribution_policy_version_id
        )
