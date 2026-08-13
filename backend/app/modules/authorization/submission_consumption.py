"""Exact AUTH resource contracts for hidden Submission consumption."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionId

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class SubmissionCreationResourceContext(BaseModel):
    """Exact TASK-owned facts authorized for one immutable Submission."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["submission_creation"]
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    task_id: UUID
    assignment_id: UUID
    admission_id: UUID
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None = Field(default=None, ge=1)
    submission_id: UUID
    submission_version: int = Field(ge=1)
    task_status: str = Field(min_length=1)
    submission_kind: Literal["initial", "revision"]
    guide_version: str = Field(min_length=1)
    source_snapshot_id: UUID
    source_snapshot_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_id: UUID
    effective_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bind_submission_and_predecessor(self):
        """Require one exact Submission and a complete predecessor pair."""
        if self.resource_id != self.submission_id:
            raise ValueError("submission resource must match submission")
        if (self.predecessor_submission_id is None) != (
            self.predecessor_submission_version is None
        ):
            raise ValueError("submission predecessor identity is incomplete")
        return self


class SubmissionBindingResourceContext(BaseModel):
    """Exact ART lineage authorized for one fixed-service Submission binding."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["submission_binding"]
    resource_id: UUID
    admission_id: UUID
    evidence_set_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None = Field(default=None, ge=1)
    submission_id: UUID
    submission_version: int = Field(ge=1)
    guide_id: UUID
    guide_version: str = Field(min_length=1)
    source_snapshot_id: UUID
    source_snapshot_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_id: UUID
    effective_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_policy_context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    logical_role: Literal["submission_bundle_original"]

    @model_validator(mode="after")
    def bind_admission(self):
        """Require one exact admission and a complete predecessor pair."""
        if self.resource_id != self.admission_id:
            raise ValueError("submission binding resource must match admission")
        if (self.predecessor_submission_id is None) != (
            self.predecessor_submission_version is None
        ):
            raise ValueError("submission binding predecessor is incomplete")
        return self


RESOURCE_BY_ACTION = {
    ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE: SubmissionBindingResourceContext,
    ActionId.SUBMISSION_CREATE: SubmissionCreationResourceContext,
}


def parse_consumption_binding(action_id: ActionId, value, invalid):
    """Parse exact submission facts into their canonical context and digest."""
    resource_type = RESOURCE_BY_ACTION.get(action_id)
    if resource_type is None:
        return None
    try:
        resource = resource_type.model_validate(value)
    except (TypeError, ValueError) as exc:
        raise invalid("invalid prepared authorization handle") from exc
    return resource
