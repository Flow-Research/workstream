"""Closed persistence inputs for the hidden review queue foundation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReviewQueueState(StrEnum):
    """Queue states persistable before ReviewLease exists."""

    PENDING = "pending"
    CLOSED = "closed"


class ReviewRoutingMode(StrEnum):
    """Stored routing shapes; selection behavior is implemented later."""

    OPEN = "open"
    PREFERRED = "preferred"


class ReviewRoutingReason(StrEnum):
    """Closed reasons for the initial stored routing shape."""

    FIRST_SUBMISSION = "first_submission"
    REVISION_RETURN = "revision_return"
    ADMIN_ASSIGNMENT = "admin_assignment"


class ReviewQueueCloseReason(StrEnum):
    """Closed queue outcomes available to later lifecycle commands."""

    REVIEW_RECORDED = "review_recorded"
    TASK_CLOSED = "task_closed"
    ADMIN_CANCELLED = "admin_cancelled"


class ReviewQueueEntryInput(BaseModel):
    """Exact values for one queue identity; this input grants no authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    project_id: str = Field(min_length=36, max_length=36)
    task_id: str = Field(min_length=36, max_length=36)
    submission_id: str = Field(min_length=36, max_length=36)
    submission_version: int = Field(gt=0)
    admitting_checker_run_id: str = Field(min_length=36, max_length=36)
    queue_state: ReviewQueueState = ReviewQueueState.PENDING
    routing_mode: ReviewRoutingMode
    routing_reason: ReviewRoutingReason
    preferred_reviewer_id: str | None = Field(default=None, min_length=36, max_length=36)
    preference_expires_at: datetime | None = None
    closed_at: datetime | None = None
    closed_reason: ReviewQueueCloseReason | None = None


class ReviewAdmissionReservationInput(BaseModel):
    """One idempotent admission reservation without lifecycle authorization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    idempotency_key: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    project_id: str = Field(min_length=36, max_length=36)
    task_id: str = Field(min_length=36, max_length=36)
    submission_id: str = Field(min_length=36, max_length=36)
    submission_version: int = Field(gt=0)
    admitting_checker_run_id: str = Field(min_length=36, max_length=36)
