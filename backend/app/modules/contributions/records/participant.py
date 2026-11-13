"""Hidden flush-only submitter contribution participant."""

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api import (
    AwardContributionFacts,
    CompleteAwardSetPort,
    CompleteAwardSetRequest,
    CompleteAwardSetResult,
    CompensationAwardConflict,
)
from app.modules.contributions.api import (
    ContributionParticipationConflict,
    ContributionParticipationUnavailable,
    ParticipationLifecycleFence,
    SubmitterContributionFacts,
    SubmitterParticipationRequest,
    SubmitterParticipationResult,
)
from app.modules.contributions.records.repository import (
    FrozenSubmitterRule,
    SubmitterContributionRepository,
)


class SubmitterContributionParticipant:
    """Create or replay exact submitter economic facts under an injected fence."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        fence: ParticipationLifecycleFence,
        awards: CompleteAwardSetPort,
    ) -> None:
        """Bind every participant to the caller's explicitly composed owners."""
        self._repository = SubmitterContributionRepository(session)
        self._fence = fence
        self._awards = awards

    async def participate_submitter(
        self, request: SubmitterParticipationRequest
    ) -> SubmitterParticipationResult:
        """Acquire first, then flush a contribution and its complete award set."""
        try:
            checked = SubmitterParticipationRequest.model_validate(request)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ContributionParticipationUnavailable(
                "contribution_participation_unavailable"
            ) from exc

        lifecycle = await self._fence.acquire(checked.expected_generation)
        if checked.acceptance_disposition == "new" and not lifecycle.new_effects_enabled:
            raise ContributionParticipationUnavailable("lifecycle is not live")
        rule = await self._repository.get_frozen_rule(
            checked.project_id, checked.contribution_policy_version_id,
            checked.task_size, checked.contribution_award_definition_id
        )
        contribution = await self._repository.apply_acceptance_disposition(checked)
        award_request = CompleteAwardSetRequest(
            disposition=checked.acceptance_disposition,
            compensation_mode=rule.compensation_mode,
            contribution=AwardContributionFacts(
                id=contribution.id,
                project_id=contribution.project_id,
                contributor_id=contribution.contributor_id,
                contribution_policy_version_id=(contribution.contribution_policy_version_id),
                contribution_type="accepted_submission",
                task_id=contribution.task_id,
                submission_id=contribution.submission_id,
                final_acceptance_id=contribution.source_final_acceptance_id,
                task_size=checked.task_size,
            ),
            definitions=rule.definitions,
            correlation_id=checked.correlation_id,
            expected_generation=checked.expected_generation,
            source_authorization_decision_id=checked.source_authorization_decision_id,
            source_routing_manifest_id=checked.source_routing_manifest_id,
        )
        try:
            award_result = CompleteAwardSetResult.model_validate(
                await self._awards.complete_award_set(award_request)
            )
        except (CompensationAwardConflict, TypeError, ValueError, ValidationError) as exc:
            raise ContributionParticipationConflict("contribution_participation_conflict") from exc
        self._require_exact_awards(checked, contribution, rule, award_result)
        return SubmitterParticipationResult(
            contribution=contribution,
            awards=award_result.awards,
        )

    @staticmethod
    def _require_exact_awards(
        request: SubmitterParticipationRequest,
        contribution: SubmitterContributionFacts,
        rule: FrozenSubmitterRule,
        result: CompleteAwardSetResult,
    ) -> None:
        """Validate an injected award owner's response before exposing facts."""
        definitions = {item.instrument_type: item for item in rule.definitions}
        if len(result.awards) != len(definitions):
            raise ContributionParticipationConflict("contribution_participation_conflict")
        for award in result.awards:
            definition = definitions.get(award.instrument_type)
            if definition is None or not _award_matches(
                award, definition, contribution, request.correlation_id
            ):
                raise ContributionParticipationConflict("contribution_participation_conflict")


def _award_matches(award, definition, contribution, correlation_id) -> bool:
    """Compare one returned award with its exact contribution and definition."""
    return (
        award.project_id == contribution.project_id
        and award.contribution_record_id == contribution.id
        and award.contributor_id == contribution.contributor_id
        and award.contribution_policy_version_id == contribution.contribution_policy_version_id
        and award.award_definition_id == definition.id
        and award.adapter_binding_id == definition.adapter_binding_id
        and award.instrument_type == definition.instrument_type
        and award.unit_code == definition.unit_code
        and award.quantity == definition.quantity
        and award.correlation_id == correlation_id
    )
