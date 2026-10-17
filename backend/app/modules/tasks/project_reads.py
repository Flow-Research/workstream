"""TASK-owned projections of one project's claims, attempts, counts and import batches.

Claims and attempts reuse the own-work row builders; only the scope differs.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contributions.api import LockedCompensationTermsPort
from app.modules.tasks.api.management_queue import TASK_STATUSES
from app.modules.tasks.api.project_reads import (
    ProjectAssignment, ProjectAssignmentQuery, ProjectSubmission, ProjectSubmissionQuery, ProjectTaskImportBatch,
    ProjectWorkCounts, TaskStatusCounts,
)
from app.modules.tasks.api.submission_history import SubmissionFindingCountsPort
from app.modules.tasks.contributor_reads import count_work, read_assignment_page, read_submission_page
from app.modules.tasks.models import (
    Submission, TaskAssignment, TaskImportBatch, TaskImportBatchMember, WorkstreamTask,
)
from app.modules.tasks.repository import TaskRepository


def _status_counts(counts: dict[str, int]) -> TaskStatusCounts:
    """Every stored status, zero when absent; an unknown stored status is an integrity failure."""
    if not set(counts) <= TASK_STATUSES:
        raise ValueError("task status outside the closed lifecycle")
    return TaskStatusCounts(**{name: counts.get(name, 0) for name in TaskStatusCounts.model_fields})


class ProjectWorkReader:
    """Fixed owner columns of one authorized project; the caller owns the transaction."""

    def __init__(
        self, session: AsyncSession, *, compensation_terms: LockedCompensationTermsPort,
        finding_counts: SubmissionFindingCountsPort,
    ) -> None:
        """Bind the response session, CON locked terms and CHECKERS finding counts."""
        self._session = session
        self._tasks = TaskRepository(session, compensation_terms=compensation_terms)
        self._finding_counts = finding_counts

    async def read_submissions(self, query: ProjectSubmissionQuery):
        """C4: the project's attempts with management finding counts."""
        scope = [WorkstreamTask.project_id == str(query.project_id)]
        if query.submitter_id is not None:
            scope.append(Submission.contributor_id == str(query.submitter_id))
        items, more = await read_submission_page(
            self._session, self._finding_counts, scope, task_id=query.task_id, status=query.status,
            updated_since=query.updated_since, after=query.after, limit=query.limit, manager=True,
        )
        return tuple(
            ProjectSubmission(**dict(item), submitter_actor_id=submitter) for submitter, item in items
        ), more

    async def read_assignments(self, query: ProjectAssignmentQuery):
        """C5: the project's claims; a closed claim keeps the own-work projection (open decision)."""
        items, more = await read_assignment_page(
            self._session, self._tasks, (TaskAssignment.project_id == str(query.project_id),),
            state=query.state, updated_since=None, after=query.after, limit=query.limit,
        )
        return tuple(
            ProjectAssignment(**dict(item), contributor_actor_id=contributor) for contributor, item in items
        ), more

    async def count_work(self, project_id: UUID) -> ProjectWorkCounts:
        """C6: tasks by status, claims by state and attempts by stored outcome."""
        project = str(project_id)
        tasks = dict((await self._session.execute(select(
            WorkstreamTask.status, func.count(),
        ).where(WorkstreamTask.project_id == project).group_by(WorkstreamTask.status))).all())
        work = await count_work(
            self._session, assignment_scope=(TaskAssignment.project_id == project,),
            submission_scope=(WorkstreamTask.project_id == project,),
        )
        return ProjectWorkCounts(
            tasks=_status_counts(tasks), assignments=work.assignments, submissions=work.submissions,
        )

    async def read_import_batches(self, project_id: UUID, *, limit: int, after):
        """C7: one creation-ordered page of batches, then one grouped member count query."""
        batch = TaskImportBatch
        statement = select(
            batch.id, batch.source_id, batch.metadata_label, batch.sha256, batch.byte_count, batch.row_count,
            batch.status, batch.created_at, batch.committed_at,
        ).where(batch.project_id == str(project_id))
        if after is not None:
            statement = statement.where(tuple_(batch.created_at, batch.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(
            statement.order_by(batch.created_at, batch.id).limit(limit + 1),
        )).all()
        selected = rows[:limit]
        counts: dict[str, dict[str, int]] = {str(row.id): {} for row in selected}
        if counts:
            member = TaskImportBatchMember
            for batch_id, status, count in (await self._session.execute(select(
                member.batch_id, WorkstreamTask.status, func.count(),
            ).join(WorkstreamTask, (WorkstreamTask.id == member.task_id)
                   & (WorkstreamTask.project_id == member.project_id)).where(
                member.project_id == str(project_id), member.batch_id.in_(list(counts)),
            ).group_by(member.batch_id, WorkstreamTask.status))).all():
                counts[str(batch_id)][status] = count
        return tuple(
            ProjectTaskImportBatch(
                batch_id=row.id, source_id=row.source_id, label=row.metadata_label, sha256=row.sha256,
                byte_count=row.byte_count, row_count=row.row_count, state=row.status,
                created_at=row.created_at, committed_at=row.committed_at,
                task_counts=_status_counts(counts[str(row.id)]),
            )
            for row in selected
        ), len(rows) > limit
