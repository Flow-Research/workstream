"""Fixed-service authority for one immutable source cleanup obligation."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubmissionSourceCleanupResourceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    resource_type: Literal["submission_source_cleanup"] = "submission_source_cleanup"
    resource_id: UUID
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    claim_id: UUID
    claim_generation: int = Field(gt=0)
    phase: Literal["claim", "confirm"]

    @model_validator(mode="after")
    def exact_cleanup(self):
        if self.resource_id != self.operation_id or self.operation_id.version != 7:
            raise ValueError("cleanup requires its exact operation")
        if self.claim_id.version != 7:
            raise ValueError("cleanup requires a generated claim identity")
        return self
