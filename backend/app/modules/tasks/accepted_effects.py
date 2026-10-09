"""Hidden two-phase TASK terminal participant for shared final acceptance."""

from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.modules.tasks.api.accepted_effects import (
    TaskAcceptedEffectsFence,
    TaskAcceptedEffectsRequest,
    TaskAcceptedEffectsResult,
    TaskAcceptedEffectsUnavailable,
    TaskAcceptedPreparation,
)
from app.modules.tasks.repository import TaskRepository


class TaskAcceptedEffectsParticipant:
    """Lock, validate, and apply TASK-owned final-acceptance effects."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        fence: TaskAcceptedEffectsFence,
    ) -> None:
        """Bind TASK effects to the caller's session and injected canonical fence."""
        self._session = session
        self._repository = TaskRepository(session)
        self._fence = fence

    async def lock_accepted_effects(
        self,
        request: TaskAcceptedEffectsRequest,
        *,
        expected_generation: int,
    ) -> TaskAcceptedPreparation:
        """Acquire the fence first, then lock and validate exact TASK lineage."""
        checked = self._validate_request(request)
        return await self._lock_and_validate(
            checked, expected_generation=expected_generation
        )

    async def apply_accepted_effects(
        self,
        request: TaskAcceptedEffectsRequest,
        *,
        disposition: Literal["new", "replay"],
        expected_generation: int,
    ) -> TaskAcceptedEffectsResult:
        """Recheck the observed disposition before mutating only terminal statuses."""
        checked = self._validate_request(request)
        if type(disposition) is not str or disposition not in ("new", "replay"):
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")
        preparation, task, assignment = await self._lock_and_validate_rows(
            checked, expected_generation=expected_generation
        )
        if preparation.disposition != disposition:
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")
        if disposition == "new":
            task.status = "accepted"
            assignment.status = "completed"
            await self._session.flush()
        return TaskAcceptedEffectsResult(
            request=checked,
            task_status="accepted",
            assignment_status="completed",
        )

    async def require_routing_source(
        self,
        request: TaskAcceptedEffectsRequest,
        manifest_id: UUID,
        *,
        source_authorization_decision_id: UUID,
        recorded_by: UUID,
        locked_review_policy_id: UUID,
        expected_generation: int,
        disposition: Literal["new", "replay"],
    ) -> None:
        """Reload and compare the actual immutable false-policy routing manifest."""
        checked = self._validate_request(request)
        if not isinstance(manifest_id, UUID):
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")
        valid = await self._session.scalar(
            text(
                "SELECT public.task_routing_acceptance_matches(:manifest, :acceptance, :decision, "
                ":actor, :project, :task, :submission, :policy, :generation, :is_new)"
            ),
            {
                "manifest": manifest_id,
                "acceptance": checked.final_acceptance_id,
                "decision": source_authorization_decision_id,
                "actor": recorded_by,
                "project": checked.project_id,
                "task": checked.task_id,
                "submission": checked.submission_id,
                "policy": locked_review_policy_id,
                "generation": expected_generation,
                "is_new": disposition == "new",
            },
        )
        if valid is not True:
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")

    async def _lock_and_validate(
        self,
        request: TaskAcceptedEffectsRequest,
        *,
        expected_generation: int,
    ) -> TaskAcceptedPreparation:
        preparation, _, _ = await self._lock_and_validate_rows(
            request, expected_generation=expected_generation
        )
        return preparation

    async def _lock_and_validate_rows(
        self,
        request: TaskAcceptedEffectsRequest,
        *,
        expected_generation: int,
    ):
        """Retain the canonical fence and Task -> Assignment -> Submission locks."""
        lifecycle = await self._fence.acquire(expected_generation)
        task = await self._repository.lock_project_task(
            request.project_id, request.task_id
        )
        if task is None:
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")
        assignment = await self._repository.lock_accepted_assignment(
            project_id=request.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
        )
        latest_submission = await self._repository.get_latest_submission_for_task(
            str(request.task_id), for_update=True, populate_existing=True
        )
        if assignment is None or latest_submission is None:
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")

        if (
            task.assigned_to != str(request.contributor_id)
            or task.locked_contribution_policy_version_id
            != request.contribution_policy_version_id
            or task.locked_review_policy_id is None
            or assignment.contributor_id != str(request.contributor_id)
            or assignment.submitter_contribution_policy_version_id
            != request.contribution_policy_version_id
            or assignment.accepted_at is None
            or assignment.released_at is not None
            or latest_submission.id != str(request.submission_id)
            or latest_submission.version != request.submission_version
            or latest_submission.task_assignment_id != str(request.assignment_id)
            or latest_submission.contributor_id != str(request.contributor_id)
            or latest_submission.contribution_policy_version_id
            != request.contribution_policy_version_id
            or latest_submission.artifact_content_id != str(request.content_id)
            or latest_submission.status != "submitted"
            or latest_submission.locked_review_policy_id
            != task.locked_review_policy_id
        ):
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")

        if (
            task.status == request.expected_task_status
            and assignment.status == "active"
        ):
            disposition: Literal["new", "replay"] = "new"
        elif task.status == "accepted" and assignment.status == "completed":
            disposition = "replay"
        else:
            raise TaskAcceptedEffectsUnavailable("task_accepted_effects_unavailable")
        if disposition == "new" and (lifecycle.phase != "live" or lifecycle.generation <= 0):
            raise TaskAcceptedEffectsUnavailable("lifecycle is not live")
        try:
            preparation = TaskAcceptedPreparation(
                disposition=disposition,
                locked_review_policy_id=UUID(task.locked_review_policy_id),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise TaskAcceptedEffectsUnavailable(
                "task_accepted_effects_unavailable"
            ) from exc
        return preparation, task, assignment

    @staticmethod
    def _validate_request(
        request: TaskAcceptedEffectsRequest,
    ) -> TaskAcceptedEffectsRequest:
        try:
            return TaskAcceptedEffectsRequest.model_validate(request)
        except (TypeError, ValueError, ValidationError) as exc:
            raise TaskAcceptedEffectsUnavailable(
                "task_accepted_effects_unavailable"
            ) from exc


__all__ = ("TaskAcceptedEffectsParticipant",)
