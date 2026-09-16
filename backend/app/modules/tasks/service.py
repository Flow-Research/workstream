"""Service layer for task queue lifecycle and assignment operations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionDenied, require_any_role
from app.modules.checkers.api.pre_submit import (
    EffectivePreSubmissionPlanningPort, EffectivePreSubmissionPlanLineage,
)
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy, PostSubmitCatalogue
from app.modules.projects.api.locked_policy import (
    ProjectLockedPolicyContextFacts, ProjectLockedPolicyContextPort,
    ProjectLockedPolicyContextRequest, ProjectLockedPolicyContextUnavailable,
)
from app.modules.checkers.gate_queue import PreReviewGateQueueError, enqueue_pre_review_gate
from app.modules.checkers.pre_review_gate import (
    find_submission_requester_provenance,
    requester_provenance_payload,
)
from app.modules.checkers.service import (
    CheckerService,
    pre_review_gate_system_actor,
)
from app.modules.tasks.authorization import can_admin_or_task_creator_manage
from app.modules.tasks.lifecycle import (
    TASK_STATUS_DRAFT,
    TASK_STATUS_EVALUATION_PENDING,
    TASK_STATUS_READY,
    TASK_STATUS_SCREENING,
    TASK_STATUS_SUBMITTED,
    InvalidTaskTransition,
    ensure_allowed_transition,
)
from app.modules.tasks.models import (
    AuditEvent,
    Submission,
    WorkstreamTask,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    AuditEventResponse,
    ForbiddenArtifactRequirement,
    PostSubmitPolicyBodySummary,
    RequiredArtifactRequirement,
    RequiredEvidenceRequirement,
    StorageReferenceRules,
    SubmissionRequirementsResponse,
    SubmissionResponse,
    TaskCreate,
    TaskGuideContext,
    TaskLockedContextResponse,
    TaskProjectContext,
    TaskResponse,
    TaskReviewPolicyContext,
    TaskRevisionPolicyContext,
    TaskWorkerLifecycleContext,
    TaskWorkerTaskContext,
    TaskWorkContextResponse,
)
from app.schemas.auth import ActorContext

PROJECT_OPERATOR_ROLES = {"admin", "project_manager"}
TASK_VIEW_ROLES = {"admin", "project_manager", "worker"}
SUBMISSION_FINALIZE_ROLES = {"admin", "project_manager"}
SUBMISSION_FINALIZED_EVENT_TYPE = "submission_finalized"
PRE_REVIEW_GATE_DISPATCH_FAILED_EVENT_TYPE = "pre_review_gate_dispatch_failed"
CONTRIBUTOR_VISIBLE_AUDIT_PAYLOAD_KEYS = {
    "assignment_id",
    "locked_guide_version",
    "locked_review_policy_id",
    "locked_review_policy_generation",
    "locked_review_policy_hash",
    "locked_revision_policy_id",
    "locked_revision_policy_generation",
    "locked_revision_policy_hash",
    "locked_contribution_policy_version_id",
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
    "locked_review_policy_id",
    "locked_review_policy_generation",
    "locked_review_policy_hash",
    "locked_revision_policy_id",
    "locked_revision_policy_generation",
    "locked_revision_policy_hash",
    "locked_contribution_policy_version_id",
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

    facts: ProjectLockedPolicyContextFacts
    locked_post_submit_policy_body: PostSubmitPolicyBodySummary


class TaskService:
    """Coordinates task lifecycle rules, assignment, and audit writes."""

    def __init__(
        self, session: AsyncSession, *, project_contexts: ProjectLockedPolicyContextPort,
        pre_submit_planner: EffectivePreSubmissionPlanningPort, post_submit_catalogue: Callable[[], PostSubmitCatalogue],
    ) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
        """
        self._project_contexts = project_contexts
        self._pre_submit_planner = pre_submit_planner
        self._post_submit_catalogue = post_submit_catalogue
        self._session = session
        self._repo = TaskRepository(session)

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
        try:
            project_identity = UUID(project_id)
        except ValueError as exc:
            raise TaskProjectNotReady("project not found") from exc
        if str(project_identity) != project_id:
            raise TaskProjectNotReady("project not found")
        project = await self._project_contexts.read_project_display(project_identity)
        if project is None or project.id != project_identity:
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
        task = await self._get_task(task_id, for_update=True)
        self._ensure_transition_allowed(task.status, TASK_STATUS_SCREENING)

        facts = await self._load_active_policy_context(task.project_id)
        self._validate_task_contract_fields(task)
        self._stamp_locked_context(task, facts)
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
        task = await self._get_task(task_id, for_update=True)
        self._ensure_transition_allowed(task.status, TASK_STATUS_READY)
        if reason is None or not reason.strip():
            raise TaskValidationError("release decision reason is required")
        self._ensure_locked_context(task)
        context = await self._load_locked_task_context(task)
        self._validate_installed_plans(context.facts)
        await self._change_task_status(actor, task, TASK_STATUS_READY, reason)
        await self._session.commit()
        await self._session.refresh(task)
        return self._task_response(actor, task)

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

    async def _load_active_policy_context(self, project_id: str) -> ProjectLockedPolicyContextFacts:
        """Resolve exact activated custody and verify both installed checker plans."""
        try:
            facts = await self._project_contexts.lock_active_policy_context(UUID(project_id))
            self._validate_installed_plans(facts)
            return facts
        except (ProjectLockedPolicyContextUnavailable, ValueError) as exc:
            raise TaskProjectNotReady("active guide policy context is unavailable") from exc

    def _validate_installed_plans(self, facts: ProjectLockedPolicyContextFacts) -> None:
        """Check deployment capability before new readiness, without executing checks."""
        try:
            self._pre_submit_planner.compile_effective_plan(
                lineage=EffectivePreSubmissionPlanLineage(
                    project_id=facts.project_id, guide_id=facts.guide_id,
                    guide_version=facts.guide_version, source_snapshot_id=facts.source_snapshot_id,
                    source_snapshot_hash=facts.source_snapshot_hash,
                    effective_policy_id=facts.effective_policy_id,
                    effective_policy_hash=facts.effective_policy_hash,
                    pre_submit_policy_id=facts.pre_submit_policy_id,
                    pre_submit_policy_bundle_hash=facts.pre_submit_policy_bundle_hash,
                ),
                effective_policy=json.loads(facts.effective_policy.value),
                compiled_bundle=json.loads(facts.compiled_pre_submit_bundle.value),
            )
            CompiledPostSubmitPolicy.model_validate_json(
                facts.compiled_post_submit_policy.value,
            ).validate_catalogue(self._post_submit_catalogue())
        except ValueError as exc:
            raise TaskProjectNotReady("installed checkers cannot execute the locked policies") from exc

    async def _load_locked_task_context(self, task: WorkstreamTask) -> LockedTaskContext:
        """Resolve frozen custody without selecting current policy or deployment capabilities."""
        missing = self._missing_locked_context_fields(task)
        if missing:
            raise TaskLockedContextInvalid("task locked context is incomplete", {"missing_fields": missing})
        try:
            facts = await self._project_contexts.lock_locked_policy_context(
                ProjectLockedPolicyContextRequest(
                    project_id=UUID(task.project_id), guide_version=task.locked_guide_version,
                    source_snapshot_id=UUID(task.locked_guide_source_snapshot_id),
                    source_snapshot_hash=task.locked_guide_source_snapshot_hash,
                    effective_policy_id=UUID(task.locked_effective_project_submission_artifact_policy_id),
                    effective_policy_hash=task.locked_effective_project_submission_artifact_policy_hash,
                    pre_submit_policy_id=UUID(task.locked_pre_submit_checker_policy_id),
                    pre_submit_policy_bundle_hash=task.locked_pre_submit_checker_bundle_hash,
                ),
            )
            expected = self._policy_stamps(facts)
            if any(getattr(task, name) != value for name, value in expected.items()):
                raise ValueError("task policy stamps differ from activation receipt")
            parsed = CompiledPostSubmitPolicy.model_validate_json(facts.compiled_post_submit_policy.value)
        except (ProjectLockedPolicyContextUnavailable, ValueError, TypeError) as exc:
            raise TaskLockedContextInvalid("task locked policy custody is invalid") from exc
        return LockedTaskContext(
            facts=facts,
            locked_post_submit_policy_body=PostSubmitPolicyBodySummary(
                schema_version=parsed.schema_version, default_checkers=parsed.default_checkers,
                required_checkers=parsed.required_checkers, warning_checkers=parsed.warning_checkers,
                execution_checkers=parsed.execution_checkers,
                blocking_severities=list(parsed.blocking_severities),
            ),
        )

    def _missing_locked_context_fields(self, task: WorkstreamTask) -> list[str]:
        """Return missing locked-context fields for a task."""
        return [field for field in LOCKED_CONTEXT_REQUIRED_FIELDS if not getattr(task, field)]

    def _work_context_response(
        self,
        task: WorkstreamTask,
        context: LockedTaskContext,
        *,
        lifecycle: TaskWorkerLifecycleContext,
    ) -> TaskWorkContextResponse:
        """Build the Contributor-safe work-context response."""
        return TaskWorkContextResponse(
            task=self._worker_safe_task_response(task),
            project=TaskProjectContext(
                id=str(context.facts.project.id),
                name=context.facts.project.name,
                slug=context.facts.project.slug,
                description=context.facts.project.description,
            ),
            guide=TaskGuideContext(
                id=str(context.facts.guide.id),
                version=context.facts.guide.version,
                change_summary=context.facts.guide.change_summary,
                effective_at=context.facts.guide.effective_at,
            ),
            review_policy=TaskReviewPolicyContext(
                policy_id=task.locked_review_policy_id or "",
                policy_generation=task.locked_review_policy_generation or 0,
                policy_hash=task.locked_review_policy_hash or "",
            ),
            revision_policy=TaskRevisionPolicyContext(
                policy_id=task.locked_revision_policy_id or "",
                policy_generation=task.locked_revision_policy_generation or 0,
                policy_hash=task.locked_revision_policy_hash or "",
            ),
            lifecycle=lifecycle,
        )

    def _submission_requirements_response(
        self,
        task: WorkstreamTask,
        context: LockedTaskContext,
    ) -> SubmissionRequirementsResponse:
        """Build Contributor-facing requirements from the locked effective policy."""
        policy = json.loads(context.facts.effective_policy.value)
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
            maximum_archive_entries=self._optional_policy_non_negative_int(
                policy, "maximum_archive_entries", minimum=1,
            ),
            maximum_archive_size_bytes=self._optional_policy_non_negative_int(
                policy, "maximum_archive_size_bytes", minimum=1,
            ),
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
        *, minimum: int = 0,
    ) -> int | None:
        """Return an optional non-negative integer from the locked policy."""
        value = policy.get(field)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
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
            locked_post_submit_checker_policy_id=(task.locked_post_submit_checker_policy_id or ""),
            locked_post_submit_checker_policy_version=(
                task.locked_post_submit_checker_policy_version or ""
            ),
            locked_post_submit_checker_policy_hash=(
                task.locked_post_submit_checker_policy_hash or ""
            ),
            locked_post_submit_checker_policy_body_summary=(context.locked_post_submit_policy_body),
            locked_review_policy_id=task.locked_review_policy_id or "",
            locked_review_policy_generation=task.locked_review_policy_generation or 0,
            locked_review_policy_hash=task.locked_review_policy_hash or "",
            locked_revision_policy_id=task.locked_revision_policy_id or "",
            locked_revision_policy_generation=task.locked_revision_policy_generation or 0,
            locked_revision_policy_hash=task.locked_revision_policy_hash or "",
            locked_contribution_policy_version_id=task.locked_contribution_policy_version_id,
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

    @staticmethod
    def _policy_stamps(facts: ProjectLockedPolicyContextFacts) -> dict[str, object]:
        """Project the single activation receipt and exact frozen inputs onto TASK locks."""
        command = facts.activation_receipt.command
        return {
            "locked_contribution_policy_version_id": command.contribution_policy_version_id,
            "locked_guide_version": facts.guide_version,
            "locked_post_submit_checker_policy_id": str(command.target.policy_id),
            "locked_post_submit_checker_policy_version": facts.guide_version,
            "locked_post_submit_checker_policy_hash": command.target.policy_hash,
            "locked_post_submit_checker_policy_body": json.loads(facts.compiled_post_submit_policy.value),
            "locked_review_policy_id": str(command.review.policy_id),
            "locked_review_policy_generation": command.review.generation,
            "locked_review_policy_hash": command.review.policy_hash,
            "locked_revision_policy_id": str(command.revision.policy_id),
            "locked_revision_policy_generation": command.revision.generation,
            "locked_revision_policy_hash": command.revision.policy_hash,
            "locked_guide_source_snapshot_id": str(facts.source_snapshot_id),
            "locked_guide_source_snapshot_hash": facts.source_snapshot_hash,
            "locked_effective_project_submission_artifact_policy_id": str(facts.effective_policy_id),
            "locked_effective_project_submission_artifact_policy_hash": facts.effective_policy_hash,
            "locked_pre_submit_checker_policy_id": str(facts.pre_submit_policy_id),
            "locked_pre_submit_checker_bundle_hash": facts.pre_submit_policy_bundle_hash,
        }

    def _stamp_locked_context(self, task: WorkstreamTask, facts: ProjectLockedPolicyContextFacts) -> None:
        """Copy the exact activated context without obsolete PaymentPolicy readiness."""
        for name, value in self._policy_stamps(facts).items():
            setattr(task, name, value)

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
            "locked_review_policy_id": task.locked_review_policy_id,
            "locked_review_policy_generation": task.locked_review_policy_generation,
            "locked_review_policy_hash": task.locked_review_policy_hash,
            "locked_revision_policy_id": task.locked_revision_policy_id,
            "locked_revision_policy_generation": task.locked_revision_policy_generation,
            "locked_revision_policy_hash": task.locked_revision_policy_hash,
            "locked_contribution_policy_version_id": (
                str(task.locked_contribution_policy_version_id)
                if task.locked_contribution_policy_version_id else None
            ),
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
        return self.task_response_for_authority(task, can_manage=can_admin_or_task_creator_manage(actor, task))

    @staticmethod
    def task_response_for_authority(task: WorkstreamTask, *, can_manage: bool) -> TaskResponse:
        """Use an explicit authorized projection, never inferred token roles."""
        response = TaskResponse.model_validate(task)
        if not can_manage:
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
            response.locked_review_policy_id = None
            response.locked_review_policy_generation = None
            response.locked_review_policy_hash = None
            response.locked_revision_policy_id = None
            response.locked_revision_policy_generation = None
            response.locked_revision_policy_hash = None
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
