"""TASK-owned immutable Submission command for the hidden composed transaction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID
from app.core.identifiers import new_record_id

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from sqlalchemy.exc import DBAPIError

from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.tasks.api.submission_context import require_revision_capacity
from app.modules.tasks.api import (
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    SubmissionCreationUnavailable,
    TaskSubmissionContextRequest,
    TaskSubmissionContextPort,
)
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.tasks.models import EvidenceItem, Submission
from app.modules.tasks.submission_participants import (
    SubmissionArtifactAdmissionPort, SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult, SubmissionArtifactReplayRequest,
)
from app.modules.tasks.submission_dispatch import (
    SubmissionDispatch, creation_request_digest, evaluation_request_event,
)
from app.modules.tasks.submission_replay import read_creation_replay
from app.modules.tasks.lifecycle import ensure_allowed_transition
from app.modules.checkers.api.execution import EvaluationCoordinationPort
from app.modules.checkers.api.selected_post_submit import (
    make_selected_post_submit_request,
)
from app.modules.outbox.api import OutboxAppendPort
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService


def build_submission(
    *,
    submission_id: str,
    task: Any,
    contributor_id: str,
    version: int,
    summary: str,
    worker_attestation: str,
    supersedes_submission_id: str | None,
    contribution_policy_version_id: UUID,
    task_assignment_id: str,
    package_uri: str | None = None,
    package_hash: str | None = None,
    artifact_hash_manifest: list[dict[str, Any]] | None = None,
    evidence_items: Sequence[EvidenceItem] = (),
) -> Submission:
    """Build a Submission with one canonical copy of the task policy locks."""
    return Submission(
        id=submission_id,
        contribution_policy_version_id=contribution_policy_version_id,
        task_id=task.id,
        task_assignment_id=task_assignment_id,
        contributor_id=contributor_id,
        version=version,
        status="submitted",
        summary=summary,
        package_uri=package_uri,
        package_hash=package_hash,
        artifact_hash_manifest=artifact_hash_manifest or [],
        worker_attestation=worker_attestation,
        locked_guide_version=task.locked_guide_version,
        locked_post_submit_checker_policy_id=task.locked_post_submit_checker_policy_id,
        locked_post_submit_checker_policy_version=task.locked_post_submit_checker_policy_version,
        locked_post_submit_checker_policy_hash=task.locked_post_submit_checker_policy_hash,
        locked_post_submit_checker_policy_body=task.locked_post_submit_checker_policy_body,
        locked_review_policy_id=task.locked_review_policy_id,
        locked_review_policy_generation=task.locked_review_policy_generation,
        locked_review_policy_hash=task.locked_review_policy_hash,
        locked_revision_policy_id=task.locked_revision_policy_id,
        locked_revision_policy_generation=task.locked_revision_policy_generation,
        locked_revision_policy_hash=task.locked_revision_policy_hash,
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
        supersedes_submission_id=supersedes_submission_id,
        evidence_items=list(evidence_items),
    )


class TaskSubmissionCreationService:
    """Sequence TASK and ART owner operations inside a caller-owned transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: SubmissionCreationAuthorizationPort | None,
        admissions: SubmissionArtifactAdmissionPort,
        contexts: TaskService,
        submission_contexts: TaskSubmissionContextPort,
        evaluations: EvaluationCoordinationPort,
        events: OutboxAppendPort,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._admissions = admissions
        self._repository = TaskRepository(session)
        self._contexts = contexts
        self._submission_contexts = submission_contexts
        self._evaluations = evaluations
        self._events = events

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        """Create one Submission without opening or committing a transaction."""
        if self._authorization is None:
            raise SubmissionCreationUnavailable("submission creation authority is unavailable")
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise RuntimeError("submission creation requires one root transaction")
        preliminary = SubmissionCreationPreparationFacts(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            contributor_id=request.contributor_id,
            admission_id=request.admission_id,
            predecessor_submission_id=request.predecessor_submission_id,
        )
        await self._authorization.authorize(preliminary)
        connection = await self._session.connection()
        if connection.in_nested_transaction():
            raise RuntimeError("submission creation requires one root transaction")
        try:
            await self._session.execute(text("SELECT pg_catalog.pg_export_snapshot()"))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != "25001":
                raise
            raise RuntimeError("submission creation requires one root transaction") from exc
        task = await self._repository.get_task(str(request.task_id), for_update=True)
        if task is None:
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        replay = await read_creation_replay(self._session, task, request)
        if replay is not None:
            return await self._replay(request, *replay)
        context = await self._submission_contexts.lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                contributor_id=request.contributor_id,
                predecessor_submission_id=request.predecessor_submission_id,
            )
        )
        # Version orders every Submission on the task; the revision allowance
        # belongs to this assignment and is carried separately in the context.
        latest_task_submission = await self._repository.get_latest_submission_for_task(task.id)
        version = latest_task_submission.version + 1 if latest_task_submission else 1
        if context.predecessor is not None and version != context.predecessor.version + 1:
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        submission_id = new_record_id()
        final = SubmissionCreationAuthorityFacts(
            task_id=preliminary.task_id,
            assignment_id=preliminary.assignment_id,
            contributor_id=preliminary.contributor_id,
            admission_id=preliminary.admission_id,
            predecessor_submission_id=preliminary.predecessor_submission_id,
            submission_id=submission_id,
            submission_version=version,
            task_context=context,
        )
        prepared_authorization = await self._authorization.prepare(final)
        try:
            project = await self._contexts._load_locked_task_context(task)
            if context.predecessor is not None:
                selected_revision = project.facts.activation_receipt.command.revision
                require_revision_capacity(
                    context, project_id=project.facts.project_id,
                    policy_id=selected_revision.policy_id,
                    policy_generation=selected_revision.generation,
                    policy_hash=selected_revision.policy_hash,
                    max_revision_rounds=RevisionPolicySemantics.model_validate_json(
                        project.facts.revision_policy.value,
                    ).max_revision_rounds,
                )
            async def authorize_creation():
                return await self._authorization.consume(prepared_authorization, final)
            receipt = await self._create_bound_submission(
                request, task, context, project, submission_id, version, authorize_creation,
                accepted_operation_id=None,
            )
        finally:
            self._authorization.close(prepared_authorization)
        return receipt.result()

    async def create_accepted(
        self, request: SubmissionCreationRequest, *, authority_facts, finalization_authority,
        snapshot_sha256: str, eligible_status: str, remediation_id: UUID | None,
    ):
        """Continue accepted service custody through the same Submission writer."""
        from dataclasses import replace
        from app.modules.tasks.accepted_submission import accepted_submission_context
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise RuntimeError("accepted creation requires a root transaction")
        task = await self._repository.get_task(str(request.task_id), for_update=True)
        if task is None or (request.task_id, request.assignment_id, request.contributor_id) != (
            authority_facts.task_id, authority_facts.assignment_id, authority_facts.contributor_id,
        ):
            raise SubmissionCreationUnavailable("accepted submission custody differs")
        context = await accepted_submission_context(
            self._session, task, request, operation_id=authority_facts.operation_id,
            snapshot_sha256=snapshot_sha256, eligible_status=eligible_status, remediation_id=remediation_id,
        )
        latest = await self._repository.get_latest_submission_for_task(task.id)
        version = latest.version + 1 if latest else 1
        if context.predecessor is not None and context.predecessor.version + 1 != version:
            raise SubmissionCreationUnavailable("accepted predecessor differs")
        submission_id = new_record_id()
        facts = replace(authority_facts, phase="commit", submission_id=submission_id, submission_version=version)
        handle = await finalization_authority.prepare(facts=facts, idempotency_key=facts.continuation_lease_id)
        decision_id = None
        async def authorize_creation():
            nonlocal decision_id
            decision_id = await finalization_authority.consume(prepared_authorization=handle, facts=facts)
            if not isinstance(decision_id, UUID):
                raise SubmissionCreationUnavailable("finalization authority is unavailable")
            return facts.acceptance_decision_id
        try:
            project = await self._contexts._load_locked_task_context(task)
            receipt = await self._create_bound_submission(
                request, task, context, project, submission_id, version, authorize_creation,
                accepted_operation_id=facts.operation_id,
            )
            return receipt.result(), decision_id
        finally:
            finalization_authority.close()

    async def _create_bound_submission(
        self, request, task, context, project, submission_id, version, authorize_creation,
        *, accepted_operation_id,
    ):
        """The sole Submission/binding/POST writer for either authorized entry."""
        submission = build_submission(
            submission_id=str(submission_id), task=task,
            contribution_policy_version_id=context.submitter_contribution_policy_version_id,
            task_assignment_id=str(context.assignment_id),
            contributor_id=str(request.contributor_id), version=version,
            summary=request.summary, worker_attestation=request.contributor_attestation,
            supersedes_submission_id=(str(context.predecessor.submission_id)
                                      if context.predecessor else None),
        )
        submission.locked_at = await self._session.scalar(select(func.now()))
        await self._repository.add_submission(submission)
        consumed = await self._admissions.consume(
            SubmissionArtifactAdmissionRequest(
                admission_id=request.admission_id,
                submission_id=submission_id,
                submission_version=version,
                task_context=context,
                project_context=project.facts,
                accepted_operation_id=accepted_operation_id,
                packet=SubmissionPacketView(
                    request.summary, request.contributor_attestation,
                ),
            )
        )
        if (
            type(consumed) is not SubmissionArtifactAdmissionResult
            or not isinstance(consumed.binding_id, UUID)
            or not isinstance(consumed.content_id, UUID)
            or consumed.selected_evaluation_content is None
        ):
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        submission.submission_bundle_admission_id = str(request.admission_id)
        submission.artifact_binding_id = str(consumed.binding_id)
        submission.artifact_content_id = str(consumed.content_id)
        submission.selected_post_submit_policy_sha256 = (
            consumed.selected_evaluation_content.policy.policy_sha256
        )
        submission.selected_post_submit_policy_body = (
            consumed.selected_evaluation_content.policy.model_dump(mode="json")
        )
        await self._session.flush()
        creation_decision_id = await authorize_creation()
        if not isinstance(creation_decision_id, UUID):
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        request_fields = dict(
            evaluation_request_id=new_record_id(),
            evaluation_generation=1,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_id=submission_id,
            submission_version=version,
            content_id=consumed.content_id,
            binding_id=consumed.binding_id,
            content_sha256=consumed.archive_sha256,
            byte_count=consumed.byte_count,
        )
        selected = consumed.selected_evaluation_content
        evaluation = make_selected_post_submit_request(
            project_id=selected.project_id,
            expected_context=selected.expected_context,
            policy=selected.policy,
            **request_fields,
        )
        if accepted_operation_id is None:
            ensure_allowed_transition(task.status, "submitted")
            task.status = "submitted"
            await self._session.flush()
        elif task.status != "evaluation_pending" or task.active_submission_operation_id != str(accepted_operation_id):
            raise SubmissionCreationUnavailable("accepted task custody differs")
        reservation = await self._evaluations.reserve_current_evaluation(evaluation)
        if (reservation.request_id != evaluation.evaluation_request_id
                or reservation.request_digest != evaluation.request_sha256
                or reservation.evaluation_generation != 1):
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        receipt = SubmissionDispatch(
            submission_id=str(submission_id), submission_version=version,
            project_id=str(context.locked_project_context.project_id),
            task_id=str(request.task_id), assignment_id=str(request.assignment_id),
            contributor_id=str(request.contributor_id), admission_id=str(request.admission_id),
            artifact_binding_id=str(consumed.binding_id), artifact_content_id=str(consumed.content_id),
            creation_decision_id=str(creation_decision_id), binding_decision_id=str(consumed.binding_decision_id),
            request_digest=creation_request_digest(request),
            creation_kind=context.kind, creation_status=context.status,
            checker_remediation_manifest_id=context.checker_remediation_manifest_id,
            evaluation_request_id=str(reservation.request_id),
            evaluation_request_digest=reservation.request_digest,
            evaluation_attempt_id=str(reservation.attempt_id), evaluation_result_id=str(reservation.result_id),
        )
        event = await self._events.append(evaluation_request_event(receipt))
        receipt.evaluation_event_id = event.event_id
        self._session.add(receipt)
        if accepted_operation_id is None:
            ensure_allowed_transition(task.status, "evaluation_pending")
        task.status = "evaluation_pending"
        await self._session.flush()
        return receipt

    async def read_finalized(self, submission_id: UUID, admission_id: UUID, creation_decision_id: UUID):
        """Read the exact retained dispatch without requiring today's TASK status."""
        receipt = await self._session.get(SubmissionDispatch, str(submission_id))
        if (receipt is None or receipt.admission_id != str(admission_id)
                or receipt.creation_decision_id != str(creation_decision_id)):
            raise SubmissionCreationUnavailable("finalized dispatch differs")
        valid = await self._session.scalar(text("SELECT public.submission_dispatch_valid(d) "
            "FROM public.submission_dispatches d WHERE submission_id=:id"), {"id": str(submission_id)})
        if valid is not True:
            raise SubmissionCreationUnavailable("finalized dispatch differs")
        return receipt.result()

    async def _replay(self, request, receipt, context) -> SubmissionCreationResult:
        """Verify the complete original commit under fresh authority, without repair."""
        facts = SubmissionCreationAuthorityFacts(
            task_id=request.task_id, assignment_id=request.assignment_id,
            contributor_id=request.contributor_id, admission_id=request.admission_id,
            predecessor_submission_id=request.predecessor_submission_id,
            submission_id=UUID(receipt.submission_id), submission_version=receipt.submission_version,
            task_context=context,
        )
        prepared = await self._authorization.prepare(facts)
        try:
            await self._authorization.validate_replay(prepared, facts, UUID(receipt.creation_decision_id))
            consumed = await self._admissions.read_consumed(SubmissionArtifactReplayRequest(
                admission_id=request.admission_id, project_id=UUID(receipt.project_id),
                task_id=request.task_id, assignment_id=request.assignment_id,
                contributor_id=request.contributor_id, submission_id=UUID(receipt.submission_id),
                submission_version=receipt.submission_version,
                packet_sha256=SubmissionPacketView(request.summary, request.contributor_attestation).sha256,
                task_context=context,
            ))
            if (consumed.binding_id, consumed.content_id, consumed.binding_decision_id) != (
                UUID(receipt.artifact_binding_id), UUID(receipt.artifact_content_id), UUID(receipt.binding_decision_id),
            ):
                raise SubmissionCreationUnavailable("submission creation is unavailable")
            stored = await self._evaluations.read_reserved_evaluation(
                project_id=UUID(receipt.project_id), task_id=UUID(receipt.task_id),
                submission_id=UUID(receipt.submission_id), request_id=UUID(receipt.evaluation_request_id),
            )
            evaluation, reservation = stored.request, stored.reservation
            if (
                reservation.request_digest != receipt.evaluation_request_digest
                or reservation.attempt_id != UUID(receipt.evaluation_attempt_id)
                or reservation.result_id != UUID(receipt.evaluation_result_id)
                or reservation.evaluation_generation != 1
                or evaluation.assignment_id != UUID(receipt.assignment_id)
                or evaluation.submission_version != receipt.submission_version
                or evaluation.binding_id != consumed.binding_id
                or evaluation.content_id != consumed.content_id
                or evaluation.content_sha256 != consumed.archive_sha256
                or evaluation.byte_count != consumed.byte_count
                or consumed.selected_evaluation_content is None
                or evaluation.project_id != consumed.selected_evaluation_content.project_id
                or evaluation.expected_context != consumed.selected_evaluation_content.expected_context
                or evaluation.policy != consumed.selected_evaluation_content.policy
            ):
                raise SubmissionCreationUnavailable("submission creation is unavailable")
            await self._events.require_existing(receipt.evaluation_event_id, evaluation_request_event(receipt))
            return receipt.result()
        finally:
            self._authorization.close(prepared)
