"""Pydantic schemas for task queue and assignment APIs."""

from __future__ import annotations

from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.api import ReadyTaskSummary, ManagementTaskSummary, OperationalTaskSummary

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.projects.api.guide_activation import GuidePolicySelection
from app.modules.projects.api.locked_policy import GuideDisplayFacts, ProjectDisplayFacts
from app.modules.tasks.api.task_detail import ContributorTaskDetail, ManagementTaskDetail


class ContributorTaskLifecycle(BaseModel):
    """Current assignment and bounded action hints; executing actions reauthorizes."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    assigned_to_current_actor: bool
    next_actions: tuple[Literal["claim", "start"], ...] = Field(max_length=1)


class _TaskWorkContext(BaseModel):
    """Detached display and exact receipt-selected governing policy identities."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project: ProjectDisplayFacts
    guide: GuideDisplayFacts
    review_policy: GuidePolicySelection
    revision_policy: GuidePolicySelection
    contribution_policy_version_id: UUID

    @model_validator(mode="after")
    def exact_project(self):
        """Reject display facts belonging to different projects."""
        if self.project.id != self.guide.project_id:
            raise ValueError("work context project differs from guide")
        return self


class ContributorTaskWorkContext(_TaskWorkContext):
    """Contributor work instructions without management data or obsolete economics."""

    task: ContributorTaskDetail
    lifecycle: ContributorTaskLifecycle

    @model_validator(mode="after")
    def exact_task(self):
        """Keep the task audience and project exact without response redaction."""
        if type(self.task) is not ContributorTaskDetail or self.task.project_id != self.project.id:
            raise ValueError("contributor work context task is invalid")
        return self


class ManagementTaskWorkContext(_TaskWorkContext):
    """Manager work instructions and provenance without contributor action hints."""

    task: ManagementTaskDetail

    @model_validator(mode="after")
    def exact_task(self):
        """Keep management facts scoped to the context project."""
        if type(self.task) is not ManagementTaskDetail or self.task.project_id != self.project.id:
            raise ValueError("management work context task is invalid")
        return self


ALLOWED_STORAGE_URI_PREFIXES = ("local://", "s3://", "r2://")
FORBIDDEN_URI_FRAGMENTS = (
    "?",
    "#",
    "@",
    "authorization=",
    "credential=",
    "password=",
    "secret=",
    "signature=",
    "token=",
    "x-amz-",
)


def validate_storage_reference(value: str | None) -> str | None:
    """Validate a storage URI/reference accepted by submission packets.

    Args:
        value: Optional storage reference supplied by the client.

    Returns:
        Normalized value when it is a safe storage reference.

    Raises:
        ValueError: If the value is not an allowed storage reference.
    """
    if value is None:
        return value
    normalized = value.strip()
    parsed = urlparse(normalized)
    matching_prefix = next(
        (prefix for prefix in ALLOWED_STORAGE_URI_PREFIXES if parsed.scheme == prefix[:-3]),
        None,
    )
    if matching_prefix is None:
        raise ValueError("uri must be a local, R2, or S3 object reference")
    lowered_auth_components = f"{parsed.query}&{parsed.fragment}".lower()
    has_signed_or_credential_fragment = any(
        fragment in lowered_auth_components
        for fragment in FORBIDDEN_URI_FRAGMENTS
        if fragment not in {"?", "#", "@"}
    )
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ValueError("uri must not include credentials, query strings, or signed URL data")
    if parsed.query or parsed.fragment or has_signed_or_credential_fragment:
        raise ValueError("uri must not include credentials, query strings, or signed URL data")
    reference = f"{parsed.netloc}{parsed.path}"
    if not reference.strip("/"):
        raise ValueError("uri must include an object reference")
    if matching_prefix in {"s3://", "r2://"} and (not parsed.netloc or not parsed.path.strip("/")):
        raise ValueError("uri must include a bucket and object key")
    decoded_segments = unquote(reference).replace("\\", "/").split("/")
    if any(segment in {"", ".", ".."} for segment in decoded_segments):
        raise ValueError("uri must not include empty or traversal path segments")
    return normalized


