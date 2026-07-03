"""Pydantic schemas for task queue and assignment APIs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    required_files: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    deadline_at: datetime | None = None


class TaskTransitionRequest(BaseModel):
    """Optional request body for task lifecycle transitions."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


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
    """Structured artifact hash entry supplied by a worker."""

    model_config = ConfigDict(extra="forbid")

    artifact: str = Field(min_length=1, max_length=1000)
    hash: str = Field(min_length=1, max_length=128)
    size_bytes: int | None = Field(default=None, ge=0)
    notes: str | None = None


class SubmissionCreate(BaseModel):
    """Request schema for creating a submission packet version."""

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
    locked_guide_version: str | None
    locked_review_policy_version: str | None
    locked_revision_policy_version: str | None
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
    required_files: list[str]
    required_evidence: list[str]
    deadline_at: datetime | None
    created_by: str
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime


class AssignmentResponse(BaseModel):
    """Response schema for task assignments."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    worker_id: str
    assigned_by: str
    assigned_at: datetime
    accepted_at: datetime | None
    released_at: datetime | None
    status: str


class TaskWithAssignmentResponse(BaseModel):
    """Response schema for a task operation that creates or uses an assignment."""

    task: TaskResponse
    assignment: AssignmentResponse


class EvidenceItemResponse(BaseModel):
    """Response schema for evidence items."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    submission_id: str
    type: str
    label: str
    uri: str | None
    hash: str | None
    size_bytes: int | None
    locked_at: datetime | None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    created_at: datetime


class SubmissionResponse(BaseModel):
    """Response schema for submission packet versions."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    worker_id: str
    version: int
    status: str
    summary: str
    package_uri: str | None
    package_hash: str | None
    artifact_hash_manifest: list[dict[str, Any]] | None
    worker_attestation: str | None
    locked_guide_version: str | None
    locked_review_policy_version: str | None
    locked_revision_policy_version: str | None
    locked_payment_policy_version: str | None
    locked_guide_source_snapshot_id: str | None
    locked_guide_source_snapshot_hash: str | None
    locked_effective_project_submission_artifact_policy_id: str | None
    locked_effective_project_submission_artifact_policy_hash: str | None
    locked_pre_submit_checker_policy_id: str | None
    locked_pre_submit_checker_bundle_hash: str | None
    submitted_at: datetime
    locked_at: datetime | None
    supersedes_submission_id: str | None
    evidence_items: list[EvidenceItemResponse] = Field(default_factory=list)


class AuditEventResponse(BaseModel):
    """Response schema for audit events."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_id: str
    external_subject: str
    external_issuer: str
    actor_roles: list[str]
    claim_snapshot: dict[str, Any] = Field(default_factory=dict)
    auth_source: str
    is_dev_auth: bool
    reason: str | None
    event_payload: dict[str, Any]
    created_at: datetime
