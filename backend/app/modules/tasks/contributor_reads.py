"""TASK-owned projections of claims and attempts, shared by the own-work and project-wide reads.

The row builders below take the caller's scope as SQL predicates; the
contributor and Project Manager readers differ only in that WHERE clause.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contributions.api import LockedCompensationTermsPort
from app.modules.tasks.api.contributor_reads import (
    AssignmentState, ContributorAssignment, ContributorAssignmentCounts, ContributorAssignmentQuery,
    ContributorLatestSubmission, ContributorSubmission,
    ContributorSubmissionCounts, ContributorSubmissionQuery, ContributorWorkCounts, NextAction,
    RevisionDisposition,
)
from app.modules.tasks.api.submission_history import (
    SubmissionAttemptStatus, SubmissionFindingCounts, SubmissionFindingCountsPort,
)
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.revision.service import RevisionSource, read_task_revisions

_AWAITING = frozenset({"submitted", "evaluation_pending", "review_pending"})


def next_action(
    state: AssignmentState, task_status: str | None,
    latest_status: SubmissionAttemptStatus | None, revision: RevisionDisposition | None,
) -> NextAction:
    """The one contributor action this claim currently allows, or ``none``."""
    if state != "active":
        return "none"
    if task_status == "claimed":
        return "start"
    if task_status == "in_progress":
        return "prepare_submission"
    if task_status in _AWAITING:
        return "awaiting_evaluation"
    if task_status == "needs_revision" and latest_status == "needs_revision" and revision == "ready":
        return "revise"
    return "none"


def _locked_terms(compensation, version_id):
    """A claim without its locked terms is an integrity failure, reported as unavailable."""
    if version_id not in compensation:
        raise ValueError("assignment locked compensation terms are missing")
    return compensation[version_id]


def _keyset(statement, page, *, updated_since, after, limit):
    """Inclusive ``updated_since`` and the strict ``(activity_at, id)`` boundary, one row past the page."""
    if updated_since is not None:
        statement = statement.where(page.c.activity_at >= updated_since)
    if after is not None:
        statement = statement.where(tuple_(page.c.activity_at, page.c.id) > (after[0], str(after[1])))
    return statement.order_by(page.c.activity_at, page.c.id).limit(limit + 1)


async def read_assignment_page(
    session: AsyncSession, tasks: TaskRepository, scope, *,
    state: AssignmentState | None, updated_since, after, limit: int,
):
    """One activity-ordered page of claims selected by ``scope`` predicates on ``TaskAssignment``.

    Returns ``((contributor_id, assignment), ...)`` and whether another page exists.
    A closed claim projects only its contributor's own facts: no current task
    status or task stamp, and the guide version of its own latest attempt.
    This is the single place that rule is applied for every reader.
    """
    assignment, task = TaskAssignment, WorkstreamTask
    scoped = select(assignment.id).where(*scope).correlate(None)
    submitted = select(
        Submission.task_assignment_id.label("assignment_id"), func.max(Submission.updated_at).label("stamp"),
    ).where(Submission.task_assignment_id.in_(scoped)).group_by(Submission.task_assignment_id).subquery()
    revised = select(
        TaskRevisionPreparation.assignment_id, func.max(TaskRevisionPreparation.created_at).label("stamp"),
    ).where(TaskRevisionPreparation.assignment_id.in_(scoped)).group_by(
        TaskRevisionPreparation.assignment_id,
    ).subquery()
    active = assignment.status == "active"
    # The task stamp describes this contributor's work only while the claim is active.
    rows = select(
        assignment.id, assignment.project_id, assignment.task_id, assignment.contributor_id, assignment.status,
        assignment.assigned_at, assignment.started_at, assignment.released_at,
        assignment.submitter_contribution_policy_version_id, task.title,
        task.status.label("task_status"), task.locked_guide_version,
        func.greatest(
            assignment.updated_at, case((active, task.updated_at)), submitted.c.stamp, revised.c.stamp,
        ).label("activity_at"),
    ).join(task, task.id == assignment.task_id).outerjoin(
        submitted, submitted.c.assignment_id == assignment.id,
    ).outerjoin(revised, revised.c.assignment_id == assignment.id).where(*scope)
    if state is not None:
        rows = rows.where(active if state == "active" else ~active)
    page = rows.subquery()
    result = (await session.execute(_keyset(
        select(page), page, updated_since=updated_since, after=after, limit=limit,
    ))).mappings().all()
    selected = result[:limit]
    latest = await _latest_submissions(session, tuple(row["id"] for row in selected))
    revisions = await read_task_revisions(session, tuple(
        RevisionSource(str(row["task_id"]), str(row["id"]))
        for row in selected if row["status"] == "active" and row["task_status"] == "needs_revision"
    ))
    compensation = {}
    for project_id in {row["project_id"] for row in selected}:
        compensation.update(await tasks.locked_compensation(UUID(str(project_id)), tuple(
            row["submitter_contribution_policy_version_id"] for row in selected
            if row["project_id"] == project_id
        )))
    items = []
    for row in selected:
        row_state: AssignmentState = "active" if row["status"] == "active" else "closed"
        submission = latest.get(str(row["id"]))
        revision = revisions.get(str(row["id"]))
        items.append((UUID(str(row["contributor_id"])), ContributorAssignment(
            assignment_id=row["id"], project_id=row["project_id"], task_id=row["task_id"],
            title=row["title"], state=row_state, assignment_status=row["status"],
            task_status=row["task_status"] if row_state == "active" else None,
            claimed_at=row["assigned_at"], started_at=row["started_at"], released_at=row["released_at"],
            locked_guide_version=(
                row["locked_guide_version"] if row_state == "active"
                else submission[1] if submission is not None else None
            ),
            compensation=_locked_terms(compensation, row["submitter_contribution_policy_version_id"]),
            latest_submission=submission[0] if submission is not None else None,
            revision=revision,
            next_action=next_action(
                row_state, row["task_status"], submission[0].status if submission is not None else None,
                revision.disposition if revision is not None else None,
            ),
            updated_at=row["activity_at"],
        )))
    return tuple(items), len(result) > limit


async def _latest_submissions(session: AsyncSession, assignment_ids):
    """Newest attempt per assignment, with its locked guide version."""
    if not assignment_ids:
        return {}
    rows = (await session.execute(select(
        Submission.task_assignment_id, Submission.id, Submission.version, Submission.attempt_status,
        Submission.status_reason, Submission.submitted_at, Submission.decided_at,
        Submission.locked_guide_version,
    ).distinct(Submission.task_assignment_id).where(
        Submission.task_assignment_id.in_([str(item) for item in assignment_ids]),
    ).order_by(Submission.task_assignment_id, Submission.version.desc()))).all()
    return {
        str(row.task_assignment_id): (ContributorLatestSubmission(
            submission_id=row.id, version=row.version, status=row.attempt_status,
            status_reason=row.status_reason, submitted_at=row.submitted_at, decided_at=row.decided_at,
        ), row.locked_guide_version)
        for row in rows
    }


async def read_submission_page(
    session: AsyncSession, finding_counts: SubmissionFindingCountsPort, scope, *,
    task_id: UUID | None, status: SubmissionAttemptStatus | None, updated_since, after, limit: int,
    manager: bool,
):
    """One activity-ordered page of attempts selected by ``scope`` on ``Submission``/``WorkstreamTask``.

    Returns ``((submitter_id, attempt), ...)`` and whether another page exists.
    ``manager`` selects which findings the counts include, as the history reads do.
    """
    # Findings commit with their checker run, before TASK routing restamps the
    # submission, so a row changes at the later of the two stamps.
    evidence = finding_counts.evidence_stamps()
    activity_at = func.greatest(Submission.updated_at, evidence.c.evidence_at).label("activity_at")
    statement = select(
        Submission.id, WorkstreamTask.project_id, Submission.task_id, Submission.contributor_id,
        WorkstreamTask.title, Submission.version, Submission.attempt_status, Submission.status_reason,
        Submission.submitted_at, Submission.decided_at, activity_at,
    ).join(WorkstreamTask, WorkstreamTask.id == Submission.task_id).outerjoin(
        evidence, evidence.c.submission_id == Submission.id,
    ).where(*scope)
    if task_id is not None:
        statement = statement.where(Submission.task_id == str(task_id))
    if status is not None:
        statement = statement.where(Submission.attempt_status == status)
    page = statement.subquery()
    rows = (await session.execute(_keyset(
        select(page), page, updated_since=updated_since, after=after, limit=limit,
    ))).all()
    selected = rows[:limit]
    counts = await finding_counts.read_finding_counts(
        tuple(UUID(str(row.id)) for row in selected), manager=manager,
    )
    return tuple(
        (UUID(str(row.contributor_id)), ContributorSubmission(
            submission_id=row.id, project_id=row.project_id, task_id=row.task_id, title=row.title,
            version=row.version, status=row.attempt_status, status_reason=row.status_reason,
            submitted_at=row.submitted_at, decided_at=row.decided_at,
            finding_counts=SubmissionFindingCounts(**dict(zip(
                ("blocking", "warning", "coverage_incomplete"), counts[UUID(str(row.id))],
            ))),
            updated_at=row.activity_at,
        ))
        for row in selected
    ), len(rows) > limit


async def count_work(session: AsyncSession, *, assignment_scope, submission_scope) -> ContributorWorkCounts:
    """Claims by state and attempts by stored outcome, each selected by its scope predicates."""
    assignments: dict[bool, int] = {}
    for status, count in (await session.execute(select(
        TaskAssignment.status, func.count(),
    ).where(*assignment_scope).group_by(TaskAssignment.status))).all():
        assignments[status == "active"] = assignments.get(status == "active", 0) + count
    submissions = dict((await session.execute(select(
        Submission.attempt_status, func.count(),
    ).join(WorkstreamTask, WorkstreamTask.id == Submission.task_id).where(
        *submission_scope,
    ).group_by(Submission.attempt_status))).all())
    return ContributorWorkCounts(
        assignments=ContributorAssignmentCounts(
            active=assignments.get(True, 0), closed=assignments.get(False, 0),
        ),
        submissions=ContributorSubmissionCounts(**{
            name: submissions.get(name, 0) for name in ContributorSubmissionCounts.model_fields
        }),
    )


class ContributorWorkReader:
    """Fixed owner columns only; the caller supplies authority, scope and the transaction."""

    def __init__(
        self, session: AsyncSession, *, compensation_terms: LockedCompensationTermsPort,
        finding_counts: SubmissionFindingCountsPort,
    ) -> None:
        self._session = session
        self._tasks = TaskRepository(session, compensation_terms=compensation_terms)
        self._finding_counts = finding_counts

    async def read_assignments(self, query: ContributorAssignmentQuery):
        if not query.project_ids:
            return (), False
        items, more = await read_assignment_page(self._session, self._tasks, (
            TaskAssignment.contributor_id == str(query.contributor_id),
            TaskAssignment.project_id.in_([str(item) for item in query.project_ids]),
        ), state=query.state, updated_since=query.updated_since, after=query.after, limit=query.limit)
        return tuple(item for _, item in items), more

    async def read_submissions(self, query: ContributorSubmissionQuery):
        if not query.project_ids:
            return (), False
        items, more = await read_submission_page(self._session, self._finding_counts, (
            Submission.contributor_id == str(query.contributor_id),
            WorkstreamTask.project_id.in_([str(item) for item in query.project_ids]),
        ), task_id=query.task_id, status=query.status, updated_since=query.updated_since,
            after=query.after, limit=query.limit, manager=False)
        return tuple(item for _, item in items), more

    async def count_work(self, contributor_id: UUID, project_ids: frozenset[UUID]) -> ContributorWorkCounts:
        if not project_ids:
            return ContributorWorkCounts(
                assignments=ContributorAssignmentCounts(active=0, closed=0),
                submissions=ContributorSubmissionCounts(**dict.fromkeys(ContributorSubmissionCounts.model_fields, 0)),
            )
        projects = [str(item) for item in project_ids]
        return await count_work(self._session, assignment_scope=(
            TaskAssignment.contributor_id == str(contributor_id), TaskAssignment.project_id.in_(projects),
        ), submission_scope=(
            Submission.contributor_id == str(contributor_id), WorkstreamTask.project_id.in_(projects),
        ))

    async def resolve_contributor_task(self, task_id: UUID, contributor_id: UUID) -> UUID | None:
        project_id = await self._session.scalar(select(TaskAssignment.project_id).where(
            TaskAssignment.task_id == str(task_id), TaskAssignment.contributor_id == str(contributor_id),
        ).limit(1))
        return None if project_id is None else UUID(str(project_id))
