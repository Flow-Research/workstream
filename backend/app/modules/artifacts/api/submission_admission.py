"""Public ART capability for consuming one verified submission admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, get_args
from uuid import UUID

from app.modules.tasks.api import TaskSubmissionContextFacts

SubmissionAdmissionConsumptionStatus = Literal["consumed", "stale"]
SubmissionAdmissionConsumptionFailure = Literal[
    "submission_bundle_admission_unavailable",
    "submission_bundle_admission_already_consumed",
    "submission_bundle_admission_context_changed",
    "submission_bundle_admission_stale",
]


class SubmissionAdmissionConsumptionError(RuntimeError):
    """Return one stable ART-owned failure without persistence details."""

    def __init__(self, code: SubmissionAdmissionConsumptionFailure) -> None:
        if code not in get_args(SubmissionAdmissionConsumptionFailure):
            raise ValueError("submission admission failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SubmissionAdmissionConsumptionRequest:
    """Exact TASK identity and locked lineage supplied to ART for consumption."""

    admission_id: UUID
    submission_id: UUID
    submission_version: int
    task_context: TaskSubmissionContextFacts

    def __post_init__(self) -> None:
        if type(self.submission_version) is not int or self.submission_version < 1:
            raise ValueError("submission version is invalid")


@dataclass(frozen=True, slots=True)
class SubmissionAdmissionConsumptionResult:
    """Bounded terminal ART facts returned to transaction composition."""

    admission_id: UUID
    binding_id: UUID | None
    content_id: UUID
    submission_id: UUID
    submission_version: int
    status: SubmissionAdmissionConsumptionStatus
    replayed: bool


class SubmissionAdmissionConsumptionPort(Protocol):
    """Consume or stale one locked admission in the caller's root transaction."""

    async def consume(
        self,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        """Apply one terminal admission transition without provider I/O."""
