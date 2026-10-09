"""Hidden TASK-owned ready queue facts; project selection is not authorization."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, TypeAlias
from uuid import UUID


class LockedTaskCompensationUnavailable(RuntimeError):
    """The task's exact locked compensation graph could not be projected."""


def _aware(value: datetime) -> bool:
    """Require an exact, timezone-aware keyset position."""
    return isinstance(value, datetime) and value.utcoffset() is not None


@dataclass(frozen=True, slots=True)
class TaskCompensationAward:
    """One contributor-safe exact award value in a TASK response."""

    instrument: Literal["money", "project_points"]
    unit: str
    quantity: str

    def __post_init__(self) -> None:
        if (
            self.instrument not in ("money", "project_points")
            or type(self.unit) is not str
            or not self.unit
            or type(self.quantity) is not str
            or not self.quantity
        ):
            raise ValueError("task compensation award is invalid")


TaskContributionTerms: TypeAlias = Literal["unpaid"] | tuple[TaskCompensationAward, ...]


@dataclass(frozen=True, slots=True)
class TaskCompensationTerms:
    """The two complete locked contribution rules disclosed by TASK."""

    contribution_policy_version_id: UUID
    accepted_submission: TaskContributionTerms
    completed_review: TaskContributionTerms

    def __post_init__(self) -> None:
        if not isinstance(self.contribution_policy_version_id, UUID):
            raise ValueError("task compensation terms are invalid")
        for value in (self.accepted_submission, self.completed_review):
            if value == "unpaid":
                continue
            if (
                type(value) is not tuple
                or not 1 <= len(value) <= 2
                or any(not isinstance(item, TaskCompensationAward) for item in value)
                or len({item.instrument for item in value}) != len(value)
            ):
                raise ValueError("task compensation terms are invalid")


@dataclass(frozen=True, slots=True)
class TaskQueueCursor:
    """Project-bound live position, not an authority token or reservation."""

    project_id: UUID
    created_at: datetime
    task_id: UUID

    def __post_init__(self) -> None:
        """Reject malformed positions before a repository can query."""
        if not all(isinstance(value, UUID) for value in (self.project_id, self.task_id)) or not _aware(self.created_at):
            raise ValueError("task queue cursor is invalid")


@dataclass(frozen=True, slots=True)
class TaskQueueRequest:
    """Bound one project and page; future callers must authorize scope first."""

    project_id: UUID
    limit: int = 50
    after: TaskQueueCursor | None = None

    def __post_init__(self) -> None:
        """Reject unbounded limits and cross-project cursor substitution."""
        if not isinstance(self.project_id, UUID) or type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("task queue request is invalid")
        if self.after is not None and (
            not isinstance(self.after, TaskQueueCursor) or self.after.project_id != self.project_id
        ):
            raise ValueError("task queue cursor differs from project")


@dataclass(frozen=True, slots=True)
class ReadyTaskSummary:
    """Detached contributor summary without source, actor or policy internals."""

    task_id: UUID
    project_id: UUID
    title: str
    task_type: str | None
    difficulty: str | None
    skill_tags: tuple[str, ...]
    estimated_time_minutes: int | None
    created_at: datetime
    compensation: TaskCompensationTerms

    def __post_init__(self) -> None:
        """Keep summary facts deeply immutable and scalar."""
        if (
            not isinstance(self.task_id, UUID) or not isinstance(self.project_id, UUID)
            or not isinstance(self.title, str)
            or any(value is not None and not isinstance(value, str) for value in (self.task_type, self.difficulty))
            or not isinstance(self.skill_tags, tuple)
            or any(not isinstance(value, str) for value in self.skill_tags)
            or (self.estimated_time_minutes is not None and type(self.estimated_time_minutes) is not int)
            or not _aware(self.created_at)
            or not isinstance(self.compensation, TaskCompensationTerms)
        ):
            raise ValueError("ready task summary is invalid")


@dataclass(frozen=True, slots=True)
class ReadyTaskPage:
    """One live eligible page; claim always revalidates current authority/state."""

    project_id: UUID
    items: tuple[ReadyTaskSummary, ...]
    next_cursor: TaskQueueCursor | None

    def __post_init__(self) -> None:
        """Prevent a projection or continuation from crossing project scope."""
        if (
            not isinstance(self.project_id, UUID) or not isinstance(self.items, tuple)
            or len(self.items) > 100
            or any(not isinstance(item, ReadyTaskSummary) or item.project_id != self.project_id for item in self.items)
        ):
            raise ValueError("ready task page is invalid")
        if self.next_cursor is not None and (
            not self.items or not isinstance(self.next_cursor, TaskQueueCursor)
            or self.next_cursor != TaskQueueCursor(
                self.project_id, self.items[-1].created_at, self.items[-1].task_id,
            )
        ):
            raise ValueError("ready task continuation differs from page")


class ReadyTaskQueuePort(Protocol):
    """Internal data-owner read; ARCH-03C supplies AUTH and public composition."""

    async def read_ready_tasks(self, request: TaskQueueRequest) -> ReadyTaskPage:
        """Read a scoped live page without claiming work or owning a transaction."""
        ...
