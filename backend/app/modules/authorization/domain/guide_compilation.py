"""Internal resource contexts for unified Project Guide compilation authority."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.api import (
    project_guide_compilation_request_authority_digest,
)
from app.modules.authorization.catalogue import ActionId

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProjectGuideCompilationRequestResourceContext(BaseModel):
    """Canonical Project Manager compilation request/recovery authority facts."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_guide_compilation_request"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    setup_run_id: UUID
    setup_generation: int = Field(ge=1)
    operation_id: UUID
    request_id: UUID
    idempotency_key: UUID
    request_facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_operation_selector(self):
        if self.resource_id != self.operation_id:
            raise ValueError("compilation request resource must match operation")
        return self


class ProjectGuideCompilationExecuteResourceContext(BaseModel):
    """Canonical fixed-service compilation preflight or persistence facts."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_guide_compilation_attempt"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    setup_run_id: UUID
    setup_generation: int = Field(ge=1)
    attempt_id: UUID
    provider_idempotency_key: UUID
    phase: Literal["preflight", "persist"]
    request_facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    result_resource_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_attempt_selector_and_phase(self):
        if self.resource_id != self.attempt_id:
            raise ValueError("compilation execute resource must match attempt")
        if (self.phase == "persist") != (self.result_resource_digest is not None):
            raise ValueError("compilation persist phase requires exact result digest")
        return self


CompilationResourceContext = (
    ProjectGuideCompilationRequestResourceContext | ProjectGuideCompilationExecuteResourceContext
)
COMPILATION_RESOURCE_BY_ACTION = {
    ActionId.PROJECT_GUIDE_COMPILATION_REQUEST: ProjectGuideCompilationRequestResourceContext,
    ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE: ProjectGuideCompilationExecuteResourceContext,
}


def persisted_result_digest(resource: object) -> str | None:
    """Return the public exact-result digest only for final persistence."""
    if (
        isinstance(resource, ProjectGuideCompilationExecuteResourceContext)
        and resource.phase == "persist"
    ):
        return resource.result_resource_digest
    return None


def request_authority_digest(
    resource: object,
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
    grant_id: UUID | None,
) -> str | None:
    """Return the grant-bound digest for one allowed human request."""
    if not isinstance(resource, ProjectGuideCompilationRequestResourceContext) or grant_id is None:
        return None
    return project_guide_compilation_request_authority_digest(
        actor_profile_id=actor_profile_id,
        identity_link_id=identity_link_id,
        grant_id=grant_id,
        project_id=resource.scope_project_id,
        operation_id=resource.operation_id,
        request_facts_digest=resource.request_facts_digest,
    )
