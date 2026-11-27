"""Bounded initial-evaluation event facts and exact caller request identity."""

from dataclasses import asdict
from uuid import UUID
from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.execution import REQUEST_EVENT
from app.modules.outbox.api import OutboxAppendInput
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.models import SubmissionDispatch


def creation_request_digest(request: SubmissionCreationRequest) -> str:
    """Bind all caller facts; admission remains the replay namespace."""
    body = asdict(request)
    if request.summary is None and request.contributor_attestation is None:
        body.pop("summary")
        body.pop("contributor_attestation")
    else:
        body.pop("feedback")
    return canonical_json_hash({
        "domain": "workstream.submission.creation",
        "request": {key: str(value) if isinstance(value, UUID) else value
                    for key, value in body.items()},
    })


def evaluation_request_event(receipt: SubmissionDispatch) -> OutboxAppendInput:
    """Publish identifiers only; the later handler must recover and reauthorize owners."""
    return OutboxAppendInput(
        event_type=REQUEST_EVENT, event_version=1, aggregate_type="submission",
        aggregate_id=UUID(receipt.submission_id), project_id=UUID(receipt.project_id),
        correlation_id=str(receipt.evaluation_request_id),
        idempotency_key="submission-evaluation:" + str(receipt.submission_id),
        payload={
            "project_id": str(receipt.project_id), "task_id": str(receipt.task_id),
            "submission_id": str(receipt.submission_id), "submission_version": receipt.submission_version,
            "request_id": str(receipt.evaluation_request_id),
            "request_digest": receipt.evaluation_request_digest, "evaluation_generation": 1,
            "attempt_id": str(receipt.evaluation_attempt_id), "result_id": str(receipt.evaluation_result_id),
            "creation_decision_id": str(receipt.creation_decision_id),
            "binding_decision_id": str(receipt.binding_decision_id),
        },
    )
