"""Pydantic schemas for project guide API requests and responses."""

from __future__ import annotations

from app.modules.projects.api.guide_documents import GuideDocumentMediaType
from app.modules.projects.api.task_examples import ProjectGuideTaskExamples

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class ReviewPolicyInput(BaseModel):
    """Input schema for review rules on a guide version."""

    model_config = ConfigDict(extra="forbid")

    human_review_required: StrictBool = True
    review_preference_window_seconds: int = Field(gt=0)
    review_lease_duration_seconds: int = Field(gt=0)
    max_active_review_leases_per_reviewer: Literal[1] = 1
    self_review_allowed: Literal[False] = False
    reject_policy: Literal["close_task"] = "close_task"
    finding_evidence_requirement: Literal[
        "optional", "required_for_blocking", "required_for_all"
    ] = "optional"
    requires_second_review: bool = False
    allowed_decisions: list[Literal["accept", "needs_revision", "reject"]] = Field(
        default_factory=lambda: ["accept", "needs_revision", "reject"]
    )
    minimum_finding_fields: list[str] = Field(default_factory=list)


class RevisionPolicyInput(BaseModel):
    """Input schema for revision-loop rules on a guide version."""

    model_config = ConfigDict(extra="forbid")

    max_revision_rounds: int = Field(ge=1)
    revision_deadline_hours: int = Field(ge=1)
    allowed_resubmission_states: list[Literal["needs_revision"]] = Field(
        default_factory=lambda: ["needs_revision"],
        min_length=1,
        max_length=1,
    )
    reviewer_reassignment_rule: str | None = None


class PaymentPolicyInput(BaseModel):
    """Input schema for payout rules on a guide version."""

    model_config = ConfigDict(extra="forbid")

    base_amount: Decimal | None = None
    currency: str | None = None
    payout_type: str | None = None
    revision_payment_rule: str | None = None
    rejection_payment_rule: str | None = None
    accepted_payment_rule: str | None = None


class ProjectGuideDocumentInput(BaseModel):
    """Declare one original document belonging to a guide version."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=500)
    media_type: GuideDocumentMediaType


class GuideSourceSnapshotItemResponse(BaseModel):
    """Response schema for a sanitized guide-source snapshot item."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    source_snapshot_id: str
    item_order: int
    source_kind: str
    source_label: str
    ingestion_adapter: str
    media_type: str | None
    created_at: datetime


class GuideSourceSnapshotResponse(BaseModel):
    """Response schema for immutable guide-source snapshots."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    manifest_schema_version: str
    manifest_json: dict[str, Any]
    bundle_hash: str
    captured_by: str
    captured_at: datetime
    items: list[GuideSourceSnapshotItemResponse] = Field(default_factory=list)


class GuideArtifactIngestResponse(BaseModel):
    """Public server commitment for one declared guide document upload."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    sha256: str
    byte_count: int
    status: str
    replayed: bool


class ProjectSetupRunResponse(BaseModel):
    """Response schema for automatic project setup run ledger rows."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    setup_generation: int
    celery_task_id: str | None
    documents_ready_at: datetime | None
    status: str
    current_step: str
    output_sufficiency_report_id: str | None
    output_submission_artifact_policy_id: str | None
    error_code: str | None
    error_artifact_incident_id: str | None
    error_summary: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class GuideSufficiencyFindingInput(BaseModel):
    """Input schema for one guide sufficiency finding."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking_gap", "warning", "info"]
    code: str = Field(max_length=100)
    message: str = Field(max_length=1000)
    location: str | None = Field(default=None, max_length=500)


class GuideSufficiencyReportCreate(BaseModel):
    """Request schema for recording guide sufficiency assessment output."""

    model_config = ConfigDict(extra="forbid")

    source_snapshot_id: str = Field(max_length=36)
    status: Literal["passed", "blocked", "passed_with_warnings"]
    findings: list[GuideSufficiencyFindingInput] = Field(default_factory=list, max_length=100)
    summary: str | None = Field(default=None, max_length=2000)


