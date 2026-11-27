"""Authorized current intake progress attached to TASK display facts."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


class PendingSubmissionOperationUnavailable(RuntimeError):
    """The active pointer cannot be safely projected."""


@dataclass(frozen=True, slots=True)
class PendingSubmissionOperation:
    """Narrow current intake identity and stage, separate from Submission history."""
    operation_id: UUID
    processing_stage: Literal[
        "receiving", "pre_checking", "finalization_pending", "operationally_stalled",
    ]

    def __post_init__(self) -> None:
        """Reject invalid identities and stages outside the active intake vocabulary."""
        if not isinstance(self.operation_id, UUID) or self.processing_stage not in {
            "receiving", "pre_checking", "finalization_pending", "operationally_stalled",
        }:
            raise ValueError("pending submission operation is invalid")


class PendingSubmissionOperationReadPort(Protocol):
    """Resolve pending progress under the caller transaction and current authority."""
    async def read(self, task_id: UUID, operation_id: UUID) -> PendingSubmissionOperation | None:
        """Use the caller transaction; return None only for denied read authority."""
        ...
