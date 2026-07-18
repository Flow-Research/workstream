"""Strict request-scoped authorization runtime contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.schemas import AdminRole, AdminScope

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class ActorKind(StrEnum):
    """Canonical actor kinds visible to authorization."""

    HUMAN = "human"
    SERVICE = "service"


class ActorStatus(StrEnum):
    """Canonical actor lifecycle states visible to authorization."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class IdentityLinkStatus(StrEnum):
    """Canonical identity-link lifecycle states visible to authorization."""

    ACTIVE = "active"
    REVOKED = "revoked"


class AuthorizationContext(BaseModel):
    """Bounded canonical identity state for one request only."""

    model_config = _STRICT_FROZEN

    actor_profile_id: UUID
    actor_kind: ActorKind
    actor_status: ActorStatus
    identity_link_id: UUID
    identity_link_status: IdentityLinkStatus
    request_id: UUID
    correlation_id: UUID


class ActorSelfResourceContext(BaseModel):
    """Server-composed facts for the caller's own actor profile."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["actor_profile"]
    resource_id: UUID
    requested_fields: tuple[Literal["display_name", "contact_email"], ...]

    @model_validator(mode="after")
    def require_unique_fields(self):
        """Reject ambiguous duplicate update-field facts."""
        if len(set(self.requested_fields)) != len(self.requested_fields):
            raise ValueError("requested fields must be unique")
        return self


class ActorProfileAdminReadResourceContext(BaseModel):
    """Server-composed selector for one administrative actor-profile read."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["actor_profile"]
    resource_id: UUID
    read_kind: Literal["profile"]


class ActorIdentityLinkAdminReadResourceContext(BaseModel):
    """Server-composed selector for one actor's administrative link read."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["actor_profile"]
    resource_id: UUID
    read_kind: Literal["identity_link"]


class SystemResourceContext(BaseModel):
    """Non-authoritative placeholder for later fixed system actions."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["system"]
    resource_id: Literal["workstream:system"]


class PermissionCatalogueResourceContext(BaseModel):
    """Fixed registered-permission definition target."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["permission_catalogue"]
    resource_id: Literal["workstream:permission_catalogue"]


class AdminRoleDefinitionsResourceContext(BaseModel):
    """Fixed administrative-role definition target."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["admin_role_definitions"]
    resource_id: Literal["workstream:admin_role_definitions"]


class AdminRoleGrantCollectionResourceContext(BaseModel):
    """Canonical system or exact-project grant collection selector."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["admin_role_grant_collection"]
    resource_id: UUID | Literal["workstream:admin_role_grants"]
    scope_type: AdminScope
    scope_project_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        """Bind the collection identifier to its exact scope."""
        if self.scope_type is AdminScope.SYSTEM:
            valid = (
                self.scope_project_id is None and self.resource_id == "workstream:admin_role_grants"
            )
        else:
            valid = self.scope_project_id is not None and self.resource_id == self.scope_project_id
        if not valid:
            raise ValueError("invalid grant collection scope")
        return self


class ActorAdminRoleGrantHistoryResourceContext(BaseModel):
    """Canonical actor history plus required scope selector."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["actor_admin_role_grant_history"]
    resource_id: UUID
    scope_type: AdminScope
    scope_project_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        """Require one structurally complete scope selector."""
        if (self.scope_type is AdminScope.PROJECT) != (self.scope_project_id is not None):
            raise ValueError("invalid actor grant history scope")
        return self


class AdminRoleGrantIssueResourceContext(BaseModel):
    """Server-composed target and scope facts for grant issuance."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["admin_role_grant_issue"]
    resource_id: UUID
    role: AdminRole
    scope_type: AdminScope
    scope_project_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        """Require role-compatible system or exact-project scope."""
        system_only = self.role in {AdminRole.ACCESS_ADMINISTRATOR, AdminRole.OPERATOR}
        if system_only and self.scope_type is not AdminScope.SYSTEM:
            raise ValueError("invalid role scope")
        if (self.scope_type is AdminScope.PROJECT) != (self.scope_project_id is not None):
            raise ValueError("invalid role scope")
        return self


class AdminRoleGrantResourceContext(BaseModel):
    """Loaded administrative grant selector for revocation."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["admin_role_grant"]
    resource_id: UUID
    existing_idempotency_record: bool = False


