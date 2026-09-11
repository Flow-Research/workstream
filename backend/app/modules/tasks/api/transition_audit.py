"""TASK transition facts passed to the shared audit owner."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.authorization import TaskAuthorityOperation


@dataclass(frozen=True, slots=True)
class TaskTransitionFacts:
    operation: TaskAuthorityOperation
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    actor_profile_id: UUID
    authorization_decision_id: UUID
    from_status: str
    to_status: str
    reason: str | None


class TaskTransitionAuditPort(Protocol):
    async def record(self, facts: TaskTransitionFacts) -> None: ...
