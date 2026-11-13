"""Exact T4 receipt, accepted context and identifier-only finalization event."""
from datetime import datetime
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from app.modules.authorization.api.submission_intake import IntakeAcceptanceAuthorityFacts
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitTerminalFacts
from app.modules.outbox.api import OutboxAppendInput


def acceptance_context(terminal: SelectedPreSubmitTerminalFacts) -> dict:
    request = terminal.lease.reservation
    lineage = request.admission_lineage
    return {
        "schema_version": "workstream.submission_acceptance_context.v1",
        "operation_id": str(request.source.location.operation_id),
        "metadata_sha256": request.metadata_sha256, "locked_context_sha256": request.locked_context_sha256,
        "selected_pre_submit_run_id": str(request.attempt_id),
        "selected_pre_submit_request_sha256": request.request_digest,
        "selected_pre_submit_terminal_sha256": terminal.terminal_digest,
        "source_sha256": request.source.source_sha256(),
        "semantic_manifest_sha256": terminal.execution.manifest_sha256,
        "predecessor_submission_id": str(lineage.predecessor_submission_id) if lineage.predecessor_submission_id else None,
        "predecessor_submission_version": lineage.predecessor_submission_version,
        "checker_remediation_manifest_id": str(lineage.checker_remediation_manifest_id) if lineage.checker_remediation_manifest_id else None,
    }


def acceptance_receipt(terminal: SelectedPreSubmitTerminalFacts, accepted_at: datetime) -> dict:
    request = terminal.lease.reservation
    return {
        "operation_id": str(request.source.location.operation_id), "task_id": str(request.task_id),
        "assignment_id": str(request.assignment_id), "status": "accepted",
        "accepted_at": accepted_at.isoformat().replace("+00:00", "Z"),
        "task_status_at_acceptance": "evaluation_pending",
        "processing_stage_at_acceptance": "finalization_pending", "replayed": False,
        "pre_submission_results": public_pre_submission_results(terminal.execution),
    }


def authority_facts(row) -> IntakeAcceptanceAuthorityFacts:
    """Reconstruct exact immutable authority without consulting later eligibility."""
    context = row.accepted_context
    return IntakeAcceptanceAuthorityFacts(
        operation_id=UUID(row.id), project_id=UUID(row.project_id), task_id=UUID(row.task_id),
        assignment_id=UUID(row.assignment_id), actor_profile_id=UUID(row.actor_profile_id),
        identity_link_id=UUID(row.identity_link_id), idempotency_key=UUID(row.idempotency_key),
        metadata_sha256=row.metadata_sha256, locked_context_sha256=row.locked_context_sha256,
        task_status=row.eligible_task_status, foreground_lease_id=UUID(row.lease_id),
        foreground_lease_generation=row.lease_generation,
        selected_pre_submit_run_id=UUID(row.selected_pre_submit_run_id),
        selected_pre_submit_request_sha256=row.selected_pre_submit_request_sha256,
        selected_pre_submit_terminal_sha256=row.selected_pre_submit_terminal_sha256,
        source_sha256=row.accepted_source_sha256, semantic_manifest_sha256=row.accepted_manifest_sha256,
        accepted_context_sha256=row.accepted_context_sha256, receipt_sha256=row.acceptance_receipt_sha256,
        accepted_at=row.accepted_at,
        predecessor_submission_id=UUID(context["predecessor_submission_id"]) if context["predecessor_submission_id"] else None,
        predecessor_submission_version=context["predecessor_submission_version"],
        checker_remediation_manifest_id=UUID(context["checker_remediation_manifest_id"]) if context["checker_remediation_manifest_id"] else None,
    )


def finalization_event(row) -> OutboxAppendInput:
    return OutboxAppendInput(
        event_type="SubmissionFinalizationRequested", event_version=1,
        aggregate_type="submission_operation", aggregate_id=UUID(row.id), project_id=UUID(row.project_id),
        correlation_id=row.id, idempotency_key="submission-finalization:" + row.id,
        payload={"operation_id": row.id, "project_id": row.project_id, "task_id": row.task_id,
                 "acceptance_decision_id": row.acceptance_decision_id,
                 "accepted_context_sha256": row.accepted_context_sha256,
                 "receipt_sha256": row.acceptance_receipt_sha256},
    )


def stage_acceptance(row, terminal: SelectedPreSubmitTerminalFacts, accepted_at: datetime) -> None:
    """Stage evidence only; the composer must supply decision/event before flushing."""
    row.accepted_at = accepted_at
    row.selected_pre_submit_run_id = str(terminal.lease.reservation.attempt_id)
    row.selected_pre_submit_request_sha256 = terminal.lease.reservation.request_digest
    row.selected_pre_submit_terminal_sha256 = terminal.terminal_digest
    row.accepted_source_sha256 = terminal.lease.reservation.source.source_sha256()
    row.accepted_manifest_sha256 = terminal.execution.manifest_sha256
    row.accepted_context = acceptance_context(terminal)
    row.accepted_context_sha256 = canonical_json_hash(row.accepted_context)
    row.acceptance_receipt = acceptance_receipt(terminal, accepted_at)
    row.acceptance_receipt_sha256 = canonical_json_hash(row.acceptance_receipt)
