"""Exact task authority facts; decisions and grant ownership stay in AUTH."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class TaskAuthorityOperation(StrEnum):
    CLAIM = "task.claim"
    START = "task.start"
    START_OVERRIDE = "operations.task.start_override"
    WORK_CONTEXT = "task.work_context.read"
    MANAGEMENT_WORK_CONTEXT = "project.task.work_context.read"


@dataclass(frozen=True, slots=True)
class TaskAuthorityFacts:
    operation: TaskAuthorityOperation
    task_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    task_status: str
    assigned_to: UUID | None
    assignment_id: UUID | None
    assignment_contributor_id: UUID | None
    locked_context_hash: str
    reason: str | None = None


class TaskAuthorityDenied(RuntimeError):
    """The exact task operation has no current canonical authority."""


class TaskAuthorizationPort(Protocol):
    """Prepare with TASK/assignment locked; consume exact facts before writes."""

    async def prepare(self, facts: TaskAuthorityFacts) -> object: ...

    async def consume(self, handle: object, facts: TaskAuthorityFacts) -> UUID: ...

    def close(self, handle: object) -> None: ...
