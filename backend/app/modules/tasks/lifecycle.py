"""Task lifecycle constants and transition guards."""

from __future__ import annotations

TASK_STATUS_DRAFT = "draft"
TASK_STATUS_SCREENING = "screening"
TASK_STATUS_READY = "ready"
TASK_STATUS_CLAIMED = "claimed"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_SUBMITTED = "submitted"
TASK_STATUS_EVALUATION_PENDING = "evaluation_pending"
TASK_STATUS_REVIEW_PENDING = "review_pending"
TASK_STATUS_NEEDS_REVISION = "needs_revision"

ALLOWED_TASK_TRANSITIONS = {
    (TASK_STATUS_DRAFT, TASK_STATUS_SCREENING),
    (TASK_STATUS_SCREENING, TASK_STATUS_READY),
    (TASK_STATUS_READY, TASK_STATUS_CLAIMED),
    (TASK_STATUS_CLAIMED, TASK_STATUS_IN_PROGRESS),
    (TASK_STATUS_IN_PROGRESS, TASK_STATUS_SUBMITTED),
    (TASK_STATUS_SUBMITTED, TASK_STATUS_EVALUATION_PENDING),
    (TASK_STATUS_REVIEW_PENDING, TASK_STATUS_EVALUATION_PENDING),
    (TASK_STATUS_EVALUATION_PENDING, TASK_STATUS_REVIEW_PENDING),
    (TASK_STATUS_EVALUATION_PENDING, TASK_STATUS_NEEDS_REVISION),
    (TASK_STATUS_NEEDS_REVISION, TASK_STATUS_SUBMITTED),
}


class InvalidTaskTransition(ValueError):
    """Raised when a task lifecycle transition is not allowed."""


def ensure_allowed_transition(from_status: str, to_status: str) -> None:
    """Validate a task status transition implemented by the current backend.

    Args:
        from_status: Current task status.
        to_status: Desired next task status.

    Raises:
        InvalidTaskTransition: If the transition is not supported.
    """
    if (from_status, to_status) not in ALLOWED_TASK_TRANSITIONS:
        raise InvalidTaskTransition(f"invalid task transition: {from_status} -> {to_status}")
