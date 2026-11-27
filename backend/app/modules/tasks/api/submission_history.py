"""Immutable history identity and authority ports; no current-assignment authority."""

from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Subquery
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


class SubmissionFindingCounts(BaseModel):
    """Finding counts of a submission's current completed post-submit run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    blocking: int
    warning: int
    coverage_incomplete: int


class SubmissionFindingCountsPort(Protocol):
    """CHECKERS counts within submissions TASK already authorized and selected.

    Each value is ``(blocking, warning, coverage_incomplete)``; plain integers keep
    CHECKERS free of a public dependency back on TASK.
    """

    async def read_finding_counts(
        self, submission_ids: tuple[UUID, ...], *, manager: bool,
    ) -> dict[UUID, tuple[int, int, int]]: ...

    def evidence_stamps(self) -> Subquery:
        """``(submission_id, evidence_at)``: when each submission's counted findings last changed."""
        ...


SubmissionAttemptStatus = Literal[
    "evaluation_pending", "review_pending", "accepted", "needs_revision", "rejected",
]
SubmissionStatusReason = Literal[
    "revision_deadline_expired", "revision_limit_reached", "checker_coverage_incomplete",
]


class ContributorSubmissionHistory(BaseModel):
    """Fixed historical packet fields for its authorized contributor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    task_id: UUID
    version: int
    status: SubmissionAttemptStatus
    status_reason: SubmissionStatusReason | None
    summary: str | None = Field(description="Retained summary on submissions recorded before project feedback.")
    feedback: str | None
    submitted_at: datetime
    decided_at: datetime | None
    finding_counts: SubmissionFindingCounts
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


class SubmissionOperationAssociationUnavailable(RuntimeError):
    """The operation's exact finalized TASK association cannot be proven."""


@dataclass(frozen=True, slots=True)
class SubmissionOperationOutcome:
    """One retained attempt and original dispatch, never current-task status."""

    submission_id: UUID
    submission_version: int
    status: SubmissionAttemptStatus
    evaluation_request_id: UUID
    evaluation_event_id: UUID
    evaluation_event_json: str


class SubmissionHistoryReadPort(Protocol):
    """TASK selects ownership before projection; the caller owns the transaction."""

    async def resolve_submission(
        self, submission_id: UUID, *, project_id: UUID | None, contributor_id: UUID | None,
    ) -> SubmissionHistoryTarget | None: ...

    async def resolve_task_history(
        self, task_id: UUID, *, project_id: UUID | None, contributor_id: UUID | None,
    ) -> SubmissionHistoryTarget | None: ...

    async def lock_history_task(self, target: SubmissionHistoryTarget) -> bool: ...

    async def read(
        self, target: SubmissionHistoryTarget, *, manager: bool,
        submission_id: UUID | None = None, limit: int = 25,
        after: tuple[int, UUID] | None = None,
    ) -> tuple[list[ContributorSubmissionHistory | ManagementSubmissionHistory], bool]: ...


    async def read_operation_outcome(
        self, *, project_id: UUID, task_id: UUID, assignment_id: UUID,
        contributor_id: UUID, submission_id: UUID, admission_id: UUID,
    ) -> SubmissionOperationOutcome:
        """Read exact finalized association after caller-owned authorization."""
        ...
