"""Derive accepted finalization progress from its exact durable delivery owner."""

from uuid import UUID

from app.core.hashing import canonical_json_hash

from app.modules.artifacts.api.submission_command import PostSubmissionProgress
from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationProgress
from app.modules.checkers.api.execution import POST_SUBMISSION_RETRY_OPTIONS
from app.modules.artifacts.intake.acceptance import finalization_event
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.artifacts.intake.recovery import recovery_event
from app.modules.artifacts.api.submission_recovery import (
    FINALIZATION_RECOVERY_EVENT, FINALIZATION_RECOVERY_SOURCES, SubmissionRecoveryPayload,
)
from app.modules.outbox.api import OutboxAppendInput, OutboxAppendPort, OutboxIdempotencyConflict, DeliveryUnavailable
from app.modules.checkers.api.delivery_reconciliation import (
    POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS,
    PostSubmitDeliveryChildPayload, post_submit_reconciliation_event_json,
)


async def finalization_progress(row, events: OutboxAppendPort, deliveries) -> SubmissionFinalizationProgress | None:
    if row.state not in {"finalization_pending", "finalized"}:
        return None
    try:
        delivery = await events.observe_delivery(UUID(row.finalization_event_id), finalization_event(row))
    except OutboxIdempotencyConflict as exc:
        raise IntakeCustodyConflict("submission_finalization_progress_unavailable") from exc
    finalized = row.state == "finalized"
    attempt_count = delivery.attempt_count
    try:
        if delivery.state == "dead_letter" and delivery.error_code == "INVOKE_OUTCOME_UNKNOWN":
            retained = await deliveries.read_finalized_unknown(
                project_id=UUID(row.project_id), event_id=UUID(row.finalization_event_id),
                event_types=FINALIZATION_RECOVERY_SOURCES,
                child_event_type=FINALIZATION_RECOVERY_EVENT, lock=False,
            )
            if retained is not None and retained.child is not None:
                payload = SubmissionRecoveryPayload.model_validate_json(retained.child.payload_json)
                source = payload.source
                if (source.operation_id != UUID(row.id) or source.project_id != UUID(row.project_id)
                        or source.task_id != UUID(row.task_id)
                        or source.original_event_id != UUID(row.finalization_event_id)
                        or source.original_claim_generation != retained.envelope.claim.claim_generation
                        or source.original_payload_digest != retained.envelope.claim.payload_digest
                        or source.acceptance_receipt_sha256 != row.acceptance_receipt_sha256):
                    raise IntakeCustodyConflict("submission_finalization_progress_inconsistent")
                delivery = await events.observe_delivery(retained.child.event_id, recovery_event(payload))
                attempt_count += delivery.attempt_count
    except (OutboxIdempotencyConflict, DeliveryUnavailable, ValueError) as exc:
        raise IntakeCustodyConflict("submission_finalization_progress_unavailable") from exc
    if not finalized and delivery.state in {"acknowledged", "cancelled"}:
        raise IntakeCustodyConflict("submission_finalization_progress_inconsistent")
    stalled = not finalized and delivery.state == "dead_letter"
    return SubmissionFinalizationProgress(
        operation_id=UUID(row.id), finalized=finalized, operationally_stalled=stalled,
        stalled_at=delivery.finalized_at if stalled else None,
        next_retry_at=delivery.next_attempt_at if not finalized else None,
        attempt_count=attempt_count, stalled_reason=delivery.error_code if stalled else None,
    )