class TaskCreate(BaseModel):
    """Request schema for creating a draft task."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    task_type: str | None = None
    difficulty: str | None = None
    skill_tags: list[str] = Field(default_factory=list)
    estimated_time_minutes: int | None = Field(default=None, ge=1)
    source_type: Literal["manual", "markdown_import", "csv_import"] = "manual"
    source_ref: str | None = None
    source_payload_hash: str | None = None
    import_batch_id: str | None = None
    external_task_id: str | None = None
    acceptance_criteria: str | None = None
    rejection_criteria: str | None = None
    deadline_at: datetime | None = None


class TaskTransitionRequest(BaseModel):
    """Optional request body for task lifecycle transitions."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


class EvidenceItemCreate(BaseModel):
    """Request schema for one evidence item in a submission packet."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "log",
        "screenshot",
        "test_result",
        "package",
        "diff",
        "note",
        "external_reference",
    ]
    label: str = Field(min_length=1, max_length=200)
    uri: str | None = Field(default=None, max_length=1000)
    hash: str | None = Field(default=None, max_length=128)
    size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _validate_uri = field_validator("uri")(validate_storage_reference)


class ArtifactHashEntry(BaseModel):
    """Structured artifact hash entry supplied by a Contributor."""

    model_config = ConfigDict(extra="forbid")

    artifact: str = Field(min_length=1, max_length=1000)
    hash: str = Field(min_length=1, max_length=128)
    size_bytes: int | None = Field(default=None, ge=0)
    notes: str | None = None


class SubmissionCreate(BaseModel):
    """Shared packet value used by retained checker feedback and evaluation."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    package_uri: str | None = Field(default=None, max_length=1000)
    package_hash: str = Field(min_length=1, max_length=128)
    artifact_hash_manifest: list[ArtifactHashEntry] = Field(min_length=1)
    worker_attestation: str = Field(min_length=1)
    evidence_items: list[EvidenceItemCreate] = Field(default_factory=list)

    _validate_package_uri = field_validator("package_uri")(validate_storage_reference)


class TaskResponse(BaseModel):
    """Response schema for task records."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    locked_contribution_policy_version_id: UUID | None
    locked_guide_version: str | None
    locked_review_policy_id: str | None
    locked_review_policy_generation: int | None
    locked_review_policy_hash: str | None
    locked_revision_policy_id: str | None
    locked_revision_policy_generation: int | None
    locked_revision_policy_hash: str | None
    locked_payment_policy_version: str | None
    locked_guide_source_snapshot_id: str | None
    locked_guide_source_snapshot_hash: str | None
    locked_effective_project_submission_artifact_policy_id: str | None
    locked_effective_project_submission_artifact_policy_hash: str | None
    locked_pre_submit_checker_policy_id: str | None
    locked_pre_submit_checker_bundle_hash: str | None
    source_type: str
    source_ref: str | None
    source_payload_hash: str | None
    import_batch_id: str | None
    external_task_id: str | None
    title: str
    description: str
    task_type: str | None
    difficulty: str | None
    skill_tags: list[str]
    estimated_time_minutes: int | None
    base_amount: Decimal | None
    currency: str | None
    payout_type: str | None
    status: str
    acceptance_criteria: str | None
    rejection_criteria: str | None
    deadline_at: datetime | None
    created_by: str | None
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime


class RequiredArtifactRequirement(BaseModel):
    """Contributor-facing required artifact rule from the locked effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str
    path: str
    hash_required: bool
    required: bool
    description: str | None = None


class RequiredEvidenceRequirement(BaseModel):
    """Contributor-facing required evidence rule from the locked effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str
    label: str
    hash_required: bool
    required: bool
    description: str | None = None


class ForbiddenArtifactRequirement(BaseModel):
    """Contributor-facing forbidden artifact rule from the locked effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pattern: str
    reason: str | None = None
    worker_facing_fix: str | None = None
    severity: str | None = None