class GuideSufficiencyAcknowledgement(BaseModel):
    """Request schema for acknowledging non-blocking sufficiency warnings."""

    model_config = ConfigDict(extra="forbid")

    acknowledgement_note: str | None = Field(default=None, max_length=1000)


class GuideSufficiencyReportResponse(BaseModel):
    """Response schema for guide sufficiency reports."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    status: str
    findings: list[dict[str, Any]]
    summary: str | None
    agent_name: str | None
    agent_version: str | None
    project_setup_run_id: str | None
    setup_generation: int | None
    agent_material_sha256: str | None
    agent_material_byte_count: int | None
    created_by: str
    created_at: datetime
    warnings_acknowledged_by_role: str | None
    warnings_acknowledged_by_actor: str | None
    warnings_acknowledged_at: datetime | None
    acknowledgement_note: str | None


class ArtifactRuleInput(BaseModel):
    """Input schema for a required artifact rule."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(max_length=100)
    path: str = Field(max_length=500)
    hash_required: Literal[True] = True
    required: bool = True
    description: str | None = Field(default=None, max_length=1000)


class EvidenceRuleInput(BaseModel):
    """Input schema for a required evidence rule."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(max_length=100)
    label: str = Field(max_length=200)
    hash_required: Literal[True] = True
    required: bool = True
    description: str | None = Field(default=None, max_length=1000)


class ForbiddenArtifactRuleInput(BaseModel):
    """Input schema for a project-specific forbidden artifact rule."""

    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(max_length=500)
    reason: str = Field(max_length=1000)
    worker_facing_fix: str | None = Field(default=None, max_length=1000)


class SubmissionArtifactPackagingInput(BaseModel):
    """Constrained packaging rules for submission artifact intake."""

    model_config = ConfigDict(extra="forbid")

    package_required: bool = False
    allowed_package_formats: list[Literal["zip", "tar", "tar.gz", "tar.zst"]] = Field(
        default_factory=list
    )


class SubmissionArtifactPolicyInput(BaseModel):
    """Machine-readable project artifact intake policy content."""

    model_config = ConfigDict(extra="forbid")

    required_artifacts: list[ArtifactRuleInput] = Field(default_factory=list, max_length=100)
    required_evidence: list[EvidenceRuleInput] = Field(default_factory=list, max_length=100)
    forbidden_artifacts: list[ForbiddenArtifactRuleInput] = Field(
        default_factory=list,
        max_length=100,
    )
    attestation_terms: list[str] = Field(default_factory=list, max_length=100)
    manifest_required: bool = True
    artifact_hash_required: bool = True
    artifact_hash_algorithm: Literal["sha256"] = "sha256"
    allowed_storage_schemes: list[Literal["local", "s3", "r2"]] = Field(
        default_factory=lambda: ["local", "s3", "r2"]
    )
    maximum_file_size_bytes: int | None = Field(default=None, gt=0)
    maximum_package_size_bytes: int | None = Field(default=None, gt=0)
    packaging: SubmissionArtifactPackagingInput = Field(
        default_factory=SubmissionArtifactPackagingInput
    )


class SubmissionArtifactPolicyCreate(BaseModel):
    """Request schema for creating a draft project submission artifact policy."""

    model_config = ConfigDict(extra="forbid")

    source_snapshot_id: UUID
    policy_version: str = Field(min_length=1, max_length=50)
    policy_body: SubmissionArtifactPolicyInput
    change_summary: str | None = Field(default=None, max_length=2000)

    @field_validator("policy_version")
    @classmethod
    def reject_reserved_agent_policy_version(cls, value: str) -> str:
        """Reserve agent-derived policy version names for Workstream."""
        stripped_value = value.strip()
        if value != stripped_value:
            raise ValueError("policy_version cannot include surrounding whitespace")
        if stripped_value.casefold().startswith("agent-"):
            raise ValueError("policy_version prefix 'agent-' is reserved")
        return value


class SubmissionArtifactPolicyUpdate(BaseModel):
    """Request schema for creating an authorized replacement draft policy."""

    model_config = ConfigDict(extra="forbid")

    expected_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    successor_policy_version: str = Field(min_length=1, max_length=50)
    policy_body: SubmissionArtifactPolicyInput | None = None
    change_summary: str | None = Field(default=None, max_length=2000)

    @field_validator("successor_policy_version")
    @classmethod
    def reject_reserved_successor_policy_version(cls, value: str) -> str:
        """Reserve agent-derived policy versions for fixed-service output."""
        stripped_value = value.strip()
        if value != stripped_value:
            raise ValueError("successor_policy_version cannot include surrounding whitespace")
        if stripped_value.casefold().startswith("agent-"):
            raise ValueError("successor_policy_version prefix 'agent-' is reserved")
        return value


class SubmissionArtifactPolicyResponse(BaseModel):
    """Response schema for project submission artifact policy records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    policy_version: str
    lifecycle_status: str
    policy_body: dict[str, Any]
    policy_hash: str
    derivation_source: str
    source_material_refs: list[str]
    derivation_agent_name: str | None
    derivation_agent_version: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    approved_by_role: str | None
    approved_by_actor: str | None
    approved_at: datetime | None
    supersedes_policy_id: str | None
    superseded_at: datetime | None
    change_summary: str | None


