"""Exact task authority facts; decisions and grant ownership stay in AUTH."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class TaskAuthorityOperation(StrEnum):
    CREATE = "project.task.create"
    SCREEN = "project.task.screen"
    RELEASE = "project.task.release"
    READ = "task.read"
    REQUIREMENTS = "task.submission_requirements.read"
    MANAGEMENT_READ = "project.task.read"
    MANAGEMENT_REQUIREMENTS = "project.task.submission_requirements.read"
    MANAGEMENT_LOCKED_CONTEXT = "project.task.locked_context.read"
    OPERATIONAL_LOCKED_CONTEXT = "operations.task.locked_context.read"
    AUDIT_LOCKED_CONTEXT = "audit.task.locked_context.read"
    AUDIT_EVIDENCE = "audit.task.evidence.read"
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
    idempotency_key: UUID | None = None
    replay_assignment_id: UUID | None = None
    request_digest: str | None = None
    replay_command_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TaskAuthorityDecision:
    """Exact consumed AUTH evidence, including immutable pre-write context JSON."""
    decision_id: UUID
    identity_link_id: UUID
    resource_context_digest: str
    resource_context_json: str


class TaskAuthorityDenied(RuntimeError):
    """The exact task operation has no current canonical authority."""


class TaskAuthorizationPort(Protocol):
    """Prepare with TASK/assignment locked; consume exact facts before writes."""

    async def prepare(self, facts: TaskAuthorityFacts) -> object: ...

    async def consume(self, handle: object, facts: TaskAuthorityFacts) -> TaskAuthorityDecision: ...

    def close(self, handle: object) -> None: ...
