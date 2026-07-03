"""Service layer for task queue lifecycle and assignment operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_any_role
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
)
from app.modules.projects.post_submit_policy import (
    parse_locked_post_submit_checker_policy_body,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.tasks.lifecycle import (
    TASK_STATUS_CLAIMED,
    TASK_STATUS_DRAFT,
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
    ReviewerProfile,
    Submission,
    TaskAssignment,
    WorkerProfile,
    WorkstreamTask,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    AssignmentResponse,
    AuditEventResponse,
    SubmissionCreate,
    SubmissionResponse,
    TaskCreate,
    TaskResponse,
    TaskWithAssignmentResponse,
)
from app.schemas.auth import ActorContext

PROJECT_OPERATOR_ROLES = {"admin", "project_manager"}
TASK_VIEW_ROLES = {"admin", "project_manager", "worker"}
TASK_CLAIM_ROLES = {"worker"}
TASK_SUBMIT_ROLES = {"worker"}
TASK_START_ROLES = {"admin", "project_manager", "worker"}
TASK_START_OPERATOR_ROLES = {"admin", "project_manager"}
SUBMISSION_LOCK_ROLES = {"admin", "project_manager"}
WORKER_VISIBLE_AUDIT_PAYLOAD_KEYS = {
    "assignment_id",
    "locked_guide_version",
    "locked_review_policy_version",
    "locked_revision_policy_version",
    "locked_payment_policy_version",
    "source_type",
    "submission_id",
    "submission_version",
    "supersedes_submission_id",
    "worker_id",
}
WORKER_REDACTED_AUDIT_EVENTS = {
    "pre_review_gate_started",
    "pre_review_gate_passed",
    "pre_review_gate_needs_revision",
    "pre_review_gate_blocked",
}


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
    """Raised when a task already has an active worker assignment."""

    status_code = 409


class WorkerProfileRequired(TaskServiceError):
    """Raised when a worker tries to claim without an active worker profile."""

    status_code = 403


class SubmissionNotFound(TaskServiceError):
    """Raised when a submission id does not match a stored packet."""

    status_code = 404


class SubmissionVersionConflict(TaskServiceError):
    """Raised when concurrent submission version allocation conflicts."""

    status_code = 409


class SubmissionCheckerGateError(TaskServiceError):
    """Raised when automatic checker gate execution blocks submission locking."""

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
            required_files=payload.required_files,
            required_evidence=payload.required_evidence,
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
        self._validate_required_task_fields(task, guide)
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
        await self._validate_locked_post_submit_policy_context(task)
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
        task = await self._get_task(task_id)
        self._ensure_transition_allowed(task.status, TASK_STATUS_CLAIMED)
        await self._require_active_worker_profile(actor)
        if await self._repo.get_active_assignment(task_id) is not None:
            raise TaskAssignmentConflict("task already has an active assignment")

        assignment = TaskAssignment(
            id=str(uuid4()),
            task_id=task.id,
            worker_id=actor.actor_id,
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
                event_payload={"assignment_id": assignment.id, "worker_id": assignment.worker_id},
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
        is_operator_override = assignment.worker_id != actor.actor_id and bool(
            set(actor.roles).intersection(TASK_START_OPERATOR_ROLES)
        )
        if assignment.worker_id != actor.actor_id and not is_operator_override:
            raise TaskTransitionBlocked("actor is not assigned to this task")
        if is_operator_override and (reason is None or not reason.strip()):
            raise TaskValidationError("operator start override reason is required")
        await self._change_task_status(
            actor,
            task,
            TASK_STATUS_IN_PROGRESS,
            reason,
            event_payload={
                "assignment_id": assignment.id,
                "worker_id": assignment.worker_id,
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
            payload: Submission packet fields supplied by the worker.

        Returns:
            Created submission response with evidence items.

        Raises:
            PermissionDenied: If the actor cannot create worker submissions.
            TaskProjectNotReady: If locked project policy context is invalid.
            TaskTransitionBlocked: If task state or assignment does not allow submission.
            TaskValidationError: If required submission fields are missing.
            SubmissionVersionConflict: If concurrent version allocation conflicts.
        """
        require_any_role(actor, TASK_SUBMIT_ROLES)
        task = await self._get_task(task_id)
        await self._require_active_worker_profile(actor)
        assignment = await self._repo.get_active_assignment(task_id)
        if assignment is None:
            raise TaskTransitionBlocked("task has no active assignment")
        if assignment.worker_id != actor.actor_id or task.assigned_to != actor.actor_id:
            raise TaskTransitionBlocked("actor is not assigned to this task")
        if task.status not in {
            TASK_STATUS_IN_PROGRESS,
            TASK_STATUS_NEEDS_REVISION,
        }:
            raise TaskTransitionBlocked(
                "task must be in progress or needs revision before submission"
            )
        self._ensure_locked_context(task)
        await self._validate_locked_post_submit_policy_context(task)

        from app.modules.checkers.service import CheckerService, CheckerServiceError

        try:
            pre_submit_response = await CheckerService(self._session).pre_submit_check(
                actor,
                task_id,
                payload,
            )
        except CheckerServiceError as exc:
            raise SubmissionCheckerGateError(str(exc), exc.status_code) from exc
        if not pre_submit_response.eligible_to_submit:
            raise PreSubmissionCheckerFailed(
                pre_submit_response.model_dump(mode="json"),
            )

        latest_submission = await self._repo.get_latest_submission_for_task(task.id)
        next_version = 1 if latest_submission is None else latest_submission.version + 1
        submission = Submission(
            id=str(uuid4()),
            task_id=task.id,
            worker_id=actor.actor_id,
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
            locked_checker_policy_version=task.locked_checker_policy_version,
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
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise SubmissionVersionConflict("submission version conflicted; retry") from exc

        persisted = await self._repo.get_submission(submission.id)
        if persisted is None:
            raise SubmissionNotFound("submission not found")
        return self._submission_response(actor, persisted)

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
        return [self._submission_response(actor, submission) for submission in submissions]

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
        return self._submission_response(actor, submission)

    async def lock_submission(
        self,
        actor: ActorContext,
        submission_id: str,
    ) -> SubmissionResponse:
        """Lock the latest submission packet before checker execution.

        Args:
            actor: Verified Flow actor context for the current request.
            submission_id: Submission id to lock.

        Returns:
            Locked submission response.

        Raises:
            PermissionDenied: If the actor cannot lock submissions.
            TaskTransitionBlocked: If the submission is stale or task state is invalid.
        """
        require_any_role(actor, SUBMISSION_LOCK_ROLES)
        submission = await self._get_submission(submission_id)
        task = await self._get_task(submission.task_id)
        latest_submission = await self._repo.get_latest_submission_for_task(task.id)
        if latest_submission is None or latest_submission.id != submission.id:
            raise TaskTransitionBlocked("only latest submission version can be locked")
        if submission.locked_at is not None:
            return self._submission_response(actor, submission)
        if task.status != TASK_STATUS_SUBMITTED:
            raise TaskTransitionBlocked("task must be submitted before locking submission")

        locked_at = datetime.now(UTC)
        submission.locked_at = locked_at
        await self._repo.lock_submission_evidence(submission.id, locked_at)
        await self._write_task_audit(
            actor,
            task,
            event_type="submission_locked",
            from_status=task.status,
            to_status=task.status,
            reason=None,
            event_payload=self._submission_audit_payload(submission),
        )
        from app.modules.checkers.service import CheckerService, CheckerServiceError

        try:
            await CheckerService(self._session).run_submission_checkers(
                actor,
                submission.id,
                "submission locked pre-review gate",
                trigger_source="submission_locked",
            )
        except CheckerServiceError as exc:
            await self._session.rollback()
            raise SubmissionCheckerGateError(str(exc), exc.status_code) from exc
        persisted = await self._repo.get_submission(submission.id)
        if persisted is None:
            raise SubmissionNotFound("submission not found")
        return self._submission_response(actor, persisted)

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
        return [self._audit_response(actor, event) for event in events]

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

    async def _get_task(self, task_id: str) -> WorkstreamTask:
        """Load a task or raise a service error.

        Args:
            task_id: Task id to load.

        Returns:
            Matching task model.

        Raises:
            TaskNotFound: If the task id is unknown.
        """
        task = await self._repo.get_task(task_id)
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
            "worker_id": submission.worker_id,
            "package_hash": submission.package_hash,
            "artifact_hash_manifest": submission.artifact_hash_manifest,
            "supersedes_submission_id": submission.supersedes_submission_id,
            "locked_at": submission.locked_at.isoformat() if submission.locked_at else None,
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

    def _validate_required_task_fields(self, task: WorkstreamTask, guide: ProjectGuide) -> None:
        """Validate guide-required task fields before screening.

        Args:
            task: Task being screened.
            guide: Active guide defining required task fields.

        Raises:
            TaskValidationError: If one or more required fields are missing.
        """
        required_fields = set(guide.required_task_fields or [])
        required_fields.update({"title", "description", "acceptance_criteria"})
        field_values = {
            "title": task.title,
            "description": task.description,
            "task_type": task.task_type,
            "difficulty": task.difficulty,
            "skill_tags": task.skill_tags,
            "estimated_time_minutes": task.estimated_time_minutes,
            "acceptance_criteria": task.acceptance_criteria,
            "rejection_criteria": task.rejection_criteria,
            "required_files": task.required_files,
            "required_evidence": task.required_evidence,
            "deadline_at": task.deadline_at,
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
        task.locked_checker_policy_version = checker_policy.guide_version
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
        missing = [
            field
            for field in (
                "locked_guide_version",
                "locked_checker_policy_version",
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
            if not getattr(task, field)
        ]
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

    async def _require_active_worker_profile(
        self,
        actor: ActorContext,
    ) -> WorkerProfile:
        """Require an active worker profile before claim.

        Args:
            actor: Verified Flow actor context.

        Returns:
            Persisted active worker profile.

        Raises:
            WorkerProfileRequired: If the actor has no active worker profile.
        """
        profile = await self._repo.get_worker_profile(actor.actor_id)
        if profile is None or profile.status != "active":
            raise WorkerProfileRequired("active worker profile is required to claim task")
        return profile

    async def ensure_reviewer_profile(
        self,
        actor: ActorContext,
        skill_tags: list[str],
    ) -> ReviewerProfile:
        """Create or refresh a reviewer profile for the current actor.

        Args:
            actor: Verified Flow actor context.
            skill_tags: Skill tags to associate with the reviewer.

        Returns:
            Persisted reviewer profile.
        """
        require_any_role(actor, {"admin", "project_manager", "reviewer"})
        return await self._repo.upsert_reviewer_profile(
            ReviewerProfile(
                id=str(uuid4()),
                actor_id=actor.actor_id,
                external_subject=actor.external_subject,
                external_issuer=actor.external_issuer,
                display_name=actor.display_name,
                email=actor.email,
                skill_tags=skill_tags,
                status="active",
            )
        )

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
            "locked_checker_policy_version": task.locked_checker_policy_version,
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
        roles = set(actor.roles)
        if roles.intersection({"admin", "project_manager"}):
            return
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
        if not set(actor.roles).intersection(PROJECT_OPERATOR_ROLES):
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
    ) -> SubmissionResponse:
        """Build a role-sensitive submission response.

        Args:
            actor: Verified actor reading the submission.
            submission: Persisted submission model.

        Returns:
            Submission response with artifact and policy provenance hidden from workers.
        """
        response = SubmissionResponse.model_validate(submission)
        if not set(actor.roles).intersection(PROJECT_OPERATOR_ROLES):
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

    def _audit_response(self, actor: ActorContext, event: AuditEvent) -> AuditEventResponse:
        """Build a public audit response with claim snapshots redacted.

        Args:
            actor: Verified actor reading the audit event.
            event: Persisted audit event.

        Returns:
            Audit response safe for the current task audit endpoint.
        """
        response = AuditEventResponse.model_validate(event)
        response.claim_snapshot = {}
        if not set(actor.roles).intersection(PROJECT_OPERATOR_ROLES):
            response.event_payload = {
                key: value
                for key, value in response.event_payload.items()
                if key in WORKER_VISIBLE_AUDIT_PAYLOAD_KEYS
            }
            if response.event_type in WORKER_REDACTED_AUDIT_EVENTS:
                response.event_type = "post_submit_checks_processing"
                response.from_status = None
                response.to_status = None
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
