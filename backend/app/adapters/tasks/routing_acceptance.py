"""Compose existing REV/TASK/CON participants under one REV-owned held fence."""

from contextlib import asynccontextmanager

from app.adapters.reviews import final_acceptance_participant
from app.modules.reviews.api.acceptance import FinalAcceptanceInput, FinalAcceptanceRequest
from app.modules.tasks.api.routing_outcome import RoutingEconomicFacts


class RoutingAcceptanceAdapter:
    def __init__(self, session):
        self._participant = final_acceptance_participant(session)

    @asynccontextmanager
    async def prepare(self, current_generation):
        async with self._participant.prepare(current_generation) as prepared:
            yield _PreparedAdapter(prepared, current_generation)


class _PreparedAdapter:
    def __init__(self, prepared, generation):
        self._prepared, self._generation = prepared, generation

    async def require_new(self):
        await self._prepared.require_new()

    async def participate(self, source, effects, authority, authorized_generation):
        if source.source.human_review_required or authorized_generation <= 0:
            raise ValueError("false acceptance source unavailable")
        result = await self._prepared.participate(
            FinalAcceptanceRequest(
                acceptance=FinalAcceptanceInput(
                    id=effects.final_acceptance_id,
                    project_id=effects.project_id,
                    task_id=effects.task_id,
                    submission_id=effects.submission_id,
                    acceptance_source="task_post_submit_route",
                    source_review_id=None,
                    source_routing_manifest_id=source.source.id,
                    accepted_submitter_id=effects.contributor_id,
                    recorded_by=authority.actor_id,
                    policy_context_ref=source.source.locked_policy.locked_review_policy_id,
                    source_authorization_decision_id=authority.decision_id,
                ),
                task_effects=effects,
                correlation_id=source.request.route_operation_id,
                expected_generation=self._generation,
            )
        )
        return RoutingEconomicFacts(
            final_acceptance_id=result.acceptance.id,
            contribution_record_id=result.participation.contribution.id,
            award_ids=tuple(award.id for award in result.participation.awards),
        )
