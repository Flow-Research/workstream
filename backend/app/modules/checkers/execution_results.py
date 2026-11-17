"""One complete member classification and closed history presentation."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.checkers.api.execution import COMPLETION_EVENT, EvaluationCompletion
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmitCurrentResultReference
from app.modules.outbox.api import OutboxAppendInput

from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
    coverage_gap_without_failure,
)


@dataclass(frozen=True, slots=True)
class ResultClassification:
    """Closed routing recommendation and counts derived from the complete locked policy."""

    routing: str
    passed: int
    warning: int
    failed: int
    blocking: int


def classify_result(
    request: PostSubmissionExecutionRequest, result: PostSubmissionExecutionResult,
    *, human_review_required: bool,
) -> ResultClassification:
    """Validate every selected member before deriving policy-governed routing.

    A coverage gap (``coverage_incomplete`` without errors) never auto-accepts:
    with human review it goes to a reviewer, otherwise it returns to the
    contributor. TASK records that return without spending a revision round.
    """
    result.validate_request(request)
    if result.outcome == "infrastructure_failed":
        return ResultClassification("not_evaluated", 0, 0, 0, 0)
    members = result.execution.external_members if result.execution else ()
    failed = sum(member.result.verdict == "failed" for member in members)
    returned = failed or (coverage_gap_without_failure(result) and not human_review_required)
    return ResultClassification(
        "needs_revision" if returned else "allow_review",
        sum(member.result.verdict == "passed" for member in members),
        0,
        failed,
        failed,
    )


RESULT_STATUS_MESSAGES = {
    "passed": ("Check passed.", None),
    "warning": ("Check reported a warning.", "Review the project guide and check findings."),
    "failed": ("Project check failed.", "Review the project guide and check findings."),
    "coverage_incomplete": (
        "Check could not evaluate part of the submission.",
        "Make the listed files readable by the project checks, then resubmit.",
    ),
}


def evaluation_completion_event(request, result, *, attempt_id: UUID,
                                execute_evidence_id: UUID, finalize_evidence_id: UUID,
                                routing_recommendation: str) -> OutboxAppendInput:
    """One exact completion envelope shared by publication and observation."""
    result.validate_request(request)
    reference = SelectedPostSubmitCurrentResultReference(
        **result.model_dump(include=set(SelectedPostSubmitCurrentResultReference.model_fields) - {"schema_version"})
    )
    reference.validate_result(result)
    event = EvaluationCompletion(
        project_id=request.project_id, task_id=request.task_id, submission_id=request.submission_id,
        reference=reference, routing_recommendation=routing_recommendation, output_binding_ids=(),
        execute_evidence_id=execute_evidence_id, finalize_evidence_id=finalize_evidence_id,
    )
    return OutboxAppendInput(
        event_type=COMPLETION_EVENT, event_version=1, aggregate_type="checker_run",
        aggregate_id=attempt_id, project_id=request.project_id,
        correlation_id=str(request.evaluation_request_id),
        idempotency_key="checker-completed:" + str(attempt_id), payload=event.model_dump(mode="json"),
    )