async def evaluation_delivery_progress(event_id, event, evaluation, events, deliveries):
    """Observe one exact current evaluation delivery, including its recovery child."""
    unavailable = "submission_evaluation_progress_unavailable"
    try:
        observation = await events.observe_delivery(event_id, event)
        if observation.state != "dead_letter" or observation.error_code != "INVOKE_OUTCOME_UNKNOWN":
            return observation
        retained = await deliveries.read_finalized_unknown(
            project_id=event.project_id, event_id=event_id,
            event_types=POST_SUBMIT_DELIVERY_SUPPORTED_EVENTS,
            child_event_type=POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT, lock=False,
        )
        if retained is None:
            raise IntakeCustodyConflict(unavailable)
        if retained.child is None:
            return observation
        payload = PostSubmitDeliveryChildPayload.model_validate_json(retained.child.payload_json)
        claim = retained.envelope.claim
        request, reservation = evaluation.current.request, evaluation.current.reservation
        if (payload.original_event_id != event_id or claim.event_id != event_id
                or claim.project_id != event.project_id
                or payload.original_claim_generation != claim.claim_generation
                or payload.original_payload_digest != claim.payload_digest
                or claim.payload_digest != canonical_json_hash(event.payload)
                or payload.original_event_type != event.event_type
                or payload.original_event_version != event.event_version
                or payload.evaluation_request_id != request.evaluation_request_id
                or payload.checker_run_id != reservation.attempt_id
                or payload.evaluation_generation != reservation.evaluation_generation):
            raise IntakeCustodyConflict(unavailable)
        return await events.observe_delivery(
            retained.child.event_id, OutboxAppendInput.model_validate_json(post_submit_reconciliation_event_json(event.project_id, payload)),
        )
    except (OutboxIdempotencyConflict, DeliveryUnavailable, ValueError) as exc:
        raise IntakeCustodyConflict(unavailable) from exc


