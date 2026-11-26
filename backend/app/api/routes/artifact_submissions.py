"""One raw-ZIP contributor mutation through ART's foreground command."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse

from app.adapters.artifacts import get_submission_intake_command, get_submission_operation_reader
from app.api.deps.authorization import get_authorization_actor_identity
from app.api.submission_intake import SubmissionIntakeHeaders, submission_intake_headers, submission_intake_body
from app.core.api_controls import error_response
from app.modules.artifacts.api.submission_command import (
    SubmissionAcceptedResponse, SubmissionIntakeCommand, SubmissionOperationReader,
    SubmissionOperationResponse, SubmissionOperationSelector,
)
from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
from app.modules.authorization.api import ActorIdentityFacts

router = APIRouter(tags=["tasks"])

_HEADER_PARAMETERS = [
    {"name": name, "in": "header", "required": required, "schema": schema}
    for name, required, schema in (
        ("Idempotency-Key", True, {"type": "string", "format": "uuid"}),
        ("X-Task-Assignment-Id", True, {"type": "string", "format": "uuid"}),
        ("X-Submission-Feedback", False, {"type": "string", "maxLength": 4096,
         "description": "Optional project feedback. Printable ASCII without leading or trailing whitespace."}),
    )
]


_FAILURE_MESSAGES = {
    "submission_unavailable": "Submission unavailable",
    "submission_packet_invalid": "The submitted ZIP or request was invalid",
    "submission_archive_limit_exceeded": "The ZIP exceeds the permitted archive limits",
    "submission_upload_timeout": "The ZIP upload timed out",
    "submission_capacity_exceeded": "Submission processing is at capacity. Try again later.",
    "submission_infrastructure_unavailable": "Submission processing is temporarily unavailable",
    "submission_outcome_unknown": "Check the original submission operation or retry with the same idempotency key",
    "submission_operation_in_progress": "This assignment already has a submission in progress",
    "submission_idempotency_conflict": "This idempotency key was used with different submission inputs",
    "pre_submission_checker_failed": "The ZIP did not pass the pre-submission checks",
    "revision_deadline_expired": "Your assignment expired. Reclaim the task if it is still available.",
    "revision_limit_reached": "Your assignment has reached its revision limit",
    "revision_context_blocked": "This assignment is waiting for its revision requirements",
    "revision_context_changed": "The revision requirements or terms changed. Read your assignment before submitting again.",
    "task_submission_predecessor_changed": "The assignment's current revision changed. Read your assignment before submitting again.",
}


def _failure_status(code: str) -> int:
    """Map a closed submission failure code to its public HTTP status."""
    if code == "submission_unavailable":
        return 404
    if code == "submission_archive_limit_exceeded":
        return 413
    if code == "submission_upload_timeout":
        return 408
    if code == "submission_capacity_exceeded":
        return 429
    if code in {"submission_packet_invalid", "pre_submission_checker_failed"}:
        return 422
    if code in {"submission_infrastructure_unavailable", "submission_outcome_unknown"}:
        return 503
    return 409


@router.post(
    "/tasks/{task_id}/submissions", response_model=SubmissionAcceptedResponse, status_code=202,
    openapi_extra={
        "x-workstream-action-id": "submission.create",
        "parameters": _HEADER_PARAMETERS,
        "requestBody": {"required": True, "content": {
            "application/zip": {"schema": {"type": "string", "format": "binary"}},
        }},
    },
    responses={
        404: {"description": "Task or contributor authority unavailable"},
        408: {"description": "Upload idle or total deadline expired"},
        409: {"description": "Operation, idempotency or governed revision conflict"},
        413: {"description": "Raw ZIP exceeds the permitted limit"},
        415: {"description": "Unsupported media type or content encoding"},
        422: {"description": "Invalid packet or bounded pre-submission QC feedback"},
        429: {"description": "Submission capacity exhausted"},
        503: {"description": "Infrastructure unavailable or acceptance outcome unknown"},
    },
)
async def submit_source(
    task_id: UUID,
    request: Request,
    headers: Annotated[SubmissionIntakeHeaders, Depends(submission_intake_headers)],
    actor: Annotated[ActorIdentityFacts, Depends(get_authorization_actor_identity)],
    command: Annotated[SubmissionIntakeCommand, Depends(get_submission_intake_command)],
) -> SubmissionAcceptedResponse | JSONResponse:
    """Acknowledge only committed acceptance, with no fabricated T5 identifiers."""
    try:
        receipt = await command.submit(
            headers.metadata, submission_intake_body(request), actor_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id, idempotency_key=headers.idempotency_key,
            declared_raw_bytes=headers.declared_raw_bytes,
        )
    except SubmissionIntakeFailure as exc:
        details = None
        if exc.code == "pre_submission_checker_failed":
            details = {"status": "failed", "eligible_to_submit": False, "results": exc.pre_submission_results or []}
        return error_response(
            request, status_code=_failure_status(exc.code), code=exc.code,
            message=_FAILURE_MESSAGES.get(exc.code, "Submission could not be completed"),
            details=details, retryable=exc.code in {"submission_capacity_exceeded", "submission_infrastructure_unavailable", "submission_outcome_unknown"},
        )
    return SubmissionAcceptedResponse.model_validate(receipt)


@router.get(
    "/tasks/{task_id}/submission-operations", response_model=SubmissionOperationResponse,
    openapi_extra={
        "x-workstream-action-id": "task.submission_operation.read",
        "x-workstream-management-action-id": "project.task.submission_operation.read",
    },
    responses={404: {"description": "Operation or current read authority unavailable"},
               422: {"description": "Exactly one operation UUID or actor-scoped idempotency key is required"},
               503: {"description": "Stored operation progress cannot be verified"}},
)
async def read_submission_operation(
    task_id: UUID, request: Request,
    selector: Annotated[SubmissionOperationSelector, Query()],
    reader: Annotated[SubmissionOperationReader, Depends(get_submission_operation_reader)],
) -> SubmissionOperationResponse | JSONResponse:
    """Read this operation's own evidence under current contributor or management authority."""
    try:
        return await reader.read(task_id, selector)
    except SubmissionIntakeFailure as exc:
        return error_response(request, status_code=_failure_status(exc.code), code=exc.code,
            message="Submission unavailable" if exc.code == "submission_unavailable" else exc.code,
            retryable=exc.code == "submission_infrastructure_unavailable")
