"""Exact accepted continuation selectors; values confer no authority themselves."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

# Existing durable OUTBOX lease convention, shared with the worker hard bound.
# Deployment qualification and independent admission sizing remain separate.
SUBMISSION_FINALIZATION_DELIVERY_LEASE_SECONDS = 300


@dataclass(frozen=True, slots=True)
class SubmissionFinalizationProgress:
    """Internal owner facts; not the complete public operation-read response."""

    operation_id: UUID
    finalized: bool
    operationally_stalled: bool
    stalled_at: datetime | None
    next_retry_at: datetime | None
    attempt_count: int


@dataclass(frozen=True, slots=True)
class SubmissionFinalizationAuthorityFacts:
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    acceptance_decision_id: UUID
    accepted_context_sha256: str
    acceptance_receipt_sha256: str
    source_sha256: str
    continuation_lease_id: UUID
    continuation_generation: int
    phase: Literal["claim", "commit"]
    submission_id: UUID | None = None
    submission_version: int | None = None
