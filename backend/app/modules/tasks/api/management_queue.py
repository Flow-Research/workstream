"""Hidden, separate TASK projections for management and operational discovery."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, get_args
from uuid import UUID

from app.modules.tasks.api.ready_queue import TaskQueueCursor, TaskQueueRequest, _aware


TaskStatus = Literal[
    "draft", "screening", "ready", "in_progress", "submitted",
    "evaluation_pending", "review_pending", "needs_revision", "accepted",
]
TASK_STATUSES = frozenset(get_args(TaskStatus))


@dataclass(frozen=True, slots=True)
class TaskQueueFilters:
    """Optional management filters; ``import_batch_id`` selects native batch membership."""

    status: TaskStatus | None = None
    assignee_actor_id: UUID | None = None
    import_batch_id: UUID | None = None
    updated_since: datetime | None = None

    def __post_init__(self) -> None:
        if (
            (self.status is not None and (not isinstance(self.status, str) or self.status not in TASK_STATUSES))
            or any(value is not None and not isinstance(value, UUID)
                   for value in (self.assignee_actor_id, self.import_batch_id))
            or (self.updated_since is not None and not _aware(self.updated_since))
        ):
            raise ValueError("task queue filters are invalid")


@dataclass(frozen=True, slots=True)
class ManagementTaskSummary:
    """Planning facts without work content, source metadata or contributor identity."""

    task_id: UUID
    project_id: UUID
    title: str
    task_type: str | None
    difficulty: str | None
    skill_tags: tuple[str, ...]
    estimated_time_minutes: int | None
    status: TaskStatus
    deadline_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Reject mutable or malformed owner facts before they escape."""
        if (
            not isinstance(self.task_id, UUID) or not isinstance(self.project_id, UUID)
            or not isinstance(self.title, str) or not isinstance(self.status, str)
            or self.status not in TASK_STATUSES
            or any(value is not None and not isinstance(value, str) for value in (self.task_type, self.difficulty))
            or not isinstance(self.skill_tags, tuple)
            or any(not isinstance(value, str) for value in self.skill_tags)
            or (self.estimated_time_minutes is not None and type(self.estimated_time_minutes) is not int)
            or (self.deadline_at is not None and not _aware(self.deadline_at))
            or not _aware(self.created_at) or not _aware(self.updated_at)
        ):
            raise ValueError("management task summary is invalid")


@dataclass(frozen=True, slots=True)
class OperationalTaskSummary:
    """Status-only facts; no task content, actors, policies or artifacts."""

    task_id: UUID
    project_id: UUID
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Keep operational output immutable and restricted to scalar facts."""
        if (
            not isinstance(self.task_id, UUID) or not isinstance(self.project_id, UUID)
            or not isinstance(self.status, str) or self.status not in TASK_STATUSES
            or not _aware(self.created_at) or not _aware(self.updated_at)
        ):
            raise ValueError("operational task summary is invalid")


def _validate_page(
    project_id: UUID,
    items: tuple[ManagementTaskSummary, ...] | tuple[OperationalTaskSummary, ...],
    next_cursor: TaskQueueCursor | None,
    item_type: type[ManagementTaskSummary] | type[OperationalTaskSummary],
) -> None:
    """Enforce exact project and continuation for the two fixed projections."""
    if (
        not isinstance(project_id, UUID) or not isinstance(items, tuple) or len(items) > 100
        or any(type(item) is not item_type or item.project_id != project_id for item in items)
    ):
        raise ValueError("task queue page is invalid")
    if next_cursor is not None and (
        not items or not isinstance(next_cursor, TaskQueueCursor)
        or next_cursor != TaskQueueCursor(project_id, items[-1].created_at, items[-1].task_id)
    ):
        raise ValueError("task queue continuation differs from page")


@dataclass(frozen=True, slots=True)
class ManagementTaskPage:
    """A bounded live management page; this conveys no authority or reservation."""

    project_id: UUID
    items: tuple[ManagementTaskSummary, ...]
    next_cursor: TaskQueueCursor | None

    def __post_init__(self) -> None:
        """Enforce the management-only field contract and exact project."""
        _validate_page(self.project_id, self.items, self.next_cursor, ManagementTaskSummary)


@dataclass(frozen=True, slots=True)
class OperationalTaskPage:
    """A bounded live status page, with no management content."""

    project_id: UUID
    items: tuple[OperationalTaskSummary, ...]
    next_cursor: TaskQueueCursor | None

    def __post_init__(self) -> None:
        """Prevent broader management facts from entering operational output."""
        _validate_page(self.project_id, self.items, self.next_cursor, OperationalTaskSummary)


class ManagementTaskQueuePort(Protocol):
    """Hidden project management facts; ARCH-03C supplies exact live authority."""

    async def read_management_tasks(
        self, request: TaskQueueRequest, filters: TaskQueueFilters = TaskQueueFilters(),
    ) -> ManagementTaskPage:
        """Read all project task states without owning the caller's transaction."""
        ...


class OperationalTaskQueuePort(Protocol):
    """Hidden status facts; selecting a project never authorizes an Operator."""

    async def read_operational_tasks(self, request: TaskQueueRequest) -> OperationalTaskPage:
        """Read project status facts without contributor-private details."""
        ...
