"""Shared CHECKERS source-row identity validation for writes and retained reads."""

from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitReservationFacts
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
