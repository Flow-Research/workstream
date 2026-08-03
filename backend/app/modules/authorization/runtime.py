"""Strict request-scoped authorization runtime contracts."""

from __future__ import annotations

from types import MappingProxyType
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
    ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ: ("post_submit_checker_policy_setup"),
}

PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION = {
    ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ: "effective_policy",
    ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ: "pre_submit_checker_policy",
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
            "guide_source_binding",
            "guide_source_read",
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
                        in {
                            "artifact_put_attempt",
                            "artifact_verification_job",
                            "guide_source_binding",
                            "guide_source_read",
                        }
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
    source_snapshot_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

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
        if (
            self.target_exists
            and not self.target_kind.endswith("_collection")
            and self.source_snapshot_id is None
        ):
            raise ValueError("existing diagnostic target requires snapshot facts")
        if self.target_exists != (self.target_binding_digest is not None):
            raise ValueError("target existence and binding digest are inconsistent")
        return self


class ProjectPolicyReadResourceContext(BaseModel):
    """Canonical current policy-chain facts for one guide-bound read."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_policy_read"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str | None
    guide_status: str | None
    target_kind: Literal["effective_policy", "pre_submit_checker_policy"]
    project_exists: bool
    project_status: str | None
    guide_exists: bool
    target_exists: bool
    source_snapshot_id: UUID | None = None
    source_snapshot_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_id: UUID | None = None
    effective_policy_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_status: str | None = None
    checker_policy_id: UUID | None = None
    checker_policy_status: str | None = None
    checker_bundle_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    target_binding_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_current_policy_shape(self):
        """Reject partial, stale, or action-incompatible policy bindings."""
        if self.guide_exists and not self.project_exists:
            raise ValueError("guide cannot exist without its project")
        if self.guide_exists != (self.guide_version is not None and self.guide_status is not None):
            raise ValueError("guide existence and lifecycle facts are inconsistent")
        if self.project_exists != (self.project_status is not None):
            raise ValueError("project existence and lifecycle facts are inconsistent")
        bound = (
            self.project_status == "active"
            and self.guide_status == "active"
            and self.source_snapshot_id is not None
            and self.source_snapshot_hash is not None
            and self.effective_policy_id is not None
            and self.effective_policy_hash is not None
            and self.effective_policy_status == "approved"
            and self.target_binding_digest is not None
        )
        if self.target_exists != bound:
            raise ValueError("policy target existence and binding facts are inconsistent")
        checker_bound = (
            self.checker_policy_id is not None
            and self.checker_policy_status == "compiled"
            and self.checker_bundle_hash is not None
        )
        if self.target_kind == "pre_submit_checker_policy":
            if self.target_exists != checker_bound:
                raise ValueError("checker target existence and binding facts are inconsistent")
        elif any(
            value is not None
            for value in (
                self.checker_policy_id,
                self.checker_policy_status,
                self.checker_bundle_hash,
            )
        ):
            raise ValueError("effective policy target cannot carry checker facts")
        return self


class ProjectActiveGuideReadResourceContext(BaseModel):
    """Canonical active-guide and non-compensation policy bundle facts."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_active_guide_read"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str | None
    guide_status: str | None
    project_exists: bool
    project_status: str | None
    guide_exists: bool
    target_exists: bool
    source_snapshot_id: UUID | None = None
    source_snapshot_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    sufficiency_report_id: UUID | None = None
    sufficiency_report_status: str | None = None
    submission_artifact_policy_id: UUID | None = None
    submission_artifact_policy_hash: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    submission_artifact_policy_status: str | None = None
    effective_policy_id: UUID | None = None
    effective_policy_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_status: str | None = None
    pre_submit_checker_policy_id: UUID | None = None
    pre_submit_checker_bundle_hash: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    pre_submit_checker_policy_status: str | None = None
    post_submit_checker_policy_id: UUID | None = None
    post_submit_checker_policy_status: str | None = None
    review_policy_id: UUID | None = None
    revision_policy_id: UUID | None = None
    policy_binding_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_active_bundle_shape(self):
        """Reject missing or partially bound active-guide facts."""
        if self.resource_id != self.guide_id:
            raise ValueError("active-guide resource must match guide")
        if self.guide_exists and not self.project_exists:
            raise ValueError("active guide cannot exist without its project")
        if self.guide_exists != (self.guide_version is not None and self.guide_status is not None):
            raise ValueError("active-guide lifecycle facts are inconsistent")
        if self.project_exists != (self.project_status is not None):
            raise ValueError("project existence and lifecycle facts are inconsistent")
        bound = (
            self.project_status == "active"
            and self.guide_status == "active"
            and self.source_snapshot_id is not None
            and self.source_snapshot_hash is not None
            and self.sufficiency_report_id is not None
            and self.sufficiency_report_status in {"passed", "passed_with_warnings"}
            and self.submission_artifact_policy_id is not None
            and self.submission_artifact_policy_hash is not None
            and self.submission_artifact_policy_status == "approved"
            and self.effective_policy_id is not None
            and self.effective_policy_hash is not None
            and self.effective_policy_status == "approved"
            and self.pre_submit_checker_policy_id is not None
            and self.pre_submit_checker_bundle_hash is not None
            and self.pre_submit_checker_policy_status == "compiled"
            and self.post_submit_checker_policy_id is not None
            and self.post_submit_checker_policy_status == "approved"
            and self.review_policy_id is not None
            and self.revision_policy_id is not None
            and self.policy_binding_digest is not None
        )
        if self.target_exists != bound:
            raise ValueError("active-guide existence and bundle facts are inconsistent")
        if not self.target_exists and any(
            value is not None
            for value in (
                self.sufficiency_report_id,
                self.sufficiency_report_status,
                self.submission_artifact_policy_id,
                self.submission_artifact_policy_hash,
                self.submission_artifact_policy_status,
                self.effective_policy_id,
                self.effective_policy_hash,
                self.effective_policy_status,
                self.pre_submit_checker_policy_id,
                self.pre_submit_checker_bundle_hash,
                self.pre_submit_checker_policy_status,
                self.post_submit_checker_policy_id,
                self.post_submit_checker_policy_status,
                self.review_policy_id,
                self.revision_policy_id,
            )
        ):
            raise ValueError("missing active-guide target cannot carry policy facts")
        return self


class ProjectCreateResourceContext(BaseModel):
    """Server-owned facts for one system-scoped project creation."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_create"]
    resource_id: UUID
    requested_project_id: UUID
    operation_generation: int = Field(ge=1)

    @model_validator(mode="after")
    def require_operation_identity(self):
        """Keep the idempotent operation distinct from the future project."""
        if self.resource_id == self.requested_project_id:
            raise ValueError("project creation operation must not impersonate project identity")
        return self


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


class ProjectReviewPolicyMutationResourceContext(BaseModel):
    """Canonical guide-bound review-policy mutation facts."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_review_policy_mutation"]
    resource_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    guide_status: Literal["draft"]
    review_policy_id: UUID
    policy_generation: int = Field(ge=1)
    policy_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    predecessor_policy_id: UUID | None = None
    predecessor_policy_generation: int | None = Field(default=None, ge=1)
    current_policy_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_review_policy_identity(self):
        """Bind the resource selector to the review policy only."""
        if self.resource_id != self.review_policy_id:
            raise ValueError("review policy resource must match policy")
        if (
            len(
                {
                    self.predecessor_policy_id is None,
                    self.predecessor_policy_generation is None,
                    self.current_policy_digest is None,
                }
            )
            != 1
        ):
            raise ValueError("review policy predecessor facts must be bound together")
        if self.policy_generation == 1 and self.predecessor_policy_id is not None:
            raise ValueError("first review policy cannot have a predecessor")
        if self.policy_generation > 1 and self.predecessor_policy_id is None:
            raise ValueError("replacement review policy requires a predecessor")
        if (
            self.predecessor_policy_generation is not None
            and self.policy_generation != self.predecessor_policy_generation + 1
        ):
            raise ValueError("review policy successor generation must be exact")
        return self


