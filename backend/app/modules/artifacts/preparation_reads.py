"""ART projection of selected PRE runs and their retained intake custody."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api.submission_preparation import (
    PreparationFindingCounts, PreparationOutcome, ProjectSubmissionBundlePreparation,
    SubmissionBundlePreparationDetail, SubmissionBundlePreparationStatus, pre_submission_finding_counts,
    public_pre_submission_results,
)
from app.modules.artifacts.models import (
    ArtifactPutAttempt, SubmissionBundleAdmission, SubmissionBundleDurableIntent,
)
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitRunReadPort, SelectedPreSubmitRunView

_ADMISSION_STATE = {"ready": "ready", "consumed": "submitted", "stale": "stale"}
# The stored run status and eligibility each projected outcome is derived from.
_OUTCOME_FILTER = {
    "pending": (("queued", "running"), None),
    "passed": (("completed",), True),
    "failed": (("completed",), False),
    "infrastructure_failed": (("infrastructure_failed",), None),
}


class SubmissionBundlePreparationReader:
    """Read-only; the caller supplies authority and the response transaction."""

    def __init__(self, session: AsyncSession, *, runs: SelectedPreSubmitRunReadPort) -> None:
        """Read selected PRE runs through the CHECKERS port."""
        self._session, self._runs = session, runs

    async def _project(self, views: tuple[SelectedPreSubmitRunView, ...]):
        """Project each run's intake outcome and storage progress with one custody query.

        Returns the run view, its execution facts and the summary fields; the
        caller adds its role-specific fields.
        """
        custody = {}
        if views:
            rows = (await self._session.execute(select(
                SubmissionBundleDurableIntent.selected_pre_submit_run_id, ArtifactPutAttempt.status,
                SubmissionBundleAdmission.id, SubmissionBundleAdmission.status,
                SubmissionBundleAdmission.consumed_by_submission_id,
            ).join(
                ArtifactPutAttempt, ArtifactPutAttempt.id == SubmissionBundleDurableIntent.put_attempt_id,
            ).outerjoin(
                SubmissionBundleAdmission,
                SubmissionBundleAdmission.durable_intent_id == SubmissionBundleDurableIntent.id,
            ).where(
                SubmissionBundleDurableIntent.selected_pre_submit_run_id.in_([str(view.run_id) for view in views]),
            ))).all()
            custody = {UUID(str(row[0])): row[1:] for row in rows}
        projected = []
        for view in views:
            terminal = view.terminal
            execution = terminal.execution if terminal is not None else None
            stored = custody.get(view.run_id)
            if view.status in {"queued", "running"}:
                outcome, state = "pending", "checking"
            elif view.status == "infrastructure_failed":
                outcome, state = "infrastructure_failed", "infrastructure_failed"
            elif execution is None:
                raise ValueError("completed preparation has no execution facts")
            elif not execution.eligible:
                outcome, state = "failed", "checks_failed"
            else:
                outcome = "passed"
                state = _ADMISSION_STATE[stored[2]] if stored is not None and stored[2] is not None else "storing"
            projected.append((view, execution, {
                "preparation_id": view.run_id, "task_id": view.task_id, "assignment_id": view.assignment_id,
                "outcome": outcome, "state": state,
                "storage_status": SubmissionBundlePreparationStatus(stored[0]) if stored is not None else None,
                "infrastructure_failure_code": terminal.infrastructure_failure_code if terminal is not None else None,
                "archive_sha256": view.archive_sha256, "archive_byte_count": view.archive_byte_count,
                "finding_counts": (
                    PreparationFindingCounts(**pre_submission_finding_counts(execution))
                    if execution is not None else None
                ),
                "admission_id": stored[1] if stored is not None and stored[2] == "ready" else None,
                "submission_id": stored[3] if stored is not None else None,
                "created_at": view.queued_at, "completed_at": view.completed_at,
            }))
        return projected

    async def read(self, *, actor_profile_id, task_id, preparation_id, limit, before):
        """Project own preparations with intake storage progress and findings, newest first."""
        views, more = await self._runs.read_contributor_runs(
            actor_profile_id=actor_profile_id, task_id=task_id, run_id=preparation_id,
            limit=limit, before=before,
        )
        return tuple(
            SubmissionBundlePreparationDetail(
                **fields, findings=public_pre_submission_results(execution) if execution is not None else [],
            )
            for _view, execution, fields in await self._project(views)
        ), more

    async def read_project(self, *, project_id: UUID, outcome: PreparationOutcome | None, limit, before):
        """Project every contributor's preparations in one project, newest first, without findings."""
        statuses, eligible = _OUTCOME_FILTER[outcome] if outcome is not None else (None, None)
        views, more = await self._runs.read_project_runs(
            project_id=project_id, statuses=statuses, eligible=eligible, limit=limit, before=before,
        )
        return tuple(
            ProjectSubmissionBundlePreparation(**fields, actor_profile_id=view.actor_profile_id)
            for view, _execution, fields in await self._project(views)
        ), more
