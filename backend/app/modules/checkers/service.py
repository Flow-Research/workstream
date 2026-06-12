"""Service layer for checker feedback, execution, and visibility."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_any_role
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.checkers.repository import CheckerRepository
from app.modules.checkers.runner import (
    CheckerContext,
    CheckerOutcome,
    ROUTING_TASK_SETUP_BLOCKED,
    UnknownChecker,
    canonical_artifact_manifest_hash,
    default_checker_registry,
    pre_submit_static_feedback,
)
from app.modules.checkers.schemas import (
    CheckerFeedbackItem,
    CheckerResultResponse,
    CheckerRunResponse,
    PreSubmitCheckResponse,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.lifecycle import (
    InvalidTaskTransition,
    TASK_STATUS_AUTO_CHECKING,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NEEDS_REVISION,
    TASK_STATUS_REVIEW_PENDING,
    TASK_STATUS_SUBMITTED,
    ensure_allowed_transition,
)
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import SubmissionCreate
from app.schemas.auth import ActorContext

CHECKER_TRIGGER_ROLES = {"admin", "project_manager"}
CHECKER_READ_ROLES = {"admin", "project_manager", "worker"}
ROUTING_ALLOW_REVIEW = "allow_review"
ROUTING_NEEDS_REVISION = "needs_revision"
ROUTING_CHECKER_RETRY = "checker_retry"
CHECKER_RUN_ALLOWED_TASK_STATUSES = {
    TASK_STATUS_SUBMITTED,
    TASK_STATUS_AUTO_CHECKING,
    TASK_STATUS_REVIEW_PENDING,
}
INTERNAL_ROUTING_RECOMMENDATIONS = {
    ROUTING_CHECKER_RETRY,
    ROUTING_TASK_SETUP_BLOCKED,
}
DEFAULT_DURABLE_CHECKERS = [
    "check_submission_packet",
    "check_policy_context_present",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
    "check_low_quality_generated_artifacts",
]


class CheckerServiceError(Exception):
    """Base class for checker service errors."""

    status_code = 400


class CheckerRunNotFound(CheckerServiceError):
    """Raised when a checker run id is unknown or hidden."""

    status_code = 404


class CheckerSubmissionNotFound(CheckerServiceError):
    """Raised when a submission id is unknown or hidden."""

    status_code = 404


class CheckerTaskNotFound(CheckerServiceError):
    """Raised when a task id is unknown or hidden."""

    status_code = 404


class CheckerExecutionBlocked(CheckerServiceError):
    """Raised when a checker run cannot be created for the current state."""

    status_code = 409


class CheckerPolicyInvalid(CheckerServiceError):
    """Raised when locked checker policy names cannot be resolved."""

    status_code = 422


class CheckerConflict(CheckerServiceError):
    """Raised when concurrent checker run attempts conflict."""

    status_code = 409


class CheckerService:
    """Coordinates checker feedback, durable runs, and result redaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a checker service bound to one database session.

        Args:
            session: Async SQLAlchemy session for this request.
        """
        self._session = session
        self._task_repo = TaskRepository(session)
        self._project_repo = ProjectRepository(session)
        self._checker_repo = CheckerRepository(session)
        self._registry = default_checker_registry()

    async def pre_submit_check(
        self,
        actor: ActorContext,
        task_id: str,
        payload: SubmissionCreate,
    ) -> PreSubmitCheckResponse:
        """Return non-authoritative static feedback for a draft submission.

        Args:
            actor: Trusted actor resolved from the Flow token.
            task_id: Task receiving the draft submission.
            payload: Draft submission packet payload.

        Returns:
            Worker-facing pre-submit feedback.
        """
        task = await self._get_task_for_actor(actor, task_id)
        if "worker" in actor.roles and task.status != TASK_STATUS_IN_PROGRESS:
            raise CheckerExecutionBlocked("task must be in progress for worker pre-submit checks")
        outcomes = await pre_submit_static_feedback(task, payload)
        eligible_to_submit = not any(outcome.blocks_review for outcome in outcomes)
        return PreSubmitCheckResponse(
            task_id=task.id,
            status="passed" if eligible_to_submit else "failed",
            eligible_to_submit=eligible_to_submit,
            results=[self._feedback_item(outcome) for outcome in outcomes],
        )

    async def run_submission_checkers(
        self,
        actor: ActorContext,
        submission_id: str,
        trigger_reason: str,
        trigger_source: str = "manual_checker_trigger",
    ) -> CheckerRunResponse:
        """Run registered checkers against one locked submission.

        Args:
            actor: Trusted admin or project manager actor resolved from the Flow token.
            submission_id: Submission whose latest locked packet should be checked.
            trigger_reason: Audit reason for the manual v0.1 trigger.
            trigger_source: Durable source label for the checker run.

        Returns:
            Persisted checker run response.

        Raises:
            PermissionDenied: If the actor cannot trigger internal checks.
            CheckerExecutionBlocked: If the submission is not locked or not checkable.
            CheckerPolicyInvalid: If the locked checker policy references unknown names.
        """
        require_any_role(actor, CHECKER_TRIGGER_ROLES)
        submission = await self._get_submission(submission_id)
        task = await self._get_task_for_actor(actor, submission.task_id)
        if submission.locked_at is None:
            raise CheckerExecutionBlocked("submission must be locked before internal checkers run")
        if task.status not in CHECKER_RUN_ALLOWED_TASK_STATUSES:
            raise CheckerExecutionBlocked("task must be submitted or in checker gate before checkers run")
        latest_submission = await self._task_repo.get_latest_submission_for_task(task.id)
        if latest_submission is None or latest_submission.id != submission.id:
            raise CheckerExecutionBlocked("only latest submission version can be checked")

        checker_policy = await self._project_repo.get_checker_policy(
            task.project_id,
            submission.locked_checker_policy_version,
        )
        if checker_policy is None:
            raise CheckerPolicyInvalid("locked checker policy not found")

        required_names = list(checker_policy.required_checkers or [])
        warning_names = list(checker_policy.warning_checkers or [])
        checker_names = list(
            dict.fromkeys(
                [
                    *DEFAULT_DURABLE_CHECKERS,
                    *required_names,
                    *warning_names,
                ]
            )
        )
        try:
            self._registry.require_registered(set(checker_names))
        except UnknownChecker as exc:
            raise CheckerPolicyInvalid(str(exc)) from exc
        try:
            artifact_manifest_hash = canonical_artifact_manifest_hash(
                submission.artifact_hash_manifest,
            )
        except ValueError:
            artifact_manifest_hash = "invalid:artifact_manifest"

        current_run = await self._checker_repo.get_current_run_for_submission(submission.id)
        if current_run is not None:
            current_run.is_current_for_submission = False
        attempt_number = 1 if current_run is None else current_run.attempt_number + 1
        await self._enter_auto_checking(
            actor,
            task,
            submission,
            trigger_reason,
            trigger_source,
        )

        context = CheckerContext(
            task=task,
            submission=submission,
            required_checker_names=frozenset(required_names),
            warning_checker_names=frozenset(warning_names),
            blocking_severities=frozenset(checker_policy.blocking_severities or []),
        )
        now = datetime.now(UTC)
        outcomes = self._apply_blocking_policy(
            await self._registry.run(context, checker_names),
            context,
        )
        audit_event = await self._write_checker_audit(
            actor,
            task,
            submission,
            attempt_number,
            trigger_reason,
            trigger_source,
        )
        checker_run = self._build_checker_run(
            actor=actor,
            submission=submission,
            outcomes=outcomes,
            artifact_manifest_hash=artifact_manifest_hash,
            attempt_number=attempt_number,
            supersedes_checker_run_id=None if current_run is None else current_run.id,
            trigger_reason=trigger_reason,
            trigger_source=trigger_source,
            audit_event_id=audit_event.id,
            now=now,
        )
        await self._apply_pre_review_gate_result(actor, task, submission, checker_run)
        try:
            checker_run = await self._checker_repo.add_run(checker_run)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise CheckerConflict("checker run conflicted with another attempt; retry") from exc

        persisted = await self._checker_repo.get_run(checker_run.id)
        if persisted is None:
            raise CheckerRunNotFound("checker run not found")
        return self._run_response_for_actor(actor, persisted)

    async def list_submission_checker_runs(
        self,
        actor: ActorContext,
        submission_id: str,
    ) -> list[CheckerRunResponse]:
        """List visible checker runs for one submission.

        Args:
            actor: Trusted actor resolved from the Flow token.
            submission_id: Submission whose checker runs should be listed.

        Returns:
            Checker run responses visible to the actor.
        """
        require_any_role(actor, CHECKER_READ_ROLES)
        submission = await self._get_submission(submission_id)
        await self._get_task_for_actor(actor, submission.task_id)
        runs = await self._checker_repo.list_runs_for_submission(submission.id)
        return [self._run_response_for_actor(actor, run) for run in runs]

    async def get_checker_run(self, actor: ActorContext, checker_run_id: str) -> CheckerRunResponse:
        """Return one visible checker run.

        Args:
            actor: Trusted actor resolved from the Flow token.
            checker_run_id: Checker run id to return.

        Returns:
            Checker run response visible to the actor.
        """
        require_any_role(actor, CHECKER_READ_ROLES)
        checker_run = await self._checker_repo.get_run(checker_run_id)
        if checker_run is None:
            raise CheckerRunNotFound("checker run not found")
        await self._get_task_for_actor(actor, checker_run.task_id)
        return self._run_response_for_actor(actor, checker_run)

    async def _get_submission(self, submission_id: str) -> Submission:
        """Load a submission or raise a checker-domain not-found error.

        Args:
            submission_id: Submission id to load.

        Returns:
            Matching submission model with evidence loaded by the task repository.
        """
        submission = await self._task_repo.get_submission(submission_id)
        if submission is None:
            raise CheckerSubmissionNotFound("submission not found")
        return submission

    async def _get_task_for_actor(self, actor: ActorContext, task_id: str) -> WorkstreamTask:
        """Load a task and enforce checker object-level visibility.

        Args:
            actor: Trusted actor resolved from the Flow token.
            task_id: Task id to load.

        Returns:
            Visible task model.
        """
        require_any_role(actor, CHECKER_READ_ROLES)
        task = await self._task_repo.get_task(task_id)
        if task is None:
            raise CheckerTaskNotFound("task not found")
        if set(actor.roles).intersection(CHECKER_TRIGGER_ROLES):
            return task
        if "worker" in actor.roles and task.assigned_to == actor.actor_id:
            return task
        raise CheckerTaskNotFound("task not found")

    def _build_checker_run(
        self,
        *,
        actor: ActorContext,
        submission: Submission,
        outcomes: list[CheckerOutcome],
        artifact_manifest_hash: str,
        attempt_number: int,
        supersedes_checker_run_id: str | None,
        trigger_reason: str,
        trigger_source: str,
        audit_event_id: str,
        now: datetime,
    ) -> CheckerRun:
        """Build a persisted checker run model from checker outcomes.

        Args:
            actor: Trusted actor that triggered the run.
            submission: Locked submission being checked.
            outcomes: Policy-adjusted checker outcomes to persist.
            artifact_manifest_hash: Canonical or invalid marker manifest hash.
            attempt_number: Monotonic attempt number for the submission.
            supersedes_checker_run_id: Previous current run id when retrying.
            trigger_reason: Audit reason supplied by the trusted trigger actor.
            trigger_source: Durable source label for the checker run.
            audit_event_id: Audit event id linked to the manual trigger.
            now: Timestamp for run start and completion.

        Returns:
            Checker run model with child result models attached.
        """
        blocking_count = sum(1 for outcome in outcomes if outcome.blocks_review)
        failed_count = sum(1 for outcome in outcomes if outcome.status == "failed")
        warning_count = sum(1 for outcome in outcomes if outcome.status == "warning")
        passed_count = sum(1 for outcome in outcomes if outcome.status == "passed")
        routing_recommendation = self._routing_recommendation_for_outcomes(outcomes)
        checker_run = CheckerRun(
            id=str(uuid4()),
            task_id=submission.task_id,
            submission_id=submission.id,
            submission_version=submission.version,
            trigger_source=trigger_source,
            status="completed",
            routing_recommendation=routing_recommendation,
            outcome_source=(
                "auto_checker"
                if routing_recommendation
                in {ROUTING_NEEDS_REVISION, ROUTING_TASK_SETUP_BLOCKED}
                else "none"
            ),
            triggered_by=actor.actor_id,
            triggered_by_subject=actor.external_subject,
            triggered_by_issuer=actor.external_issuer,
            trigger_auth_source=actor.auth_source,
            trigger_reason=trigger_reason,
            audit_event_id=audit_event_id,
            attempt_number=attempt_number,
            supersedes_checker_run_id=supersedes_checker_run_id,
            is_current_for_submission=True,
            locked_guide_version=submission.locked_guide_version,
            locked_checker_policy_version=submission.locked_checker_policy_version,
            locked_review_policy_version=submission.locked_review_policy_version,
            locked_revision_policy_version=submission.locked_revision_policy_version,
            locked_payment_policy_version=submission.locked_payment_policy_version,
            package_hash=submission.package_hash,
            artifact_hash_manifest=submission.artifact_hash_manifest,
            artifact_manifest_hash=artifact_manifest_hash,
            passed_count=passed_count,
            warning_count=warning_count,
            failed_count=failed_count,
            blocking_count=blocking_count,
            started_at=now,
            completed_at=now,
        )
        checker_run.results = [
            CheckerResult(
                id=str(uuid4()),
                checker_run_id=checker_run.id,
                task_id=submission.task_id,
                submission_id=submission.id,
                checker_name=outcome.checker_name,
                status=outcome.status,
                severity=outcome.severity,
                blocks_review=outcome.blocks_review,
                message=outcome.message,
                worker_message=outcome.worker_message,
                worker_suggested_fix=outcome.worker_suggested_fix,
                worker_evidence_refs=outcome.worker_evidence_refs,
                worker_visible=outcome.worker_visible,
                metadata_json=outcome.metadata,
            )
            for outcome in outcomes
        ]
        return checker_run

    async def _enter_auto_checking(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
        trigger_reason: str,
        trigger_source: str,
    ) -> None:
        """Move a task into the internal checker gate when needed.

        Args:
            actor: Trusted actor that triggered the gate.
            task: Task associated with the submission.
            submission: Locked submission being checked.
            trigger_reason: Audit reason for checker execution.
            trigger_source: Durable source label for the checker run.
        """
        if task.status == TASK_STATUS_AUTO_CHECKING:
            return
        from_status = task.status
        self._ensure_transition_allowed(from_status, TASK_STATUS_AUTO_CHECKING)
        task.status = TASK_STATUS_AUTO_CHECKING
        await self._write_gate_audit(
            actor,
            task,
            submission,
            event_type="pre_review_gate_started",
            from_status=from_status,
            to_status=TASK_STATUS_AUTO_CHECKING,
            reason=trigger_reason,
            event_payload={"trigger_source": trigger_source},
        )

    async def _apply_pre_review_gate_result(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
        checker_run: CheckerRun,
    ) -> None:
        """Apply task routing from a completed checker run.

        Args:
            actor: Trusted actor that triggered the checker run.
            task: Task whose lifecycle is gated by checker results.
            submission: Locked submission checked by the run.
            checker_run: Completed checker run carrying the routing recommendation.
        """
        if checker_run.routing_recommendation == ROUTING_ALLOW_REVIEW:
            await self._complete_gate_transition(
                actor,
                task,
                submission,
                checker_run,
                TASK_STATUS_REVIEW_PENDING,
                "pre_review_gate_passed",
            )
            return
        if checker_run.routing_recommendation == ROUTING_NEEDS_REVISION:
            await self._complete_gate_transition(
                actor,
                task,
                submission,
                checker_run,
                TASK_STATUS_NEEDS_REVISION,
                "pre_review_gate_needs_revision",
            )
            return
        await self._write_gate_audit(
            actor,
            task,
            submission,
            event_type="pre_review_gate_blocked",
            from_status=task.status,
            to_status=task.status,
            reason=checker_run.trigger_reason,
            event_payload={
                "checker_run_id": checker_run.id,
                "routing_recommendation": checker_run.routing_recommendation,
                "outcome_source": checker_run.outcome_source,
                "trigger_source": checker_run.trigger_source,
            },
        )

    async def _complete_gate_transition(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
        checker_run: CheckerRun,
        to_status: str,
        event_type: str,
    ) -> None:
        """Transition a task out of the checker gate.

        Args:
            actor: Trusted actor that triggered the checker run.
            task: Task being transitioned.
            submission: Locked submission checked by the run.
            checker_run: Completed checker run driving the transition.
            to_status: Target task status.
            event_type: Audit event type for the gate result.
        """
        from_status = task.status
        self._ensure_transition_allowed(from_status, to_status)
        task.status = to_status
        await self._write_gate_audit(
            actor,
            task,
            submission,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            reason=checker_run.trigger_reason,
            event_payload={
                "checker_run_id": checker_run.id,
                "routing_recommendation": checker_run.routing_recommendation,
                "outcome_source": checker_run.outcome_source,
                "trigger_source": checker_run.trigger_source,
                "blocking_count": checker_run.blocking_count,
                "warning_count": checker_run.warning_count,
                "failed_count": checker_run.failed_count,
            },
        )

    async def _write_gate_audit(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        reason: str | None,
        event_payload: dict | None = None,
    ) -> AuditEvent:
        """Persist an audit event for pre-review gate routing.

        Args:
            actor: Trusted actor triggering the gate.
            task: Task associated with the gate.
            submission: Submission checked by the gate.
            event_type: Audit event type.
            from_status: Previous task status.
            to_status: New task status or same status for internal blocks.
            reason: Audit reason for the gate.
            event_payload: Additional structured event data.

        Returns:
            Persisted audit event.
        """
        audit = actor.audit_context()
        payload = {
            "task_id": task.id,
            "submission_id": submission.id,
            "submission_version": submission.version,
            "locked_guide_version": submission.locked_guide_version,
            "locked_checker_policy_version": submission.locked_checker_policy_version,
            "locked_review_policy_version": submission.locked_review_policy_version,
            "locked_revision_policy_version": submission.locked_revision_policy_version,
            "locked_payment_policy_version": submission.locked_payment_policy_version,
        }
        if event_payload:
            payload.update(event_payload)
        return await self._task_repo.add_audit_event(
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

    async def _write_checker_audit(
        self,
        actor: ActorContext,
        task: WorkstreamTask,
        submission: Submission,
        attempt_number: int,
        trigger_reason: str,
        trigger_source: str,
    ) -> AuditEvent:
        """Persist the audit event for a manual checker trigger.

        Args:
            actor: Trusted admin or project manager actor triggering the checker run.
            task: Task associated with the submission.
            submission: Submission being checked.
            attempt_number: Checker attempt number for the submission.
            trigger_reason: Audit reason supplied by the trusted trigger actor.
            trigger_source: Durable source label for the checker run.

        Returns:
            Persisted audit event linked from the checker run.
        """
        audit = actor.audit_context()
        return await self._task_repo.add_audit_event(
            AuditEvent(
                id=str(uuid4()),
                entity_type="submission",
                entity_id=submission.id,
                event_type="checker_run_triggered",
                from_status=task.status,
                to_status=task.status,
                actor_id=audit.actor_id,
                external_subject=audit.external_subject,
                external_issuer=audit.external_issuer,
                actor_roles=list(audit.actor_roles),
                claim_snapshot=audit.claim_snapshot,
                auth_source=audit.auth_source,
                is_dev_auth=audit.is_dev_auth,
                reason=trigger_reason,
                event_payload={
                    "task_id": task.id,
                    "submission_id": submission.id,
                    "submission_version": submission.version,
                    "attempt_number": attempt_number,
                    "trigger_source": trigger_source,
                    "locked_guide_version": submission.locked_guide_version,
                    "locked_checker_policy_version": submission.locked_checker_policy_version,
                    "locked_review_policy_version": submission.locked_review_policy_version,
                    "locked_revision_policy_version": submission.locked_revision_policy_version,
                    "locked_payment_policy_version": submission.locked_payment_policy_version,
                },
            )
        )

    @staticmethod
    def _routing_recommendation_for_outcomes(outcomes: list[CheckerOutcome]) -> str:
        """Return the run routing recommendation using the Chunk 8 priority order.

        Args:
            outcomes: Policy-adjusted checker outcomes.

        Returns:
            Canonical checker routing recommendation for the run.
        """
        if any(outcome.routing_recommendation == ROUTING_CHECKER_RETRY for outcome in outcomes):
            return ROUTING_CHECKER_RETRY
        if any(
            outcome.routing_recommendation == ROUTING_TASK_SETUP_BLOCKED
            for outcome in outcomes
        ):
            return ROUTING_TASK_SETUP_BLOCKED
        if any(outcome.blocks_review for outcome in outcomes):
            return ROUTING_NEEDS_REVISION
        return ROUTING_ALLOW_REVIEW

    @staticmethod
    def _apply_blocking_policy(
        outcomes: list[CheckerOutcome],
        context: CheckerContext,
    ) -> list[CheckerOutcome]:
        """Apply locked checker policy to raw checker outcomes.

        Args:
            outcomes: Raw checker outcomes from registered checkers.
            context: Locked checker context with policy checker names and severities.

        Returns:
            Outcomes with ``blocks_review`` derived from locked policy.
        """
        adjusted: list[CheckerOutcome] = []
        for outcome in outcomes:
            blocks_review = (
                outcome.status == "failed"
                and (
                    outcome.blocks_review
                    or outcome.checker_name in context.required_checker_names
                    or outcome.severity in context.blocking_severities
                )
            )
            adjusted.append(replace(outcome, blocks_review=blocks_review))
        return adjusted

    @staticmethod
    def _ensure_transition_allowed(from_status: str, to_status: str) -> None:
        """Validate checker-driven task transitions through the shared lifecycle guard.

        Args:
            from_status: Current task status.
            to_status: Desired checker-gate task status.

        Raises:
            CheckerExecutionBlocked: If the transition is not implemented.
        """
        try:
            ensure_allowed_transition(from_status, to_status)
        except InvalidTaskTransition as exc:
            raise CheckerExecutionBlocked(str(exc)) from exc

    def _run_response_for_actor(
        self,
        actor: ActorContext,
        checker_run: CheckerRun,
    ) -> CheckerRunResponse:
        """Build a checker run response with role-sensitive result redaction.

        Args:
            actor: Trusted actor requesting the run.
            checker_run: Persisted checker run with result rows loaded.

        Returns:
            Checker run response visible to that actor.
        """
        has_checker_admin_access = bool(set(actor.roles).intersection(CHECKER_TRIGGER_ROLES))
        hide_internal_route_from_worker = (
            not has_checker_admin_access
            and checker_run.routing_recommendation in INTERNAL_ROUTING_RECOMMENDATIONS
        )
        results = []
        for result in checker_run.results:
            if hide_internal_route_from_worker:
                continue
            if not has_checker_admin_access and not result.worker_visible:
                continue
            results.append(
                CheckerResultResponse(
                    id=result.id,
                    checker_run_id=result.checker_run_id,
                    task_id=result.task_id,
                    submission_id=result.submission_id,
                    checker_name=result.checker_name,
                    status=result.status,
                    severity=result.severity,
                    blocks_review=result.blocks_review,
                    message=result.message if has_checker_admin_access else None,
                    worker_message=result.worker_message,
                    worker_suggested_fix=result.worker_suggested_fix,
                    worker_evidence_refs=result.worker_evidence_refs,
                    worker_visible=result.worker_visible,
                    metadata=result.metadata_json if has_checker_admin_access else {},
                    created_at=result.created_at,
                )
            )
        routing_recommendation = (
            "not_evaluated"
            if hide_internal_route_from_worker
            else checker_run.routing_recommendation
        )
        outcome_source = (
            "none" if hide_internal_route_from_worker else checker_run.outcome_source
        )
        passed_count = 0 if hide_internal_route_from_worker else checker_run.passed_count
        warning_count = 0 if hide_internal_route_from_worker else checker_run.warning_count
        failed_count = 0 if hide_internal_route_from_worker else checker_run.failed_count
        blocking_count = 0 if hide_internal_route_from_worker else checker_run.blocking_count
        return CheckerRunResponse(
            id=checker_run.id,
            task_id=checker_run.task_id,
            submission_id=checker_run.submission_id,
            submission_version=checker_run.submission_version,
            trigger_source=checker_run.trigger_source,
            status=checker_run.status,
            routing_recommendation=routing_recommendation,
            outcome_source=outcome_source,
            triggered_by=checker_run.triggered_by if has_checker_admin_access else None,
            triggered_by_subject=(
                checker_run.triggered_by_subject if has_checker_admin_access else None
            ),
            triggered_by_issuer=(
                checker_run.triggered_by_issuer if has_checker_admin_access else None
            ),
            trigger_auth_source=(
                checker_run.trigger_auth_source if has_checker_admin_access else None
            ),
            trigger_reason=checker_run.trigger_reason if has_checker_admin_access else None,
            audit_event_id=checker_run.audit_event_id if has_checker_admin_access else None,
            attempt_number=checker_run.attempt_number,
            supersedes_checker_run_id=checker_run.supersedes_checker_run_id,
            is_current_for_submission=checker_run.is_current_for_submission,
            locked_guide_version=(
                checker_run.locked_guide_version if has_checker_admin_access else None
            ),
            locked_checker_policy_version=(
                checker_run.locked_checker_policy_version if has_checker_admin_access else None
            ),
            locked_review_policy_version=(
                checker_run.locked_review_policy_version if has_checker_admin_access else None
            ),
            locked_revision_policy_version=(
                checker_run.locked_revision_policy_version if has_checker_admin_access else None
            ),
            locked_payment_policy_version=(
                checker_run.locked_payment_policy_version if has_checker_admin_access else None
            ),
            package_hash=checker_run.package_hash if has_checker_admin_access else None,
            artifact_hash_manifest=(
                checker_run.artifact_hash_manifest if has_checker_admin_access else []
            ),
            artifact_manifest_hash=(
                checker_run.artifact_manifest_hash if has_checker_admin_access else None
            ),
            passed_count=passed_count,
            warning_count=warning_count,
            failed_count=failed_count,
            blocking_count=blocking_count,
            queued_at=checker_run.queued_at,
            started_at=checker_run.started_at,
            completed_at=checker_run.completed_at,
            failure_code=checker_run.failure_code if has_checker_admin_access else None,
            failure_message=checker_run.failure_message if has_checker_admin_access else None,
            created_at=checker_run.created_at,
            results=results,
        )

    @staticmethod
    def _feedback_item(outcome: CheckerOutcome) -> CheckerFeedbackItem:
        """Convert an internal checker outcome to pre-submit feedback.

        Args:
            outcome: Checker outcome from a non-authoritative static check.

        Returns:
            Worker-facing feedback item.
        """
        return CheckerFeedbackItem(
            checker_name=outcome.checker_name,
            status=outcome.status,
            severity=outcome.severity,
            would_block_if_submitted=outcome.blocks_review,
            worker_message=outcome.worker_message or "Checker feedback is not worker-visible.",
            worker_suggested_fix=outcome.worker_suggested_fix,
            worker_evidence_refs=outcome.worker_evidence_refs,
        )
