"""Public TASK contracts for locked Submission lifecycle context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol, get_args
from uuid import UUID

from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.api.revision import ContributorRevisionContext


TaskSubmissionContextKind = Literal["initial", "checker_remediation"]
TaskSubmissionContextStatus = Literal["in_progress", "needs_revision"]
TaskSubmissionContextFailure = Literal[
    "task_submission_context_invalid",
    "task_submission_operation_in_progress",
    "revision_acknowledgement_required",
    "revision_acknowledgement_invalid",
    "task_submission_predecessor_changed",
    "revision_limit_reached",
    "revision_deadline_expired",
    "revision_context_blocked",
    "revision_context_changed",
]


class TaskSubmissionContextUnavailable(RuntimeError):
    """Report one stable failure without exposing TASK persistence."""

    def __init__(self, code: TaskSubmissionContextFailure) -> None:
        """Validate and retain one failure from the public closed set."""
        if code not in get_args(TaskSubmissionContextFailure):
            raise ValueError("task submission context failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TaskSubmissionContextRequest:
    """Exact TASK-owned selectors supplied to a transaction-bound port."""

    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    predecessor_submission_id: UUID | None


@dataclass(frozen=True, slots=True)
class TaskRetainedSubmissionParentsRequest:
    """Immutable submission parent identity retained after selected PRE."""

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID


@dataclass(frozen=True, slots=True)
class TaskLockedProjectContextReferences:
    """Immutable project-policy references locked onto one TASK row."""

    project_id: UUID
    locked_contribution_policy_version_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str

    def __post_init__(self) -> None:
        """Reject incomplete locked string references."""
        if not isinstance(self.locked_contribution_policy_version_id, UUID):
            raise ValueError("task contribution policy identity is invalid")
        values = (
            self.guide_version,
            self.source_snapshot_hash,
            self.effective_policy_hash,
            self.pre_submit_policy_bundle_hash,
        )
        if any(not value.strip() for value in values):
            raise ValueError("task locked project context reference is empty")


@dataclass(frozen=True, slots=True)
class SubmissionPredecessorFacts:
    """TASK-owned identity of the immediate immutable Submission predecessor."""

    submission_id: UUID
    version: int
    revision_round: int

    def __post_init__(self) -> None:
        """Reject invalid versions; a coverage return leaves the next round at zero."""
        if type(self.version) is not int or self.version < 1:
            raise ValueError("submission predecessor version is invalid")
        if type(self.revision_round) is not int or self.revision_round < 0:
            raise ValueError("submission predecessor revision round is invalid")


@dataclass(frozen=True, slots=True)
class TaskSubmissionContextFacts:
    """Locked TASK, assignment, predecessor, and project-reference facts."""

    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    status: TaskSubmissionContextStatus
    kind: TaskSubmissionContextKind
    predecessor: SubmissionPredecessorFacts | None
    submitter_contribution_policy_version_id: UUID
    locked_project_context: TaskLockedProjectContextReferences
    locked_policy: TaskPolicyLineage
    acceptance_criteria: str | None
    checker_remediation_manifest_id: UUID | None = None
    revision_context: ContributorRevisionContext | None = None
    revision_context_required: bool = False

    def __post_init__(self) -> None:
        """Enforce the exact initial or checker-remediation lifecycle shape."""
        if (
            not isinstance(self.submitter_contribution_policy_version_id, UUID)
            or self.submitter_contribution_policy_version_id
            != self.locked_project_context.locked_contribution_policy_version_id
        ):
            raise ValueError("assignment contribution policy differs from task")
        if self.acceptance_criteria is not None and type(self.acceptance_criteria) is not str:
            raise ValueError("task acceptance criteria is invalid")
        reference_fields = {
            "guide_version": "locked_guide_version",
            "source_snapshot_id": "locked_guide_source_snapshot_id",
            "source_snapshot_hash": "locked_guide_source_snapshot_hash",
            "effective_policy_id": "locked_effective_project_submission_artifact_policy_id",
            "effective_policy_hash": "locked_effective_project_submission_artifact_policy_hash",
            "pre_submit_policy_id": "locked_pre_submit_checker_policy_id",
            "pre_submit_policy_bundle_hash": "locked_pre_submit_checker_bundle_hash",
            "locked_contribution_policy_version_id": "locked_contribution_policy_version_id",
        }
        if any(getattr(self.locked_project_context, ref) != getattr(self.locked_policy, stamp)
               for ref, stamp in reference_fields.items()):
            raise ValueError("task submission context policy references differ")
        is_initial = (
            self.status == "in_progress"
            and self.kind == "initial"
            and self.predecessor is None
            and self.checker_remediation_manifest_id is None
        )
        is_remediation = (
            self.status == "needs_revision"
            and self.kind == "checker_remediation"
            and self.predecessor is not None
            and isinstance(self.checker_remediation_manifest_id, UUID)
        )
        if not (is_initial or is_remediation):
            raise ValueError("task submission context predecessor is inconsistent")


class TaskSubmissionContextPort(Protocol):
    """Transaction-bound TASK capability implemented inside the TASK module."""

    async def lock_submission_context(
        self,
        request: TaskSubmissionContextRequest,
    ) -> TaskSubmissionContextFacts:
        """Lock and return exact TASK-owned lifecycle facts."""

    async def lock_retained_submission_parents(
        self,
        request: TaskRetainedSubmissionParentsRequest,
    ) -> None:
        """Lock retained TASK parents without reauthorizing current lifecycle."""


def require_revision_capacity(
    task: TaskSubmissionContextFacts, *, project_id: UUID, policy_id: UUID,
    policy_generation: int, policy_hash: str, max_revision_rounds: int,
) -> None:
    """Apply the exact locked policy to a new attempt; initial work is round zero."""
    if task.predecessor is None:
        return
    if task.revision_context_required and task.revision_context is None:
        raise TaskSubmissionContextUnavailable("revision_context_blocked")
    if (task.revision_context is not None and task.revision_context.outcome != "blocked"
            and task.revision_context.target.lineage != task.locked_policy):
        raise TaskSubmissionContextUnavailable("revision_context_changed")
    if task.revision_context is not None and task.revision_context.disposition != "ready":
        code = task.revision_context.disposition
        raise TaskSubmissionContextUnavailable(
            "revision_context_blocked" if code == "context_blocked" else code
        )
    locked = task.locked_policy
    if (
        task.locked_project_context.project_id != project_id
        or (locked.locked_revision_policy_id, locked.locked_revision_policy_generation,
            locked.locked_revision_policy_hash)
        != (policy_id, policy_generation, policy_hash)
    ):
        raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
    # A global Submission version is not an assignment's revision allowance.
    if task.predecessor.revision_round > max_revision_rounds:
        raise TaskSubmissionContextUnavailable("revision_limit_reached")



def require_revision_acknowledgement(
    task: TaskSubmissionContextFacts, preparation_id: UUID | str | None, preparation_sha256: str | None,
) -> None:
    """Compare an explicit packet acknowledgement with canonical locked revision facts."""
    if task.predecessor is None:
        if preparation_id is not None or preparation_sha256 is not None:
            raise TaskSubmissionContextUnavailable("revision_acknowledgement_invalid")
        return
    context = task.revision_context
    if context is None:
        raise TaskSubmissionContextUnavailable("revision_context_changed")
    if preparation_id is None and preparation_sha256 is None:
        raise TaskSubmissionContextUnavailable("revision_acknowledgement_required")
    if not isinstance(preparation_id, (UUID, str)) or not isinstance(preparation_sha256, str):
        raise TaskSubmissionContextUnavailable("revision_acknowledgement_invalid")
    try:
        acknowledged_id = UUID(preparation_id) if isinstance(preparation_id, str) else preparation_id
    except ValueError as exc:
        raise TaskSubmissionContextUnavailable("revision_acknowledgement_invalid") from exc
    if re.fullmatch(r"sha256:[0-9a-f]{64}", preparation_sha256) is None:
        raise TaskSubmissionContextUnavailable("revision_acknowledgement_invalid")
    if (context.source_submission_id != task.predecessor.submission_id
            or context.source_routing_manifest_id != task.checker_remediation_manifest_id
            or acknowledged_id != context.preparation_id
            or preparation_sha256 != context.preparation_sha256):
        raise TaskSubmissionContextUnavailable("revision_context_changed")
