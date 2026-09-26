"""CHECKERS owns retained run projection; TASK supplies immutable ownership."""

from sqlalchemy import select, tuple_

from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.checkers.api.history import (
    ContributorCheckerHistory, ManagementCheckerHistory,
    ContributorCheckerResult, ManagementCheckerResult,
)


class CheckerHistoryRepository:
    def __init__(self, session):
        self._session = session

    async def read(self, *, submission_id, task_id, manager, run_id=None, limit=25, after=None):
        schema = ManagementCheckerHistory if manager else ContributorCheckerHistory
        result_schema = ManagementCheckerResult if manager else ContributorCheckerResult
        fields = [name for name in schema.model_fields if name != "results"]
        statement = select(*(getattr(CheckerRun, name) for name in fields)).where(
            CheckerRun.submission_id == str(submission_id),
            CheckerRun.task_id == str(task_id),
        )
        if run_id is not None:
            statement = statement.where(CheckerRun.id == str(run_id))
        if after is not None:
            statement = statement.where(tuple_(CheckerRun.created_at, CheckerRun.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(statement.order_by(CheckerRun.created_at, CheckerRun.id).limit(limit + 1))).mappings().all()
        values = []
        for row in rows[:limit]:
            result_query = select(*(getattr(CheckerResult, name) for name in result_schema.model_fields)).where(
                CheckerResult.checker_run_id == row["id"],
                CheckerResult.submission_id == str(submission_id),
                CheckerResult.task_id == str(task_id),
            )
            if not manager:
                # The private route predicate stays in SQL and never enters a DTO.
                result_query = result_query.where(
                    CheckerResult.worker_visible.is_(True),
                    select(CheckerRun.id).where(
                        CheckerRun.id == row["id"],
                        CheckerRun.routing_recommendation.not_in(("checker_retry", "task_setup_blocked")),
                    ).exists(),
                )
            results = (await self._session.execute(result_query.order_by(CheckerResult.id))).mappings().all()
            values.append(schema(**row, results=[dict(item) for item in results]))
        return values, len(rows) > limit
