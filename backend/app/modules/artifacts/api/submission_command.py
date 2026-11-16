"""Public single-request submission command and explicit deployment contract."""
from collections.abc import AsyncIterator
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata, SubmissionSourceCapacityLimits
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitRuntimeProfile
from app.modules.tasks.api.management_queue import TaskStatus

Seconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class SubmissionExecutionProfile(BaseModel):
    """Required finite values; validity does not establish measured qualification."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    capacity: SubmissionSourceCapacityLimits
    runtime: SelectedPreSubmitRuntimeProfile
    upload_total_seconds: Seconds
    upload_idle_seconds: Seconds
    foreground_lease_seconds: Seconds
    heartbeat_seconds: Seconds
    replay_total_seconds: Seconds
    part_bytes: int = Field(ge=5 * 1024**2, le=16 * 1024**2)

    @model_validator(mode="after")
    def bounded_envelopes(self) -> Self:
        """Require consistent, finite and representable upload and lease envelopes."""
        if not self.heartbeat_seconds < self.foreground_lease_seconds <= self.upload_total_seconds:
            raise ValueError("submission foreground lease envelope is invalid")
        if self.foreground_lease_seconds * 1000 > self.runtime.aggregate_deadline_ms:
            raise ValueError("submission foreground lease exceeds PRE deadline")
        if self.upload_idle_seconds > min(self.upload_total_seconds, self.replay_total_seconds):
            raise ValueError("submission idle timeout exceeds request envelope")
        # Validate representability before admission or any provider activity.
        from datetime import UTC, datetime, timedelta
        for value in (self.upload_total_seconds, self.replay_total_seconds):
            try:
                datetime.now(UTC) + timedelta(seconds=value)
            except OverflowError:
                raise ValueError("submission request envelope is not representable") from None
        return self


class SubmissionAcceptedResponse(BaseModel):
    """Stable T4 snapshot; Submission/evaluation IDs do not exist until T5."""

    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    task_id: UUID
    assignment_id: UUID
    status: Literal["accepted"]
    accepted_at: AwareDatetime
    task_status_at_acceptance: Literal["evaluation_pending"]
    processing_stage_at_acceptance: Literal["finalization_pending"]
    replayed: bool
    pre_submission_results: list[dict[str, object]]


class SubmissionIntakeCommand(Protocol):
    """Single raw-ZIP mutation whose success is durable T4 acceptance."""
    async def submit(
        self, metadata: SubmissionIntakeMetadata, chunks: AsyncIterator[bytes], *,
        actor_id: UUID, identity_link_id: UUID, idempotency_key: UUID,
        declared_raw_bytes: int | None,
    ) -> dict:
        """Return committed acceptance or a bounded SubmissionIntakeFailure."""
        ...


class SubmissionOperationSelector(BaseModel):
    """Two selectors for one read; key scope is supplied by authenticated context."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID | None = None
    idempotency_key: UUID | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        """Reject missing selectors and ambiguous operation/key combinations."""
        if (self.operation_id is None) == (self.idempotency_key is None):
            raise ValueError("exactly one submission operation selector is required")
        return self


class SubmissionOperationResponse(BaseModel):
    """Authorized operation projection; nullable fields are required on the wire."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    task_id: UUID
    assignment_id: UUID
    idempotency_key: UUID
    operation_state: Literal[
        "receiving", "pre_checking", "finalization_pending", "finalized",
        "rejected", "failed", "abandoned", "cancelled",
    ]
    processing_stage: Literal[
        "receiving", "pre_checking", "finalization_pending", "evaluation_pending",
        "evaluation_running", "review_pending", "needs_revision", "accepted",
        "rejected", "failed", "abandoned", "cancelled", "operationally_stalled",
    ]
    accepted_at: AwareDatetime | None
    task_status_at_acceptance: Literal["evaluation_pending"] | None
    current_task_status: TaskStatus | None
    submission_id: UUID | None
    submission_version: Annotated[int, Field(strict=True, gt=0)] | None
    evaluation_request_id: UUID | None
    pre_submission_results: list[dict[str, object]]
    failure_code: str | None
    operationally_stalled: bool
    next_action: Literal[
        "wait", "correct_and_submit_new_key", "retry_new_key_after_terminal",
        "inspect_governed_outcome",
    ]


class SubmissionOperationReader(Protocol):
    """Read stored progress for an authenticated operation selector."""
    async def read(self, task_id: UUID, selector: SubmissionOperationSelector) -> SubmissionOperationResponse:
        """Read one authorized operation without changing submission state."""
        ...
