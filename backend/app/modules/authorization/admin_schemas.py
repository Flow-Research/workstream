"""Strict public schemas for administrative authorization surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.schemas import AdminRole, AdminScope

_STRICT = ConfigDict(extra="forbid")


def _bounded_reason(value: str) -> str:
    if not 1 <= len(value.encode("utf-8")) <= 500:
        raise ValueError("reason must contain 1 to 500 UTF-8 bytes")
    return value


Reason = Annotated[str, Field(min_length=1), AfterValidator(_bounded_reason)]


class PermissionDefinitionResponse(BaseModel):
    """One registered permission identifier."""

    model_config = _STRICT
    permission_id: PermissionId


class PermissionDefinitionsResponse(BaseModel):
    """Complete immutable permission catalogue."""

    model_config = _STRICT
    items: tuple[PermissionDefinitionResponse, ...]
    total: Literal[74]


class AdminRoleDefinitionResponse(BaseModel):
    """One exact administrative role definition."""

    model_config = _STRICT
    role: AdminRole
    allowed_scopes: tuple[AdminScope, ...]
    permission_ids: tuple[PermissionId, ...]


class AdminRoleDefinitionsResponse(BaseModel):
    """Complete immutable administrative role matrix."""

    model_config = _STRICT
    items: tuple[AdminRoleDefinitionResponse, ...]
    total: Literal[5]


class AdminRoleGrantIssueBody(BaseModel):
    """Request body for one administrative grant issuance."""

    model_config = _STRICT
    target_actor_profile_id: UUID
    role: AdminRole
    scope_type: AdminScope
    scope_project_id: UUID | None = None
    reason: Reason


class AdminRoleGrantRevokeBody(BaseModel):
    """Request body for one administrative grant revocation."""

    model_config = _STRICT
    reason: Reason


class AdminRoleGrantResponse(BaseModel):
    """Privacy-bounded immutable administrative grant history."""

    model_config = _STRICT
    grant_id: UUID
    target_actor_profile_id: UUID
    role: AdminRole
    scope_type: AdminScope
    scope_project_id: UUID | None
    status: Literal["active", "revoked"]
    version: Literal[1, 2]
    granted_by_ref_kind: Literal["actor_profile", "system_principal"]
    granted_by_ref: str
    granted_by_admin_role_grant_id: UUID | None
    grant_reason: str
    granted_at: datetime
    revoked_by_actor_profile_id: UUID | None
    revoked_by_admin_role_grant_id: UUID | None
    revoked_reason: str | None
    revoked_at: datetime | None


class AdminRoleGrantCollectionResponse(BaseModel):
    """Scope-filtered grant collection page."""

    model_config = _STRICT
    items: tuple[AdminRoleGrantResponse, ...]
    total: Annotated[int, Field(ge=0)]
    next_cursor: str | None


class AuthorityMutationResponse(BaseModel):
    """Stable bounded response reference for an authority mutation."""

    model_config = _STRICT
    resource_type: Literal["admin_role_grant"]
    resource_id: UUID
    version: Literal[1, 2]
    http_status: Literal[200, 201]
