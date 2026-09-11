"""Privacy-bounded audit classification shared by AUTH capabilities."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId, PermissionId

CONTEXT_DIGEST_RESOURCE_TYPES = (
    "task_authority",
    "artifact_put_attempt",
    "artifact_verification_job",
    "artifact_pending_work",
    "guide_source_binding",
    "guide_source_read",
    "pre_submit_checker_input",
    "project_diagnostic",
    "project_policy_read",
    "project_active_guide_read",
    "project_guide_compilation_request",
    "project_guide_compilation_attempt",
    "project_guide_sufficiency_projection",
    "project_submission_artifact_policy_projection",
    "project_guide_setup_finalization",
    "contribution_policy",
)


AuthorizationDecisionResourceType = Literal[
    "task_authority",
    "actor_profile",
    "actor_authorization_context",
    "project",
    "project_diagnostic",
    "project_policy_read",
    "project_active_guide_read",
    "project_create",
    "project_guide_mutation",
    "project_guide_source_snapshot_mutation",
    "project_guide_mutation_request",
    "project_review_policy_mutation",
    "project_revision_policy_mutation",
    "project_policy_mutation_request",
    "project_guide_sufficiency_mutation",
    "project_submission_artifact_policy_mutation",
    "project_guide_compilation_request",
    "project_guide_compilation_attempt",
    "project_guide_setup_finalization",
    "project_setup_run_mutation",
    "project_guide_sufficiency_projection",
    "project_submission_artifact_policy_projection",
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
    "guide_source_binding",
    "guide_source_read",
    "pre_submit_checker_input",
    "submission_bundle_preparation_preflight",
    "submission_bundle_preparation",
    "submission_creation",
    "submission_binding",
    "compensation_adapter_binding",
    "contribution_policy",
]


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
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    decision_id: UUID
    action_id: ActionId | None
    permission_id: PermissionId | None
    allowed: bool
    denial_code: AuthorizationDenialCode | None
    resource_type: AuthorizationDecisionResourceType
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
            if (
                self.action_id
                not in {
                    ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
                    ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
                    ActionId.PROJECT_ACTIVE_GUIDE_READ,
                }
                or self.matched_grant_id is None
                or self.matched_scope_project_id is None
            ):
                raise ValueError("denied decision carries invalid matched-grant provenance")
        return self


class AuthorizationDenied(Exception):
    def __init__(self, decision: AuthorizationDecision) -> None:
        if decision.allowed or decision.denial_code is None:
            raise TypeError("authorization denial requires a denied decision")
        self.decision = decision
        super().__init__("Authorization denied")

    @property
    def public_code(self) -> str:
        denial_code = self.decision.denial_code
        if denial_code is None:
            raise RuntimeError("authorization denial lost its denial code")
        if denial_code in {
            AuthorizationDenialCode.UNKNOWN_ACTION,
            AuthorizationDenialCode.ACTION_UNAVAILABLE,
        }:
            return AuthorizationDenialCode.PERMISSION_NOT_GRANTED.value
        return denial_code.value
class AuthorizationEvidenceUnavailable(RuntimeError):
    pass
