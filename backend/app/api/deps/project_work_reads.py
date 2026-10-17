"""Compose a project's work reads through the shared project management read runner."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.contributor_reads import AwardTotal
from app.api.deps.project_management_reads import ProjectManagementReadRunner, ProjectManagementReads
from app.db.session import get_db_session
from app.modules.checkers.api.history import CheckerHistoryReadPort
from app.modules.compensation.api.award_reads import ProjectAwardTotalsPort
from app.modules.tasks.api.contributor_reads import (
    AssignmentState, ContributorAssignmentCounts, ContributorSubmissionCounts,
)
from app.modules.tasks.api.project_reads import (
    ProjectAssignmentPage, ProjectAssignmentQuery, ProjectSubmissionPage, ProjectSubmissionQuery,
    ProjectTaskImportBatchPage, ProjectWorkCounts, ProjectWorkReadPort, TaskStatusCounts,
)
from app.modules.tasks.api.submission_history import SubmissionAttemptStatus

_FROZEN = ConfigDict(extra="forbid", frozen=True)


class ProjectWorkSummary(BaseModel):
    """One project's work counts, acceptance rate, checker infrastructure failures and award totals.

    ``acceptance_rate`` is accepted over decided attempts (accepted,
    needs_revision, rejected) and null before any attempt is decided.
    ``award_totals`` is null unless the caller also holds a current
    exact-project Finance Authority grant; then it lists every instrument and
    unit total, empty when no award exists.
    """

    model_config = _FROZEN
    project_id: UUID
    tasks: TaskStatusCounts
    assignments: ContributorAssignmentCounts
    submissions: ContributorSubmissionCounts
    acceptance_rate: float | None = Field(ge=0, le=1)
    checker_infrastructure_failures: int = Field(ge=0)
    award_totals: tuple[AwardTotal, ...] | None

    @classmethod
    def from_facts(cls, project_id: UUID, counts: ProjectWorkCounts, failures: int, totals) -> "ProjectWorkSummary":
        """Build the summary from TASK counts, the CHECKERS count and optional compensation totals."""
        attempts = counts.submissions
        decided = attempts.accepted + attempts.needs_revision + attempts.rejected
        return cls(
            project_id=project_id, tasks=counts.tasks, assignments=counts.assignments, submissions=attempts,
            acceptance_rate=attempts.accepted / decided if decided else None,
            checker_infrastructure_failures=failures,
            award_totals=None if totals is None else tuple(
                AwardTotal(instrument=total.instrument_type, unit=total.unit_code, quantity=format(total.quantity, "f"))
                for total in totals
            ),
        )


def _instant(value: datetime | None) -> str | None:
    """Canonical cursor-bound text for an optional instant."""
    return None if value is None else value.astimezone(UTC).isoformat(timespec="microseconds")


def _id(value: UUID | None) -> str | None:
    """Canonical cursor-bound text for an optional identifier."""
    return None if value is None else str(value)


class ProjectWorkReadOperation:
    """C4–C7 over the shared project management read runner."""

    def __init__(
        self, runner: ProjectManagementReadRunner, *,
        work: ProjectWorkReadPort, checkers: CheckerHistoryReadPort, awards: ProjectAwardTotalsPort,
    ) -> None:
        """Compose the read runner and the owner read ports for one request."""
        self._runner = runner
        self._work, self._checkers, self._awards = work, checkers, awards

    async def submissions(
        self, project_id: UUID, *, status: SubmissionAttemptStatus | None, task_id: UUID | None,
        submitter_actor_id: UUID | None, updated_since: datetime | None, limit: int, cursor: str | None,
    ) -> ProjectSubmissionPage:
        """C4: the project's attempts by activity time."""
        request = self._runner.request("project.submission.list", project_id, {
            "limit": limit, "order": "activity_at_id_asc", "status": status, "task_id": _id(task_id),
            "submitter_actor_id": _id(submitter_actor_id), "updated_since": _instant(updated_since),
        }, cursor=cursor)

        async def read(grant):
            items, more = await self._work.read_submissions(ProjectSubmissionQuery(
                project_id=grant.project_id, task_id=task_id, submitter_id=submitter_actor_id, status=status,
                updated_since=updated_since, limit=limit, after=self._runner.position(grant),
            ))
            last = items[-1] if items else None
            return ProjectSubmissionPage(items=items, next_cursor=self._runner.next_cursor(
                request, more, last and last.updated_at, last and last.submission_id,
            ))

        return await self._runner.run(request, read)

    async def assignments(
        self, project_id: UUID, *, state: AssignmentState | None, limit: int, cursor: str | None,
    ) -> ProjectAssignmentPage:
        """C5: the project's claims by activity time."""
        request = self._runner.request("project.assignment.list", project_id, {
            "limit": limit, "order": "activity_at_id_asc", "state": state,
        }, cursor=cursor)

        async def read(grant):
            items, more = await self._work.read_assignments(ProjectAssignmentQuery(
                project_id=grant.project_id, state=state, limit=limit, after=self._runner.position(grant),
            ))
            last = items[-1] if items else None
            return ProjectAssignmentPage(items=items, next_cursor=self._runner.next_cursor(
                request, more, last and last.updated_at, last and last.assignment_id,
            ))

        return await self._runner.run(request, read)

    async def summary(self, project_id: UUID) -> ProjectWorkSummary:
        """C6: counts, acceptance rate, infrastructure failures, and award totals only under Finance."""
        request = self._runner.request("project.summary.read", project_id, {})

        async def read(grant):
            counts = await self._work.count_work(grant.project_id)
            failures = await self._checkers.count_infrastructure_failures(grant.project_id)
            totals = (await self._awards.read_project_award_totals(grant.project_id)
                      if grant.award_totals_visible else None)
            return ProjectWorkSummary.from_facts(grant.project_id, counts, failures, totals)

        return await self._runner.run(request, read)

    async def import_batches(self, project_id: UUID, *, limit: int, cursor: str | None) -> ProjectTaskImportBatchPage:
        """C7: the project's import batches by creation time, with member counts."""
        request = self._runner.request("project.task.import_batch.list", project_id, {
            "limit": limit, "order": "created_at_id_asc",
        }, cursor=cursor)

        async def read(grant):
            items, more = await self._work.read_import_batches(
                grant.project_id, limit=limit, after=self._runner.position(grant),
            )
            last = items[-1] if items else None
            return ProjectTaskImportBatchPage(items=items, next_cursor=self._runner.next_cursor(
                request, more, last and last.created_at, last and last.batch_id,
            ))

        return await self._runner.run(request, read)


async def get_project_work_reads(
    runner: ProjectManagementReads, session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectWorkReadOperation:
    """Build the project work read operation from request-scoped owner adapters."""
    from app.adapters.checkers import checker_history_repository
    from app.adapters.compensation import project_award_totals_port
    from app.adapters.tasks import project_work_reader

    return ProjectWorkReadOperation(
        runner, work=project_work_reader(session), checkers=checker_history_repository(session),
        awards=project_award_totals_port(session),
    )
