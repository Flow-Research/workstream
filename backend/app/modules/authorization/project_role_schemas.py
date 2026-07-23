"""Strict public contracts for independent project-role mutations."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorization.schemas import (
    ProjectRole,
    ProjectRoleQualificationEvidence,
)

_STRICT = ConfigDict(extra="forbid", strict=True)


class ProjectRoleGrantIssueBody(BaseModel):
    model_config = _STRICT

    target_actor_profile_id: UUID
    role: ProjectRole
    qualification: ProjectRoleQualificationEvidence
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class ProjectRoleGrantRevokeBody(BaseModel):
    model_config = _STRICT

    reason: Annotated[str, Field(min_length=1, max_length=500)]


class ProjectRoleGrantMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    qualification_snapshot_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    role: ProjectRole
    status: Literal["active", "revoked"]
    version: Literal[1, 2]
