"""Bounded task lifecycle evidence; selectors never confer authority."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.ready_queue import _aware


class TaskEvidenceInvalid(ValueError):
    """Persisted task evidence cannot satisfy its fixed projection contract."""


@dataclass(frozen=True, slots=True)
class TaskEvidenceCursor:
    """A live event position bound to one project and task, not a permission."""

    project_id: UUID
    task_id: UUID
    created_at: datetime
    event_id: UUID

    def __post_init__(self) -> None:
        if not all(isinstance(value, UUID) for value in (self.project_id, self.task_id, self.event_id)) or not _aware(self.created_at):
            raise ValueError("task evidence cursor is invalid")


@dataclass(frozen=True, slots=True)
class AuditTaskEvidenceRequest:
    """Callers must authorize this exact scope before using the read."""

    project_id: UUID
    task_id: UUID
    limit: int = 50
    after: TaskEvidenceCursor | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.project_id, UUID) or not isinstance(self.task_id, UUID)
            or type(self.limit) is not int or not 1 <= self.limit <= 100
        ):
            raise ValueError("task evidence request is invalid")
        if self.after is not None and (
            type(self.after) is not TaskEvidenceCursor
            or (self.after.project_id, self.after.task_id) != (self.project_id, self.task_id)
        ):
            raise ValueError("task evidence cursor differs from scope")


@dataclass(frozen=True, slots=True)
class AuditTaskEvidence:
    """Fixed event facts without claims, free text or arbitrary payloads."""

    event_id: UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_id: str
    created_at: datetime
    assignment_id: UUID | None
    authorization_decision_id: UUID | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.event_id, UUID) or not isinstance(self.event_type, str)
            or not isinstance(self.actor_id, str) or not _aware(self.created_at)
            or any(value is not None and not isinstance(value, str) for value in (self.from_status, self.to_status))
            or any(value is not None and not isinstance(value, UUID) for value in (self.assignment_id, self.authorization_decision_id))
            or (self.event_type in {"TaskCreated", "TaskScreened", "TaskReleased"}
                and (self.assignment_id is not None or self.authorization_decision_id is None))
            or (self.event_type not in {"TaskCreated", "TaskScreened", "TaskReleased"}
                and (self.assignment_id is None) != (self.authorization_decision_id is None))
        ):
            raise ValueError("task evidence facts are invalid")


@dataclass(frozen=True, slots=True)
class AuditTaskEvidencePage:
    """One scoped statement snapshot; continuation does not reserve history."""

    project_id: UUID
    task_id: UUID
    items: tuple[AuditTaskEvidence, ...]
    next_cursor: TaskEvidenceCursor | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.project_id, UUID) or not isinstance(self.task_id, UUID)
            or not isinstance(self.items, tuple) or len(self.items) > 100
            or any(type(item) is not AuditTaskEvidence for item in self.items)
        ):
            raise ValueError("task evidence page is invalid")
        if self.next_cursor is not None and (
            not self.items or type(self.next_cursor) is not TaskEvidenceCursor
            or self.next_cursor != TaskEvidenceCursor(
                self.project_id, self.task_id, self.items[-1].created_at, self.items[-1].event_id,
            )
        ):
            raise ValueError("task evidence continuation differs from page")


class AuditTaskEvidencePort(Protocol):
    """Evidence facts; the public operation supplies covered Audit Authority."""

    async def read_audit_task_evidence(self, request: AuditTaskEvidenceRequest) -> AuditTaskEvidencePage | None:
        """Conceal absent/foreign tasks without owning the caller transaction."""
        ...
