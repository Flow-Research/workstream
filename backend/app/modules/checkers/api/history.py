"""Fixed retained-checker history DTOs; no execution authority."""
from datetime import datetime
from dataclasses import dataclass
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict


CheckerStatus = Literal["queued", "running", "completed", "failed"]
CheckerResultStatus = Literal["passed", "warning", "failed"]
CheckerSeverity = Literal["info", "low", "medium", "high", "critical"]
CheckerRoutingRecommendation = Literal["not_evaluated", "allow_review", "needs_revision", "checker_retry", "task_setup_blocked"]
CheckerOutcomeSource = Literal["none", "auto_checker"]

class ContributorCheckerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    checker_name: str
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


@dataclass(frozen=True, slots=True)
class CheckerHistoryReference:
    """Minimal CHECKERS-owned identity; the composition resolves TASK ownership."""

    run_id: UUID
    task_id: UUID
    submission_id: UUID
