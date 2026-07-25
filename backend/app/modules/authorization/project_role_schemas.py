"""Strict public contracts for independent project-role mutations."""

from typing import Annotated, Literal
import unicodedata
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.authorization.schemas import (
    ProjectRole,
    ProjectRoleQualificationEvidence,
)

_STRICT = ConfigDict(extra="forbid")


def _reason(value: str) -> str:
    """Validate one canonical project-role mutation reason."""

    if (
        value != value.strip()
        or not 1 <= len(value.encode("utf-8")) <= 500
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        raise ValueError("invalid project-role mutation reason")
    return value


Reason = Annotated[str, Field(min_length=1), AfterValidator(_reason)]


class ProjectRoleGrantIssueBody(BaseModel):
    """Request body for one project-role grant issuance."""

    model_config = _STRICT

    target_actor_profile_id: UUID
    role: ProjectRole
    qualification: ProjectRoleQualificationEvidence
    reason: Reason


class ProjectRoleGrantRevokeBody(BaseModel):
    """Request body for one project-role grant revocation."""

    model_config = _STRICT

    reason: Reason


class ProjectRoleGrantMutationResponse(BaseModel):
    """Stable project-role grant state returned after a mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    qualification_snapshot_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    role: ProjectRole
    status: Literal["active", "revoked"]
    version: Literal[1, 2]
