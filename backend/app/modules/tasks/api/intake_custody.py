"""Narrow TASK participation in a caller-owned intake transaction, not AUTH."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest, TaskSubmissionContextFacts
from app.modules.tasks.api.management_queue import TaskStatus


@dataclass(frozen=True, slots=True)
class IntakeTaskSnapshot:
    """Exact TASK context captured while its row and assignment remain locked."""

    project_id: UUID
    eligible_status: str
    context_json: str


@dataclass(frozen=True, slots=True)
class IntakeTaskReadContext:
    """Current visibility and candidate facts, never a historical attempt outcome."""
    current_task_status: TaskStatus | None
    candidate: TaskSubmissionContextFacts | None


class IntakeTaskCustodyPort(Protocol):
    """Maintain the pointer and T4 pending state inside authorized owner work."""

    async def claim(self, request: TaskSubmissionContextRequest, operation_id: UUID) -> IntakeTaskSnapshot:
        """Lock canonical submission context and install its unique operation pointer."""
        ...

    async def lock(self, task_id: UUID) -> UUID:
        """Acquire TASK first and return its project without asserting eligibility."""
        ...

    async def require_active(self, task_id: UUID, operation_id: UUID) -> UUID:
        """Lock TASK and require its exact active operation; return the project."""
        ...

    async def release(self, task_id: UUID, operation_id: UUID) -> None:
        """Clear only this operation's pointer inside the terminal transaction."""
        ...

    async def accept(self, task_id: UUID, operation_id: UUID, expected_status: str) -> None:
        """T4-only direct transition; deferred custody requires exact accepted AUTH/event."""
        ...


    async def read_operation_context(
        self, request: TaskSubmissionContextRequest, *, project_id: UUID,
        reader_id: UUID, management: bool, own_submitter: bool,
    ) -> IntakeTaskReadContext:
        """After AUTH, read visibility and a candidate needing locked policy/ack checks."""
        ...
