"""Hidden TASK detail facts; exact selectors and visibility never grant authority."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.ready_queue import TaskCompensationTerms, _aware


@dataclass(frozen=True, slots=True)
class ManagementTaskDetailRequest:
    """A future caller must authorize this exact project before reading."""

    project_id: UUID
    task_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, UUID) or not isinstance(self.task_id, UUID):
            raise ValueError("task detail request is invalid")


@dataclass(frozen=True, slots=True)
class ContributorTaskDetailRequest:
    """The caller binds the contributor to current authority, never client input."""

    project_id: UUID
    task_id: UUID
    contributor_id: UUID

    def __post_init__(self) -> None:
        if not all(isinstance(value, UUID) for value in (self.project_id, self.task_id, self.contributor_id)):
            raise ValueError("task detail request is invalid")


@dataclass(frozen=True, slots=True)
class _TaskDetailFields:
    """Shared immutable work instructions, without policy or economic metadata."""

    task_id: UUID
    project_id: UUID
    title: str
    description: str
    task_type: str | None
    difficulty: str | None
    skill_tags: tuple[str, ...]
    estimated_time_minutes: int | None
    status: str
    acceptance_criteria: str | None
    rejection_criteria: str | None
    deadline_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.task_id, UUID) or not isinstance(self.project_id, UUID)
            or any(not isinstance(value, str) for value in (self.title, self.description, self.status))
            or any(value is not None and not isinstance(value, str) for value in (
                self.task_type, self.difficulty, self.acceptance_criteria, self.rejection_criteria,
            ))
            or not isinstance(self.skill_tags, tuple) or any(not isinstance(tag, str) for tag in self.skill_tags)
            or (self.estimated_time_minutes is not None and type(self.estimated_time_minutes) is not int)
            or (self.deadline_at is not None and not _aware(self.deadline_at))
            or not _aware(self.created_at) or not _aware(self.updated_at)
        ):
            raise ValueError("task detail facts are invalid")


@dataclass(frozen=True, slots=True)
class ContributorTaskDetail(_TaskDetailFields):
    """Work instructions plus contributor-safe locked compensation terms."""

    compensation: TaskCompensationTerms

    def __post_init__(self) -> None:
        _TaskDetailFields.__post_init__(self)
        if not isinstance(self.compensation, TaskCompensationTerms):
            raise ValueError("task detail facts are invalid")


@dataclass(frozen=True, slots=True)
class ManagementTaskDetail(_TaskDetailFields):
    """Management work instructions plus exact source and assignment display facts."""

    source_type: str
    source_ref: str | None
    source_payload_hash: str | None
    import_batch_id: str | None
    external_task_id: str | None
    created_by: str
    assigned_to: str | None

    def __post_init__(self) -> None:
        _TaskDetailFields.__post_init__(self)
        if (
            not isinstance(self.source_type, str) or not isinstance(self.created_by, str)
            or any(value is not None and not isinstance(value, str) for value in (
                self.source_ref, self.source_payload_hash, self.import_batch_id, self.external_task_id, self.assigned_to,
            ))
        ):
            raise ValueError("task detail facts are invalid")


class ContributorTaskDetailPort(Protocol):
    """Hidden project/task/assignment visibility facts; no authorization decision."""

    async def read_contributor_task_detail(self, request: ContributorTaskDetailRequest) -> ContributorTaskDetail | None:
        """Conceal missing or invisible tasks without an existence probe."""
        ...


class ManagementTaskDetailPort(Protocol):
    """Hidden project management detail; exact public authority remains separate."""

    async def read_management_task_detail(self, request: ManagementTaskDetailRequest) -> ManagementTaskDetail | None:
        """Read all task states without taking ownership of the transaction."""
        ...
