"""TASK-owned fixed history projections over retained immutable submissions."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api.submission_history import (
    SubmissionFindingCounts, SubmissionFindingCountsPort, SubmissionHistoryTarget,
    SubmissionOperationAssociationUnavailable, SubmissionOperationOutcome,
)
from app.modules.tasks.submission_dispatch import evaluation_request_event
from app.modules.tasks.models import EvidenceItem, Submission, SubmissionDispatch, WorkstreamTask
from app.modules.tasks.api.submission_history import ContributorSubmissionHistory, ManagementSubmissionHistory


class SubmissionHistoryRepository:
    """Read only exact owner columns; caller owns authorization and transaction."""

    def __init__(self, session: AsyncSession, *, finding_counts: SubmissionFindingCountsPort):
        self._session = session
        self._finding_counts = finding_counts

    def _targets(self, *, project_id, contributor_id):
        statement = select(
            WorkstreamTask.project_id, Submission.task_id,
            Submission.id.label("submission_id"), Submission.contributor_id,
        ).join(WorkstreamTask, WorkstreamTask.id == Submission.task_id)
        if project_id is not None:
            statement = statement.where(WorkstreamTask.project_id == str(project_id))
        if contributor_id is not None:
            statement = statement.where(Submission.contributor_id == str(contributor_id))
        return statement

    @staticmethod
    def _target(row):
        return None if row is None else SubmissionHistoryTarget(**{
            key: UUID(str(value)) for key, value in row.items()
        })

    async def resolve_submission(self, submission_id, *, project_id, contributor_id):
        result = await self._session.execute(self._targets(
            project_id=project_id, contributor_id=contributor_id,
        ).where(Submission.id == str(submission_id)))
        return self._target(result.mappings().one_or_none())

    async def resolve_task_history(self, task_id, *, project_id, contributor_id):
        # A Submitter grant never reveals a task with only somebody else's history.
        result = await self._session.execute(self._targets(
            project_id=project_id, contributor_id=contributor_id,
        ).where(Submission.task_id == str(task_id)).order_by(Submission.version, Submission.id).limit(1))
        target = self._target(result.mappings().one_or_none())
        return target

    async def lock_history_task(self, target):
        result = await self._session.scalar(select(WorkstreamTask.id).where(
            WorkstreamTask.id == str(target.task_id),
            WorkstreamTask.project_id == str(target.project_id),
        ).with_for_update())
        return result is not None

    async def read(self, target, *, manager: bool, submission_id=None, limit=25, after=None):
        schema = ManagementSubmissionHistory if manager else ContributorSubmissionHistory
        computed = {"evidence_items", "status", "finding_counts"}
        fields = [name for name in schema.model_fields if name not in computed]
        statement = select(
            *(getattr(Submission, name) for name in fields),
            Submission.attempt_status.label("status"),
        ).where(
            Submission.task_id == str(target.task_id),
        )
        if not manager:
            statement = statement.where(Submission.contributor_id == str(target.contributor_id))
        if submission_id is not None:
            statement = statement.where(Submission.id == str(submission_id))
        if after is not None:
            statement = statement.where(tuple_(Submission.version, Submission.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(statement.order_by(Submission.version, Submission.id).limit(limit + 1))).mappings().all()
        page = rows[:limit]
        ids = tuple(UUID(str(row["id"])) for row in page)
        evidence: dict[str, list[dict]] = {}
        if ids:
            for item in (await self._session.execute(select(
                EvidenceItem.submission_id, EvidenceItem.id, EvidenceItem.type,
                EvidenceItem.label, EvidenceItem.size_bytes,
            ).where(EvidenceItem.submission_id.in_([str(item) for item in ids])).order_by(
                EvidenceItem.submission_id, EvidenceItem.id,
            ))).mappings():
                values = dict(item)
                evidence.setdefault(str(values.pop("submission_id")), []).append(values)
        counts = await self._finding_counts.read_finding_counts(ids, manager=manager)
        values = [
            schema(
                **row, evidence_items=evidence.get(str(row["id"]), []),
                finding_counts=SubmissionFindingCounts(**dict(zip(
                    ("blocking", "warning", "coverage_incomplete"), counts[UUID(str(row["id"]))],
                ))),
            )
            for row in page
        ]
        return values, len(rows) > limit


    async def read_operation_outcome(
        self, *, project_id: UUID, task_id: UUID, assignment_id: UUID,
        contributor_id: UUID, submission_id: UUID, admission_id: UUID,
    ) -> SubmissionOperationOutcome:
        """Prove exact accepted association; never substitute a newer attempt."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise SubmissionOperationAssociationUnavailable("submission_operation_association_unavailable")
        row = (await self._session.execute(select(
            Submission.id, Submission.version, Submission.attempt_status,
            SubmissionDispatch,
        ).join(SubmissionDispatch, SubmissionDispatch.submission_id == Submission.id).join(
            WorkstreamTask, WorkstreamTask.id == Submission.task_id,
        ).where(
            Submission.id == str(submission_id),
            Submission.task_id == str(task_id),
            Submission.task_assignment_id == str(assignment_id),
            Submission.contributor_id == str(contributor_id),
            WorkstreamTask.project_id == str(project_id),
            SubmissionDispatch.project_id == str(project_id),
            SubmissionDispatch.task_id == str(task_id),
            SubmissionDispatch.assignment_id == str(assignment_id),
            SubmissionDispatch.contributor_id == str(contributor_id),
            SubmissionDispatch.admission_id == str(admission_id),
            SubmissionDispatch.submission_version == Submission.version,
        ))).one_or_none()
        if row is None:
            raise SubmissionOperationAssociationUnavailable("submission_operation_association_unavailable")
        return SubmissionOperationOutcome(
            submission_id=UUID(row.id), submission_version=row.version,
            status=row.attempt_status, evaluation_request_id=UUID(row.SubmissionDispatch.evaluation_request_id),
            evaluation_event_id=UUID(str(row.SubmissionDispatch.evaluation_event_id)),
            evaluation_event=evaluation_request_event(row.SubmissionDispatch),
        )
