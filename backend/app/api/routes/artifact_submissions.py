"""One raw-ZIP contributor mutation through ART's foreground command."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.adapters.artifacts import get_submission_intake_command
from app.api.deps.authorization import get_authorization_actor_identity
from app.api.submission_intake import SubmissionIntakeHeaders, submission_intake_headers
from app.core.api_controls import error_response
from app.modules.artifacts.api.submission_command import SubmissionAcceptedResponse, SubmissionIntakeCommand
from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
from app.modules.authorization.api import ActorIdentityFacts

router = APIRouter(tags=["tasks"])

_HEADER_PARAMETERS = [
    {"name": name, "in": "header", "required": required, "schema": schema}
    for name, required, schema in (
        ("Idempotency-Key", True, {"type": "string", "format": "uuid"}),
        ("X-Task-Assignment-Id", True, {"type": "string", "format": "uuid"}),
        ("X-Submission-Summary", False, {"type": "string", "maxLength": 65536}),
        ("X-Contributor-Attestation", False, {"type": "string", "maxLength": 65536}),
        ("X-Predecessor-Submission-Id", False, {"type": "string", "format": "uuid"}),
        ("X-Revision-Preparation-Id", False, {"type": "string", "format": "uuid"}),
        ("X-Revision-Preparation-Sha256", False, {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}),
    )
]


def _failure_status(code: str) -> int:
    if code == "submission_unavailable":
        return 404
    if code == "submission_archive_limit_exceeded":
        return 413
    if code == "submission_upload_timeout":
        return 408
    if code == "submission_capacity_exceeded":
        return 429
    if code in {"submission_packet_invalid", "pre_submission_checker_failed", "revision_acknowledgement_invalid"}:
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
            headers.metadata, request.stream(), actor_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id, idempotency_key=headers.idempotency_key,
            declared_raw_bytes=headers.declared_raw_bytes,
        )
    except SubmissionIntakeFailure as exc:
        details = None
        if exc.code == "pre_submission_checker_failed":
            details = {"status": "failed", "eligible_to_submit": False, "results": exc.pre_submission_results or []}
        return error_response(
            request, status_code=_failure_status(exc.code), code=exc.code,
            message="Submission unavailable" if exc.code == "submission_unavailable" else exc.code,
            details=details, retryable=exc.code in {"submission_capacity_exceeded", "submission_infrastructure_unavailable", "submission_outcome_unknown"},
        )
    return SubmissionAcceptedResponse.model_validate(receipt)
