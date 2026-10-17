"""A project's attempts, claims, work counts and import batches; TASK projects, AUTH decides."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.tasks.api.contributor_reads import (
    AssignmentState, ContributorAssignment, ContributorAssignmentCounts, ContributorSubmission,
    ContributorSubmissionCounts,
)
from app.modules.tasks.api.submission_history import SubmissionAttemptStatus

TaskImportBatchState = Literal["pending", "committed"]

_FROZEN = ConfigDict(extra="forbid", frozen=True)


class ProjectSubmission(ContributorSubmission):
    """One attempt in the project, in the contributor attempt shape, with its submitter."""

    submitter_actor_id: UUID


class ProjectSubmissionPage(BaseModel):
    """One activity-ordered page of the project's attempts."""

    model_config = _FROZEN
    items: tuple[ProjectSubmission, ...]
    next_cursor: str | None


class ProjectAssignment(ContributorAssignment):
    """One claim in the project, in the contributor claim shape, with its contributor.

    A closed claim projects only its contributor's own facts, exactly as the
    contributor's own read does.
    """

    contributor_actor_id: UUID


class ProjectAssignmentPage(BaseModel):
    """One activity-ordered page of the project's claims."""

    model_config = _FROZEN
    items: tuple[ProjectAssignment, ...]
    next_cursor: str | None


class TaskStatusCounts(BaseModel):
    """Tasks per stored lifecycle status; every status is present."""

    model_config = _FROZEN
    draft: int = Field(ge=0)
    screening: int = Field(ge=0)
    ready: int = Field(ge=0)
    claimed: int = Field(ge=0)
    in_progress: int = Field(ge=0)
    submitted: int = Field(ge=0)
    evaluation_pending: int = Field(ge=0)
    review_pending: int = Field(ge=0)
    needs_revision: int = Field(ge=0)
    accepted: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class ProjectWorkCounts:
    """Tasks by status, claims by state and attempts by stored outcome in one project."""

    tasks: TaskStatusCounts
    assignments: ContributorAssignmentCounts
    submissions: ContributorSubmissionCounts


class ProjectTaskImportBatch(BaseModel):
    """One native import batch, its stored state and its member tasks by current status."""

    model_config = _FROZEN
    batch_id: UUID
    source_id: UUID
    label: str | None
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1)
    row_count: int = Field(ge=1, le=500)
    state: TaskImportBatchState
    created_at: AwareDatetime
    committed_at: AwareDatetime | None
    task_counts: TaskStatusCounts


class ProjectTaskImportBatchPage(BaseModel):
    """One creation-ordered page of the project's import batches."""

    model_config = _FROZEN
    items: tuple[ProjectTaskImportBatch, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ProjectSubmissionQuery:
    """Attempts in one already authorized project, after an optional keyset boundary."""

    project_id: UUID
    task_id: UUID | None
    submitter_id: UUID | None
    status: SubmissionAttemptStatus | None
    updated_since: datetime | None
    limit: int
    after: tuple[datetime, UUID] | None


@dataclass(frozen=True, slots=True)
class ProjectAssignmentQuery:
    """Claims in one already authorized project, after an optional keyset boundary."""

    project_id: UUID
    state: AssignmentState | None
    limit: int
    after: tuple[datetime, UUID] | None


class ProjectWorkReadPort(Protocol):
    """Read-only TASK projections of one project; the caller owns authority and the transaction."""

    async def read_submissions(
        self, query: ProjectSubmissionQuery,
    ) -> tuple[tuple[ProjectSubmission, ...], bool]:
        """Return one page of attempts and whether another page exists."""
        ...

    async def read_assignments(
        self, query: ProjectAssignmentQuery,
    ) -> tuple[tuple[ProjectAssignment, ...], bool]:
        """Return one page of claims and whether another page exists."""
        ...

    async def count_work(self, project_id: UUID) -> ProjectWorkCounts:
        """Count the project's tasks, claims and attempts."""
        ...

    async def read_import_batches(
        self, project_id: UUID, *, limit: int, after: tuple[datetime, UUID] | None,
    ) -> tuple[tuple[ProjectTaskImportBatch, ...], bool]:
        """Return one page of import batches with member counts and whether another page exists."""
        ...


__all__ = (
    "ProjectAssignment", "ProjectAssignmentPage", "ProjectAssignmentQuery", "ProjectSubmission",
    "ProjectSubmissionPage", "ProjectSubmissionQuery", "ProjectTaskImportBatch", "ProjectTaskImportBatchPage",
    "ProjectWorkCounts", "ProjectWorkReadPort", "TaskImportBatchState", "TaskStatusCounts",
)
