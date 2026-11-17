"""Shared CHECKERS source-row identity validation for writes and retained reads."""

from uuid import UUID

from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitReservationFacts, SelectedPreSubmitLeaseFacts
from app.modules.checkers.models import SelectedPreSubmitRun


def matches_source_request(row: SelectedPreSubmitRun, facts: SelectedPreSubmitReservationFacts) -> bool:
    return (
        row.request_json == facts.canonical_body()
        and row.request_digest == facts.request_digest
        and row.id == str(facts.attempt_id)
        and row.actor_profile_id == str(facts.actor_profile_id)
        and row.identity_link_id == str(facts.identity_link_id)
        and row.project_id == str(facts.project_id)
        and row.task_id == str(facts.task_id)
        and row.assignment_id == str(facts.assignment_id)
        and row.idempotency_key == str(facts.idempotency_key)
        and row.source_operation_id == str(facts.source.location.operation_id)
        and row.prepared_generation_id is None
        and row.policy_sha256 == facts.policy_sha256
        and row.default_behavior_sha256 == facts.default_behavior_sha256
        and row.default_input_sha256 is None
        and row.archive_sha256 == facts.archive_sha256
        and row.archive_byte_count == facts.archive_byte_count
        and row.semantic_manifest_sha256 is None
        and row.execution_budget_ms == facts.execution_budget_ms
    )


def matches_terminal(row: SelectedPreSubmitRun, request, terminal) -> bool:
    """Check retained outcome/lease/timing without conferring current liveness."""
    if terminal is None:
        if type(request) is SelectedPreSubmitReservationFacts:
            if row.finalize_evidence_id is not None:
                return False
            if row.status == "queued":
                if (row.lease_id is not None or row.lease_generation != 0
                        or row.lease_expires_at is not None or row.started_at is not None
                        or row.execute_evidence_id is not None):
                    return False
            elif row.status == "running":
                SelectedPreSubmitLeaseFacts(request, UUID(str(row.lease_id)),
                                            row.lease_generation, row.lease_expires_at)
                if (row.execute_evidence_id is None or row.started_at is None
                        or not row.queued_at <= row.started_at <= row.lease_expires_at):
                    return False
        return (
            row.status in {"queued", "running"} and row.terminal_digest is None
            and row.eligible is None and row.completed_at is None
        )
    return (
        terminal.lease.reservation == request
        and terminal.terminal_digest == row.terminal_digest
        and terminal.outcome == row.status
        and str(terminal.lease.lease_id) == str(row.lease_id)
        and terminal.lease.lease_generation == row.lease_generation
        and terminal.lease.lease_expires_at == row.lease_expires_at
        and terminal.queued_at == row.queued_at
        and terminal.started_at == row.started_at
        and terminal.completed_at == row.completed_at
        and (terminal.execution.eligible if terminal.execution is not None else None) is row.eligible
    )
