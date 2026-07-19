"""Service layer for task queue lifecycle and assignment operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.permissions import PermissionDenied, require_any_role
from app.modules.checkers.compiler import (
    PreSubmitCheckerCompilerError,
    validate_compiled_pre_submit_checker_bundle,
)
from app.modules.checkers.gate_queue import PreReviewGateQueueError, enqueue_pre_review_gate
from app.modules.checkers.pre_review_gate import (
    find_submission_requester_provenance,
    requester_provenance_payload,
)
from app.modules.checkers.service import (
    CheckerService,
    CheckerServiceError,
    pre_review_gate_system_actor,
)
from app.modules.actors.models import LegacyWorkflowEligibility
from app.modules.actors.service import (
    ActiveHumanWriteActorRequired,
    ActorService,
    CanonicalWriteActorUnavailable,
    LegacyWorkflowEligibilityCompatibility,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
)
from app.modules.projects.post_submit_policy import (
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.tasks.authorization import can_admin_or_task_creator_manage
from app.modules.tasks.lifecycle import (
    TASK_STATUS_CLAIMED,
    TASK_STATUS_DRAFT,
    TASK_STATUS_EVALUATION_PENDING,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NEEDS_REVISION,
    TASK_STATUS_READY,
    TASK_STATUS_SCREENING,
    TASK_STATUS_SUBMITTED,
    InvalidTaskTransition,
    ensure_allowed_transition,
)
from app.modules.tasks.models import (
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    AssignmentResponse,
    AuditEventResponse,
    ForbiddenArtifactRequirement,
    PostSubmitPolicyBodySummary,
    RequiredArtifactRequirement,
    RequiredEvidenceRequirement,
    StorageReferenceRules,
    SubmissionCreate,
    SubmissionRequirementsResponse,
    SubmissionResponse,
    TaskCreate,
    TaskGuideContext,
    TaskLockedContextResponse,
    TaskPaymentPolicyContext,
    TaskProjectContext,
    TaskResponse,
    TaskReviewPolicyContext,
    TaskRevisionPolicyContext,
    TaskWorkerLifecycleContext,
    TaskWorkerTaskContext,
    TaskWorkContextResponse,
    TaskWithAssignmentResponse,
)
from app.schemas.auth import ActorContext

PROJECT_OPERATOR_ROLES = {"admin", "project_manager"}
TASK_VIEW_ROLES = {"admin", "project_manager", "worker"}
TASK_CLAIM_ROLES = {"worker"}
TASK_SUBMIT_ROLES = {"worker"}
TASK_START_ROLES = {"admin", "project_manager", "worker"}
TASK_START_OPERATOR_ROLES = {"admin", "project_manager"}
SUBMISSION_FINALIZE_ROLES = {"admin", "project_manager"}
SUBMISSION_FINALIZED_EVENT_TYPE = "submission_finalized"
PRE_REVIEW_GATE_DISPATCH_FAILED_EVENT_TYPE = "pre_review_gate_dispatch_failed"
CONTRIBUTOR_VISIBLE_AUDIT_PAYLOAD_KEYS = {
    "assignment_id",
    "locked_guide_version",
    "locked_review_policy_version",
    "locked_revision_policy_version",
    "locked_payment_policy_version",
    "source_type",
    "submission_id",
    "submission_version",
    "supersedes_submission_id",
    "contributor_id",
}
CONTRIBUTOR_REDACTED_AUDIT_EVENTS = {
    "pre_review_gate_started",
    "pre_review_gate_passed",
    "pre_review_gate_needs_revision",
    "pre_review_gate_blocked",
    PRE_REVIEW_GATE_DISPATCH_FAILED_EVENT_TYPE,
    "pre_review_gate_repair_requested",
}
SUBMISSION_CREATE_REQUIRED_PACKET_FIELDS = (
    "summary",
    "package_hash",
    "artifact_hash_manifest",
    "worker_attestation",
)
LOCKED_CONTEXT_REQUIRED_FIELDS = (
    "locked_guide_version",
    "locked_post_submit_checker_policy_id",
    "locked_post_submit_checker_policy_version",
    "locked_post_submit_checker_policy_hash",
    "locked_post_submit_checker_policy_body",
    "locked_review_policy_version",
    "locked_revision_policy_version",
    "locked_payment_policy_version",
    "locked_guide_source_snapshot_id",
    "locked_guide_source_snapshot_hash",
    "locked_effective_project_submission_artifact_policy_id",
    "locked_effective_project_submission_artifact_policy_hash",
    "locked_pre_submit_checker_policy_id",
    "locked_pre_submit_checker_bundle_hash",
)


class TaskServiceError(Exception):
    """Base error for task service failures mapped to API responses."""

    status_code = 400


class TaskNotFound(TaskServiceError):
    """Raised when a task id does not match a stored task."""

    status_code = 404


class TaskProjectNotReady(TaskServiceError):
    """Raised when a project does not have active guide and policy context."""

    status_code = 422


class TaskTransitionBlocked(TaskServiceError):
    """Raised when a task lifecycle transition is blocked by policy."""

    status_code = 409


class TaskValidationError(TaskServiceError):
    """Raised when a task is missing fields required by its guide."""

    status_code = 422


class TaskAssignmentConflict(TaskServiceError):
    """Raised when a task already has an active Contributor assignment."""

    status_code = 409


class ActiveContributorRequired(TaskServiceError):
    """Raised when the canonical caller cannot perform a contributor write."""

    status_code = 403
    code = "active_contributor_required"
    message = "Active contributor identity required"


class ContributorIdentityUnavailable(TaskServiceError):
    """Raised when canonical contributor identity cannot be revalidated."""

    status_code = 503
    code = "contributor_identity_unavailable"
    message = "Contributor identity verification unavailable"
    retryable = True


class LegacySubmitterEligibilityRequired(TaskServiceError):
    """Raised when a submitter lacks temporary legacy workflow eligibility."""

    status_code = 403


class SubmissionNotFound(TaskServiceError):
    """Raised when a submission id does not match a stored packet."""

    status_code = 404


class SubmissionVersionConflict(TaskServiceError):
    """Raised when concurrent submission version allocation conflicts."""

    status_code = 409


class SubmissionCheckerGateError(TaskServiceError):
    """Raised when automatic checker gate execution blocks submission intake."""

    def __init__(self, message: str, status_code: int) -> None:
        """Create a task-layer error preserving the checker gate status code.

        Args:
            message: Checker service error message safe for API responses.
            status_code: HTTP status code chosen by the checker service.
        """
        super().__init__(message)
        self.status_code = status_code


class PreSubmissionCheckerFailed(TaskServiceError):
    """Raised when the locked pre-submit checker blocks submission creation."""

    status_code = 422
    code = "pre_submission_checker_failed"

    def __init__(self, details: dict) -> None:
        """Create a pre-submit failure carrying structured checker feedback."""
        super().__init__(self.code)
        self.details = details


class TaskLockedContextInvalid(TaskServiceError):
    """Raised when a task's stamped policy provenance is missing or inconsistent."""

    status_code = 422
    code = "task_locked_context_invalid"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Create a locked-context error with machine-readable details.

        Args:
            message: Human-readable error summary safe for API responses.
            details: Optional structured error details.
        """
        super().__init__(message)
        self.details = details or {"message": message}


@dataclass(frozen=True)
class LockedTaskContext:
    """Validated records bound to one task's stamped locked context."""

    project: Project
    guide: ProjectGuide
    source_snapshot: GuideSourceSnapshot
    effective_policy: EffectiveProjectSubmissionArtifactPolicy
    pre_submit_checker_policy: PreSubmitCheckerPolicy
    post_submit_checker_policy: PostSubmitCheckerPolicy
    locked_post_submit_policy_body: PostSubmitPolicyBodySummary
    review_policy: ReviewPolicy
    revision_policy: RevisionPolicy
    payment_policy: PaymentPolicy


