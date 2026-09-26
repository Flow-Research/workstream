"""Immutable history identity and authority ports; no current-assignment authority."""

from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Literal, Protocol
from uuid import UUID

HistoryKind = Literal["task_submission_history", "submission_history", "checker_history"]


@dataclass(frozen=True, slots=True)
class SubmissionHistoryTarget:
    """Server-selected ownership anchored to an immutable Submission."""

    project_id: UUID
    task_id: UUID
    submission_id: UUID
    contributor_id: UUID


@dataclass(frozen=True, slots=True)
class HistoryReadAuthorityFacts:
    """Exact resource and query committed by one history read decision."""

    action: str
    resource_type: HistoryKind
    resource_id: UUID
    target: SubmissionHistoryTarget
    actor_id: UUID
    query_digest: str


class HistoryReadAuthorityPort(Protocol):
    """AUTH stages fresh evidence in the caller's read transaction."""

    async def require_history(self, facts: HistoryReadAuthorityFacts) -> None: ...


class SubmissionEvidenceDescriptor(BaseModel):
    """Public evidence description without storage coordinates or private metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    type: str
    label: str
    size_bytes: int | None


class ContributorSubmissionHistory(BaseModel):
    """Fixed historical packet fields for its authorized contributor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    task_id: UUID
    version: int
    status: str
    summary: str
    submitted_at: datetime
    locked_at: datetime | None
    supersedes_submission_id: UUID | None
    evidence_items: list[SubmissionEvidenceDescriptor]


class ManagementSubmissionHistory(ContributorSubmissionHistory):
    """Project Manager lineage inspection without private artifacts or economics."""

    contributor_id: UUID
    task_assignment_id: UUID
    contribution_policy_version_id: UUID
    locked_guide_version: str
    locked_post_submit_checker_policy_id: UUID
    locked_post_submit_checker_policy_version: str
    locked_post_submit_checker_policy_hash: str
    locked_review_policy_id: UUID
    locked_review_policy_generation: int
    locked_review_policy_hash: str
    locked_revision_policy_id: UUID
    locked_revision_policy_generation: int
    locked_revision_policy_hash: str
    locked_guide_source_snapshot_id: UUID | None
    locked_guide_source_snapshot_hash: str | None
    locked_effective_project_submission_artifact_policy_id: UUID | None
    locked_effective_project_submission_artifact_policy_hash: str | None
    locked_pre_submit_checker_policy_id: UUID | None
    locked_pre_submit_checker_bundle_hash: str | None


class ContributorSubmissionHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: list[ContributorSubmissionHistory]
    next_cursor: str | None


class ManagementSubmissionHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: list[ManagementSubmissionHistory]
    next_cursor: str | None
