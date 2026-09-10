"""Exact guide metadata and source-snapshot authorization facts."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProjectGuideMutationResourceContext(BaseModel):
    """Canonical draft-guide facts for create or update."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_guide_mutation"]
    resource_id: UUID
    operation_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    target_kind: Literal["create", "update"]
    guide_exists: bool
    guide_status: str | None = None
    guide_version: str | None = None
    predecessor_snapshot_id: UUID | None = None
    predecessor_snapshot_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    operation_generation: int = Field(ge=1)
    request_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    task_examples_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    task_examples_count: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def require_guide_identity(self):
        """Reject cross-resource and partial guide lineage."""
        if self.resource_id != self.guide_id:
            raise ValueError("guide mutation resource must match guide")
        if self.guide_exists != (self.guide_status is not None and self.guide_version is not None):
            raise ValueError("guide mutation lifecycle facts are inconsistent")
        if self.guide_exists != (self.target_kind == "update"):
            raise ValueError("guide mutation operation and existence are inconsistent")
        if (self.predecessor_snapshot_id is None) != (self.predecessor_snapshot_hash is None):
            raise ValueError("guide mutation predecessor facts must be bound together")
        if self.target_kind == "create" and self.predecessor_snapshot_id is not None:
            raise ValueError("guide creation cannot bind predecessor source lineage")
        example_facts = (self.request_digest, self.task_examples_hash, self.task_examples_count)
        if self.target_kind == "create" and any(value is None for value in example_facts):
            raise ValueError("guide creation requires task example commitment")
        if self.target_kind == "update" and any(value is not None for value in example_facts):
            raise ValueError("guide update cannot replace task examples")
        return self


class ProjectGuideMutationPrepareDenialResourceContext(BaseModel):
    """Requested guide target used only to evidence a prepare-time denial."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_guide_mutation_request"]
    resource_id: UUID
    scope_project_id: UUID
    requested_guide_id: UUID | None = None
    requested_target_kind: Literal["guide_create", "guide_update", "source_snapshot_create"]

    @model_validator(mode="after")
    def require_requested_target(self):
        """Bind creates to the project and existing-guide requests to a guide id."""
        if self.requested_target_kind == "guide_create":
            if self.resource_id != self.scope_project_id or self.requested_guide_id is not None:
                raise ValueError("guide-create denial must identify only the project")
        elif self.requested_guide_id is None or self.resource_id != self.requested_guide_id:
            raise ValueError("guide mutation denial must identify the requested guide")
        return self


class ProjectGuideSourceSnapshotMutationResourceContext(BaseModel):
    """Canonical guide and source-snapshot lineage for snapshot creation."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_guide_source_snapshot_mutation"]
    resource_id: UUID
    operation_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    guide_status: str
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    predecessor_snapshot_id: UUID | None = None
    predecessor_snapshot_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    operation_generation: int = Field(ge=1)

    @model_validator(mode="after")
    def require_snapshot_identity(self):
        """Reject copied snapshot selectors and partial predecessor facts."""
        if self.resource_id != self.source_snapshot_id:
            raise ValueError("source snapshot resource must match snapshot")
        if (self.predecessor_snapshot_id is None) != (self.predecessor_snapshot_hash is None):
            raise ValueError("source snapshot predecessor facts must be bound together")
        return self
