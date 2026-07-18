"""Project guide analysis agent contracts."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProjectAgentRuntimeError(Exception):
    """Raised when a project-agent runtime cannot complete a trusted operation."""


class ProjectAgentRuntimeConfigurationError(ProjectAgentRuntimeError):
    """Raised when a configured project-agent runtime is unavailable or incomplete."""


class GuideSourceItemMaterial(BaseModel):
    """One immutable source item made available to setup agents."""

    model_config = ConfigDict(extra="forbid")

    source_kind: str
    durable_ref: str
    ingestion_adapter: str
    content_hash: str
    content_cid: str | None = None
    media_type: str | None = None
    content_excerpt: str | None = None


class RepresentativeTaskMaterialContext(BaseModel):
    """Representative task material used for guide sufficiency analysis."""

    model_config = ConfigDict(extra="forbid")

    items: list[GuideSourceItemMaterial] = Field(default_factory=list)


class GuideSourceMaterial(BaseModel):
    """Immutable project and task-context material made available to setup agents."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    guide_material: dict[str, Any]
    source_items: list[GuideSourceItemMaterial] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    representative_task_material: RepresentativeTaskMaterialContext = Field(
        default_factory=RepresentativeTaskMaterialContext
    )


class AgentFinding(BaseModel):
    """Structured finding emitted by a project setup agent."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking_gap", "warning", "info"]
    code: str = Field(max_length=100)
    message: str = Field(max_length=1000)
    location: str | None = Field(default=None, max_length=500)


class GuideSufficiencyAgentResult(BaseModel):
    """Structured output from the project guide sufficiency agent."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "guide_sufficient",
        "guide_blocked",
        "guide_sufficient_with_warnings",
    ]
    findings: list[AgentFinding] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=2000)
    agent_name: str = Field(default="ProjectGuideSufficiencyAgent", max_length=100)
    agent_version: str = Field(max_length=50)


class SubmissionArtifactPolicyDerivationResult(BaseModel):
    """Structured output from the submission artifact policy derivation agent."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(max_length=50)
    policy_body: dict[str, Any]
    change_summary: str | None = Field(default=None, max_length=2000)
    agent_name: str = Field(default="SubmissionArtifactPolicyDerivationAgent", max_length=100)
    agent_version: str = Field(max_length=100)


class PostSubmitCheckerCatalogEntry(BaseModel):
    """One registered deterministic checker available for post-submit setup."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=100)
    platform_default: bool = False


class PostSubmitCheckerPolicyEvidenceRef(BaseModel):
    """Bounded source-evidence reference for post-submit derivation reasons."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(max_length=200)


class PostSubmitCheckerPolicyReason(BaseModel):
    """Reason tying a requested checker to bounded source evidence."""

    model_config = ConfigDict(extra="forbid")

    checker_name: str = Field(max_length=100)
    rationale: str = Field(max_length=1000)
    evidence_refs: list[PostSubmitCheckerPolicyEvidenceRef] = Field(
        default_factory=list,
        max_length=10,
    )


class UnsupportedPostSubmitCheckerGap(BaseModel):
    """Unsupported required post-submit checker requirement from guide setup."""

    model_config = ConfigDict(extra="forbid")

    requested_checker: str = Field(max_length=500)
    reason: str = Field(max_length=1000)
    evidence_refs: list[PostSubmitCheckerPolicyEvidenceRef] = Field(
        default_factory=list,
        max_length=10,
    )


class PostSubmitCheckerPolicyCorrectionFeedback(BaseModel):
    """Bounded operator feedback for replacing one superseded checker policy."""

    model_config = ConfigDict(extra="forbid")

    superseded_policy_id: str = Field(max_length=36)
    superseded_policy_hash: str = Field(max_length=71)
    required_checkers: list[str] = Field(default_factory=list, max_length=100)
    warning_checkers: list[str] = Field(default_factory=list, max_length=100)
    blocking_severities: list[str] = Field(default_factory=list, max_length=10)
    correction_reason: str = Field(max_length=500)


class PostSubmitCheckerPolicyDerivationContext(BaseModel):
    """Server-owned context supplied to the post-submit policy derivation agent."""

    model_config = ConfigDict(extra="forbid")

    sufficiency_report_summary: dict[str, Any]
    effective_policy_summary: dict[str, Any]
    pre_submit_checker_summary: dict[str, Any]
    registered_checker_catalog: list[PostSubmitCheckerCatalogEntry]
    correction_feedback: PostSubmitCheckerPolicyCorrectionFeedback | None = None


class PostSubmitCheckerPolicyDerivationResult(BaseModel):
    """Structured output from the post-submit checker policy derivation agent."""

    model_config = ConfigDict(extra="forbid")

    required_checkers: list[str] = Field(default_factory=list, max_length=100)
    warning_checkers: list[str] = Field(default_factory=list, max_length=100)
    blocking_severities: list[str] | None = Field(default=None, max_length=10)
    reasons: list[PostSubmitCheckerPolicyReason] = Field(default_factory=list, max_length=100)
    unsupported_required_checks: list[UnsupportedPostSubmitCheckerGap] = Field(
        default_factory=list,
        max_length=100,
    )
    setup_notes: list[str] = Field(default_factory=list, max_length=20)
    agent_name: str = Field(default="PostSubmitCheckerPolicyDerivationAgent", max_length=100)
    agent_version: str = Field(max_length=100)


class ProjectGuideAgentRuntime(Protocol):
    """Port implemented by project guide setup agent runtimes."""

    async def analyze_guide_sufficiency(
        self,
        material: GuideSourceMaterial,
    ) -> GuideSufficiencyAgentResult:
        """Assess whether guide material is sufficient for project setup."""

    async def derive_submission_artifact_policy(
        self,
        material: GuideSourceMaterial,
        sufficiency_report: GuideSufficiencyAgentResult,
    ) -> SubmissionArtifactPolicyDerivationResult:
        """Derive the machine-readable submission artifact policy."""

    async def derive_post_submit_checker_policy(
        self,
        material: GuideSourceMaterial,
        context: PostSubmitCheckerPolicyDerivationContext,
    ) -> PostSubmitCheckerPolicyDerivationResult:
        """Derive the constrained project post-submit checker policy spec."""