class StorageReferenceRules(BaseModel):
    """Contributor-facing storage-reference constraints for staged artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    allowed_storage_schemes: tuple[str, ...]
    allowed_uri_prefixes: tuple[str, ...]
    credentials_allowed: bool
    query_strings_allowed: bool
    fragments_allowed: bool
    path_traversal_allowed: bool


class SubmissionPackagingRequirements(BaseModel):
    """Fixed packaging requirements from the historical effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_required: bool
    allowed_package_formats: tuple[Literal["zip", "tar", "tar.gz", "tar.zst"], ...] | None = None


class _TaskSubmissionRequirements(BaseModel):
    """Contributor-safe exact submission requirements for a locked task."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: UUID
    project_id: UUID
    guide_version: str = Field(pattern=r"\S")
    policy_schema_version: str | None
    merge_algorithm_version: str | None
    required_packet_fields: tuple[str, ...]
    required_artifacts: tuple[RequiredArtifactRequirement, ...]
    required_evidence: tuple[RequiredEvidenceRequirement, ...]
    forbidden_artifacts: tuple[ForbiddenArtifactRequirement, ...]
    attestation_terms: tuple[str, ...]
    manifest_required: bool
    artifact_hash_required: bool
    artifact_hash_algorithm: Literal["sha256"]
    allowed_storage_schemes: tuple[str, ...]
    storage_reference_rules: StorageReferenceRules
    maximum_file_size_bytes: int | None
    maximum_package_size_bytes: int | None
    maximum_archive_entries: int | None
    maximum_archive_size_bytes: int | None
    packaging: SubmissionPackagingRequirements


class ContributorTaskSubmissionRequirements(_TaskSubmissionRequirements):
    """Contributor-safe intake requirements without policy internals or actors."""


class ManagementTaskSubmissionRequirements(_TaskSubmissionRequirements):
    """Separate management requirements; no additional private fields are needed."""


class PostSubmitPolicyBodySummary(BaseModel):
    """Detached immutable summary of the exact locked post-submit policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str | None
    default_checkers: tuple[str, ...]
    required_checkers: tuple[str, ...]
    warning_checkers: tuple[str, ...]
    execution_checkers: tuple[str, ...]
    blocking_severities: tuple[str, ...]


class _TaskLockedContextReferences(TaskPolicyLineage):
    """Exact TASK/project selectors alongside the shared immutable policy lineage."""

    task_id: UUID
    project_id: UUID


class ManagementTaskLockedContext(_TaskLockedContextReferences):
    """Management provenance plus the bounded historical checker summary."""

    locked_post_submit_checker_policy_body_summary: PostSubmitPolicyBodySummary


class OperationalTaskLockedContext(_TaskLockedContextReferences):
    """Operational provenance references; no policy body or private task details."""


class AuditTaskLockedContext(_TaskLockedContextReferences):
    """Audit provenance references; evidence and policy-body reads are separate."""


class AssignmentResponse(BaseModel):
    """Response schema for task assignments."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    project_id: str
    submitter_contribution_policy_version_id: UUID
    contributor_id: str
    assigned_by: str
    assigned_at: datetime
    accepted_at: datetime | None
    released_at: datetime | None
    status: str


class TaskWithAssignmentResponse(BaseModel):
    """Response schema for a task operation that creates or uses an assignment."""

    task: TaskResponse
    assignment: AssignmentResponse


class ContributorTaskQueueResponse(BaseModel):
    """A live ready page; its cursor neither reserves work nor conveys authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    items: tuple[ReadyTaskSummary, ...]
    next_cursor: str | None


class ManagementTaskQueueResponse(BaseModel):
    """Project planning facts with a bounded continuation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    items: tuple[ManagementTaskSummary, ...]
    next_cursor: str | None


class OperationalTaskQueueResponse(BaseModel):
    """Status-only project discovery, excluding management and work content."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    items: tuple[OperationalTaskSummary, ...]
    next_cursor: str | None
