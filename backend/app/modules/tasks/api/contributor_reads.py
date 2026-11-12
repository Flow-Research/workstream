"""The caller's own assignments and attempts across projects; TASK projects, AUTH decides."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.tasks.api.management_queue import TaskStatus
from app.modules.tasks.api.ready_queue import TaskCompensationTerms
from app.modules.tasks.api.revision import ContributorRevisionContext
from app.modules.tasks.api.submission_history import (
    SubmissionAttemptStatus, SubmissionFindingCounts, SubmissionFindingCountsPort, SubmissionStatusReason,
)

AssignmentStatus = Literal["active", "completed", "revision_expired", "revision_exhausted", "authority_revoked"]
AssignmentState = Literal["active", "closed"]
NextAction = Literal["prepare_submission", "awaiting_evaluation", "revise", "none"]
RevisionDisposition = Literal[
    "ready", "context_blocked", "revision_deadline_expired",
]

_FROZEN = ConfigDict(extra="forbid", frozen=True)


class ContributorLatestSubmission(BaseModel):
    """The newest own attempt on this assignment."""

    model_config = _FROZEN
    submission_id: UUID
    version: int = Field(gt=0)
    status: SubmissionAttemptStatus
    status_reason: SubmissionStatusReason | None
    submitted_at: AwareDatetime
    decided_at: AwareDatetime | None


class ContributorAssignment(BaseModel):
    """One own claim. A closed one projects only the contributor's own facts."""

    model_config = _FROZEN
    assignment_id: UUID
    project_id: UUID
    task_id: UUID
    title: str
    state: AssignmentState
    assignment_status: AssignmentStatus
    task_status: TaskStatus | None
    claimed_at: AwareDatetime
    started_at: AwareDatetime | None
    released_at: AwareDatetime | None
    locked_guide_version: str | None
    compensation: TaskCompensationTerms
    latest_submission: ContributorLatestSubmission | None
    revision: ContributorRevisionContext | None
    next_action: NextAction
    updated_at: AwareDatetime = Field(description=(
        "Activity time: the latest own assignment, submission or revision stamp, "
        "plus the task stamp while active. Orders the list and drives updated_since."
    ))


class ContributorAssignmentPage(BaseModel):
    model_config = _FROZEN
    items: tuple[ContributorAssignment, ...]
    next_cursor: str | None


class ContributorSubmission(BaseModel):
    """One own immutable attempt and its stored outcome."""

    model_config = _FROZEN
    submission_id: UUID
    project_id: UUID
    task_id: UUID
    title: str
    version: int = Field(gt=0)
    status: SubmissionAttemptStatus
    status_reason: SubmissionStatusReason | None
    submitted_at: AwareDatetime
    decided_at: AwareDatetime | None
    finding_counts: SubmissionFindingCounts
    updated_at: AwareDatetime = Field(description=(
        "Activity time: the later of the submission stamp and when its current checker "
        "run's findings changed. Orders the list and drives updated_since."
    ))


class ContributorSubmissionPage(BaseModel):
    model_config = _FROZEN
    items: tuple[ContributorSubmission, ...]
    next_cursor: str | None


class ContributorAssignmentCounts(BaseModel):
    model_config = _FROZEN
    active: int = Field(ge=0)
    closed: int = Field(ge=0)


class ContributorSubmissionCounts(BaseModel):
    model_config = _FROZEN
    evaluation_pending: int = Field(ge=0)
    review_pending: int = Field(ge=0)
    accepted: int = Field(ge=0)
    needs_revision: int = Field(ge=0)
    rejected: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class ContributorWorkCounts:
    assignments: ContributorAssignmentCounts
    submissions: ContributorSubmissionCounts


@dataclass(frozen=True, slots=True)
class ContributorAssignmentQuery:
    """Own rows in already authorized projects, after an optional keyset boundary."""

    contributor_id: UUID
    project_ids: frozenset[UUID]
    state: AssignmentState | None
    updated_since: datetime | None
    limit: int
    after: tuple[datetime, UUID] | None


@dataclass(frozen=True, slots=True)
class ContributorSubmissionQuery:
    contributor_id: UUID
    project_ids: frozenset[UUID]
    task_id: UUID | None
    status: SubmissionAttemptStatus | None
    updated_since: datetime | None
    limit: int
    after: tuple[datetime, UUID] | None


class ContributorWorkReadPort(Protocol):
    """Read-only TASK projections; the caller owns authority and the transaction."""

    async def read_assignments(
        self, query: ContributorAssignmentQuery,
    ) -> tuple[tuple[ContributorAssignment, ...], bool]: ...

    async def read_submissions(
        self, query: ContributorSubmissionQuery,
    ) -> tuple[tuple[ContributorSubmission, ...], bool]: ...

    async def count_work(
        self, contributor_id: UUID, project_ids: frozenset[UUID],
    ) -> ContributorWorkCounts: ...

    async def resolve_contributor_task(self, task_id: UUID, contributor_id: UUID) -> UUID | None:
        """Return the task's project only when this contributor ever held it."""
        ...


__all__ = (
    "AssignmentState", "AssignmentStatus", "ContributorAssignment", "ContributorAssignmentCounts",
    "ContributorAssignmentPage", "ContributorAssignmentQuery", "ContributorLatestSubmission",
    "ContributorSubmission", "ContributorSubmissionCounts",
    "ContributorSubmissionPage", "ContributorSubmissionQuery", "ContributorWorkCounts",
    "ContributorWorkReadPort", "NextAction", "RevisionDisposition",
    "SubmissionFindingCountsPort", "TaskStatus",
)
