"""Hidden shared acceptance core; no production entry or AUTH capability."""

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contributions.api import (
    ContributionParticipationConflict,
    ContributionParticipationUnavailable,
    SubmitterParticipationPort,
    SubmitterParticipationRequest,
    SubmitterParticipationResult,
)
from app.modules.reviews.acceptance.repository import FinalAcceptanceRepository
from app.modules.reviews.api.acceptance import (
    FinalAcceptanceConflict, FinalAcceptanceRequest, FinalAcceptanceResult,
)
from app.modules.reviews.api.lifecycle import JointLifecycleMutationFence
from app.modules.tasks.api.accepted_effects import (
    TaskAcceptedEffectsPort, TaskAcceptedEffectsResult, TaskAcceptedEffectsUnavailable,
    TaskAcceptedPreparation,
)


class FinalAcceptanceParticipant:
    """Compose existing owners in one caller transaction; never commit or authorize."""

    def __init__(
        self, session: AsyncSession, *, fence: JointLifecycleMutationFence,
        tasks: TaskAcceptedEffectsPort, contributions: SubmitterParticipationPort,
    ) -> None:
        self._fence = fence
        self._tasks = tasks
        self._contributions = contributions
        self._repository = FinalAcceptanceRepository(session)

    async def participate(self, request: FinalAcceptanceRequest) -> FinalAcceptanceResult:
        """Fence, lock TASK, bind source, persist acceptance, then stage owner effects."""
        try:
            checked = FinalAcceptanceRequest.model_validate(request)
        except (TypeError, ValueError, ValidationError) as exc:
            raise FinalAcceptanceConflict("final_acceptance_conflict") from exc
        lifecycle = await self._fence.acquire(checked.expected_generation)
        try:
            return await self._participate(checked, lifecycle)
        except (
            TaskAcceptedEffectsUnavailable, ContributionParticipationConflict,
            ContributionParticipationUnavailable,
            TypeError, ValueError, ValidationError,
        ) as exc:
            raise FinalAcceptanceConflict("final_acceptance_conflict") from exc

    async def _participate(self, request: FinalAcceptanceRequest, lifecycle) -> FinalAcceptanceResult:
        source, task = request.acceptance, request.task_effects
        prepared = TaskAcceptedPreparation.model_validate(
            await self._tasks.lock_accepted_effects(
                task, expected_generation=request.expected_generation,
            )
        )
        if prepared.disposition == "new" and (lifecycle.phase != "live" or lifecycle.generation <= 0):
            raise FinalAcceptanceConflict("lifecycle is not live")
        if prepared.locked_review_policy_id != source.policy_context_ref:
            raise FinalAcceptanceConflict("final_acceptance_conflict")
        if source.acceptance_source == "human_review":
            await self._repository.require_human_source(request)
        else:
            await self._tasks.require_routing_source(task, source.source_routing_manifest_id)
        acceptance = await self._repository.persist(source, disposition=prepared.disposition)
        effects = TaskAcceptedEffectsResult.model_validate(
            await self._tasks.apply_accepted_effects(
                task, disposition=prepared.disposition,
                expected_generation=request.expected_generation,
            )
        )
        if effects.request != task:
            raise FinalAcceptanceConflict("final_acceptance_conflict")
        participation_request = SubmitterParticipationRequest(
            acceptance_disposition=prepared.disposition,
            project_id=source.project_id, task_id=source.task_id,
            submission_id=source.submission_id, final_acceptance_id=source.id,
            task_assignment_id=task.assignment_id, contributor_id=task.contributor_id,
            contribution_policy_version_id=task.contribution_policy_version_id,
            artifact_hash=task.content_sha256, correlation_id=request.correlation_id,
            expected_generation=request.expected_generation,
        )
        participation = SubmitterParticipationResult.model_validate(
            await self._contributions.participate_submitter(participation_request)
        )
        contribution = participation.contribution
        expected = {
            "project_id": source.project_id, "task_id": source.task_id,
            "submission_id": source.submission_id, "contributor_id": task.contributor_id,
            "source_final_acceptance_id": source.id,
            "source_task_assignment_id": task.assignment_id,
            "artifact_hash": task.content_sha256,
            "contribution_policy_version_id": task.contribution_policy_version_id,
        }
        if any(getattr(contribution, key) != value for key, value in expected.items()):
            raise FinalAcceptanceConflict("final_acceptance_conflict")
        return FinalAcceptanceResult(
            acceptance=acceptance, task_effects=effects, participation=participation,
        )
