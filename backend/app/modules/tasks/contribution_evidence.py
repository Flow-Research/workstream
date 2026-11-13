"""TASK-owned exact selected source metadata for contribution evidence."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api.contribution_evidence import ContributionTaskEvidence
from app.modules.tasks.models import Submission, WorkstreamTask


class ContributionTaskEvidenceRepository:
    """Read task metadata without lifecycle changes or an independent disclosure grant."""

    def __init__(self, session: AsyncSession) -> None:
        """Share the caller's export snapshot and commit ownership."""
        self._session = session

    async def read_contribution_tasks(
        self, selectors: tuple[tuple[UUID, UUID, UUID], ...]
    ) -> tuple[ContributionTaskEvidence, ...]:
        """Pre-filter by both project and task before returning any source text."""
        if len(selectors) > 1_000 or len(set(selectors)) != len(selectors):
            raise ValueError("invalid contribution task selection")
        if not selectors:
            return ()
        rows = (await self._session.execute(select(WorkstreamTask, Submission).join(
            Submission, Submission.task_id == WorkstreamTask.id,
        ).where(tuple_(WorkstreamTask.project_id,WorkstreamTask.id,Submission.id).in_(
            [(str(project), str(task), str(submission)) for project, task, submission in selectors]
        )))).all()
        return tuple(ContributionTaskEvidence(
            project_id=UUID(task.project_id), task_id=UUID(task.id), submission_id=UUID(submission.id),
            task_size=submission.task_size, contribution_policy_version_id=submission.contribution_policy_version_id,
            contribution_award_definition_id=submission.contribution_award_definition_id,
            title=task.title, source_type=task.source_type, source_ref=task.source_ref,
            external_task_id=task.external_task_id,
        ) for task, submission in rows)
