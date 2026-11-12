"""Exact accepted-finalization recovery values; none confer authority."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FINALIZATION_RECOVERY_EVENT = "SubmissionFinalizationRecoveryRequested"
FINALIZATION_RECOVERY_SOURCES = (("SubmissionFinalizationRequested", 1),)


class RecoveryValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True,
                              revalidate_instances="always", hide_input_in_errors=True)


class SubmissionRecoveryCommand(RecoveryValue):
    operation_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    request_id: UUID
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def bounded_reason(cls, value):
        if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("invalid finalization recovery reason")
        return value


class SubmissionRecoverySource(RecoveryValue):
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    original_event_id: UUID
    original_claim_generation: int = Field(gt=0)
    original_payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    acceptance_receipt_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class SubmissionRecoveryAuthority(RecoveryValue):
    decision_id: UUID
    identity_link_id: UUID
    resource_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class SubmissionRecoveryPayload(RecoveryValue):
    command: SubmissionRecoveryCommand
    source: SubmissionRecoverySource
    authority: SubmissionRecoveryAuthority

    @model_validator(mode="after")
    def exact_source(self):
        if (self.command.operation_id != self.source.operation_id
                or self.command.project_id != self.source.project_id):
            raise ValueError("finalization recovery source differs")
        return self


class SubmissionRecoveryResult(RecoveryValue):
    operation_id: UUID
    recovery_event_id: UUID
    state: Literal["pending", "active", "acknowledged", "unknown", "held"]


class SubmissionRecoveryUnavailable(RuntimeError):
    """Absent, denied, conflicting or unqualified recovery; no provider detail."""


class SubmissionRecoveryAuthorizationPort(Protocol):
    async def authorize(self, command: SubmissionRecoveryCommand,
                        source: SubmissionRecoverySource) -> SubmissionRecoveryAuthority: ...
    async def validate_cause(self, payload: SubmissionRecoveryPayload) -> None: ...