class ProjectRevisionPolicyMutationResourceContext(BaseModel):
    """Canonical guide-bound revision-policy mutation facts."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_revision_policy_mutation"]
    resource_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    guide_status: Literal["draft"]
    revision_policy_id: UUID
    policy_generation: int = Field(ge=1)
    policy_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    predecessor_policy_id: UUID | None = None
    predecessor_policy_generation: int | None = Field(default=None, ge=1)
    current_policy_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_revision_policy_identity(self):
        """Bind the resource selector to the revision policy only."""
        if self.resource_id != self.revision_policy_id:
            raise ValueError("revision policy resource must match policy")
        if (
            len(
                {
                    self.predecessor_policy_id is None,
                    self.predecessor_policy_generation is None,
                    self.current_policy_digest is None,
                }
            )
            != 1
        ):
            raise ValueError("revision policy predecessor facts must be bound together")
        if self.policy_generation == 1 and self.predecessor_policy_id is not None:
            raise ValueError("first revision policy cannot have a predecessor")
        if self.policy_generation > 1 and self.predecessor_policy_id is None:
            raise ValueError("replacement revision policy requires a predecessor")
        if (
            self.predecessor_policy_generation is not None
            and self.policy_generation != self.predecessor_policy_generation + 1
        ):
            raise ValueError("revision policy successor generation must be exact")
        return self


class ProjectPolicyMutationPrepareDenialResourceContext(BaseModel):
    """Privacy-bounded requested selectors for policy PREP denial evidence."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_policy_mutation_request"]
    resource_id: UUID
    scope_project_id: UUID
    requested_guide_id: UUID
    requested_policy_kind: Literal["review", "revision"]
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_requested_guide(self):
        """Require denial evidence to identify its exact requested guide."""
        if self.resource_id != self.requested_guide_id:
            raise ValueError("policy mutation denial must identify the requested guide")
        return self


