"""Pydantic schemas for checker feedback, runs, and results."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.tasks.schemas import SubmissionCreate

CheckerStatus = Literal["queued", "running", "completed", "failed"]
CheckerResultStatus = Literal["passed", "warning", "failed"]
CheckerSeverity = Literal["info", "low", "medium", "high", "critical"]
# Checker routing recommendations are not human review decision tokens.
# Human review decisions remain only: accept, needs_revision, reject.
CheckerRoutingRecommendation = Literal[
    "not_evaluated",
    "allow_review",
    "needs_revision",
    "checker_retry",
    "task_setup_blocked",
]
CheckerOutcomeSource = Literal["none", "auto_checker"]


class CheckerRunRequest(BaseModel):
    """Request schema for manually triggering an internal checker run."""

    model_config = ConfigDict(extra="forbid")

    trigger_reason: str = Field(min_length=1, max_length=1000)

    @field_validator("trigger_reason")
    @classmethod
    def require_non_empty_reason(cls, value: str) -> str:
        """Require a non-empty audit reason after trimming whitespace."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("trigger_reason must not be blank")
        return stripped


class PreSubmitCheckRequest(BaseModel):
    """Request schema for non-authoritative pre-submit checker feedback."""

    model_config = ConfigDict(extra="forbid")

    submission: SubmissionCreate


class CheckerFeedbackItem(BaseModel):
    """Worker-facing checker feedback item."""

    checker_name: str
    status: CheckerResultStatus
    severity: CheckerSeverity
    would_block_if_submitted: bool
    worker_message: str
    worker_suggested_fix: str | None = None
    worker_evidence_refs: list[str] = Field(default_factory=list)


class PreSubmitCheckResponse(BaseModel):
    """Response schema for non-authoritative pre-submit feedback."""

    task_id: str
    authoritative: Literal[False] = False
    status: Literal["passed", "failed"]
    eligible_to_submit: bool
    results: list[CheckerFeedbackItem]


class CheckerResultResponse(BaseModel):
    """Response schema for one persisted checker result."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    checker_run_id: str
    task_id: str
    submission_id: str
    checker_name: str
    status: CheckerResultStatus
    severity: CheckerSeverity
    blocks_review: bool
    message: str | None = None
    worker_message: str | None = None
    worker_suggested_fix: str | None = None
    worker_evidence_refs: list[str] = Field(default_factory=list)
    worker_visible: bool
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    created_at: datetime


class CheckerRunResponse(BaseModel):
    """Response schema for one persisted checker run with results."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    submission_id: str
    submission_version: int
    trigger_source: str | None = None
    status: CheckerStatus
    routing_recommendation: CheckerRoutingRecommendation | None = None
    outcome_source: CheckerOutcomeSource | None = None
    triggered_by: str | None
    triggered_by_subject: str | None
    triggered_by_issuer: str | None
    trigger_auth_source: str | None
    trigger_reason: str | None
    audit_event_id: str | None
    attempt_number: int
    supersedes_checker_run_id: str | None
    is_current_for_submission: bool
    locked_guide_version: str | None
    locked_checker_policy_version: str | None
    locked_post_submit_checker_policy_id: str | None = None
    locked_post_submit_checker_policy_version: str | None = None
    locked_post_submit_checker_policy_hash: str | None = None
    locked_review_policy_version: str | None
    locked_revision_policy_version: str | None
    locked_payment_policy_version: str | None
    package_hash: str | None
    artifact_hash_manifest: list[dict[str, Any]]
    artifact_manifest_hash: str | None
    passed_count: int
    warning_count: int
    failed_count: int
    blocking_count: int
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    results: list[CheckerResultResponse] = Field(default_factory=list)


class CheckerRunPublicResponse(BaseModel):
    """Conservative public schema for worker-readable checker run endpoints.

    Runtime responses are role-sensitive. Actors with checker-operation roles
    may receive additional internal audit and provenance fields from
    ``CheckerRunResponse``; worker-readable OpenAPI surfaces advertise only this
    safe subset.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    submission_id: str
    submission_version: int
    status: CheckerStatus
    attempt_number: int
    supersedes_checker_run_id: str | None
    is_current_for_submission: bool
    artifact_hash_manifest: list[dict[str, Any]]
    passed_count: int
    warning_count: int
    failed_count: int
    blocking_count: int
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    results: list[CheckerResultResponse] = Field(default_factory=list)
