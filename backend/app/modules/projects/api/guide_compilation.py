"""Dependency-safe hidden execution port for unified guide compilation."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectGuideCompilationExecutionClassification(StrEnum):
    """Closed durable outcomes visible to hidden callers."""

    RESERVED = "compilation_reserved"
    PROVIDER_UNRESOLVED = "provider_outcome_unresolved"
    ACCEPTED_NOT_PERSISTED = "provider_result_accepted_not_persisted"
    PERSISTED = "compilation_persisted"
    INVALID_TERMINAL = "compilation_invalid_terminal"


class ProjectGuideCompilationExecutionCommand(BaseModel):
    """Select one existing authorized compilation attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: UUID


class ProjectGuideCompilationExecutionResult(BaseModel):
    """Bounded receipt without guide, provider, or authorization material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    attempt_id: UUID
    provider_idempotency_key: UUID
    classification: ProjectGuideCompilationExecutionClassification
    compilation_id: UUID | None = None


ProjectGuideCompilationExecutionErrorCode = Literal[
    "attempt_unavailable",
    "context_unavailable",
    "service_authority_denied",
    "storage_unavailable",
]


class ProjectGuideCompilationExecutionError(RuntimeError):
    """Safe hidden failure that never advances durable attempt state."""

    def __init__(self, code: ProjectGuideCompilationExecutionErrorCode) -> None:
        super().__init__(code)
        self.code = code


class ProjectGuideCompilationExecutionPort(Protocol):
    """Execute or recover one already-authorized compilation attempt."""

    async def execute(
        self, command: ProjectGuideCompilationExecutionCommand
    ) -> ProjectGuideCompilationExecutionResult: ...


__all__ = (
    "ProjectGuideCompilationExecutionClassification",
    "ProjectGuideCompilationExecutionCommand",
    "ProjectGuideCompilationExecutionError",
    "ProjectGuideCompilationExecutionErrorCode",
    "ProjectGuideCompilationExecutionPort",
    "ProjectGuideCompilationExecutionResult",
)