class EffectiveProjectSubmissionArtifactPolicyResponse(BaseModel):
    """Response schema for merged effective project submission artifact policy."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    submission_artifact_policy_id: str
    submission_artifact_policy_hash: str
    lifecycle_status: str
    merge_algorithm_version: str
    effective_policy: dict[str, Any]
    effective_policy_hash: str
    created_by: str
    created_at: datetime
    supersedes_effective_policy_id: str | None
    superseded_at: datetime | None


class PreSubmitCheckerPolicyResponse(BaseModel):
    """Response schema for project-scoped pre-submit checker bundle contracts."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    effective_policy_id: str
    effective_policy_hash: str
    lifecycle_status: str
    compiler_version: str | None
    compiled_bundle: dict[str, Any] | None
    compiled_bundle_hash: str | None
    checker_names: list[str]
    checker_configs: dict[str, Any]
    created_by: str
    created_at: datetime
    supersedes_pre_submit_checker_policy_id: str | None
    superseded_at: datetime | None


class PreSubmitCheckerPolicySummaryResponse(BaseModel):
    """Project API summary for a pre-submit checker bundle contract."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    effective_policy_id: str
    effective_policy_hash: str
    lifecycle_status: str
    compiler_version: str | None
    compiled_bundle_hash: str | None
    checker_names: list[str]
    created_by: str
    created_at: datetime
    supersedes_pre_submit_checker_policy_id: str | None
    superseded_at: datetime | None


class ActiveGuidePreSubmitCheckerPolicyResponse(PreSubmitCheckerPolicySummaryResponse):
    """Active-guide response schema for project pre-submit checker context."""

    checker_configs: dict[str, Any]


class ProjectCreate(BaseModel):
    """Request schema for creating a project shell."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200, pattern=r"^[^\x00]*$")
    slug: str = Field(max_length=120, pattern=r"^[^\x00]*$")
    description: str | None = Field(default=None, pattern=r"^[^\x00]*$")


class ProjectResponse(BaseModel):
    """Response schema for project records."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ContributorProjectResponse(BaseModel):
    """Minimal project identity visible through an exact contributor grant."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    name: str
    status: str


class ProjectGuideCreate(BaseModel):
    """Create guide metadata with at least one illustrative task example."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(max_length=50, pattern=r"^[^\x00]*$")
    change_summary: str | None = Field(default=None, max_length=1000, pattern=r"^[^\x00]*$")
    task_examples: ProjectGuideTaskExamples
    documents: list[ProjectGuideDocumentInput] = Field(min_length=1, max_length=100)


class ProjectGuideUpdate(BaseModel):
    """Request schema for editing mutable fields on a draft guide."""

    model_config = ConfigDict(extra="forbid")

    change_summary: str | None = Field(default=None, max_length=1000, pattern=r"^[^\x00]*$")


class ProjectGuideResponse(BaseModel):
    """Response schema for project guide records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    version: str
    status: str
    change_summary: str | None
    task_examples: ProjectGuideTaskExamples | None
    task_examples_hash: str | None
    approved_by: str | None
    effective_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    superseded_at: datetime | None