class SubmissionOperationReadService:
    """One root-transaction read across the existing durable evidence owners."""

    def __init__(self, session, *, tasks, authority, history, evaluations, prechecks, projects, events, deliveries):
        self._session, self._tasks, self._authority = session, tasks, authority
        self._history, self._evaluations, self._prechecks = history, evaluations, prechecks
        self._projects, self._events, self._deliveries = projects, events, deliveries

    async def read(self, task_id, selector, *, actor_id):
        from sqlalchemy import text
        from app.modules.artifacts.api.submission_command import SubmissionOperationResponse
        from app.modules.artifacts.intake.repository import SubmissionIntakeRepository
        from app.modules.authorization.api.submission_intake import IntakeAuthorityDenied, IntakeOperationReadFacts
        from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest

        repository = SubmissionIntakeRepository(self._session, self._tasks)
        operation_id = selector.operation_id
        if operation_id is None:
            found = await repository.find_actor_key(actor_id, selector.idempotency_key)
            if found is None:
                raise IntakeAuthorityDenied("submission intake is unavailable")
            operation_id = UUID(found.id)
        try:
            row = await repository._lock(operation_id)
        except IntakeCustodyConflict as exc:
            if str(exc) == "intake_unavailable":
                raise IntakeAuthorityDenied("submission intake is unavailable") from None
            raise
        if row.task_id != str(task_id):
            raise IntakeAuthorityDenied("submission intake is unavailable")
        access = await self._authority.authorize_operation_read(IntakeOperationReadFacts(
            UUID(row.id), UUID(row.project_id), task_id, UUID(row.actor_profile_id)))
        current = await self._tasks.read_operation_context(
            TaskSubmissionContextRequest(
                task_id, UUID(row.assignment_id), UUID(row.actor_profile_id), select_predecessor=True,
            ),
            project_id=UUID(row.project_id), reader_id=actor_id,
            management=access.management, own_submitter=access.own_submitter,
        )
        accepted = row.state in {"finalization_pending", "finalized"}
        if accepted:
            await self._session.execute(text("SELECT public.require_submission_acceptance(o) "
                "FROM public.submission_intake_operations o WHERE id=:id"), {"id": UUID(row.id)})
            results = row.acceptance_receipt["pre_submission_results"]
        else:
            results = await self._feedback(row, repository)
        action = "wait"
        stage, stalled, submission_id, version, request_id, failure_code, post = await self._attempt_progress(row)
        if row.state in {"rejected", "failed", "abandoned", "cancelled"}:
            action = "inspect_governed_outcome"
            if row.state != "cancelled" and await self._permits_new_intake(current.candidate):
                action = "correct_and_submit_new_key" if row.state == "rejected" else "retry_new_key_after_terminal"
        elif row.state == "finalized" and stalled:
            action = "contact_operator"
        elif row.state == "finalized" and stage not in {"evaluation_pending", "evaluation_running"}:
            action = "inspect_governed_outcome"
        return SubmissionOperationResponse(
            operation_id=UUID(row.id), task_id=task_id, assignment_id=UUID(row.assignment_id),
            idempotency_key=UUID(row.idempotency_key), operation_state=row.state,
            processing_stage=stage, accepted_at=row.accepted_at,
            task_status_at_acceptance="evaluation_pending" if accepted else None,
            current_task_status=current.current_task_status, submission_id=submission_id,
            submission_version=version, evaluation_request_id=request_id,
            pre_submission_results=results, failure_code=failure_code, operationally_stalled=stalled,
            post_submission_progress=post, next_action=action,
        )

    @staticmethod
    def _public_failure(code):
        if code is not None and code not in {
            "submission_packet_invalid", "submission_archive_limit_exceeded", "submission_upload_timeout",
            "submission_pre_timeout",
            "submission_infrastructure_unavailable", "pre_submission_checker_failed",
            "submission_foreground_expired", "submission_operation_cancelled", "revision_deadline_expired",
            "submission_unavailable", "revision_context_changed", "revision_context_blocked",
            "revision_limit_reached", "task_submission_predecessor_changed",
        }:
            code = "submission_operation_terminal"
        return code

    async def _attempt_progress(self, row):
        stage, stalled = row.state, False
        submission_id = version = request_id = None
        failure_code = self._public_failure(row.failure_code)
        post = None
        task_id = UUID(row.task_id)
        if row.state == "finalization_pending":
            progress = await finalization_progress(row, self._events, self._deliveries)
            stalled = progress.operationally_stalled
            stage = "operationally_stalled" if stalled else "finalization_pending"
        elif row.state == "finalized":
            if row.finalized_submission_id is None or row.finalized_admission_id is None:
                raise IntakeCustodyConflict("submission_operation_association_unavailable")
            outcome = await self._history.read_operation_outcome(
                project_id=UUID(row.project_id), task_id=task_id, assignment_id=UUID(row.assignment_id),
                contributor_id=UUID(row.actor_profile_id), submission_id=UUID(row.finalized_submission_id),
                admission_id=UUID(row.finalized_admission_id),
            )
            evaluation = await self._evaluations.read_current_progress(
                project_id=UUID(row.project_id), task_id=task_id, submission_id=outcome.submission_id,
                original_request_id=outcome.evaluation_request_id,
            )
            submission_id, version = outcome.submission_id, outcome.submission_version
            request_id = evaluation.current.request.evaluation_request_id
            if outcome.status != "evaluation_pending":
                stage = outcome.status
            else:
                event_id = evaluation.completion_event_id or evaluation.retry_event_id or outcome.evaluation_event_id
                event = OutboxAppendInput.model_validate_json(evaluation.delivery_event_json or outcome.evaluation_event_json)
                delivery = await evaluation_delivery_progress(event_id, event, evaluation, self._events, self._deliveries)
                if evaluation.failure_code is not None:
                    failure_code = f"post_submission_{evaluation.failure_code}"
                elif delivery.state == "dead_letter":
                    failure_code = ("post_submission_outcome_unknown" if delivery.error_code == "INVOKE_OUTCOME_UNKNOWN"
                                    else "post_submission_delivery_failed")
                stalled = failure_code is not None
                if not stalled and evaluation.previous_failure_code is not None and evaluation.status in {"queued", "running"}:
                    failure_code = f"post_submission_{evaluation.previous_failure_code}"
                post = PostSubmissionProgress(
                    attempt=evaluation.current.reservation.evaluation_generation,
                    automatic_attempt_limit=POST_SUBMISSION_RETRY_OPTIONS.max_attempts,
                    next_attempt_at=delivery.next_attempt_at if evaluation.status == "queued" else None,
                )
                stage = ("operationally_stalled" if stalled else
                         "evaluation_running" if evaluation.live_worker_lease else "evaluation_pending")
        return stage, stalled, submission_id, version, request_id, failure_code, post

    async def read_assignment_attempt(self, query):
        """Read one assignment-scoped operation and the original PRE projection."""
        from sqlalchemy import select, text
        from app.modules.artifacts.api.submission_command import AssignmentIntakeAttempt, AssignmentIntakeUnavailable
        from app.modules.artifacts.intake.models import SubmissionIntakeOperation
        from app.modules.artifacts.intake.repository import SubmissionIntakeRepository

        model = SubmissionIntakeOperation
        statement = select(model).where(
            model.project_id == str(query.project_id), model.task_id == str(query.task_id),
            model.assignment_id == str(query.assignment_id), model.actor_profile_id == str(query.contributor_id),
        )
        if query.active_operation_id is not None:
            statement = statement.where(model.id == str(query.active_operation_id))
        row = await self._session.scalar(statement.order_by(model.created_at.desc(), model.id.desc()).limit(1))
        if row is None:
            if query.active_operation_id is not None:
                raise AssignmentIntakeUnavailable("assignment operation unavailable")
            return None
        try:
            if row.accepted_at is not None:
                await self._session.execute(text("SELECT public.require_submission_acceptance(o) "
                    "FROM public.submission_intake_operations o WHERE id=:id"), {"id": UUID(row.id)})
                results = row.acceptance_receipt["pre_submission_results"]
            else:
                repository = SubmissionIntakeRepository(self._session, self._tasks)
                results = await self._feedback(row, repository)
            stage, stalled, submission_id, _, _, failure_code, post = await self._attempt_progress(row)
            return AssignmentIntakeAttempt(
                operation_id=UUID(row.id), stage=stage, failure_code=failure_code,
                submission_id=submission_id, pre_submission_results=results, post_submission_progress=post,
                operationally_stalled=stalled or row.failure_code == "submission_infrastructure_unavailable",
            )
        except IntakeCustodyConflict as exc:
            raise AssignmentIntakeUnavailable("assignment operation unavailable") from exc

    async def _feedback(self, row, repository):
        from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
        terminal = await self._prechecks.read_source_terminal(source_operation_id=UUID(row.id))
        if terminal is None or terminal.execution is None:
            return []
        reservation = terminal.lease.reservation
        if (reservation.metadata_sha256 != row.metadata_sha256
                or reservation.actor_profile_id != UUID(row.actor_profile_id)
                or reservation.idempotency_key != UUID(row.idempotency_key)
                or reservation.task_id != UUID(row.task_id)
                or reservation.assignment_id != UUID(row.assignment_id)
                or reservation.source != repository._sealed_source(row)):
            raise IntakeCustodyConflict("submission_operation_pre_inconsistent")
        return public_pre_submission_results(terminal.execution)

    async def _permits_new_intake(self, candidate):
        from dataclasses import asdict
        from app.modules.projects.api.locked_policy import (
            ProjectLockedPolicyContextRequest, ProjectLockedPolicyContextUnavailable,
        )
        from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
        from app.modules.tasks.api.submission_context import (
            TaskSubmissionContextUnavailable, require_revision_capacity,
        )
        if candidate is None:
            return False
        references = asdict(candidate.locked_project_context)
        references.pop("locked_contribution_policy_version_id")
        try:
            project = await self._projects.lock_locked_policy_context(ProjectLockedPolicyContextRequest(**references))
            if candidate.predecessor is not None:
                revision = project.activation_receipt.command.revision
                require_revision_capacity(candidate, project_id=project.project_id,
                    policy_id=revision.policy_id, policy_generation=revision.generation, policy_hash=revision.policy_hash,
                    max_revision_rounds=RevisionPolicySemantics.model_validate_json(project.revision_policy.value).max_revision_rounds)
        except (ProjectLockedPolicyContextUnavailable, TaskSubmissionContextUnavailable):
            return False
        return True
