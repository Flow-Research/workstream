"""Dependency-safe hidden execution port for unified guide compilation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class ProjectGuideCompilationDelivery(BaseModel):
    """The broker's actual delivery identity and exact immutable setup selector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    setup_run_id: UUID
    setup_generation: Annotated[int, Field(gt=0)]
    task_id: UUID


class ProjectGuideCompilationDeliveryError(RuntimeError):
    """Reject a broker selector that does not identify the current setup generation."""

    def __init__(self) -> None:
        super().__init__("stale compilation delivery")


class ProjectGuideCompilationDeliveryPort(Protocol):
    """Deliver the exact generation through the PROJECTS-owned coordinator."""

    async def run(self, delivery: ProjectGuideCompilationDelivery) -> dict:
        """Return bounded terminal or recoverable diagnostics for this delivery."""
        ...


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
    "runtime_unavailable",
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


class ProjectGuideSetupFinalizationCommand(BaseModel):
    """Exact current generation selected by an internal caller."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    project_id: UUID
    guide_id: UUID
    setup_run_id: UUID
    setup_generation: Annotated[int, Field(gt=0)]
    compilation_id: UUID


class ProjectGuideSetupFinalizationReceipt(BaseModel):
    """Bounded immutable finalization custody, without raw compilation or AUTH handle."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    finalization_id: UUID
    operation_id: UUID
    project_id: UUID
    guide_id: UUID
    setup_run_id: UUID
    setup_generation: int
    result_classification: Literal["guide_blocked", "draft_ready", "draft_ready_with_warnings"]
    setup_outcome: Literal["sufficiency_blocked", "policy_draft_ready"]
    sufficiency_report_id: UUID
    artifact_policy_id: UUID | None
    authorization_decision_event_id: UUID


class ProjectGuideSetupFinalizationError(RuntimeError):
    """Concealed failure; callers must roll back the current root transaction."""

    def __init__(
        self,
        code: Literal[
            "source_state_unavailable", "service_authority_denied", "storage_unavailable"
        ],
    ) -> None:
        super().__init__(code)
        self.code = code


class ProjectGuideSetupFinalizationPort(Protocol):
    """Finalize existing compilation/projection custody inside the caller transaction."""

    async def finalize(
        self, command: ProjectGuideSetupFinalizationCommand
    ) -> ProjectGuideSetupFinalizationReceipt: ...


__all__ = (
    "ProjectGuideCompilationDelivery",
    "ProjectGuideCompilationDeliveryError",
    "ProjectGuideCompilationDeliveryPort",
    "ProjectGuideSetupFinalizationCommand",
    "ProjectGuideSetupFinalizationReceipt",
    "ProjectGuideSetupFinalizationError",
    "ProjectGuideSetupFinalizationPort",
    "ProjectGuideCompilationExecutionClassification",
    "ProjectGuideCompilationExecutionCommand",
    "ProjectGuideCompilationExecutionError",
    "ProjectGuideCompilationExecutionErrorCode",
    "ProjectGuideCompilationExecutionPort",
    "ProjectGuideCompilationExecutionResult",
)