class ProjectGuideDocumentResponse(BaseModel):
    """Public document selector and immutable declaration; no storage coordinates."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    label: str
    media_type: GuideDocumentMediaType
    order: int = Field(ge=0)


class ProjectGuideWaitingSetupResponse(BaseModel):
    """Initial setup identity returned by guide creation and exact replay."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal["awaiting_documents"] = "awaiting_documents"


class ProjectGuideCreateResponse(ProjectGuideResponse):
    """Created guide with its declared upload targets and initial waiting setup."""

    documents: list[ProjectGuideDocumentResponse] = Field(min_length=1, max_length=100)
    setup: ProjectGuideWaitingSetupResponse


class PostSubmitCheckerPolicyResponse(BaseModel):
    """Response schema for post-submit checker policy records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_version: str
    required_checkers: list[str]
    warning_checkers: list[str]
    blocking_severities: list[str]
    policy_hash: str | None
    lifecycle_status: str
    approved_by_role: str | None
    approved_by_actor: str | None
    approved_at: datetime | None
    created_at: datetime












class ReviewPolicyResponse(BaseModel):
    """Response schema for review policy records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_version: str
    policy_generation: int
    policy_hash: str | None
    human_review_required: StrictBool = True
    semantics_format: Literal["v1", "v2"] = "v1"
    semantics_status: Literal["complete", "legacy_incomplete"]
    supersedes_policy_id: str | None
    review_preference_window_seconds: int | None
    review_lease_duration_seconds: int | None
    max_active_review_leases_per_reviewer: int | None
    self_review_allowed: bool | None
    reject_policy: str | None
    finding_evidence_requirement: str | None
    requires_second_review: bool
    allowed_decisions: list[str]
    minimum_finding_fields: list[str]
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def require_explicit_current_mode(cls, value: Any) -> Any:
        """Only legacy stored responses may omit the versioned setting."""
        if (
            isinstance(value, dict)
            and value.get("semantics_format") == "v2"
            and "human_review_required" not in value
        ):
            raise ValueError("v2 review policy requires explicit human_review_required")
        return value

    @model_validator(mode="after")
    def validate_legacy_mode(self) -> ReviewPolicyResponse:
        """Legacy response recovery cannot imply automated acceptance."""
        if self.semantics_format == "v1" and not self.human_review_required:
            raise ValueError("legacy review policy requires human review")
        return self


class RevisionPolicyResponse(BaseModel):
    """Response schema for revision policy records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    guide_version: str
    policy_generation: int
    policy_hash: str | None
    semantics_status: Literal["complete", "legacy_incomplete"]
    supersedes_policy_id: str | None
    max_revision_rounds: int
    revision_deadline_hours: int
    allowed_resubmission_states: list[str]
    reviewer_reassignment_rule: str | None
    created_at: datetime


class PaymentPolicyResponse(BaseModel):
    """Response schema for payment policy records."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    guide_version: str
    base_amount: Decimal | None
    currency: str | None
    payout_type: str | None
    revision_payment_rule: str | None
    rejection_payment_rule: str | None
    accepted_payment_rule: str | None
    created_at: datetime




class ActiveGuideReadResponse(BaseModel):
    """Strict administrative read projection for one active guide."""

    model_config = ConfigDict(extra="forbid")

    guide: ProjectGuideResponse
    guide_source_snapshot: GuideSourceSnapshotResponse
    guide_sufficiency_report: GuideSufficiencyReportResponse
    submission_artifact_policy: SubmissionArtifactPolicyResponse
    effective_submission_artifact_policy: EffectiveProjectSubmissionArtifactPolicyResponse
    pre_submit_checker_policy: ActiveGuidePreSubmitCheckerPolicyResponse
    post_submit_checker_policy: PostSubmitCheckerPolicyResponse
    review_policy: ReviewPolicyResponse
    revision_policy: RevisionPolicyResponse
