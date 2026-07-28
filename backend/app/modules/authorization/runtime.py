"""Strict request-scoped authorization runtime contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.schemas import AdminRole, AdminScope, ProjectRole

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)

PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION = {
    ActionId.PROJECT_SETUP_RUN_READ: "setup_run",
    ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST: "sufficiency_report_collection",
    ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ: "sufficiency_report",
    ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST: "submission_artifact_policy_collection",
    ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ: "submission_artifact_policy",
    ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ: (
        "post_submit_checker_policy_setup"
    ),
}


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


class HumanAuthorizationContext(BaseModel):
    """Bounded canonical human identity state for one request only."""

    model_config = _STRICT_FROZEN

    actor_profile_id: UUID
    actor_kind: Literal[ActorKind.HUMAN]
    actor_status: ActorStatus
    identity_link_id: UUID
    identity_link_status: IdentityLinkStatus
    request_id: UUID
    correlation_id: UUID


class ServiceAuthorizationContext(BaseModel):
    """Bounded canonical fixed-service identity state for one request only."""

    model_config = _STRICT_FROZEN

    actor_profile_id: UUID
    actor_kind: Literal[ActorKind.SERVICE]
    actor_status: ActorStatus
    identity_link_id: UUID
    identity_link_status: IdentityLinkStatus
    service_identity: ServiceIdentity
    request_id: UUID
    correlation_id: UUID


AuthorizationContext = HumanAuthorizationContext | ServiceAuthorizationContext


class PreparedAuthorityScopeKind(StrEnum):
    """Closed untrusted scope selectors accepted by prepared authorization."""

    ACTOR_SELF = "actor_self"
    SYSTEM = "system"
    PROJECT = "project"
    ARTIFACT_INTERNAL = "artifact_internal"


class PreparedAuthorityScope(BaseModel):
    """Caller-requested authority scope normalized before authority locking."""

    model_config = _STRICT_FROZEN

    kind: PreparedAuthorityScopeKind
    actor_profile_id: UUID | None = None
    project_id: UUID | None = None
    target_actor_profile_id: UUID | None = None
    role: ProjectRole | None = None
    grant_id: UUID | None = None
    artifact_resource_type: (
        Literal[
            "artifact_put_attempt",
            "artifact_verification_job",
            "artifact_pending_work",
        ]
        | None
    ) = None
    artifact_resource_id: UUID | Literal["workstream:artifact_pending_work"] | None = None

    @model_validator(mode="after")
    def validate_selector(self):
        """Require exactly the identifier owned by the selected scope kind."""
        valid = (
            (
                self.kind is PreparedAuthorityScopeKind.ACTOR_SELF
                and self.actor_profile_id is not None
                and self.project_id is None
                and self.target_actor_profile_id is None
                and self.role is None
                and self.grant_id is None
                and self.artifact_resource_type is None
                and self.artifact_resource_id is None
            )
            or (
                self.kind is PreparedAuthorityScopeKind.SYSTEM
                and self.actor_profile_id is None
                and self.project_id is None
                and self.target_actor_profile_id is None
                and self.role is None
                and self.grant_id is None
                and self.artifact_resource_type is None
                and self.artifact_resource_id is None
            )
            or (
                self.kind is PreparedAuthorityScopeKind.PROJECT
                and self.actor_profile_id is None
                and self.project_id is not None
                and not (self.target_actor_profile_id is not None and self.grant_id is not None)
                and ((self.target_actor_profile_id is None) == (self.role is None))
                and self.artifact_resource_type is None
                and self.artifact_resource_id is None
            )
            or (
                self.kind is PreparedAuthorityScopeKind.ARTIFACT_INTERNAL
                and self.actor_profile_id is None
                and self.project_id is None
                and self.target_actor_profile_id is None
                and self.role is None
                and self.grant_id is None
                and self.artifact_resource_type is not None
                and self.artifact_resource_id is not None
                and (
                    (
                        self.artifact_resource_type == "artifact_pending_work"
                        and self.artifact_resource_id == "workstream:artifact_pending_work"
                    )
                    or (
                        self.artifact_resource_type
                        in {"artifact_put_attempt", "artifact_verification_job"}
                        and isinstance(self.artifact_resource_id, UUID)
                    )
                )
            )
        )
        if not valid:
            raise ValueError("invalid prepared authority scope")
        return self


class PreparedAuthorizationInput(BaseModel):
    """Strict caller input bound privately to one prepared authorization."""

    model_config = _STRICT_FROZEN

    idempotency_key: UUID
    request_value: JsonValue


class PreparedAuthorizationHandleInvalid(Exception):
    """Generic failure for forged, stale, reused, or mismatched capabilities."""


class PreparedAuthorizationUnsupported(Exception):
    """Fail-closed preparation outcome for actions without a current lock plan."""

    def __init__(self, denial_code: AuthorizationDenialCode) -> None:
        self.denial_code = denial_code
        super().__init__("prepared authorization is unsupported")


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


class ProjectReadResourceContext(BaseModel):
    """Canonical project facts for one project identity read."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project"]
    resource_id: UUID
    scope_project_id: UUID
    project_exists: bool = True
    project_status: str | None

    @model_validator(mode="after")
    def require_exact_project(self):
        """Bind the resource and authority scope to one project."""
        if self.resource_id != self.scope_project_id:
            raise ValueError("project read scope must match resource")
        if self.project_exists != (self.project_status is not None):
            raise ValueError("project existence and status are inconsistent")
        return self