class ProjectSetupServiceCustodyContext(BaseModel):
    """Locked setup-run custody required by one fixed-service product effect."""

    model_config = _STRICT_FROZEN

    setup_run_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    setup_generation: int = Field(ge=1)
    expected_step: Literal[
        "guide_sufficiency",
        "submission_artifact_policy",
        "post_submit_policy",
    ]
    task_id: UUID
    correlation_id: UUID
    stale_output_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def _require_setup_custody(
    custody: ProjectSetupServiceCustodyContext,
    *,
    label: str,
    expected_step: str,
    setup_generation: int,
    stale_output_digest: str | None,
    scope_project_id: UUID,
    guide_id: UUID,
    source_snapshot_id: UUID,
) -> None:
    """Reject setup-service custody that does not match the protected lineage."""
    if custody.expected_step != expected_step:
        raise ValueError(f"{label} setup-service step is inconsistent")
    if custody.setup_generation != setup_generation:
        raise ValueError(f"{label} setup generation is inconsistent")
    if custody.stale_output_digest != stale_output_digest:
        raise ValueError(f"{label} stale output is inconsistent")
    if (
        custody.scope_project_id != scope_project_id
        or custody.guide_id != guide_id
        or custody.source_snapshot_id != source_snapshot_id
    ):
        raise ValueError(f"{label} setup lineage is inconsistent")


