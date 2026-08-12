"""Hidden delivery surface for ART-owned contributor bundle preparation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.adapters.artifacts import (
    get_submission_bundle_preparation_actor,
    get_submission_bundle_preparation_command,
)
from app.core.api_controls import request_ids
from app.modules.artifacts.api import (
    SubmissionBundlePreparationCommand,
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationStatus,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.authorization.api import ActorIdentityFacts

router = APIRouter(tags=["tasks"])


class SubmissionBundlePreparationResponse(BaseModel):
    """Bounded hidden operation state without provider or scratch coordinates."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    put_attempt_id: UUID
    admission_id: UUID | None
    submission_bundle_preparation_status: SubmissionBundlePreparationStatus
    replayed: bool


@router.post(
    "/tasks/{task_id}/submission-bundle-preparations",
    response_model=SubmissionBundlePreparationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def prepare_submission_bundle(
    task_id: str,
    request: Request,
    actor: Annotated[ActorIdentityFacts, Depends(get_submission_bundle_preparation_actor)],
    command: Annotated[
        SubmissionBundlePreparationCommand,
        Depends(get_submission_bundle_preparation_command),
    ],
    assignment_id: Annotated[str | None, Header(alias="X-Task-Assignment-Id")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    summary: Annotated[str | None, Header(alias="X-Submission-Summary")] = None,
    contributor_attestation: Annotated[
        str | None, Header(alias="X-Contributor-Attestation")
    ] = None,
    predecessor_submission_id: Annotated[
        str | None, Header(alias="X-Predecessor-Submission-Id")
    ] = None,
) -> SubmissionBundlePreparationResponse:
    """Run the hidden continuous ZIP preparation surface; AUTH remains fail closed."""
    if None in (assignment_id, idempotency_key, summary, contributor_attestation):
        raise HTTPException(status_code=404, detail="Task not found")
    assert assignment_id is not None and idempotency_key is not None
    assert summary is not None and contributor_attestation is not None
    try:
        identifiers = (
            UUID(task_id),
            UUID(assignment_id),
            UUID(idempotency_key),
            UUID(predecessor_submission_id) if predecessor_submission_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    try:
        request_id, correlation_id = (UUID(value) for value in request_ids(request))
        result = await command.prepare(
            SubmissionBundlePreparationRequest(
                actor=actor,
                request_id=request_id,
                correlation_id=correlation_id,
                task_id=identifiers[0],
                assignment_id=identifiers[1],
                predecessor_submission_id=identifiers[3],
                idempotency_key=identifiers[2],
                summary=summary,
                contributor_attestation=contributor_attestation,
                media_type=request.headers.get("content-type", ""),
                byte_source=request.stream(),
            )
        )
    except SubmissionBundlePreparationUnavailable as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except SubmissionBundlePreparationRejected as exc:
        code = str(exc)
        if code == "submission_bundle_preparation_context_changed":
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=422, detail=code) from exc
    return SubmissionBundlePreparationResponse.model_validate(result, from_attributes=True)