class ProjectDiagnosticReadResourceContext(BaseModel):
    """Canonical project-guide diagnostic facts for one bounded read."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_diagnostic"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str | None
    target_kind: Literal[
        "setup_run",
        "sufficiency_report_collection",
        "sufficiency_report",
        "submission_artifact_policy_collection",
        "submission_artifact_policy",
        "post_submit_checker_policy_setup",
    ]
    project_exists: bool
    guide_exists: bool
    target_exists: bool
    target_binding_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    source_snapshot_id: UUID | None = None
    source_snapshot_hash: str | None = None

    @model_validator(mode="after")
    def require_canonical_shape(self):
        """Reject fabricated child facts and partially bound snapshots."""
        if self.guide_exists and not self.project_exists:
            raise ValueError("guide cannot exist without its project")
        if self.target_exists and not self.guide_exists:
            raise ValueError("diagnostic target cannot exist without its guide")
        if self.guide_exists != (self.guide_version is not None):
            raise ValueError("guide existence and version are inconsistent")
        if (self.source_snapshot_id is None) != (self.source_snapshot_hash is None):
            raise ValueError("source snapshot id and hash must be bound together")
        if not self.target_exists and self.source_snapshot_id is not None:
            raise ValueError("missing diagnostic target cannot carry snapshot facts")
        if self.target_exists != (self.target_binding_digest is not None):
            raise ValueError("target existence and binding digest are inconsistent")
        return self


class ActorAuthorizationContextResourceContext(BaseModel):
    """Self-owned selector for authority projected onto one project."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["actor_authorization_context"]
    resource_id: UUID
    scope_project_id: UUID
    project_exists: bool = True
    project_status: str | None

    @model_validator(mode="after")
    def require_project_existence_shape(self):
        """Keep missing-project selectors free of fabricated lifecycle facts."""
        if self.project_exists != (self.project_status is not None):
            raise ValueError("project existence and status are inconsistent")
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


class ActorProfileLifecycleResourceContext(BaseModel):
    """Server-composed target for one exact profile lifecycle transition."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["actor_profile"]
    resource_id: UUID
    transition: Literal["suspend", "reactivate", "deactivate"]
    existing_idempotency_record: bool = False


class ActorIdentityLinkLifecycleResourceContext(BaseModel):
    """Server-composed target for one exact identity-link transition."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["actor_identity_link"]
    resource_id: UUID
    transition: Literal["revoke", "reactivate"]
    existing_idempotency_record: bool = False


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


class ProjectContributorCandidateCollectionResourceContext(BaseModel):
    """Canonical project facts for privacy-safe candidate discovery."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_contributor_candidate_collection"]
    resource_id: UUID
    scope_project_id: UUID
    project_status: Literal["draft", "active", "paused", "archived"]

    @model_validator(mode="after")
    def bind_project(self):
        if self.resource_id != self.scope_project_id:
            raise ValueError("invalid candidate project scope")
        return self


class ProjectRoleGrantCollectionResourceContext(BaseModel):
    """Canonical project facts for one grant-history collection."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_role_grant_collection"]
    resource_id: UUID
    scope_project_id: UUID
    project_status: Literal["draft", "active", "paused", "archived"]

    @model_validator(mode="after")
    def bind_project(self):
        if self.resource_id != self.scope_project_id:
            raise ValueError("invalid project-role grant scope")
        return self


class ProjectRoleGrantReadResourceContext(BaseModel):
    """Canonical project and grant identifiers for one history read."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_role_grant"]
    resource_id: UUID
    scope_project_id: UUID
    project_status: Literal["draft", "active", "paused", "archived"]


class ProjectRoleGrantIssueResourceContext(BaseModel):
    """Server-composed facts for issuing one exact independent role."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_role_grant"]
    resource_id: UUID
    scope_project_id: UUID
    target_actor_profile_id: UUID
    role: ProjectRole
    project_status: Literal["draft", "active", "paused", "archived"]
    target_eligible: bool
    active_exact_role_exists: bool