class ProjectGuideSufficiencyMutationResourceContext(BaseModel):
    """Canonical snapshot and report facts for sufficiency mutations."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_guide_sufficiency_mutation"]
    resource_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_kind: Literal["report", "run", "warning_acknowledgement"]
    execution_kind: Literal["human", "setup_service"]
    sufficiency_report_id: UUID | None = None
    setup_generation: int = Field(ge=1)
    material_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    stale_output_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    setup_service_custody: ProjectSetupServiceCustodyContext | None = None

    @model_validator(mode="after")
    def require_sufficiency_identity(self):
        """Require report identity only for report-bound operations."""
        report_bound = self.target_kind in {"report", "warning_acknowledgement"}
        if report_bound != (self.sufficiency_report_id is not None):
            raise ValueError("sufficiency report facts do not match target kind")
        expected = self.sufficiency_report_id or self.source_snapshot_id
        if self.resource_id != expected:
            raise ValueError("sufficiency resource does not match target")
        service_execution = self.execution_kind == "setup_service"
        if service_execution != (self.setup_service_custody is not None):
            raise ValueError("sufficiency service execution requires exact setup custody")
        if service_execution:
            if self.target_kind != "run":
                raise ValueError("only a sufficiency run may use setup-service authority")
            _require_setup_custody(
                self.setup_service_custody,
                label="sufficiency",
                expected_step="guide_sufficiency",
                setup_generation=self.setup_generation,
                stale_output_digest=self.stale_output_digest,
                scope_project_id=self.scope_project_id,
                guide_id=self.guide_id,
                source_snapshot_id=self.source_snapshot_id,
            )
        return self


class ProjectSubmissionArtifactPolicyMutationResourceContext(BaseModel):
    """Canonical submission-artifact policy lineage for one mutation."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_submission_artifact_policy_mutation"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_kind: Literal["create", "derive", "update", "approve"]
    execution_kind: Literal["human", "setup_service"]
    policy_id: UUID
    policy_generation: int = Field(ge=1)
    setup_generation: int = Field(ge=1)
    policy_status: str | None = None
    policy_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    stale_output_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    effective_output_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    compiled_pre_submit_output_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    setup_service_custody: ProjectSetupServiceCustodyContext | None = None

    @model_validator(mode="after")
    def require_submission_policy_identity(self):
        """Reject cross-policy selectors and partial current-policy facts."""
        if self.resource_id != self.policy_id:
            raise ValueError("submission policy resource must match policy")
        if (self.policy_status is None) != (self.policy_digest is None):
            raise ValueError("submission policy status and digest must be bound together")
        service_execution = self.execution_kind == "setup_service"
        if service_execution != (self.setup_service_custody is not None):
            raise ValueError("policy service execution requires exact setup custody")
        if service_execution != (self.target_kind == "derive"):
            raise ValueError("policy derivation requires setup-service authority")
        if service_execution:
            _require_setup_custody(
                self.setup_service_custody,
                label="submission policy",
                expected_step="submission_artifact_policy",
                setup_generation=self.setup_generation,
                stale_output_digest=self.stale_output_digest,
                scope_project_id=self.scope_project_id,
                guide_id=self.guide_id,
                source_snapshot_id=self.source_snapshot_id,
            )
        return self