class ServiceActorProvisionResourceContext(BaseModel):
    """Fixed local identity targeted by controlled service provisioning."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["service_actor_provisioning"]
    resource_id: ServiceIdentity


AuthorizationResourceContext = (
    ActorSelfResourceContext
    | ActorProfileAdminReadResourceContext
    | ActorIdentityLinkAdminReadResourceContext
    | SystemResourceContext
    | PermissionCatalogueResourceContext
    | AdminRoleDefinitionsResourceContext
    | AdminRoleGrantCollectionResourceContext
    | ActorAdminRoleGrantHistoryResourceContext
    | AdminRoleGrantIssueResourceContext
    | AdminRoleGrantResourceContext
    | ServiceActorProvisionResourceContext
)


def authorization_resource_digest(resource: AuthorizationResourceContext) -> str:
    """Bind a decision to every scalar fact in its typed resource context."""
    return canonical_json_hash(
        {"resource_context": resource.model_dump(mode="json", exclude_none=True)}
    )


class AuthorizationDenialCode(StrEnum):
    """Closed internal authorization outcomes."""

    UNKNOWN_ACTION = "unknown_action"
    ACTION_UNAVAILABLE = "action_unavailable"
    IDENTITY_LINK_REVOKED = "identity_link_revoked"
    ACTOR_DEACTIVATED = "actor_deactivated"
    ACTOR_SUSPENDED = "actor_suspended"
    RESOURCE_GUARD_DENIED = "resource_guard_denied"
    PERMISSION_NOT_GRANTED = "permission_not_granted"
    SCOPE_NOT_AUTHORIZED = "scope_not_authorized"
    SELF_GRANT_FORBIDDEN = "self_grant_forbidden"
    SELF_ROLE_REVOKE_FORBIDDEN = "self_role_revoke_forbidden"
    ACTOR_NOT_FOUND = "actor_not_found"
    GRANT_NOT_FOUND = "grant_not_found"
    RESOURCE_NOT_FOUND = "resource_not_found"


class MatchedAuthorityKind(StrEnum):
    """Privacy-bounded authority source classifications."""

    ACTOR_SELF = "actor_self"
    ADMIN_ROLE_GRANT = "admin_role_grant"


class AuthorizationDecision(BaseModel):
    """Frozen decision safe for feature code, evidence, and error mapping."""

    model_config = _STRICT_FROZEN

    decision_id: UUID
    action_id: ActionId | None
    permission_id: PermissionId | None
    allowed: bool
    denial_code: AuthorizationDenialCode | None
    resource_type: Literal[
        "actor_profile",
        "system",
        "permission_catalogue",
        "admin_role_definitions",
        "admin_role_grant_collection",
        "actor_admin_role_grant_history",
        "admin_role_grant_issue",
        "admin_role_grant",
        "service_actor_provisioning",
    ]
    resource_id: (
        UUID
        | ServiceIdentity
        | Literal[
            "workstream:system",
            "workstream:permission_catalogue",
            "workstream:admin_role_definitions",
            "workstream:admin_role_grants",
        ]
    )
    resource_context_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    matched_authority_kind: MatchedAuthorityKind | None
    matched_grant_id: UUID | None = None
    matched_scope_project_id: UUID | None = None
    revalidated: bool
    request_id: UUID
    correlation_id: UUID

    @model_validator(mode="after")
    def validate_outcome(self):
        """Keep allow and deny fields mutually coherent."""
        if self.allowed != (self.denial_code is None):
            raise ValueError("authorization outcome is inconsistent")
        if self.allowed != (self.matched_authority_kind is not None):
            raise ValueError("authorization authority match is inconsistent")
        if (self.action_id is None) != (self.permission_id is None):
            raise ValueError("action and permission must be present together")
        if self.allowed and self.action_id is None:
            raise ValueError("allowed decisions require action and permission")
        if self.matched_authority_kind is MatchedAuthorityKind.ACTOR_SELF:
            if self.matched_grant_id is not None or self.matched_scope_project_id is not None:
                raise ValueError("actor-self decisions cannot carry grant scope")
        elif self.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT:
            if self.matched_grant_id is None:
                raise ValueError("grant decisions require matched grant")
        elif self.matched_grant_id is not None or self.matched_scope_project_id is not None:
            raise ValueError("denied decisions cannot carry authority matches")
        return self


class AuthorizationDenied(Exception):
    """Fail-closed control flow carrying only one bounded decision."""

    def __init__(self, decision: AuthorizationDecision) -> None:
        if decision.allowed or decision.denial_code is None:
            raise TypeError("authorization denial requires a denied decision")
        self.decision = decision
        super().__init__("Authorization denied")

    @property
    def public_code(self) -> str:
        """Map internal catalogue outcomes to the stable public denial."""
        if self.decision.denial_code in {
            AuthorizationDenialCode.UNKNOWN_ACTION,
            AuthorizationDenialCode.ACTION_UNAVAILABLE,
        }:
            return AuthorizationDenialCode.PERMISSION_NOT_GRANTED.value
        return self.decision.denial_code.value


class AuthorizationEvidenceUnavailable(RuntimeError):
    """Authorization evidence could not be persisted safely."""
