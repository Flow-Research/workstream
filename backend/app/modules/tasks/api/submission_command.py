"""Public TASK capability for immutable admission-backed Submission creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, get_args
from uuid import UUID

from app.modules.tasks.api.submission_context import TaskSubmissionContextFacts

class SubmissionCreationUnavailable(RuntimeError):
    """Conceal an unavailable admission-backed Submission creation capability."""


SubmissionCreationAdmissionFailure = Literal[
    "submission_bundle_admission_unavailable",
    "submission_bundle_admission_already_consumed",
    "submission_bundle_admission_context_changed",
    "submission_bundle_admission_stale",
]


class SubmissionCreationAdmissionError(RuntimeError):
    """Stable TASK-facing rejection of an ART admission consumption request."""

    def __init__(self, code: SubmissionCreationAdmissionFailure) -> None:
        if code not in get_args(SubmissionCreationAdmissionFailure):
            raise ValueError("submission admission failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SubmissionCreationRequest:
    """Contributor input and server-selected identities for one Submission."""

    admission_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    predecessor_submission_id: UUID | None
    summary: str | None = None
    contributor_attestation: str | None = None
    feedback: str | None = None


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

    async def prepare(self, facts: SubmissionCreationAuthorityFacts) -> object:
        """Prepare fresh exact authority before ART admission state is inspected."""

    async def consume(
        self, prepared_authorization: object, facts: SubmissionCreationAuthorityFacts
    ) -> UUID:
        """Consume final exact authority and return its retained decision identity."""

    async def validate_replay(
        self, prepared_authorization: object, facts: SubmissionCreationAuthorityFacts,
        decision_id: UUID,
    ) -> None:
        """Verify the original allow under fresh current authority without consuming."""

    def close(self, prepared_authorization: object) -> None:
        """Discard process-local authority after every success or failure path."""


@dataclass(frozen=True, slots=True)
class SubmissionCreationResult:
    """Bounded immutable result of the hidden composed transaction."""

    submission_id: UUID
    submission_version: int
    admission_id: UUID
    artifact_binding_id: UUID
    artifact_content_id: UUID
    creation_decision_id: UUID
    binding_decision_id: UUID
    evaluation_request_id: UUID
    evaluation_request_digest: str
    evaluation_attempt_id: UUID
    evaluation_result_id: UUID
    evaluation_event_id: UUID


class SubmissionCreationCommand(Protocol):
    """Create one immutable Submission through transaction-bound owner ports."""

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        """Apply one atomic TASK/ART operation without committing independently."""
