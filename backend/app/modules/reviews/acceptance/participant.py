"""Hidden shared acceptance core; mandatory source custody and caller-owned commit."""

from contextlib import asynccontextmanager
from collections.abc import Callable

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
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from app.modules.tasks.api.accepted_effects import (
    TaskAcceptedEffectsPort, TaskAcceptedEffectsResult, TaskAcceptedEffectsUnavailable,
    TaskAcceptedPreparation,
)


class FinalAcceptanceParticipant:
    """Compose existing owners in one caller transaction; never commit or authorize."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tasks: Callable[[JointLifecycleMutationFence], TaskAcceptedEffectsPort],
        contributions: Callable[[JointLifecycleMutationFence], SubmitterParticipationPort],
    ) -> None:
        """Compose TASK and CON participants using the same held REV fence."""
        self._fence = PostgresJointLifecycleMutationFence(session)
        self._tasks = tasks
        self._contributions = contributions
        self._repository = FinalAcceptanceRepository(session)

    @asynccontextmanager
    async def prepare(self, expected_generation: int):
        """Acquire REV once, before the caller locks TASK or consumes AUTH."""
        async with self._fence.hold(expected_generation) as held:
            prepared = _PreparedFinalAcceptance(
                self,
                held,
                expected_generation,
                self._tasks(held),
                self._contributions(held),
            )
            try:
                yield prepared
            finally:
                prepared.close()

    async def _participate(
        self, request: FinalAcceptanceRequest, lifecycle, tasks, contributions
    ) -> FinalAcceptanceResult:
        """Stage the complete authorized acceptance or verify its exact retained tuple."""
        source, task = request.acceptance, request.task_effects
        prepared = TaskAcceptedPreparation.model_validate(
            await tasks.lock_accepted_effects(
                task,
                expected_generation=request.expected_generation,
            )
        )
        if prepared.disposition == "new" and (lifecycle.phase != "live" or lifecycle.generation <= 0):
            raise FinalAcceptanceConflict("lifecycle is not live")
        if prepared.locked_review_policy_id != source.policy_context_ref:
            raise FinalAcceptanceConflict("final_acceptance_conflict")
        if source.acceptance_source == "human_review":
            raise FinalAcceptanceConflict("human acceptance authority remains unavailable")
        else:
            await tasks.require_routing_source(
                task,
                source.source_routing_manifest_id,
                source_authorization_decision_id=source.source_authorization_decision_id,
                recorded_by=source.recorded_by,
                locked_review_policy_id=source.policy_context_ref,
                expected_generation=request.expected_generation,
                disposition=prepared.disposition,
            )
        acceptance = await self._repository.persist(source, disposition=prepared.disposition)
        effects = TaskAcceptedEffectsResult.model_validate(
            await tasks.apply_accepted_effects(
                task,
                disposition=prepared.disposition,
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
            await contributions.participate_submitter(participation_request)
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


class _PreparedFinalAcceptance:
    """Closed owner capability; neither detached lifecycle facts nor AUTH."""

    def __init__(self, owner, held, generation, tasks, contributions):
        """Retain owner participants bound to one held root-transaction fence."""
        self._owner, self._held = owner, held
        self.generation = generation
        self._tasks, self._contributions = tasks, contributions
        self._closed = False

    def close(self):
        """Invalidate the prepared capability when its context exits."""
        self._closed = True

    async def require_new(self) -> None:
        """Deny new effects before the caller consumes routing authority."""
        if self._closed:
            raise FinalAcceptanceConflict("acceptance preparation is closed")
        lifecycle = await self._held.acquire(self.generation)
        if lifecycle.phase != "live" or lifecycle.generation <= 0:
            raise FinalAcceptanceConflict("lifecycle is not live")

    async def participate(self, request: FinalAcceptanceRequest) -> FinalAcceptanceResult:
        """Reject closed or changed generations before staging shared acceptance."""
        if self._closed:
            raise FinalAcceptanceConflict("acceptance preparation is closed")
        try:
            checked = FinalAcceptanceRequest.model_validate(request)
            if checked.expected_generation != self.generation:
                raise FinalAcceptanceConflict("acceptance generation differs")
            lifecycle = await self._held.acquire(self.generation)
            return await self._owner._participate(
                checked,
                lifecycle,
                self._tasks,
                self._contributions,
            )
        except (
            TaskAcceptedEffectsUnavailable,
            ContributionParticipationConflict,
            ContributionParticipationUnavailable,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            raise FinalAcceptanceConflict("final_acceptance_conflict") from exc
