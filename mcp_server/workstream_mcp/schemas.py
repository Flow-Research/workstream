"""Stable schemas and catalogue metadata for the contributor MCP surface."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


MCP_PROMPTS: tuple[str, ...] = ()
STABLE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
MAX_METADATA_DEPTH = 5
MAX_METADATA_COLLECTION_ITEMS = 100
MAX_METADATA_STRING_LENGTH = 10000
BoundedEvidenceRef = Annotated[str, Field(min_length=1, max_length=1000)]


@dataclass(frozen=True, slots=True)
class ResourceDefinition:
    """One WS-MCP-001 resource type and its supported URI templates."""

    name: str
    title: str
    uri_templates: tuple[str, ...]
    mutating: bool = False


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One WS-MCP-001 tool."""

    name: str
    title: str
    mutating: bool = True
    input_fields: tuple[str, ...] = ()


RESOURCE_DEFINITIONS: tuple[ResourceDefinition, ...] = (
    ResourceDefinition(
        name="my_projects",
        title="My Projects",
        uri_templates=("workstream://me/projects",),
    ),
    ResourceDefinition(
        name="my_contributions",
        title="My Contributions",
        uri_templates=(
            "workstream://me/contributions",
            "workstream://me/contributions/projects/{project_id}",
        ),
    ),
    ResourceDefinition(
        name="tasks",
        title="Tasks",
        uri_templates=("workstream://tasks", "workstream://projects/{project_id}/tasks"),
    ),
    ResourceDefinition(
        name="task_context",
        title="Task Context",
        uri_templates=("workstream://tasks/{task_id}/context",),
    ),
    ResourceDefinition(
        name="task_status",
        title="Task Status",
        uri_templates=("workstream://tasks/{task_id}/status",),
    ),
    ResourceDefinition(
        name="current_review",
        title="Current Review",
        uri_templates=("workstream://projects/{project_id}/current-review",),
    ),
    ResourceDefinition(
        name="review_context",
        title="Review Context",
        uri_templates=("workstream://reviews/{review_ref}/context",),
    ),
)

TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition("claim_task", "Claim Task", input_fields=("task_id", "request_id")),
    ToolDefinition(
        "release_task",
        "Release Task",
        input_fields=("task_id", "request_id", "reason"),
    ),
    ToolDefinition(
        "run_pre_submit_check",
        "Run Pre-Submit Check",
        mutating=False,
        input_fields=("task_id", "submission", "request_id"),
    ),
    ToolDefinition(
        "submit_task",
        "Submit Task",
        input_fields=("task_id", "submission", "request_id"),
    ),
    ToolDefinition(
        "claim_review",
        "Claim Review",
        input_fields=("project_id", "review_routing_ref", "request_id"),
    ),
    ToolDefinition(
        "release_review",
        "Release Review",
        input_fields=("review_ref", "request_id"),
    ),
    ToolDefinition(
        "submit_review",
        "Submit Review",
        input_fields=("review_ref", "decision", "findings", "request_id"),
    ),
)


class RequestIdInput(BaseModel):
    """Common idempotency input for mutating MCP tools."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class ClaimTaskInput(RequestIdInput):
    """Input for claim_task."""

    task_id: str = Field(min_length=1, max_length=100)

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str) -> str:
        """Validate a task identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "task_id")


class ReleaseTaskInput(RequestIdInput):
    """Input for release_task."""

    task_id: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str) -> str:
        """Validate a task identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "task_id")


class ArtifactHashEntryInput(BaseModel):
    """One declared artifact hash in a contributor submission packet."""

    model_config = ConfigDict(extra="forbid")

    artifact: str = Field(min_length=1, max_length=1000)
    hash: str = Field(min_length=1, max_length=128)
    size_bytes: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=10000)


class EvidenceItemInput(BaseModel):
    """One contributor-supplied evidence reference."""

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
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=100)

    @field_validator("metadata")
    @classmethod
    def bound_metadata_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject deeply nested or oversized arbitrary evidence metadata."""
        _validate_bounded_metadata(value)
        return value


class SubmissionInput(BaseModel):
    """The Workstream submission packet accepted by existing Submitter APIs."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=10000)
    package_uri: str | None = Field(default=None, max_length=1000)
    package_hash: str = Field(min_length=1, max_length=128)
    artifact_hash_manifest: list[ArtifactHashEntryInput] = Field(min_length=1, max_length=1000)
    worker_attestation: str = Field(min_length=1, max_length=20000)
    evidence_items: list[EvidenceItemInput] = Field(default_factory=list, max_length=1000)


class CandidateSubmissionInput(RequestIdInput):
    """Input for run_pre_submit_check and submit_task."""

    task_id: str = Field(min_length=1, max_length=100)
    submission: SubmissionInput

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str) -> str:
        """Validate a task identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "task_id")


class ClaimReviewInput(RequestIdInput):
    """Input for claim_review."""

    project_id: str = Field(min_length=1, max_length=100)
    review_routing_ref: str = Field(min_length=1, max_length=200)

    @field_validator("project_id", "review_routing_ref")
    @classmethod
    def normalize_string_ids(cls, value: str, info: Any) -> str:
        """Validate review claim identifiers used as URI or HTTP path segments."""
        return normalize_stable_ref(value, info.field_name)


class ReleaseReviewInput(RequestIdInput):
    """Input for release_review."""

    review_ref: str = Field(min_length=1, max_length=200)

    @field_validator("review_ref")
    @classmethod
    def normalize_review_ref(cls, value: str) -> str:
        """Validate a review identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "review_ref")


class ReviewFindingInput(BaseModel):
    """Portable, actionable finding supplied with a human review decision."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    evidence_refs: list[BoundedEvidenceRef] = Field(default_factory=list, max_length=100)


class SubmitReviewInput(RequestIdInput):
    """Input for submit_review."""

    review_ref: str = Field(min_length=1, max_length=200)
    decision: Literal["accept", "needs_revision", "reject"]
    findings: list[ReviewFindingInput] = Field(default_factory=list, max_length=100)

    @field_validator("review_ref")
    @classmethod
    def normalize_review_ref(cls, value: str) -> str:
        """Validate a review identifier used as one URI or HTTP path segment."""
        return normalize_stable_ref(value, "review_ref")


class OperationResult(BaseModel):
    """Structured MCP operation result."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    outcome: str
    workstream_ref: str | None = None
    next_resource: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str


def normalize_stable_ref(value: str, field_name: str) -> str:
    """Validate an opaque Workstream reference carried in one path segment."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if normalized in {".", ".."}:
        raise ValueError(f"{field_name} must not be a relative path segment")
    if not STABLE_REF_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, dot, underscore, colon, or hyphen"
        )
    return normalized


def _validate_bounded_metadata(value: Any, *, depth: int = 0) -> None:
    """Bound arbitrary evidence metadata before it reaches a gateway."""
    if depth > MAX_METADATA_DEPTH:
        raise ValueError("metadata nesting exceeds the supported depth")
    if isinstance(value, str):
        if len(value) > MAX_METADATA_STRING_LENGTH:
            raise ValueError("metadata string exceeds the supported length")
        return
    if isinstance(value, dict):
        if len(value) > MAX_METADATA_COLLECTION_ITEMS:
            raise ValueError("metadata object has too many entries")
        for key, item in value.items():
            _validate_bounded_metadata(key, depth=depth + 1)
            _validate_bounded_metadata(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_METADATA_COLLECTION_ITEMS:
            raise ValueError("metadata list has too many items")
        for item in value:
            _validate_bounded_metadata(item, depth=depth + 1)
        return
    if value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("metadata must contain JSON-compatible values")
