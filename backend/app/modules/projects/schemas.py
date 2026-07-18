"""Pydantic schemas for project guide API requests and responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewPolicyInput(BaseModel):
    """Input schema for review rules on a guide version."""

    model_config = ConfigDict(extra="forbid")

    requires_second_review: bool = False
    allowed_decisions: list[Literal["accept", "needs_revision", "reject"]] = Field(
        default_factory=lambda: ["accept", "needs_revision", "reject"]
    )
    minimum_finding_fields: list[str] = Field(default_factory=list)
    sla_hours: int | None = None


class RevisionPolicyInput(BaseModel):
    """Input schema for revision-loop rules on a guide version."""

    model_config = ConfigDict(extra="forbid")

    max_revision_rounds: int = Field(ge=1)
    revision_deadline_hours: int = Field(ge=1)
    auto_reject_after_limit: bool = True
    allowed_resubmission_states: list[str] = Field(default_factory=lambda: ["needs_revision"])
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


class GuideSourceSnapshotItemInput(BaseModel):
    """Input schema for one source item in a guide material bundle."""

    model_config = ConfigDict(extra="forbid")

    source_kind: str = Field(max_length=50)
    durable_ref: str = Field(max_length=2048)
    ingestion_adapter: str = Field(max_length=100)
    content_hash: str = Field(max_length=71)
    content_cid: str | None = Field(default=None, max_length=200)
    media_type: str | None = Field(default=None, max_length=100)
    content_excerpt: str | None = Field(default=None, max_length=12000)


class GuideSourceSnapshotCreate(BaseModel):
    """Request schema for creating an immutable guide-source snapshot."""

    model_config = ConfigDict(extra="forbid")

    items: list[GuideSourceSnapshotItemInput] = Field(default_factory=list, max_length=100)


class GuideSourceSnapshotItemResponse(BaseModel):
    """Response schema for a sanitized guide-source snapshot item."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_snapshot_id: str
    item_order: int
    source_kind: str
    durable_ref: str
    ingestion_adapter: str
    content_hash: str
    content_cid: str | None
    media_type: str | None
    created_at: datetime


class GuideSourceSnapshotResponse(BaseModel):
    """Response schema for immutable guide-source snapshots."""

    model_config = ConfigDict(from_attributes=True)

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


class ProjectSetupRunResponse(BaseModel):
    """Response schema for automatic project setup run ledger rows."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    celery_task_id: str | None
    status: str
    current_step: str
    output_sufficiency_report_id: str | None
    output_submission_artifact_policy_id: str | None
    output_post_submit_checker_policy_id: str | None
    post_submit_derivation_summary: dict[str, Any] | None
    error_code: str | None
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

    model_config = ConfigDict(from_attributes=True)

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

    source_snapshot_id: str = Field(max_length=36)
    policy_version: str = Field(max_length=50)
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
    """Request schema for editing a draft project submission artifact policy."""

    model_config = ConfigDict(extra="forbid")

    policy_body: SubmissionArtifactPolicyInput | None = None
    change_summary: str | None = Field(default=None, max_length=2000)


class SubmissionArtifactPolicyApprove(BaseModel):
    """Request schema for approving a draft submission artifact policy."""

    model_config = ConfigDict(extra="forbid")

    approval_note: str | None = Field(default=None, max_length=2000)


class SubmissionArtifactPolicyResponse(BaseModel):
    """Response schema for project submission artifact policy records."""

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

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

    name: str
    slug: str
    description: str | None = None


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


class ProjectGuideCreate(BaseModel):
    """Request schema for guide material plus optional activation policies."""

    model_config = ConfigDict(extra="forbid")

    version: str
    content_markdown: str
    change_summary: str | None = None
    source_snapshot: GuideSourceSnapshotCreate | None = None
    review_policy: ReviewPolicyInput | None = None
    revision_policy: RevisionPolicyInput | None = None
    payment_policy: PaymentPolicyInput | None = None


class ProjectGuideUpdate(BaseModel):
    """Request schema for editing mutable fields on a draft guide."""

    model_config = ConfigDict(extra="forbid")

    content_markdown: str | None = None
    change_summary: str | None = None
    review_policy: ReviewPolicyInput | None = None
    revision_policy: RevisionPolicyInput | None = None
    payment_policy: PaymentPolicyInput | None = None


class ProjectGuideResponse(BaseModel):
    """Response schema for project guide records."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    version: str
    status: str
    content_markdown: str
    change_summary: str | None
    approved_by: str | None
    effective_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    superseded_at: datetime | None


