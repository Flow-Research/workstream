"""Existing Operator gate-repair authority narrowed to accepted finalization."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.artifacts.api.submission_recovery import SubmissionRecoveryCommand, SubmissionRecoverySource


class SubmissionRecoveryResourceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    resource_type: Literal["submission_operation"] = "submission_operation"
    resource_id: UUID
    scope_project_id: UUID
    identity_link_id: UUID
    command: SubmissionRecoveryCommand
    source: SubmissionRecoverySource

    @model_validator(mode="after")
    def exact_source(self):
        if (self.resource_id != self.command.operation_id or self.resource_id != self.source.operation_id
                or self.scope_project_id != self.command.project_id
                or self.scope_project_id != self.source.project_id):
            raise ValueError("finalization recovery authority source differs")
        return self