class TaskService:
    """Coordinates task lifecycle rules, assignment, and audit writes."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
        """
        self._session = session
        self._repo = TaskRepository(session)
        self._project_repo = ProjectRepository(session)
        self._actors = ActorService(session)
        self._legacy_workflow_eligibility = LegacyWorkflowEligibilityCompatibility(session)

    async def create_task(
        self,
        actor: ActorContext,
        project_id: str,
        payload: TaskCreate,
    ) -> TaskResponse:
        """Create a draft task under a project.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the task.
            payload: Draft task fields.

        Returns:
            Created task response.

        Raises:
            PermissionDenied: If the actor cannot create tasks.
            TaskProjectNotReady: If the project id is unknown.
        """
        require_any_role(actor, PROJECT_OPERATOR_ROLES)
        project = await self._project_repo.get_project(project_id)
        if project is None:
            raise TaskProjectNotReady("project not found")

        task = WorkstreamTask(
            id=str(uuid4()),
            project_id=project_id,
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            source_payload_hash=payload.source_payload_hash,
            import_batch_id=payload.import_batch_id,
            external_task_id=payload.external_task_id,
            title=payload.title,
            description=payload.description,
            task_type=payload.task_type,
            difficulty=payload.difficulty,
            skill_tags=payload.skill_tags,
            estimated_time_minutes=payload.estimated_time_minutes,
            status=TASK_STATUS_DRAFT,
            acceptance_criteria=payload.acceptance_criteria,
            rejection_criteria=payload.rejection_criteria,
            deadline_at=payload.deadline_at,
            created_by=actor.actor_id,
        )
        task = await self._repo.add_task(task)
        await self._write_task_audit(
            actor,
            task,
            event_type="task_created",
            from_status=None,
            to_status=TASK_STATUS_DRAFT,
            reason=None,
            event_payload={"source_type": task.source_type},
        )
        await self._session.commit()
        await self._session.refresh(task)
        return self._task_response(actor, task)

    async def get_task(self, actor: ActorContext, task_id: str) -> TaskResponse:
        """Return one task visible to authorized workflow actors.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task id to load.

        Returns:
            Matching task response.

        Raises:
            PermissionDenied: If the actor cannot view tasks.
            TaskNotFound: If the task id is unknown.
        """
        require_any_role(actor, TASK_VIEW_ROLES)
        task = await self._get_task(task_id)
        await self._ensure_task_visible(actor, task)
        return self._task_response(actor, task)

    async def get_task_work_context(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> TaskWorkContextResponse:
        """Return Contributor-safe work context from the task's locked provenance.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task whose context should be returned.

        Returns:
            Contributor-facing task, guide, policy, and lifecycle context.

        Raises:
            PermissionDenied: If the actor cannot view tasks.
            TaskNotFound: If the task is unknown or hidden.
            TaskLockedContextInvalid: If locked context is incomplete or stale.
        """
        require_any_role(actor, TASK_VIEW_ROLES)
        task = await self._get_task(task_id)
        await self._ensure_task_visible(actor, task)
        context = await self._load_locked_task_context(task)
        eligibility = (
            await self._legacy_workflow_eligibility.get_active_submitter_eligibility(
                actor.actor_id
            )
        )
        return self._work_context_response(
            actor,
            task,
            context,
            has_active_submitter_eligibility=(
                "worker" in actor.roles and eligibility is not None
            ),
        )

    async def get_task_submission_requirements(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> SubmissionRequirementsResponse:
        """Return exact Contributor submission requirements for a locked task.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task whose locked requirements should be returned.

        Returns:
            Contributor-facing submission artifact requirements.

        Raises:
            PermissionDenied: If the actor cannot view tasks.
            TaskNotFound: If the task is unknown or hidden.
            TaskLockedContextInvalid: If locked context is incomplete or stale.
        """
        require_any_role(actor, TASK_VIEW_ROLES)
        task = await self._get_task(task_id)
        await self._ensure_task_visible(actor, task)
        context = await self._load_locked_task_context(task)
        return self._submission_requirements_response(task, context)

    async def get_task_locked_context(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> TaskLockedContextResponse:
        """Return operator-only locked provenance for a task.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task whose locked provenance should be returned.

        Returns:
            Full locked guide and policy provenance for support/debugging.

        Raises:
            PermissionDenied: If the actor is not an operator.
            TaskNotFound: If the task is unknown.
            TaskLockedContextInvalid: If locked context is incomplete or stale.
        """
        require_any_role(actor, PROJECT_OPERATOR_ROLES)
        task = await self._get_task(task_id)
        if not can_admin_or_task_creator_manage(actor, task):
            raise TaskNotFound("task not found")
        context = await self._load_locked_task_context(task)
        return self._locked_context_response(task, context)

    async def move_to_screening(
        self,
        actor: ActorContext,
        task_id: str,
        reason: str | None = None,
    ) -> TaskResponse:
        """Move a draft task to screening and lock active guide context.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Draft task to screen.
            reason: Optional transition reason stored in audit.

        Returns:
            Updated task response.

        Raises:
            PermissionDenied: If the actor cannot screen tasks.
            TaskNotFound: If the task id is unknown.
            TaskProjectNotReady: If active guide or policies are missing.
            TaskValidationError: If required task fields are incomplete.
        """
        require_any_role(actor, PROJECT_OPERATOR_ROLES)
        task = await self._get_task(task_id)
        self._ensure_transition_allowed(task.status, TASK_STATUS_SCREENING)

        (
            guide,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
            source_snapshot,
            effective_policy,
            pre_submit_checker_policy,
        ) = await self._load_active_policy_context(task.project_id)
        self._validate_task_contract_fields(task)
        self._stamp_locked_context(
            task,
            guide,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
            source_snapshot,
            effective_policy,
            pre_submit_checker_policy,
        )
        await self._change_task_status(actor, task, TASK_STATUS_SCREENING, reason)
        await self._session.commit()
        await self._session.refresh(task)
        return self._task_response(actor, task)

    async def release_to_ready(
        self,
        actor: ActorContext,
        task_id: str,
        reason: str | None = None,
    ) -> TaskResponse:
        """Release a screened task to the ready queue.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Screened task to release.
            reason: Optional transition reason stored in audit.

        Returns:
            Updated task response.

        Raises:
            PermissionDenied: If the actor cannot release tasks.
            TaskTransitionBlocked: If locked policy context is incomplete.
        """
        require_any_role(actor, PROJECT_OPERATOR_ROLES)
        task = await self._get_task(task_id)
        self._ensure_transition_allowed(task.status, TASK_STATUS_READY)
        if reason is None or not reason.strip():
            raise TaskValidationError("release decision reason is required")
        self._ensure_locked_context(task)
        await self._load_locked_task_context(task)
        await self._change_task_status(actor, task, TASK_STATUS_READY, reason)
        await self._session.commit()
        await self._session.refresh(task)
        return self._task_response(actor, task)

    async def claim_task(
        self,
        actor: ActorContext,
        task_id: str,
        reason: str | None = None,
    ) -> TaskWithAssignmentResponse:
        """Claim a ready task for the current actor.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Ready task to claim.
            reason: Optional transition reason stored in audit.

        Returns:
            Task and active assignment response.

        Raises:
            PermissionDenied: If the actor cannot claim tasks.
            TaskAssignmentConflict: If an active assignment already exists.
        """
        require_any_role(actor, TASK_CLAIM_ROLES)
        await self._require_active_contributor(actor)
        task = await self._get_task(task_id, for_update=True)
        self._ensure_transition_allowed(task.status, TASK_STATUS_CLAIMED)
        await self._require_legacy_submitter_eligibility(actor)
        if await self._repo.get_active_assignment(task_id, for_update=True) is not None:
            raise TaskAssignmentConflict("task already has an active assignment")

        assignment = TaskAssignment(
            id=str(uuid4()),
            task_id=task.id,
            contributor_id=actor.actor_id,
            assigned_by=actor.actor_id,
            accepted_at=datetime.now(UTC),
            status="active",
        )
        try:
            assignment = await self._repo.add_assignment(assignment)
            task.assigned_to = actor.actor_id
            await self._change_task_status(
                actor,
                task,
                TASK_STATUS_CLAIMED,
                reason,
                event_payload={
                    "assignment_id": assignment.id,
                    "contributor_id": assignment.contributor_id,
                },
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise TaskAssignmentConflict("task already has an active assignment") from exc
        await self._session.refresh(task)
        await self._session.refresh(assignment)
        return TaskWithAssignmentResponse(
            task=self._task_response(actor, task),
            assignment=AssignmentResponse.model_validate(assignment),
        )

    async def start_task(
        self,
        actor: ActorContext,
        task_id: str,
        reason: str | None = None,
    ) -> TaskResponse:
        """Move a claimed task into active work.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Claimed task to start.
            reason: Optional transition reason stored in audit.

        Returns:
            Updated task response.

        Raises:
            PermissionDenied: If the actor cannot start this task.
            TaskTransitionBlocked: If no active assignment exists.
        """
        require_any_role(actor, TASK_START_ROLES)
        task = await self._get_task(task_id)
        self._ensure_transition_allowed(task.status, TASK_STATUS_IN_PROGRESS)
        assignment = await self._repo.get_active_assignment(task_id)
        if assignment is None:
            raise TaskTransitionBlocked("task has no active assignment")
        is_operator_override = assignment.contributor_id != actor.actor_id and bool(
            set(actor.roles).intersection(TASK_START_OPERATOR_ROLES)
        )
        if assignment.contributor_id != actor.actor_id and not is_operator_override:
            raise TaskTransitionBlocked("actor is not assigned to this task")
        if not is_operator_override:
            await self._require_legacy_submitter_eligibility(actor)
        if is_operator_override and (reason is None or not reason.strip()):
            raise TaskValidationError("operator start override reason is required")
        await self._change_task_status(
            actor,
            task,
            TASK_STATUS_IN_PROGRESS,
            reason,
            event_payload={
                "assignment_id": assignment.id,
                "contributor_id": assignment.contributor_id,
                "operator_override": bool(is_operator_override),
            },
            event_type="task_start_override" if is_operator_override else "task_status_changed",
        )
        await self._session.commit()
        await self._session.refresh(task)
        return self._task_response(actor, task)

    async def create_submission(
        self,
        actor: ActorContext,
        task_id: str,
        payload: SubmissionCreate,
    ) -> SubmissionResponse:
        """Create a task-owned submission packet version.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task receiving the submission packet.
            payload: Submission packet fields supplied by the Contributor.

        Returns:
            Created submission response with evidence items.

        Raises:
            PermissionDenied: If the actor cannot create Contributor submissions.
            TaskProjectNotReady: If locked project policy context is invalid.
            TaskTransitionBlocked: If task state or assignment does not allow submission.
            TaskValidationError: If required submission fields are missing.
            SubmissionVersionConflict: If concurrent version allocation conflicts.
        """
        require_any_role(actor, TASK_SUBMIT_ROLES)
        await self._require_active_contributor(actor)
        task = await self._get_task(task_id, for_update=True)
        if "worker" in actor.roles and task.assigned_to not in {None, actor.actor_id}:
            raise TaskNotFound("task not found")
        await self._require_legacy_submitter_eligibility(actor)
        assignment = await self._repo.get_active_assignment(task_id, for_update=True)
        if assignment is None:
            raise TaskTransitionBlocked("task has no active assignment")
        if assignment.contributor_id != actor.actor_id or task.assigned_to != actor.actor_id:
            raise TaskNotFound("task not found")
        if task.status not in {
            TASK_STATUS_IN_PROGRESS,
            TASK_STATUS_NEEDS_REVISION,
        }:
            raise TaskTransitionBlocked(
                "task must be in progress or needs revision before submission"
            )
        self._ensure_locked_context(task)
        await self._load_locked_task_context(task)

        try:
            pre_submit_response = await CheckerService(self._session).pre_submit_check(
                actor,
                task_id,
                payload,
            )
        except CheckerServiceError as exc:
            raise SubmissionCheckerGateError(str(exc), exc.status_code) from exc
        if not pre_submit_response.eligible_to_submit:
            pre_submit_details = pre_submit_response.model_dump(mode="json")
            await self._write_task_audit(
                actor,
                task,
                event_type="pre_submission_check_failed",
                from_status=task.status,
                to_status=task.status,
                reason=None,
                event_payload={"pre_submit_check": pre_submit_details},
            )
            await self._session.commit()
            raise PreSubmissionCheckerFailed(pre_submit_details)

        latest_submission = await self._repo.get_latest_submission_for_task(task.id)
        next_version = 1 if latest_submission is None else latest_submission.version + 1
        submission = Submission(
            id=str(uuid4()),
            task_id=task.id,
            contributor_id=actor.actor_id,
            version=next_version,
            status="submitted",
            summary=payload.summary,
            package_uri=payload.package_uri,
            package_hash=payload.package_hash,
            artifact_hash_manifest=[
                entry.model_dump(mode="json") for entry in payload.artifact_hash_manifest
            ],
            worker_attestation=payload.worker_attestation,
            locked_guide_version=task.locked_guide_version,
            locked_post_submit_checker_policy_id=task.locked_post_submit_checker_policy_id,
            locked_post_submit_checker_policy_version=(
                task.locked_post_submit_checker_policy_version
            ),
            locked_post_submit_checker_policy_hash=task.locked_post_submit_checker_policy_hash,
            locked_post_submit_checker_policy_body=task.locked_post_submit_checker_policy_body,
            locked_review_policy_version=task.locked_review_policy_version,
            locked_revision_policy_version=task.locked_revision_policy_version,
            locked_payment_policy_version=task.locked_payment_policy_version,
            locked_guide_source_snapshot_id=task.locked_guide_source_snapshot_id,
            locked_guide_source_snapshot_hash=task.locked_guide_source_snapshot_hash,
            locked_effective_project_submission_artifact_policy_id=(
                task.locked_effective_project_submission_artifact_policy_id
            ),
            locked_effective_project_submission_artifact_policy_hash=(
                task.locked_effective_project_submission_artifact_policy_hash
            ),
            locked_pre_submit_checker_policy_id=task.locked_pre_submit_checker_policy_id,
            locked_pre_submit_checker_bundle_hash=task.locked_pre_submit_checker_bundle_hash,
            supersedes_submission_id=None if latest_submission is None else latest_submission.id,
            evidence_items=[
                EvidenceItem(
                    id=str(uuid4()),
                    type=evidence.type,
                    label=evidence.label,
                    uri=evidence.uri,
                    hash=evidence.hash,
                    size_bytes=evidence.size_bytes,
                    metadata_json=evidence.metadata,
                )
                for evidence in payload.evidence_items
            ],
        )
        try:
            submission = await self._repo.add_submission(submission)
            event_payload = self._submission_audit_payload(submission)
            if task.status in {TASK_STATUS_IN_PROGRESS, TASK_STATUS_NEEDS_REVISION}:
                await self._change_task_status(
                    actor,
                    task,
                    TASK_STATUS_SUBMITTED,
                    reason=None,
                    event_payload=event_payload,
                    event_type="submission_created",
                )
            else:
                await self._write_task_audit(
                    actor,
                    task,
                    event_type="submission_created",
                    from_status=task.status,
                    to_status=task.status,
                    reason=None,
                    event_payload=event_payload,
                )
            await self._finalize_submission_for_evaluation(actor, task, submission)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise SubmissionVersionConflict("submission version conflicted; retry") from exc

        await self._enqueue_pre_review_gate_after_commit(
            actor,
            submission.id,
            raise_on_failure=False,
        )
        persisted = await self._repo.get_submission(submission.id)
        if persisted is None:
            raise SubmissionNotFound("submission not found")
        return self._submission_response(
            actor,
            persisted,
            has_operator_access=can_admin_or_task_creator_manage(actor, task),
        )

    async def list_task_submissions(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> list[SubmissionResponse]:
        """List submission versions for one visible task.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task whose submissions should be listed.

        Returns:
            Submission responses ordered by version.
        """
        require_any_role(actor, TASK_VIEW_ROLES)
        task = await self._get_task(task_id)
        await self._ensure_task_visible(actor, task)
        submissions = await self._repo.list_submissions_for_task(task.id)
        has_operator_access = can_admin_or_task_creator_manage(actor, task)
        return [
            self._submission_response(
                actor,
                submission,
                has_operator_access=has_operator_access,
            )
            for submission in submissions
        ]

    async def get_submission(
        self,
        actor: ActorContext,
        submission_id: str,
    ) -> SubmissionResponse:
        """Return one visible submission packet.

        Args:
            actor: Verified Flow actor context for the current request.
            submission_id: Submission id to load.

        Returns:
            Submission response.
        """
        require_any_role(actor, TASK_VIEW_ROLES)
        submission = await self._get_submission(submission_id)
        task = await self._get_task(submission.task_id)
        await self._ensure_task_visible(actor, task)
        return self._submission_response(
            actor,
            submission,
            has_operator_access=can_admin_or_task_creator_manage(actor, task),
        )

    async def finalize_submission(
        self,
        actor: ActorContext,
        submission_id: str,
    ) -> SubmissionResponse:
        """Repair or re-check the automatic gate for a locked submission.

        Args:
            actor: Verified Flow actor context for the current request.
            submission_id: Submission id whose automatic gate should be repaired.

        Returns:
            Locked submission response.

        Raises:
            PermissionDenied: If the actor cannot repair the automatic gate.
            TaskTransitionBlocked: If the submission is stale or task state is invalid.
        """
        require_any_role(actor, SUBMISSION_FINALIZE_ROLES)
        submission = await self._get_submission(submission_id)
        task = await self._get_task(submission.task_id)
        await self._ensure_submission_finalize_authorized(actor, task)
        has_operator_access = can_admin_or_task_creator_manage(actor, task)
        latest_submission = await self._repo.get_latest_submission_for_task(task.id)
        if latest_submission is None or latest_submission.id != submission.id:
            raise TaskTransitionBlocked("only latest submission version can be repair-checked")
        if submission.status != "submitted":
            raise TaskTransitionBlocked("submission must be submitted before repair check")
        if submission.locked_at is not None:
            repair_snapshot = await CheckerService(self._session).pre_review_gate_repair_snapshot(
                submission.id
            )
            requester_provenance = await self._submission_finalization_requester_provenance(
                task,
                submission,
            )
            await self._enqueue_pre_review_gate_after_commit(
                actor,
                submission.id,
                requester_provenance=requester_provenance,
                repair_snapshot=repair_snapshot,
            )
            persisted = await self._repo.get_submission(submission_id)
            if persisted is None:
                raise SubmissionNotFound("submission not found")
            return self._submission_response(
                actor,
                persisted,
                has_operator_access=has_operator_access,
            )
        raise TaskTransitionBlocked(
            "submission is not locked; create a submission to trigger automatic pre-review gate"
        )

    async def _ensure_submission_finalize_authorized(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
    ) -> None:
        """Enforce object-level authorization for automatic gate repair.

        Args:
            actor: Verified actor requesting repair.
            task: Task that owns the submission being repaired.

        Raises:
            PermissionDenied: If the role is valid but not authorized for this task.
        """
        if can_admin_or_task_creator_manage(actor, task):
            return
        raise PermissionDenied("actor is not authorized to repair this submission gate")

    async def _finalize_submission_for_evaluation(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
    ) -> None:
        """Stamp the immutable submission boundary before post-submit evaluation."""
        if submission.locked_at is not None:
            return
        locked_at = datetime.now(UTC)
        did_finalize = await self._repo.finalize_submission_if_unlocked(submission.id, locked_at)
        if not did_finalize:
            persisted = await self._repo.get_submission(submission.id, populate_existing=True)
            if persisted is not None and persisted.locked_at is not None:
                submission.locked_at = persisted.locked_at
                return
            raise TaskTransitionBlocked("submission lock conflicted; retry")
        submission.locked_at = locked_at
        await self._repo.lock_submission_evidence(submission.id, locked_at)
        await self._write_task_audit(
            actor,
            task,
            event_type=SUBMISSION_FINALIZED_EVENT_TYPE,
            from_status=task.status,
            to_status=task.status,
            reason=None,
            event_payload=self._submission_audit_payload(submission),
        )

    async def _enqueue_pre_review_gate_after_commit(
        self,
        actor: ActorContext,
        submission_id: str,
        *,
        requester_provenance: dict[str, str] | None = None,
        repair_snapshot: dict[str, Any] | None = None,
        raise_on_failure: bool = True,
    ) -> str:
        """Enqueue the system-owned post-submit checker gate after persistence."""
        checker_service = CheckerService(self._session)
        repair_submission: Submission | None = None
        repair_task: WorkstreamTask | None = None
        checker_run, should_enqueue = await checker_service.ensure_automatic_pre_review_gate_queued(
            submission_id,
            force_enqueue_queued=repair_snapshot is not None,
        )
        if not should_enqueue:
            if repair_snapshot is not None and checker_run.status == "failed":
                raise TaskTransitionBlocked(
                    "automatic pre-review gate failure is not repairable through finalize; "
                    "inspect checker run"
                )
            return checker_run.id
        if repair_snapshot is not None:
            dispatch_claimed = await checker_service.claim_pre_review_gate_repair_dispatch(
                checker_run.id
            )
            if not dispatch_claimed:
                return checker_run.id
        requester_payload = requester_provenance or self._requester_provenance_payload(actor)
        try:
            task_id = await asyncio.to_thread(
                enqueue_pre_review_gate,
                checker_run_id=checker_run.id,
                requester_provenance=requester_payload,
            )
        except PreReviewGateQueueError as exc:
            enqueue_failure_recorded = await checker_service.mark_pre_review_gate_enqueue_failed(
                checker_run.id
            )
            if not enqueue_failure_recorded:
                if raise_on_failure:
                    raise SubmissionCheckerGateError(
                        "pre-review gate claim is no longer current",
                        409,
                    ) from exc
                return checker_run.id
            await self._mark_pre_review_gate_dispatch_failed(
                submission_id,
                checker_run.id,
                str(exc),
                requester_payload,
            )
            if raise_on_failure:
                raise SubmissionCheckerGateError(str(exc), 503) from exc
            return checker_run.id
        if repair_snapshot is not None:
            if repair_submission is None:
                repair_submission = await self._get_submission(submission_id)
            if repair_task is None:
                repair_task = await self._get_task(repair_submission.task_id)
            await self._write_pre_review_gate_repair_audit(
                actor,
                repair_task,
                repair_submission,
                checker_run_id=checker_run.id,
                should_enqueue=should_enqueue,
                repair_snapshot=repair_snapshot,
            )
            await self._session.commit()
        return task_id

    async def _mark_pre_review_gate_dispatch_failed(
        self,
        submission_id: str,
        checker_run_id: str,
        failure_message: str,
        requester_payload: dict[str, str],
    ) -> None:
        """Move locked submission packets into the evaluation repair lane after dispatch failure."""
        submission = await self._get_submission(submission_id)
        task = await self._get_task(submission.task_id)
        event_payload = {
            "submission_id": submission.id,
            "submission_version": submission.version,
            "checker_run_id": checker_run_id,
            "failure_code": "pre_review_gate_enqueue_failed",
            "failure_message": failure_message[:1000],
            **requester_payload,
        }
        system_actor = pre_review_gate_system_actor()
        if task.status == TASK_STATUS_SUBMITTED:
            await self._change_task_status(
                system_actor,
                task,
                TASK_STATUS_EVALUATION_PENDING,
                reason="automatic pre-review gate dispatch failed; operator repair required",
                event_payload=event_payload,
                event_type=PRE_REVIEW_GATE_DISPATCH_FAILED_EVENT_TYPE,
            )
        else:
            await self._write_task_audit(
                system_actor,
                task,
                event_type=PRE_REVIEW_GATE_DISPATCH_FAILED_EVENT_TYPE,
                from_status=task.status,
                to_status=task.status,
                reason="automatic pre-review gate dispatch failed; operator repair required",
                event_payload=event_payload,
            )
        await self._session.commit()

    async def _submission_finalization_requester_provenance(
        self,
        task: WorkstreamTask,
        submission: Submission,
    ) -> dict[str, str]:
        """Load original submitter/lock provenance for repair enqueue."""
        events = await self._repo.list_audit_events("task", task.id)
        provenance = find_submission_requester_provenance(
            events,
            submission_id=submission.id,
            event_type=SUBMISSION_FINALIZED_EVENT_TYPE,
        )
        if provenance is not None:
            return provenance
        raise TaskTransitionBlocked("submission lock audit provenance is missing")

    async def _write_pre_review_gate_repair_audit(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
        *,
        checker_run_id: str,
        should_enqueue: bool,
        repair_snapshot: dict[str, Any],
    ) -> None:
        """Record a scoped operator attempt to repair the automatic gate."""
        await self._write_task_audit(
            actor,
            task,
            event_type="pre_review_gate_repair_requested",
            from_status=task.status,
            to_status=task.status,
            reason="repair automatic pre-review gate",
            event_payload={
                **self._submission_audit_payload(submission),
                "checker_run_id": checker_run_id,
                "repair_action": "requeue_automatic_pre_review_gate",
                "should_enqueue": should_enqueue,
                **repair_snapshot,
            },
        )

    @staticmethod
    def _requester_provenance_payload(actor: ActorContext) -> dict[str, str]:
        """Build the minimal requester provenance safe to send through Celery."""
        return requester_provenance_payload(actor)

    async def list_task_audit_events(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> list[AuditEventResponse]:
        """Return audit events for one task.

        Args:
            actor: Verified Flow actor context for the current request.
            task_id: Task whose audit trail should be loaded.

        Returns:
            Audit events ordered by creation time.
        """
        require_any_role(actor, TASK_VIEW_ROLES)
        task = await self._get_task(task_id)
        await self._ensure_task_visible(actor, task)
        events = await self._repo.list_audit_events("task", task.id)
        has_operator_access = can_admin_or_task_creator_manage(actor, task)
        return [
            self._audit_response(actor, event, has_operator_access=has_operator_access)
            for event in events
        ]

    async def _get_submission(self, submission_id: str) -> Submission:
        """Load a submission packet or raise a service error.

        Args:
            submission_id: Submission id to load.

        Returns:
            Matching submission model.

        Raises:
            SubmissionNotFound: If the submission id is unknown.
        """
        submission = await self._repo.get_submission(submission_id)
        if submission is None:
            raise SubmissionNotFound("submission not found")
        return submission

    async def _get_task(
        self,
        task_id: str,
        *,
        for_update: bool = False,
    ) -> WorkstreamTask:
        """Load a task or raise a service error.

        Args:
            task_id: Task id to load.

        Returns:
            Matching task model.

        Raises:
            TaskNotFound: If the task id is unknown.
        """
        task = await self._repo.get_task(task_id, for_update=for_update)
        if task is None:
            raise TaskNotFound("task not found")
        return task

    async def _require_active_contributor(self, actor: ActorContext) -> None:
        """Revalidate the exact canonical caller before contributor writes."""
        try:
            await self._actors.require_active_human_write_actor(actor)
        except ActiveHumanWriteActorRequired as exc:
            await self._session.rollback()
            raise ActiveContributorRequired(ActiveContributorRequired.message) from exc
        except (CanonicalWriteActorUnavailable, SQLAlchemyError) as exc:
            await self._session.rollback()
            raise ContributorIdentityUnavailable(
                ContributorIdentityUnavailable.message
            ) from exc

    @staticmethod
    def _submission_audit_payload(submission: Submission) -> dict:
        """Build the task audit payload for a submission event.

        Args:
            submission: Submission model associated with the audit event.

        Returns:
            Structured audit payload without raw package or evidence URIs.
        """
        return {
            "submission_id": submission.id,
            "submission_version": submission.version,
            "contributor_id": submission.contributor_id,
            "package_hash": submission.package_hash,
            "artifact_hash_manifest": submission.artifact_hash_manifest,
            "supersedes_submission_id": submission.supersedes_submission_id,
            "finalized_at": submission.locked_at.isoformat() if submission.locked_at else None,
            "locked_guide_source_snapshot_id": submission.locked_guide_source_snapshot_id,
            "locked_guide_source_snapshot_hash": submission.locked_guide_source_snapshot_hash,
            "locked_post_submit_checker_policy_id": (
                submission.locked_post_submit_checker_policy_id
            ),
            "locked_post_submit_checker_policy_version": (
                submission.locked_post_submit_checker_policy_version
            ),
            "locked_post_submit_checker_policy_hash": (
                submission.locked_post_submit_checker_policy_hash
            ),
            "locked_effective_project_submission_artifact_policy_id": (
                submission.locked_effective_project_submission_artifact_policy_id
            ),
            "locked_effective_project_submission_artifact_policy_hash": (
                submission.locked_effective_project_submission_artifact_policy_hash
            ),
            "locked_pre_submit_checker_policy_id": submission.locked_pre_submit_checker_policy_id,
            "locked_pre_submit_checker_bundle_hash": (
                submission.locked_pre_submit_checker_bundle_hash
            ),
        }

    async def _load_active_policy_context(
        self,
        project_id: str,
    ) -> tuple[
        ProjectGuide,
        PostSubmitCheckerPolicy,
        ReviewPolicy,
        RevisionPolicy,
        PaymentPolicy,
        GuideSourceSnapshot,
        EffectiveProjectSubmissionArtifactPolicy,
        PreSubmitCheckerPolicy,
    ]:
        """Load the active guide plus every policy needed for task locking.

        Args:
            project_id: Project whose active context should be loaded.

        Returns:
            Active guide and policy models.

        Raises:
            TaskProjectNotReady: If any required context is missing.
        """
        try:
            guide = await self._project_repo.get_active_guide(project_id)
            if guide is None:
                raise TaskProjectNotReady("project has no active guide")
            checker_policy = await self._project_repo.get_post_submit_checker_policy(
                project_id,
                guide.version,
            )
            review_policy = await self._project_repo.get_review_policy(project_id, guide.version)
            revision_policy = await self._project_repo.get_revision_policy(
                project_id,
                guide.version,
            )
            payment_policy = await self._project_repo.get_payment_policy(project_id, guide.version)
            submission_artifact_policy = (
                await self._project_repo.get_current_approved_submission_artifact_policy(
                    project_id,
                    guide.version,
                )
            )
            if (
                checker_policy is None
                or review_policy is None
                or revision_policy is None
                or payment_policy is None
                or submission_artifact_policy is None
            ):
                raise TaskProjectNotReady("active guide policy context is incomplete")
            source_snapshot = await self._project_repo.get_guide_source_snapshot(
                submission_artifact_policy.source_snapshot_id
            )
            if (
                source_snapshot is None
                or source_snapshot.bundle_hash != submission_artifact_policy.source_snapshot_hash
            ):
                raise TaskProjectNotReady("active guide source snapshot context is incomplete")
            effective_policy = await self._project_repo.get_effective_submission_artifact_policy(
                project_id,
                guide.version,
                source_snapshot.id,
            )
            if effective_policy is None:
                raise TaskProjectNotReady(
                    "active effective submission artifact policy is incomplete"
                )
            pre_submit_checker_policy = (
                await self._project_repo.get_pre_submit_checker_policy_for_effective_policy(
                    effective_policy.id
                )
            )
        except ProjectRepositoryIntegrityError as exc:
            raise TaskProjectNotReady("active guide policy context is ambiguous") from exc
        if (
            pre_submit_checker_policy is None
            or pre_submit_checker_policy.lifecycle_status != "compiled"
            or not pre_submit_checker_policy.compiled_bundle_hash
        ):
            raise TaskProjectNotReady("active project pre-submit checker policy is incomplete")
        if not checker_policy.policy_hash or not checker_policy.policy_body:
            raise TaskProjectNotReady("active post-submit checker policy hash is incomplete")
        try:
            parsed_checker_policy = parse_locked_post_submit_checker_policy_body(
                checker_policy.policy_body,
                project_id=checker_policy.project_id,
                guide_version=checker_policy.guide_version,
                policy_hash=checker_policy.policy_hash,
            )
        except ValueError as exc:
            raise TaskProjectNotReady("active post-submit checker policy hash is invalid") from exc
        if (
            parsed_checker_policy.required_checkers != checker_policy.required_checkers
            or parsed_checker_policy.warning_checkers != checker_policy.warning_checkers
            or parsed_checker_policy.blocking_severities != checker_policy.blocking_severities
        ):
            raise TaskProjectNotReady("active post-submit checker policy hash is invalid")
        return (
            guide,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
            source_snapshot,
            effective_policy,
            pre_submit_checker_policy,
        )

    async def _load_locked_task_context(self, task: WorkstreamTask) -> LockedTaskContext:
        """Load and validate every row stamped into a task's locked context.

        Args:
            task: Task whose locked context is authoritative.

        Returns:
            Validated locked task context rows.

        Raises:
            TaskLockedContextInvalid: If any stamped row is missing, stale, or
                inconsistent with the task's locked ids and hashes.
        """
        missing = self._missing_locked_context_fields(task)
        if missing:
            raise TaskLockedContextInvalid(
                "task locked context is incomplete",
                {"missing_fields": missing},
            )

        project = await self._project_repo.get_project(task.project_id)
        guide = await self._project_repo.get_guide_by_version(
            task.project_id,
            task.locked_guide_version or "",
        )
        if project is None or guide is None or guide.project_id != task.project_id:
            raise TaskLockedContextInvalid(
                "task locked guide context is invalid",
                {"field": "locked_guide_version"},
            )

        source_snapshot = await self._project_repo.get_guide_source_snapshot(
            task.locked_guide_source_snapshot_id or "",
        )
        if (
            source_snapshot is None
            or source_snapshot.project_id != task.project_id
            or source_snapshot.guide_version != task.locked_guide_version
            or source_snapshot.bundle_hash != task.locked_guide_source_snapshot_hash
            or canonical_json_hash(source_snapshot.manifest_json) != source_snapshot.bundle_hash
        ):
            raise TaskLockedContextInvalid(
                "task locked guide source snapshot is invalid",
                {"field": "locked_guide_source_snapshot_hash"},
            )

        effective_policy = (
            await self._project_repo.get_effective_submission_artifact_policy_by_id(
                task.locked_effective_project_submission_artifact_policy_id or "",
            )
        )
        if (
            effective_policy is None
            or effective_policy.project_id != task.project_id
            or effective_policy.guide_version != task.locked_guide_version
            or effective_policy.source_snapshot_id != source_snapshot.id
            or effective_policy.source_snapshot_hash != source_snapshot.bundle_hash
            or effective_policy.effective_policy_hash
            != task.locked_effective_project_submission_artifact_policy_hash
            or effective_policy.lifecycle_status not in {"approved", "superseded"}
            or canonical_json_hash(effective_policy.effective_policy)
            != task.locked_effective_project_submission_artifact_policy_hash
        ):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": "locked_effective_project_submission_artifact_policy_hash"},
            )

        pre_submit_checker_policy = await self._project_repo.get_pre_submit_checker_policy(
            task.locked_pre_submit_checker_policy_id or "",
        )
        compiled_bundle = (
            pre_submit_checker_policy.compiled_bundle
            if pre_submit_checker_policy is not None
            else None
        )
        if (
            pre_submit_checker_policy is None
            or pre_submit_checker_policy.project_id != task.project_id
            or pre_submit_checker_policy.guide_version != task.locked_guide_version
            or pre_submit_checker_policy.source_snapshot_id != source_snapshot.id
            or pre_submit_checker_policy.source_snapshot_hash != source_snapshot.bundle_hash
            or pre_submit_checker_policy.effective_policy_id != effective_policy.id
            or pre_submit_checker_policy.effective_policy_hash
            != effective_policy.effective_policy_hash
            or pre_submit_checker_policy.lifecycle_status not in {"compiled", "superseded"}
            or pre_submit_checker_policy.compiled_bundle_hash
            != task.locked_pre_submit_checker_bundle_hash
            or not isinstance(compiled_bundle, dict)
            or canonical_json_hash(compiled_bundle) != task.locked_pre_submit_checker_bundle_hash
        ):
            raise TaskLockedContextInvalid(
                "task locked project pre-submit checker policy is invalid",
                {"field": "locked_pre_submit_checker_bundle_hash"},
            )
        try:
            compiled_checker_names = validate_compiled_pre_submit_checker_bundle(
                effective_policy.effective_policy,
                effective_policy.effective_policy_hash,
                compiled_bundle,
                compiler_version=pre_submit_checker_policy.compiler_version,
            )
        except PreSubmitCheckerCompilerError as exc:
            raise TaskLockedContextInvalid(
                "task locked project pre-submit checker policy is invalid",
                {"field": "locked_pre_submit_checker_bundle_hash"},
            ) from exc
        if list(pre_submit_checker_policy.checker_names or []) != compiled_checker_names:
            raise TaskLockedContextInvalid(
                "task locked project pre-submit checker projection is invalid",
                {"field": "locked_pre_submit_checker_policy_id"},
            )

        post_submit_checker_policy = (
            await self._project_repo.get_post_submit_checker_policy_by_id(
                task.locked_post_submit_checker_policy_id or "",
            )
        )
        if (
            post_submit_checker_policy is None
            or post_submit_checker_policy.project_id != task.project_id
            or post_submit_checker_policy.guide_version
            != task.locked_post_submit_checker_policy_version
            or post_submit_checker_policy.guide_version != task.locked_guide_version
            or post_submit_checker_policy.policy_hash
            != task.locked_post_submit_checker_policy_hash
        ):
            raise TaskLockedContextInvalid(
                "task locked post-submit checker policy is invalid",
                {"field": "locked_post_submit_checker_policy_hash"},
            )
        try:
            parsed_post_submit_body = parse_locked_post_submit_checker_policy_body(
                task.locked_post_submit_checker_policy_body,
                project_id=task.project_id,
                guide_version=task.locked_post_submit_checker_policy_version or "",
                policy_hash=task.locked_post_submit_checker_policy_hash or "",
            )
        except ValueError as exc:
            raise TaskLockedContextInvalid(
                "task locked post-submit checker policy body is invalid",
                {"field": "locked_post_submit_checker_policy_body"},
            ) from exc
        post_submit_summary = PostSubmitPolicyBodySummary(
            schema_version=(task.locked_post_submit_checker_policy_body or {}).get(
                "schema_version"
            ),
            default_checkers=parsed_post_submit_body.default_checkers,
            required_checkers=parsed_post_submit_body.required_checkers,
            warning_checkers=parsed_post_submit_body.warning_checkers,
            execution_checkers=parsed_post_submit_body.execution_checkers,
            blocking_severities=parsed_post_submit_body.blocking_severities,
        )

        review_policy = await self._project_repo.get_review_policy(
            task.project_id,
            task.locked_review_policy_version or "",
        )
        revision_policy = await self._project_repo.get_revision_policy(
            task.project_id,
            task.locked_revision_policy_version or "",
        )
        payment_policy = await self._project_repo.get_payment_policy(
            task.project_id,
            task.locked_payment_policy_version or "",
        )
        if (
            review_policy is None
            or review_policy.guide_version != task.locked_guide_version
            or revision_policy is None
            or revision_policy.guide_version != task.locked_guide_version
            or payment_policy is None
            or payment_policy.guide_version != task.locked_guide_version
        ):
            raise TaskLockedContextInvalid(
                "task locked review, revision, or payment policy is invalid",
                {"field": "locked_policy_versions"},
            )

        return LockedTaskContext(
            project=project,
            guide=guide,
            source_snapshot=source_snapshot,
            effective_policy=effective_policy,
            pre_submit_checker_policy=pre_submit_checker_policy,
            post_submit_checker_policy=post_submit_checker_policy,
            locked_post_submit_policy_body=post_submit_summary,
            review_policy=review_policy,
            revision_policy=revision_policy,
            payment_policy=payment_policy,
        )

    def _missing_locked_context_fields(self, task: WorkstreamTask) -> list[str]:
        """Return missing locked-context fields for a task."""
        return [
            field
            for field in LOCKED_CONTEXT_REQUIRED_FIELDS
            if not getattr(task, field)
        ]

    def _work_context_response(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        context: LockedTaskContext,
        *,
        has_active_submitter_eligibility: bool,
    ) -> TaskWorkContextResponse:
        """Build the Contributor-safe work-context response."""
        return TaskWorkContextResponse(
            task=self._worker_safe_task_response(task),
            project=TaskProjectContext(
                id=context.project.id,
                name=context.project.name,
                slug=context.project.slug,
                description=context.project.description,
            ),
            guide=TaskGuideContext(
                id=context.guide.id,
                version=context.guide.version,
                content_markdown=context.guide.content_markdown,
                change_summary=context.guide.change_summary,
                effective_at=context.guide.effective_at,
            ),
            review_policy=TaskReviewPolicyContext(
                guide_version=task.locked_review_policy_version or "",
            ),
            revision_policy=TaskRevisionPolicyContext(
                guide_version=task.locked_revision_policy_version or "",
            ),
            payment_policy=TaskPaymentPolicyContext(
                guide_version=task.locked_payment_policy_version or "",
                base_amount=task.base_amount,
                currency=task.currency,
                payout_type=task.payout_type,
            ),
            lifecycle=self._worker_lifecycle_context(
                actor,
                task,
                has_active_submitter_eligibility=has_active_submitter_eligibility,
            ),
        )

    def _submission_requirements_response(
        self,
        task: WorkstreamTask,
        context: LockedTaskContext,
    ) -> SubmissionRequirementsResponse:
        """Build Contributor-facing requirements from the locked effective policy."""
        policy = context.effective_policy.effective_policy
        if not isinstance(policy, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": "effective_policy"},
            )
        allowed_storage_schemes = self._policy_string_list(
            policy,
            "allowed_storage_schemes",
        )
        required_artifacts = self._policy_list(policy, "required_artifacts")
        required_evidence = self._policy_list(policy, "required_evidence")
        forbidden_artifacts = self._policy_list(policy, "forbidden_artifacts")
        return SubmissionRequirementsResponse(
            task_id=task.id,
            project_id=task.project_id,
            guide_version=task.locked_guide_version or "",
            policy_schema_version=self._optional_policy_text(policy, "schema_version"),
            merge_algorithm_version=self._optional_policy_text(
                policy,
                "merge_algorithm_version",
            ),
            required_packet_fields=self._required_packet_fields(policy),
            required_artifacts=[
                RequiredArtifactRequirement(
                    key=self._policy_rule_text(rule, "key", "required_artifacts"),
                    path=self._policy_rule_text(rule, "path", "required_artifacts"),
                    hash_required=self._policy_rule_bool(
                        rule,
                        "hash_required",
                        "required_artifacts",
                    ),
                    required=self._policy_rule_bool(
                        rule,
                        "required",
                        "required_artifacts",
                    ),
                    description=self._optional_policy_rule_text(
                        rule,
                        "description",
                        "required_artifacts",
                    ),
                )
                for rule in required_artifacts
            ],
            required_evidence=[
                RequiredEvidenceRequirement(
                    key=self._policy_rule_text(rule, "key", "required_evidence"),
                    label=self._policy_rule_text(rule, "label", "required_evidence"),
                    hash_required=self._policy_rule_bool(
                        rule,
                        "hash_required",
                        "required_evidence",
                    ),
                    required=self._policy_rule_bool(
                        rule,
                        "required",
                        "required_evidence",
                    ),
                    description=self._optional_policy_rule_text(
                        rule,
                        "description",
                        "required_evidence",
                    ),
                )
                for rule in required_evidence
            ],
            forbidden_artifacts=[
                ForbiddenArtifactRequirement(
                    pattern=self._policy_rule_text(rule, "pattern", "forbidden_artifacts"),
                    reason=self._optional_policy_rule_text(
                        rule,
                        "reason",
                        "forbidden_artifacts",
                    ),
                    worker_facing_fix=self._optional_policy_rule_text(
                        rule,
                        "worker_facing_fix",
                        "forbidden_artifacts",
                    ),
                    severity=self._optional_policy_rule_text(
                        rule,
                        "severity",
                        "forbidden_artifacts",
                    ),
                )
                for rule in forbidden_artifacts
            ],
            attestation_terms=self._policy_string_list(policy, "attestation_terms"),
            manifest_required=self._policy_bool(policy, "manifest_required"),
            artifact_hash_required=self._policy_bool(policy, "artifact_hash_required"),
            artifact_hash_algorithm="sha256",
            allowed_storage_schemes=allowed_storage_schemes,
            storage_reference_rules=StorageReferenceRules(
                allowed_storage_schemes=allowed_storage_schemes,
                allowed_uri_prefixes=[f"{scheme}://" for scheme in allowed_storage_schemes],
                credentials_allowed=False,
                query_strings_allowed=False,
                fragments_allowed=False,
                path_traversal_allowed=False,
            ),
            maximum_file_size_bytes=self._optional_policy_non_negative_int(
                policy,
                "maximum_file_size_bytes",
            ),
            maximum_package_size_bytes=self._optional_policy_non_negative_int(
                policy,
                "maximum_package_size_bytes",
            ),
            packaging=self._policy_object(policy, "packaging"),
        )

    def _policy_list(self, policy: dict[str, Any], field: str) -> list[Any]:
        """Return a list field from the locked policy or fail closed."""
        value = policy.get(field, [])
        if not isinstance(value, list):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _policy_string_list(self, policy: dict[str, Any], field: str) -> list[str]:
        """Return a string-list field from the locked policy or fail closed."""
        values = self._policy_list(policy, field)
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise TaskLockedContextInvalid(
                    "task locked effective project submission artifact policy is invalid",
                    {"field": f"effective_policy.{field}"},
                )
            normalized.append(value.strip())
        return normalized

    def _policy_bool(self, policy: dict[str, Any], field: str) -> bool:
        """Return a boolean field from the locked policy or fail closed."""
        value = policy.get(field, True)
        if not isinstance(value, bool):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _policy_object(self, policy: dict[str, Any], field: str) -> dict[str, Any]:
        """Return an object field from the locked policy or fail closed."""
        value = policy.get(field, {})
        if not isinstance(value, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return dict(value)

    def _optional_policy_text(self, policy: dict[str, Any], field: str) -> str | None:
        """Return an optional text field from the locked policy or fail closed."""
        value = policy.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _optional_policy_non_negative_int(
        self,
        policy: dict[str, Any],
        field: str,
    ) -> int | None:
        """Return an optional non-negative integer from the locked policy."""
        value = policy.get(field)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _required_packet_fields(self, policy: dict[str, Any]) -> list[str]:
        """Return exact submission packet fields required by API and policy."""
        required_fields: list[str] = []
        policy_fields = policy.get("required_packet_fields", [])
        if not isinstance(policy_fields, list):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": "effective_policy.required_packet_fields"},
            )
        for field in (*SUBMISSION_CREATE_REQUIRED_PACKET_FIELDS, *policy_fields):
            if not isinstance(field, str) or not field.strip():
                raise TaskLockedContextInvalid(
                    "task locked effective project submission artifact policy is invalid",
                    {"field": "effective_policy.required_packet_fields"},
                )
            normalized = field.strip()
            if normalized not in required_fields:
                required_fields.append(normalized)
        return required_fields

    def _policy_rule_text(self, rule: object, key: str, collection: str) -> str:
        """Return a required text field from a locked policy rule or fail closed."""
        if not isinstance(rule, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}"},
            )
        value = rule.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}.{key}"},
            )
        return value

    def _optional_policy_rule_text(
        self,
        rule: object,
        key: str,
        collection: str,
    ) -> str | None:
        """Return an optional text field from a locked policy rule."""
        if not isinstance(rule, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}"},
            )
        value = rule.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}.{key}"},
            )
        return value

    def _policy_rule_bool(
        self,
        rule: object,
        key: str,
        collection: str,
    ) -> bool:
        """Return a boolean field from a locked policy rule or fail closed."""
        if not isinstance(rule, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}"},
            )
        value = rule.get(key, True)
        if not isinstance(value, bool):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}.{key}"},
            )
        return value

    def _locked_context_response(
        self,
        task: WorkstreamTask,
        context: LockedTaskContext,
    ) -> TaskLockedContextResponse:
        """Build the operator-only locked-context response."""
        return TaskLockedContextResponse(
            task_id=task.id,
            project_id=task.project_id,
            locked_guide_version=task.locked_guide_version or "",
            locked_guide_source_snapshot_id=task.locked_guide_source_snapshot_id or "",
            locked_guide_source_snapshot_hash=task.locked_guide_source_snapshot_hash or "",
            locked_effective_project_submission_artifact_policy_id=(
                task.locked_effective_project_submission_artifact_policy_id or ""
            ),
            locked_effective_project_submission_artifact_policy_hash=(
                task.locked_effective_project_submission_artifact_policy_hash or ""
            ),
            locked_pre_submit_checker_policy_id=task.locked_pre_submit_checker_policy_id or "",
            locked_pre_submit_checker_bundle_hash=(
                task.locked_pre_submit_checker_bundle_hash or ""
            ),
            locked_post_submit_checker_policy_id=(
                task.locked_post_submit_checker_policy_id or ""
            ),
            locked_post_submit_checker_policy_version=(
                task.locked_post_submit_checker_policy_version or ""
            ),
            locked_post_submit_checker_policy_hash=(
                task.locked_post_submit_checker_policy_hash or ""
            ),
            locked_post_submit_checker_policy_body_summary=(
                context.locked_post_submit_policy_body
            ),
            locked_review_policy_version=task.locked_review_policy_version or "",
            locked_revision_policy_version=task.locked_revision_policy_version or "",
            locked_payment_policy_version=task.locked_payment_policy_version or "",
        )

    def _worker_safe_task_response(self, task: WorkstreamTask) -> TaskWorkerTaskContext:
        """Build a task summary without private source/import provenance."""
        return TaskWorkerTaskContext(
            id=task.id,
            project_id=task.project_id,
            locked_guide_version=task.locked_guide_version or "",
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            difficulty=task.difficulty,
            skill_tags=list(task.skill_tags),
            estimated_time_minutes=task.estimated_time_minutes,
            base_amount=task.base_amount,
            currency=task.currency,
            payout_type=task.payout_type,
            status=task.status,
            acceptance_criteria=task.acceptance_criteria,
            rejection_criteria=task.rejection_criteria,
            deadline_at=task.deadline_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _worker_lifecycle_context(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        *,
        has_active_submitter_eligibility: bool,
    ) -> TaskWorkerLifecycleContext:
        """Build Contributor-facing lifecycle booleans and next actions."""
        assigned_to_current_actor = task.assigned_to == actor.actor_id
        can_submit = (
            has_active_submitter_eligibility
            and assigned_to_current_actor
            and task.status
            in {
                TASK_STATUS_IN_PROGRESS,
                TASK_STATUS_NEEDS_REVISION,
            }
        )
        next_actions: list[str] = []
        if (
            has_active_submitter_eligibility
            and task.status == TASK_STATUS_READY
            and task.assigned_to is None
        ):
            next_actions.append("claim")
        elif (
            has_active_submitter_eligibility
            and task.status == TASK_STATUS_CLAIMED
            and assigned_to_current_actor
        ):
            next_actions.append("start")
        elif can_submit:
            next_actions.extend(["run_pre_submit_check", "submit"])
        return TaskWorkerLifecycleContext(
            status=task.status,
            assigned_to_current_actor=assigned_to_current_actor,
            can_run_pre_submit_check=can_submit,
            can_submit=can_submit,
            next_actions=next_actions,
        )

    def _validate_task_contract_fields(self, task: WorkstreamTask) -> None:
        """Validate task source and reviewability fields before screening.

        Args:
            task: Task being screened.

        Raises:
            TaskValidationError: If one or more required fields are missing.
        """
        required_fields = {"title", "description", "acceptance_criteria"}
        field_values = {
            "title": task.title,
            "description": task.description,
            "acceptance_criteria": task.acceptance_criteria,
        }
        missing = [
            field
            for field in sorted(required_fields)
            if not self._field_has_value(field_values.get(field))
        ]
        if missing:
            raise TaskValidationError(f"task missing required fields: {', '.join(missing)}")

    @staticmethod
    def _field_has_value(value: object) -> bool:
        """Return whether a required field value is present.

        Args:
            value: Field value from the task model.

        Returns:
            ``True`` when the value should satisfy a required field.
        """
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list | tuple | set | dict):
            return bool(value)
        return True

    def _stamp_locked_context(
        self,
        task: WorkstreamTask,
        guide: ProjectGuide,
        checker_policy: PostSubmitCheckerPolicy,
        review_policy: ReviewPolicy,
        revision_policy: RevisionPolicy,
        payment_policy: PaymentPolicy,
        source_snapshot: GuideSourceSnapshot,
        effective_policy: EffectiveProjectSubmissionArtifactPolicy,
        pre_submit_checker_policy: PreSubmitCheckerPolicy,
    ) -> None:
        """Stamp server-owned guide and policy context onto a task.

        Args:
            task: Task receiving locked context.
            guide: Active guide.
            checker_policy: Checker policy for the guide version.
            review_policy: Review policy for the guide version.
            revision_policy: Revision policy for the guide version.
            payment_policy: Payment policy for the guide version.
            source_snapshot: Immutable guide source snapshot for the active setup.
            effective_policy: Effective project submission artifact policy.
            pre_submit_checker_policy: Compiled project pre-submit checker policy.
        """
        task.locked_guide_version = guide.version
        task.locked_post_submit_checker_policy_id = checker_policy.id
        task.locked_post_submit_checker_policy_version = checker_policy.guide_version
        task.locked_post_submit_checker_policy_hash = checker_policy.policy_hash
        task.locked_post_submit_checker_policy_body = dict(checker_policy.policy_body or {})
        task.locked_review_policy_version = review_policy.guide_version
        task.locked_revision_policy_version = revision_policy.guide_version
        task.locked_payment_policy_version = payment_policy.guide_version
        task.locked_guide_source_snapshot_id = source_snapshot.id
        task.locked_guide_source_snapshot_hash = source_snapshot.bundle_hash
        task.locked_effective_project_submission_artifact_policy_id = effective_policy.id
        task.locked_effective_project_submission_artifact_policy_hash = (
            effective_policy.effective_policy_hash
        )
        task.locked_pre_submit_checker_policy_id = pre_submit_checker_policy.id
        task.locked_pre_submit_checker_bundle_hash = (
            pre_submit_checker_policy.compiled_bundle_hash
        )
        task.base_amount = payment_policy.base_amount
        task.currency = payment_policy.currency
        task.payout_type = payment_policy.payout_type

    def _ensure_locked_context(self, task: WorkstreamTask) -> None:
        """Ensure all guide and policy version fields are locked.

        Args:
            task: Task whose locked context should be checked.

        Raises:
            TaskTransitionBlocked: If any context field is missing.
        """
        missing = self._missing_locked_context_fields(task)
        if missing:
            raise TaskTransitionBlocked(f"task missing locked context: {', '.join(missing)}")

    async def _validate_locked_post_submit_policy_context(self, task: WorkstreamTask) -> None:
        """Validate the task's locked post-submit checker policy before submission.

        Args:
            task: Task whose locked post-submit policy context should be
                verified before a submission row can be created.

        Raises:
            TaskProjectNotReady: If the locked post-submit policy row is
                missing, mismatched, or no longer hashes to the stamped value.
        """
        policy = await self._project_repo.get_post_submit_checker_policy_by_id(
            task.locked_post_submit_checker_policy_id or ""
        )
        if (
            policy is None
            or policy.project_id != task.project_id
            or policy.guide_version != task.locked_post_submit_checker_policy_version
            or policy.guide_version != task.locked_guide_version
            or policy.policy_hash != task.locked_post_submit_checker_policy_hash
        ):
            raise TaskProjectNotReady("locked post-submit checker policy is invalid")
        try:
            parse_locked_post_submit_checker_policy_body(
                task.locked_post_submit_checker_policy_body,
                project_id=task.project_id,
                guide_version=task.locked_post_submit_checker_policy_version or "",
                policy_hash=task.locked_post_submit_checker_policy_hash or "",
            )
        except ValueError as exc:
            raise TaskProjectNotReady("locked post-submit checker policy hash is invalid") from exc

    async def _require_legacy_submitter_eligibility(
        self,
        actor: ActorContext,
    ) -> LegacyWorkflowEligibility:
        """Require temporary active submitter eligibility for intake workflows.

        Args:
            actor: Verified Flow actor context.

        Returns:
            Persisted active legacy submitter eligibility.

        Raises:
            LegacySubmitterEligibilityRequired: If eligibility is absent or inactive.
        """
        profile = await self._legacy_workflow_eligibility.get_active_submitter_eligibility(
            actor.actor_id
        )
        if profile is None:
            raise LegacySubmitterEligibilityRequired(
                "active legacy submitter eligibility is required"
            )
        return profile

    async def _change_task_status(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        to_status: str,
        reason: str | None,
        event_payload: dict | None = None,
        event_type: str = "task_status_changed",
    ) -> None:
        """Apply a lifecycle transition and write the audit event.

        Args:
            actor: Verified Flow actor context.
            task: Task being transitioned.
            to_status: Next task status.
            reason: Optional transition reason for audit.
            event_payload: Structured event details to store with the audit event.
            event_type: Audit event type.
        """
        from_status = task.status
        self._ensure_transition_allowed(from_status, to_status)
        task.status = to_status
        await self._write_task_audit(
            actor,
            task,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            event_payload=event_payload,
        )

    async def _write_task_audit(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        reason: str | None,
        event_payload: dict | None = None,
    ) -> None:
        """Persist an actor-attributed task audit event.

        Args:
            actor: Verified Flow actor context.
            task: Task associated with the event.
            event_type: Type of audit event.
            from_status: Previous task status when applicable.
            to_status: New task status when applicable.
            reason: Optional event reason.
            event_payload: Optional structured event metadata.
        """
        audit = actor.audit_context()
        payload = {
            "locked_guide_version": task.locked_guide_version,
            "locked_post_submit_checker_policy_id": task.locked_post_submit_checker_policy_id,
            "locked_post_submit_checker_policy_version": (
                task.locked_post_submit_checker_policy_version
            ),
            "locked_post_submit_checker_policy_hash": task.locked_post_submit_checker_policy_hash,
            "locked_review_policy_version": task.locked_review_policy_version,
            "locked_revision_policy_version": task.locked_revision_policy_version,
            "locked_payment_policy_version": task.locked_payment_policy_version,
            "locked_guide_source_snapshot_id": task.locked_guide_source_snapshot_id,
            "locked_guide_source_snapshot_hash": task.locked_guide_source_snapshot_hash,
            "locked_effective_project_submission_artifact_policy_id": (
                task.locked_effective_project_submission_artifact_policy_id
            ),
            "locked_effective_project_submission_artifact_policy_hash": (
                task.locked_effective_project_submission_artifact_policy_hash
            ),
            "locked_pre_submit_checker_policy_id": task.locked_pre_submit_checker_policy_id,
            "locked_pre_submit_checker_bundle_hash": task.locked_pre_submit_checker_bundle_hash,
            "assigned_to": task.assigned_to,
        }
        if event_payload:
            payload.update(event_payload)
        await self._repo.add_audit_event(
            AuditEvent(
                id=str(uuid4()),
                entity_type="task",
                entity_id=task.id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                actor_id=audit.actor_id,
                external_subject=audit.external_subject,
                external_issuer=audit.external_issuer,
                actor_roles=list(audit.actor_roles),
                claim_snapshot=audit.claim_snapshot,
                auth_source=audit.auth_source,
                is_dev_auth=audit.is_dev_auth,
                reason=reason,
                event_payload=payload,
            )
        )

    async def _ensure_task_visible(self, actor: ActorContext, task: WorkstreamTask) -> None:
        """Apply object-level task visibility rules.

        Args:
            actor: Verified Flow actor context.
            task: Task being read.

        Raises:
            TaskNotFound: If the actor has no object-level visibility.
        """
        if can_admin_or_task_creator_manage(actor, task):
            return
        roles = set(actor.roles)
        if "worker" in roles:
            if task.status == TASK_STATUS_READY or task.assigned_to == actor.actor_id:
                return
        raise TaskNotFound("task not found")

    def _task_response(self, actor: ActorContext, task: WorkstreamTask) -> TaskResponse:
        """Build a role-sensitive task response.

        Args:
            actor: Verified actor reading the task.
            task: Persisted task model.

        Returns:
            Task response with internal locked policy hashes hidden from workers.
        """
        response = TaskResponse.model_validate(task)
        if not can_admin_or_task_creator_manage(actor, task):
            response.source_ref = None
            response.source_payload_hash = None
            response.import_batch_id = None
            response.external_task_id = None
            response.created_by = None
            response.assigned_to = None
            response.locked_guide_source_snapshot_id = None
            response.locked_guide_source_snapshot_hash = None
            response.locked_effective_project_submission_artifact_policy_id = None
            response.locked_effective_project_submission_artifact_policy_hash = None
            response.locked_pre_submit_checker_policy_id = None
            response.locked_pre_submit_checker_bundle_hash = None
        return response

    def _submission_response(
        self,
        actor: ActorContext,
        submission: Submission,
        *,
        has_operator_access: bool,
    ) -> SubmissionResponse:
        """Build a role-sensitive submission response.

        Args:
            actor: Verified actor reading the submission.
            submission: Persisted submission model.
            has_operator_access: Whether the actor has scoped operator access
                to the task that owns this submission.

        Returns:
            Submission response with artifact and policy provenance hidden from workers.
        """
        response = SubmissionResponse.model_validate(submission)
        if not has_operator_access:
            response.package_uri = None
            response.package_hash = None
            response.artifact_hash_manifest = None
            response.worker_attestation = None
            response.locked_guide_version = None
            response.locked_review_policy_version = None
            response.locked_revision_policy_version = None
            response.locked_payment_policy_version = None
            response.locked_guide_source_snapshot_id = None
            response.locked_guide_source_snapshot_hash = None
            response.locked_effective_project_submission_artifact_policy_id = None
            response.locked_effective_project_submission_artifact_policy_hash = None
            response.locked_pre_submit_checker_policy_id = None
            response.locked_pre_submit_checker_bundle_hash = None
            for evidence_item in response.evidence_items:
                evidence_item.uri = None
                evidence_item.hash = None
                evidence_item.metadata = {}
        return response

    def _audit_response(
        self,
        actor: ActorContext,
        event: AuditEvent,
        *,
        has_operator_access: bool,
    ) -> AuditEventResponse:
        """Build a public audit response with claim snapshots redacted.

        Args:
            actor: Verified actor reading the audit event.
            event: Persisted audit event.
            has_operator_access: Whether the actor has scoped operator access
                to the task that owns this audit event.

        Returns:
            Audit response safe for the current task audit endpoint.
        """
        response = AuditEventResponse.model_validate(event)
        response.claim_snapshot = {}
        if not has_operator_access:
            response.event_payload = {
                key: value
                for key, value in response.event_payload.items()
                if key in CONTRIBUTOR_VISIBLE_AUDIT_PAYLOAD_KEYS
            }
            if response.event_type in CONTRIBUTOR_REDACTED_AUDIT_EVENTS:
                response.event_type = "post_submit_checks_processing"
                response.from_status = None
                response.to_status = None
                response.actor_id = None
                response.external_subject = None
                response.external_issuer = None
                response.actor_roles = []
                response.auth_source = None
                response.is_dev_auth = None
                response.reason = None
        return response

    def _ensure_transition_allowed(self, from_status: str, to_status: str) -> None:
        """Map lifecycle transition validation into service-layer errors.

        Args:
            from_status: Current task status.
            to_status: Desired next task status.

        Raises:
            TaskTransitionBlocked: If the transition is not implemented by this chunk.
        """
        try:
            ensure_allowed_transition(from_status, to_status)
        except InvalidTaskTransition as exc:
            raise TaskTransitionBlocked(str(exc)) from exc