class PostSubmitCheckerPolicyResponse(BaseModel):
    """Response schema for post-submit checker policy records."""

    model_config = ConfigDict(from_attributes=True)

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


class PostSubmitCheckerPolicyApproval(BaseModel):
    """Request schema for approving a compiled post-submit checker policy."""

    model_config = ConfigDict(extra="forbid")


class PostSubmitCheckerPolicyCorrectionRequest(BaseModel):
    """Request schema for requesting correction of a compiled post-submit policy."""

    model_config = ConfigDict(extra="forbid")

    correction_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("correction_reason")
    @classmethod
    def normalize_correction_reason(cls, value: str) -> str:
        """Strip correction feedback and reject an empty normalized reason."""
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("correction_reason must contain non-whitespace text")
        return normalized


class PostSubmitCheckerPolicySetupSummaryResponse(BaseModel):
    """Operator-visible summary for generated post-submit checker setup."""

    id: str
    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash_redacted: bool = True
    effective_policy_id: str
    effective_policy_hash: str
    pre_submit_checker_policy_id: str
    pre_submit_checker_bundle_hash: str
    required_checkers: list[str]
    warning_checkers: list[str]
    blocking_severities: list[str]
    policy_hash: str | None
    lifecycle_status: str
    approved_by_role: str | None
    approved_by_actor: str | None
    approved_at: datetime | None
    created_by: str
    created_at: datetime


class PostSubmitCheckerPolicyCorrectionSummaryResponse(BaseModel):
    """Operator-visible audit summary for one rejected compiled policy."""

    policy_id: str
    policy_hash: str | None
    required_checkers: list[str]
    warning_checkers: list[str]
    blocking_severities: list[str]
    correction_reason: str
    correction_requested_by_role: str
    correction_requested_by_actor: str
    correction_requested_at: datetime


class PostSubmitCheckerPolicySetupResponse(BaseModel):
    """Response schema for current post-submit checker policy setup state."""

    project_id: str
    guide_id: str
    guide_version: str
    setup_run: ProjectSetupRunResponse
    post_submit_checker_policy: PostSubmitCheckerPolicySetupSummaryResponse | None
    derivation_input_summary: dict[str, Any]
    correction_history: list[PostSubmitCheckerPolicyCorrectionSummaryResponse]


class ReviewPolicyResponse(BaseModel):
    """Response schema for review policy records."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    guide_version: str
    requires_second_review: bool
    allowed_decisions: list[str]
    minimum_finding_fields: list[str]
    sla_hours: int | None
    created_at: datetime


class RevisionPolicyResponse(BaseModel):
    """Response schema for revision policy records."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    guide_version: str
    max_revision_rounds: int
    revision_deadline_hours: int
    auto_reject_after_limit: bool
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


class ActiveGuideResponse(BaseModel):
    """Response schema for an active guide and its policy context."""

    guide: ProjectGuideResponse
    guide_source_snapshot: GuideSourceSnapshotResponse
    guide_sufficiency_report: GuideSufficiencyReportResponse
    submission_artifact_policy: SubmissionArtifactPolicyResponse
    effective_submission_artifact_policy: EffectiveProjectSubmissionArtifactPolicyResponse
    pre_submit_checker_policy: ActiveGuidePreSubmitCheckerPolicyResponse
    post_submit_checker_policy: PostSubmitCheckerPolicyResponse
    review_policy: ReviewPolicyResponse
    revision_policy: RevisionPolicyResponse
    payment_policy: PaymentPolicyResponse
