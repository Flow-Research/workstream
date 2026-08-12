"""Public TASK capability for immutable admission-backed Submission creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.submission_context import TaskSubmissionContextFacts

class SubmissionCreationUnavailable(RuntimeError):
    """Conceal the unavailable hidden Submission creation capability."""


@dataclass(frozen=True, slots=True)
class SubmissionCreationRequest:
    """Contributor input and server-selected identities for one Submission."""

    admission_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    predecessor_submission_id: UUID | None
    summary: str
    contributor_attestation: str

    def __post_init__(self) -> None:
        """Reject empty contributor-authored text at the public boundary."""
        if not self.summary.strip() or not self.contributor_attestation.strip():
            raise ValueError("submission text is empty")


@dataclass(frozen=True, slots=True)
class SubmissionCreationPreparationFacts:
    """TASK selectors checked before protected state is revealed."""

    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    admission_id: UUID
    predecessor_submission_id: UUID | None


@dataclass(frozen=True, slots=True)
class SubmissionCreationAuthorityFacts(SubmissionCreationPreparationFacts):
    """Exact final TASK identity/version required for authority consumption."""

    submission_id: UUID
    submission_version: int
    task_context: TaskSubmissionContextFacts

    def __post_init__(self) -> None:
        if self.submission_version < 1:
            raise ValueError("submission version is invalid")
        if (
            self.task_context.task_id != self.task_id
            or self.task_context.assignment_id != self.assignment_id
            or self.task_context.contributor_id != self.contributor_id
            or (
                self.task_context.predecessor.submission_id
                if self.task_context.predecessor is not None
                else None
            )
            != self.predecessor_submission_id
        ):
            raise ValueError("submission authority context is inconsistent")


class SubmissionCreationAuthorizationPort(Protocol):
    """Authorize and finally consume human Submission authority in one transaction."""

    async def authorize(self, facts: SubmissionCreationPreparationFacts) -> None:
        """Conceal denial before TASK state is locked or revealed."""

    async def consume(self, facts: SubmissionCreationAuthorityFacts) -> None:
        """Consume final exact authority after protected facts are known."""


@dataclass(frozen=True, slots=True)
class SubmissionArtifactAdmissionRequest:
    """Exact TASK allocation supplied to the artifact admission participant."""

    admission_id: UUID
    submission_id: UUID
    submission_version: int
    task_context: TaskSubmissionContextFacts


@dataclass(frozen=True, slots=True)
class SubmissionArtifactAdmissionResult:
    """Artifact identities returned after exact admission consumption."""

    binding_id: UUID
    content_id: UUID


class SubmissionArtifactAdmissionPort(Protocol):
    """Consume one ready artifact admission in the caller-owned transaction."""

    async def consume(
        self, request: SubmissionArtifactAdmissionRequest
    ) -> SubmissionArtifactAdmissionResult:
        """Return exact binding/content identity or raise an owner error."""


@dataclass(frozen=True, slots=True)
class SubmissionCreationResult:
    """Bounded immutable result of the hidden composed transaction."""

    submission_id: UUID
    submission_version: int
    admission_id: UUID
    artifact_binding_id: UUID
    artifact_content_id: UUID


class SubmissionCreationCommand(Protocol):
    """Create one immutable Submission through transaction-bound owner ports."""

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        """Apply one atomic TASK/ART operation without committing independently."""