class ProjectPostSubmitCheckerPolicyMutationResourceContext(BaseModel):
    """Canonical post-submit checker-policy lineage for one mutation."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_post_submit_checker_policy_mutation"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_kind: Literal["approve", "correction_request", "derive"]
    execution_kind: Literal["human", "setup_service"]
    checker_policy_id: UUID
    setup_generation: int = Field(ge=1)
    lifecycle_status: str
    compiled_policy_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    setup_service_custody: ProjectSetupServiceCustodyContext | None = None

    @model_validator(mode="after")
    def require_checker_policy_identity(self):
        """Bind the resource selector to the checker policy only."""
        if self.resource_id != self.checker_policy_id:
            raise ValueError("checker policy resource must match policy")
        service_execution = self.execution_kind == "setup_service"
        if service_execution != (self.setup_service_custody is not None):
            raise ValueError("checker service execution requires exact setup custody")
        if service_execution != (self.target_kind == "derive"):
            raise ValueError("checker derivation requires setup-service authority")
        if service_execution:
            _require_setup_custody(
                self.setup_service_custody,
                label="checker policy",
                expected_step="post_submit_policy",
                setup_generation=self.setup_generation,
                stale_output_digest=self.compiled_policy_digest,
                scope_project_id=self.scope_project_id,
                guide_id=self.guide_id,
                source_snapshot_id=self.source_snapshot_id,
            )
        return self


class ProjectSetupRunMutationResourceContext(BaseModel):
    """Canonical setup-run step custody for one ledger mutation."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_setup_run_mutation"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    setup_run_id: UUID
    setup_generation: int = Field(ge=1)
    expected_step: Literal["guide_sufficiency", "submission_artifact_policy", "post_submit_policy"]
    task_id: UUID
    correlation_id: UUID
    stale_output_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_setup_run_identity(self):
        """Bind setup ledger authority to the exact active run."""
        if self.resource_id != self.setup_run_id:
            raise ValueError("setup-run resource must match run")
        return self