class ProjectRoleGrantRevokeResourceContext(BaseModel):
    """Locked exact-project grant facts used for revocation."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_role_grant"]
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    role: ProjectRole
    project_status: Literal["draft", "active", "paused", "archived"]
    status: Literal["active", "revoked"]
    version: Literal[1, 2]


class ArtifactPutAttemptResourceContext(BaseModel):
    """Exact fenced put-attempt facts composed by ART from locked rows."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["artifact_put_attempt"]
    resource_id: UUID
    operation_identity: str
    namespace_fingerprint: str
    sha256: str
    byte_count: int = Field(ge=0)
    executor_id: UUID
    execution_generation: int = Field(gt=0)


class ArtifactVerificationJobResourceContext(BaseModel):
    """Exact fenced verification-job facts composed by ART from locked rows."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["artifact_verification_job"]
    resource_id: UUID
    replica_id: UUID
    namespace_fingerprint: str
    provider_object_ref: str
    sha256: str
    byte_count: int = Field(ge=0)
    executor_id: UUID
    execution_generation: int = Field(gt=0)


class ArtifactPendingWorkResourceContext(BaseModel):
    """One database-cutoff pending-work page composed only by ART."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["artifact_pending_work"]
    resource_id: Literal["workstream:artifact_pending_work"]
    scanner_kind: Literal["put_resolution_and_verification"]
    database_cutoff_iso: str
    page_size: int = Field(gt=0, le=1000)
    put_attempt_ids: tuple[UUID, ...] = Field(max_length=1000)
    verification_job_ids: tuple[UUID, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def bind_page_size(self):
        if len(self.put_attempt_ids) + len(self.verification_job_ids) > self.page_size:
            raise ValueError("artifact pending-work page exceeds its bound")
        return self


AuthorizationResourceContext = (
    ActorSelfResourceContext
    | ProjectReadResourceContext
    | ProjectDiagnosticReadResourceContext
    | ActorAuthorizationContextResourceContext
    | ActorProfileAdminReadResourceContext
    | ActorIdentityLinkAdminReadResourceContext
    | ActorProfileLifecycleResourceContext
    | ActorIdentityLinkLifecycleResourceContext
    | SystemResourceContext
    | PermissionCatalogueResourceContext
    | AdminRoleDefinitionsResourceContext
    | AdminRoleGrantCollectionResourceContext
    | ActorAdminRoleGrantHistoryResourceContext
    | AdminRoleGrantIssueResourceContext
    | AdminRoleGrantResourceContext
    | ServiceActorProvisionResourceContext
    | ProjectContributorCandidateCollectionResourceContext
    | ProjectRoleGrantCollectionResourceContext
    | ProjectRoleGrantReadResourceContext
    | ProjectRoleGrantIssueResourceContext
    | ProjectRoleGrantRevokeResourceContext
    | ArtifactPutAttemptResourceContext
    | ArtifactVerificationJobResourceContext
    | ArtifactPendingWorkResourceContext
)


def authorization_resource_digest(resource: AuthorizationResourceContext) -> str:
    """Bind a decision to every scalar fact in its typed resource context."""
    return canonical_json_hash(
        {"resource_context": resource.model_dump(mode="json", exclude_none=True)}
    )


def authorization_resource_selector_id(resource_type: str, raw_id: str) -> UUID:
    """Return a bounded UUID selector for missing-resource decision evidence."""
    try:
        return UUID(raw_id)
    except (TypeError, ValueError, AttributeError):
        return uuid5(NAMESPACE_URL, f"workstream:{resource_type}-selector:{raw_id}")


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
    PROJECT_ROLE_GRANT = "project_role_grant"
    FIXED_SERVICE = "fixed_service"


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
        "actor_authorization_context",
        "project",
        "project_diagnostic",
        "actor_identity_link",
        "system",
        "permission_catalogue",
        "admin_role_definitions",
        "admin_role_grant_collection",
        "actor_admin_role_grant_history",
        "admin_role_grant_issue",
        "admin_role_grant",
        "service_actor_provisioning",
        "project_contributor_candidate_collection",
        "project_role_grant_collection",
        "project_role_grant",
        "artifact_put_attempt",
        "artifact_verification_job",
        "artifact_pending_work",
    ]
    resource_id: (
        UUID
        | ServiceIdentity
        | Literal[
            "workstream:system",
            "workstream:permission_catalogue",
            "workstream:admin_role_definitions",
            "workstream:admin_role_grants",
            "workstream:artifact_pending_work",
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
        elif self.matched_authority_kind is MatchedAuthorityKind.PROJECT_ROLE_GRANT:
            if self.matched_grant_id is None or self.matched_scope_project_id is None:
                raise ValueError("project-role decisions require matched grant and scope")
        elif self.matched_authority_kind is MatchedAuthorityKind.FIXED_SERVICE:
            if self.matched_grant_id is not None or self.matched_scope_project_id is not None:
                raise ValueError("fixed-service decisions cannot carry grant scope")
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
