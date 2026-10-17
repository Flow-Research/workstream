"""Fixed history projection from closed results and the sole currentness fence."""

from uuid import UUID

from sqlalchemy import func, select, tuple_

from app.modules.checkers.models import (
    CheckerResult, CheckerResultFinding, CheckerRun, CheckerSubmissionFence,
)
from app.modules.checkers.api.history import (
    ContributorCheckerHistory, ManagementCheckerHistory,
    ContributorCheckerResult, ManagementCheckerResult,
)
from app.modules.checkers.execution_results import RESULT_STATUS_MESSAGES

# One closed mapping from stored finding level to the public result projection.
_FINDING_STATUS = {
    "info": ("passed", "info"),
    "warning": ("warning", "low"),
    "error": ("failed", "error"),
    "coverage_incomplete": ("coverage_incomplete", "medium"),
}


class CheckerHistoryRepository:
    def __init__(self, session):
        self._session = session

    async def read(self, *, submission_id, task_id, manager, run_id=None, limit=25, after=None):
        schema = ManagementCheckerHistory if manager else ContributorCheckerHistory
        current = select(CheckerSubmissionFence.submission_id).where(
            CheckerSubmissionFence.submission_id == CheckerRun.submission_id,
            CheckerSubmissionFence.current_run_id == CheckerRun.id,
            CheckerRun.status == "completed",
        ).correlate(CheckerRun).exists().label("is_current_for_submission")
        fields = []
        for name in schema.model_fields:
            if name == "results":
                continue
            fields.append(current if name == "is_current_for_submission" else
                          CheckerRun.evaluation_generation.label(name) if name == "attempt_number" else
                          getattr(CheckerRun, name))
        statement = select(*fields).where(CheckerRun.submission_id == str(submission_id),
                                          CheckerRun.task_id == str(task_id))
        if run_id is not None:
            statement = statement.where(CheckerRun.id == str(run_id))
        if after is not None:
            statement = statement.where(tuple_(CheckerRun.created_at, CheckerRun.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(statement.order_by(CheckerRun.created_at, CheckerRun.id).limit(limit + 1))).mappings().all()
        page = rows[:limit]
        results = await self._results(
            [row["id"] for row in page], submission_id=submission_id, task_id=task_id, manager=manager,
        )
        values = [schema(**row, results=results.get(str(row["id"]), [])) for row in page]
        return values, len(rows) > limit

    async def _results(self, run_ids, *, submission_id, task_id, manager):
        """Project every member and finding of the page's runs in one query."""
        if not run_ids:
            return {}
        result_schema = ManagementCheckerResult if manager else ContributorCheckerResult
        statement = select(
            CheckerResult.checker_run_id, CheckerResult.id.label("member_id"),
            CheckerResult.checker_name, CheckerResult.status.label("member_status"),
            CheckerResult.severity.label("member_severity"), CheckerResult.failure_category,
            CheckerResultFinding.id.label("finding_id"), CheckerResultFinding.check_id,
            CheckerResultFinding.path, CheckerResultFinding.line, CheckerResultFinding.level,
        ).join(
            CheckerRun, CheckerRun.id == CheckerResult.checker_run_id,
        ).outerjoin(
            CheckerResultFinding, CheckerResultFinding.checker_result_id == CheckerResult.id,
        ).where(
            CheckerResult.checker_run_id.in_([str(run_id) for run_id in run_ids]),
            CheckerResult.submission_id == str(submission_id), CheckerResult.task_id == str(task_id),
        )
        if not manager:
            statement = statement.where(
                CheckerResult.failure_category != "task_configuration",
                CheckerRun.routing_recommendation != "task_setup_blocked",
            )
        rows = (await self._session.execute(statement.order_by(
            CheckerResult.checker_run_id, CheckerResult.member_order,
            CheckerResultFinding.finding_order,
        ))).mappings().all()
        projected: dict[str, list] = {}
        for row in rows:
            if row["finding_id"] is None:
                status, severity = row["member_status"], row["member_severity"]
            else:
                status, severity = _FINDING_STATUS[row["level"]]
            message, fix = RESULT_STATUS_MESSAGES[status]
            visible = row["failure_category"] != "task_configuration"
            item = {
                "id": row["finding_id"] or row["member_id"],
                "checker_name": row["checker_name"], "check_id": row["check_id"],
                "path": row["path"], "line": row["line"], "status": status, "severity": severity,
                "worker_message": message if visible else None,
                "worker_suggested_fix": fix if visible else None,
            }
            if manager:
                item.update(message=message, blocks_review=status == "failed")
            projected.setdefault(str(row["checker_run_id"]), []).append(result_schema(**item))
        return projected

    def evidence_stamps(self):
        """Counts change when the current run completes or a retry moves the fence to a new run."""
        return select(
            CheckerSubmissionFence.submission_id.label("submission_id"),
            func.coalesce(CheckerRun.completed_at, CheckerRun.queued_at).label("evidence_at"),
        ).join(CheckerRun, CheckerRun.id == CheckerSubmissionFence.current_run_id).subquery()

    async def read_finding_counts(self, submission_ids, *, manager):
        """Count (blocking, warning, coverage_incomplete) findings of each current completed run.

        Contributors count only the findings their history read shows them.
        """
        counts = {UUID(str(submission_id)): (0, 0, 0) for submission_id in submission_ids}
        if not counts:
            return counts
        statement = select(
            CheckerSubmissionFence.submission_id,
            func.count().filter(CheckerResultFinding.level == "error").label("blocking"),
            func.count().filter(CheckerResultFinding.level == "warning").label("warning"),
            func.count().filter(
                CheckerResultFinding.level == "coverage_incomplete"
            ).label("coverage_incomplete"),
        ).join(
            CheckerRun, CheckerRun.id == CheckerSubmissionFence.current_run_id,
        ).join(
            CheckerResultFinding, CheckerResultFinding.checker_run_id == CheckerRun.id,
        ).join(
            CheckerResult, CheckerResult.id == CheckerResultFinding.checker_result_id,
        ).where(
            CheckerSubmissionFence.submission_id.in_([str(item) for item in counts]),
            CheckerRun.status == "completed",
        ).group_by(CheckerSubmissionFence.submission_id)
        if not manager:
            statement = statement.where(
                CheckerResult.failure_category != "task_configuration",
                CheckerRun.routing_recommendation != "task_setup_blocked",
            )
        for row in (await self._session.execute(statement)).mappings():
            counts[UUID(str(row["submission_id"]))] = (
                row["blocking"], row["warning"], row["coverage_incomplete"],
            )
        return counts

    async def count_infrastructure_failures(self, project_id) -> int:
        """Post-submit checker runs in the project that ended ``infrastructure_failed``."""
        return await self._session.scalar(select(func.count()).select_from(CheckerRun).where(
            CheckerRun.project_id == str(project_id), CheckerRun.status == "infrastructure_failed",
        ))