class ProjectGuideActivationResourceContext(BaseModel):
    """Complete guide and active-bundle identity for terminal activation."""

    model_config = _STRICT_FROZEN

    resource_type: Literal["project_guide_activation"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    sufficiency_report_id: UUID
    submission_artifact_policy_id: UUID
    pre_submit_checker_policy_id: UUID
    post_submit_checker_policy_id: UUID
    review_policy_id: UUID
    revision_policy_id: UUID
    active_bundle_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    activation_generation: int = Field(ge=1)

    @model_validator(mode="after")
    def require_activation_identity(self):
        """Bind terminal activation to the selected guide."""
        if self.resource_id != self.guide_id:
            raise ValueError("guide activation resource must match guide")
        return self


PROJECT_MUTATION_RESOURCE_BY_ACTION = MappingProxyType(
    {
        ActionId.PROJECT_CREATE: ProjectCreateResourceContext,
        ActionId.PROJECT_GUIDE_CREATE: ProjectGuideMutationResourceContext,
        ActionId.PROJECT_GUIDE_UPDATE: ProjectGuideMutationResourceContext,
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE: (
            ProjectGuideSourceSnapshotMutationResourceContext
        ),
        ActionId.PROJECT_REVIEW_POLICY_UPDATE: ProjectReviewPolicyMutationResourceContext,
        ActionId.PROJECT_REVISION_POLICY_UPDATE: ProjectRevisionPolicyMutationResourceContext,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE: (
            ProjectGuideSufficiencyMutationResourceContext
        ),
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN: ProjectGuideSufficiencyMutationResourceContext,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE: (
            ProjectGuideSufficiencyMutationResourceContext
        ),
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE: (
            ProjectSubmissionArtifactPolicyMutationResourceContext
        ),
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE: (
            ProjectSubmissionArtifactPolicyMutationResourceContext
        ),
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE: (
            ProjectSubmissionArtifactPolicyMutationResourceContext
        ),
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE: (
            ProjectSubmissionArtifactPolicyMutationResourceContext
        ),
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_APPROVE: (
            ProjectPostSubmitCheckerPolicyMutationResourceContext
        ),
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_CORRECTION_REQUEST: (
            ProjectPostSubmitCheckerPolicyMutationResourceContext
        ),
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE: (
            ProjectPostSubmitCheckerPolicyMutationResourceContext
        ),
        ActionId.PROJECT_SETUP_RUN_UPDATE: ProjectSetupRunMutationResourceContext,
        ActionId.PROJECT_GUIDE_ACTIVATE: ProjectGuideActivationResourceContext,
    }
)

PROJECT_SUFFICIENCY_TARGET_KIND_BY_ACTION = MappingProxyType(
    {
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE: "report",
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN: "run",
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE: "warning_acknowledgement",
    }
)

PROJECT_GUIDE_TARGET_KIND_BY_ACTION = MappingProxyType(
    {
        ActionId.PROJECT_GUIDE_CREATE: "create",
        ActionId.PROJECT_GUIDE_UPDATE: "update",
    }
)

PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION = MappingProxyType(
    {
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE: "create",
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE: "derive",
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE: "update",
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE: "approve",
    }
)

PROJECT_POST_SUBMIT_POLICY_TARGET_KIND_BY_ACTION = MappingProxyType(
    {
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_APPROVE: "approve",
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_CORRECTION_REQUEST: "correction_request",
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE: "derive",
    }
)


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


class GuideSourceIngestResourceContext(BaseModel):
    """Exact locked guide lineage and server-owned byte facts for ingest."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    operation_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_exact_lineage(self):
        """Keep the final resource bound to one concrete project lineage."""
        if self.resource_id != self.scope_project_id:
            raise ValueError("guide ingest project scope must match resource")
        if len({self.guide_source_item_id, self.guide_source_snapshot_id, self.guide_id}) != 3:
            raise ValueError("guide ingest lineage identifiers must be distinct")
        return self


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


class GuideSourceBindingResourceContext(BaseModel):
    """Exact verified guide-source lineage authorized for one binding write."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["guide_source_binding"]
    resource_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int = Field(gt=0)
    content_id: UUID
    verified_replica_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    logical_role: Literal["guide_source_original"]

    @model_validator(mode="after")
    def bind_source_item(self):
        """Use the exact source item as the prepared resource selector."""
        if self.resource_id != self.guide_source_item_id:
            raise ValueError("guide binding resource must match source item")
        return self


class GuideSourceReadResourceContext(BaseModel):
    """Exact verified binding and replica facts authorized for one provider read."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["guide_source_read"]
    resource_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int = Field(gt=0)
    binding_id: UUID
    content_id: UUID
    verified_replica_id: UUID
    storage_namespace_id: str = Field(min_length=1, max_length=255)
    namespace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    verification_receipt_id: UUID
    verification_generation: int = Field(ge=0)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def bind_artifact_binding(self):
        """Use the exact immutable binding as the prepared resource selector."""
        if self.resource_id != self.binding_id:
            raise ValueError("guide read resource must match binding")
        return self


AuthorizationResourceContext = (
    ActorSelfResourceContext
    | ProjectReadResourceContext
    | ProjectDiagnosticReadResourceContext
    | ProjectPolicyReadResourceContext
    | ProjectActiveGuideReadResourceContext
    | ProjectCreateResourceContext
    | ProjectGuideMutationResourceContext
    | ProjectGuideMutationPrepareDenialResourceContext
    | ProjectGuideSourceSnapshotMutationResourceContext
    | ProjectReviewPolicyMutationResourceContext
    | ProjectRevisionPolicyMutationResourceContext
    | ProjectGuideSufficiencyMutationResourceContext
    | ProjectSubmissionArtifactPolicyMutationResourceContext
    | ProjectPostSubmitCheckerPolicyMutationResourceContext
    | ProjectSetupRunMutationResourceContext
    | ProjectGuideActivationResourceContext
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
    | GuideSourceIngestResourceContext
    | ArtifactPutAttemptResourceContext
    | ArtifactVerificationJobResourceContext
    | ArtifactPendingWorkResourceContext
    | GuideSourceBindingResourceContext
    | GuideSourceReadResourceContext
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
    """Fail-closed control flow carrying only one bounded decision."""

    def __init__(self, decision: AuthorizationDecision) -> None:
        if decision.allowed or decision.denial_code is None:
            raise TypeError("authorization denial requires a denied decision")
        self.decision = decision
        super().__init__("Authorization denied")

    @property
    def public_code(self) -> str:
        """Map internal catalogue outcomes to the stable public denial."""
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
    """Authorization evidence could not be persisted safely."""
