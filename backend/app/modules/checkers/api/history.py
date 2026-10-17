"""Fixed retained-checker history DTOs; no execution authority."""
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Subquery


CheckerStatus = Literal["queued", "running", "completed", "infrastructure_failed"]
CheckerResultStatus = Literal["passed", "warning", "failed", "coverage_incomplete"]
CheckerSeverity = Literal["info", "low", "medium", "high", "critical", "error"]
CheckerRoutingRecommendation = Literal["not_evaluated", "allow_review", "needs_revision", "task_setup_blocked"]
CheckerOutcomeSource = Literal["none", "auto_checker"]

class ContributorCheckerResult(BaseModel):
    """One stored finding, or one member that reported no findings."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    checker_name: str
    check_id: str | None
    path: str | None
    line: int | None
    status: CheckerResultStatus
    severity: CheckerSeverity
    worker_message: str | None
    worker_suggested_fix: str | None


class ManagementCheckerResult(ContributorCheckerResult):
    message: str
    blocks_review: bool


class ContributorCheckerHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    task_id: UUID
    submission_id: UUID
    submission_version: int
    status: CheckerStatus
    attempt_number: int
    supersedes_checker_run_id: UUID | None
    is_current_for_submission: bool
    created_at: datetime
    completed_at: datetime | None
    results: list[ContributorCheckerResult]


class ManagementCheckerHistory(ContributorCheckerHistory):
    routing_recommendation: CheckerRoutingRecommendation
    outcome_source: CheckerOutcomeSource
    trigger_source: str
    locked_guide_version: str
    locked_post_submit_checker_policy_id: UUID
    locked_post_submit_checker_policy_version: str
    locked_post_submit_checker_policy_hash: str
    locked_review_policy_id: UUID
    locked_review_policy_generation: int
    locked_review_policy_hash: str
    locked_revision_policy_id: UUID
    locked_revision_policy_generation: int
    locked_revision_policy_hash: str
    results: list[ManagementCheckerResult]


class ContributorCheckerHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: list[ContributorCheckerHistory]
    next_cursor: str | None


class ManagementCheckerHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: list[ManagementCheckerHistory]
    next_cursor: str | None


class CheckerHistoryReadPort(Protocol):
    """CHECKERS reads only within the already authorized immutable TASK parent."""

    async def read(
        self, *, submission_id: UUID, task_id: UUID, manager: bool,
        run_id: UUID | None = None, limit: int = 25,
        after: tuple[datetime, UUID] | None = None,
    ) -> tuple[list[ContributorCheckerHistory | ManagementCheckerHistory], bool]: ...

    async def read_finding_counts(
        self, submission_ids: tuple[UUID, ...], *, manager: bool,
    ) -> dict[UUID, tuple[int, int, int]]:
        """Return (blocking, warning, coverage_incomplete) per current completed run.

        This satisfies TASK's ``SubmissionFindingCountsPort`` structurally, without
        a public dependency from CHECKERS back onto TASK.
        """
        ...

    def evidence_stamps(self) -> Subquery:
        """``(submission_id, evidence_at)``: when the current run completed, else when it was queued."""
        ...

    async def count_infrastructure_failures(self, project_id: UUID) -> int:
        """Count the project's post-submit checker runs whose status is ``infrastructure_failed``."""
        ...
