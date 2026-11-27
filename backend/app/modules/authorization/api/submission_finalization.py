"""Fixed-service continuation of immutable human submission acceptance."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubmissionFinalizationResourceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    resource_type: Literal["submission_finalization"] = "submission_finalization"
    resource_id: UUID
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    acceptance_decision_id: UUID
    accepted_context_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    acceptance_receipt_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    continuation_lease_id: UUID
    continuation_generation: int = Field(gt=0)
    phase: Literal["claim", "commit"]
    submission_id: UUID | None
    submission_version: int | None = Field(ge=1)

    @model_validator(mode="after")
    def exact_continuation(self):
        if self.resource_id != self.operation_id or self.operation_id.version != 7:
            raise ValueError("finalization requires its exact operation")
        if self.continuation_lease_id.version != 7:
            raise ValueError("finalization requires a generated lease identity")
        if self.phase == "claim":
            if self.submission_id is not None or self.submission_version is not None:
                raise ValueError("claim cannot authorize a Submission")
        elif (self.submission_id is None or self.submission_id.version != 7
              or self.submission_version is None):
            raise ValueError("commit requires the exact Submission identity")
        return self
