"""Narrow TASK participation in a caller-owned intake transaction, not AUTH."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest


@dataclass(frozen=True, slots=True)
class IntakeTaskSnapshot:
    """Exact TASK context captured while its row and assignment remain locked."""

    project_id: UUID
    eligible_status: str
    context_json: str


class IntakeTaskCustodyPort(Protocol):
    """Maintain the task pointer only; caller must supply authorized owner work."""

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
