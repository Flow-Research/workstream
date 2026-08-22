"""Hidden PROJECTS ports for deterministic unified-compilation projections."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectGuideProjectionComponent(StrEnum):
    """Closed projection components owned by this hidden capability."""

    GUIDE_SUFFICIENCY = "guide_sufficiency"
    SUBMISSION_ARTIFACT_POLICY = "submission_artifact_policy"


class ProjectGuideProjectionCommand(BaseModel):
    """Select one already-persisted unified compilation attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: UUID


class ProjectGuideProjectionReceipt(BaseModel):
    """Bounded immutable receipt for a created or replayed component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    attempt_id: UUID
    component: ProjectGuideProjectionComponent
    output_id: UUID
    output_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    disposition: Literal["projected", "replayed"]


ProjectGuideProjectionErrorCode = Literal[
    "attempt_unavailable",
    "component_forbidden",
    "component_unprojectable",
    "source_state_unavailable",
    "service_authority_denied",
    "storage_unavailable",
]


class ProjectGuideProjectionError(RuntimeError):
    """Safe hidden failure without product, provider, or AUTH detail."""

    def __init__(self, code: ProjectGuideProjectionErrorCode) -> None:
        """Create an error containing only its stable public code."""
        super().__init__(code)
        self.code = code


class GuideSufficiencyProjectionPort(Protocol):
    """Project the canonical sufficiency component exactly once."""

    async def project_guide_sufficiency(
        self, command: ProjectGuideProjectionCommand
    ) -> ProjectGuideProjectionReceipt:
        """Create or replay the canonical guide-sufficiency report."""
        ...


class ArtifactPolicyProjectionPort(Protocol):
    """Project the canonical artifact-policy component exactly once."""

    async def project_submission_artifact_policy(
        self, command: ProjectGuideProjectionCommand
    ) -> ProjectGuideProjectionReceipt:
        """Create or replay the canonical artifact-policy draft."""
        ...


__all__ = (
    "ArtifactPolicyProjectionPort",
    "GuideSufficiencyProjectionPort",
    "ProjectGuideProjectionCommand",
    "ProjectGuideProjectionComponent",
    "ProjectGuideProjectionError",
    "ProjectGuideProjectionErrorCode",
    "ProjectGuideProjectionReceipt",
)
