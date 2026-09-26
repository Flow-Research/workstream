"""TASK-owned fixed history projections over retained immutable submissions."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api.submission_history import SubmissionHistoryTarget
from app.modules.tasks.models import EvidenceItem, Submission, WorkstreamTask
from app.modules.tasks.api.submission_history import ContributorSubmissionHistory, ManagementSubmissionHistory


class SubmissionHistoryRepository:
    """Read only exact owner columns; caller owns authorization and transaction."""

    def __init__(self, session: AsyncSession):
        self._session = session

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
        fields = [name for name in schema.model_fields if name != "evidence_items"]
        statement = select(*(getattr(Submission, name) for name in fields)).where(
            Submission.task_id == str(target.task_id),
        )
        if not manager:
            statement = statement.where(Submission.contributor_id == str(target.contributor_id))
        if submission_id is not None:
            statement = statement.where(Submission.id == str(submission_id))
        if after is not None:
            statement = statement.where(tuple_(Submission.version, Submission.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(statement.order_by(Submission.version, Submission.id).limit(limit + 1))).mappings().all()
        values = []
        for row in rows[:limit]:
            evidence = (await self._session.execute(select(
                EvidenceItem.id, EvidenceItem.type, EvidenceItem.label, EvidenceItem.size_bytes,
            ).where(EvidenceItem.submission_id == row["id"]).order_by(EvidenceItem.id))).mappings().all()
            values.append(schema(**row, evidence_items=[dict(item) for item in evidence]))
        return values, len(rows) > limit
