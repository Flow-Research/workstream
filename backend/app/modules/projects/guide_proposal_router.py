"""Public exact-compilation review and pre-submission policy decisions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.artifacts import guide_document_manifest_port
from app.adapters.checkers import project_guide_approval_compiler
from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.guide_proposals import ProposalRequest, get_proposal_request, get_correction_dispatch
from app.core.api_controls import ApiErrorResponse, StructuredHTTPException
from app.modules.projects.api.guide_proposal_package import GuideProposalReviewPackage
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval, GuideProposalApprovalInput, GuideProposalApprovalReceipt,
    GuideProposalCorrection, GuideProposalCorrectionInput, GuideProposalCorrectionReceipt,
    GuideProposalError, GuideProposalSelection, GuideProposalDispatchResponse,
)
from app.modules.projects.guide_mutation_router import require_guide_mutation_key

router = APIRouter(
    prefix="/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}",
    tags=["projects"],
    dependencies=[Depends(enforce_human_authorization_read)],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
)


IDEMPOTENCY_PARAMETER = {
    "name": "Idempotency-Key", "in": "header", "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def require_proposal_key(request: Request) -> UUID:
    """Raise immediately for missing keys before FastAPI resolves identity or SQL."""
    return require_guide_mutation_key(request.headers.get("Idempotency-Key", ""))


def proposal_http_error(exc: GuideProposalError) -> StructuredHTTPException:
    """Conceal selectors and authority; retain bounded actionable conflicts."""
    if exc.code in {"authority_unavailable", "proposal_unavailable"}:
        code, status, message = "proposal_unavailable", 404, "Guide proposal unavailable"
    elif exc.code == "storage_unavailable":
        code, status, message = exc.code, 503, "Guide proposal storage unavailable"
    else:
        code, status, message = exc.code, 409, "Guide proposal conflicts with current state"
    return StructuredHTTPException(
        status_code=status, detail=code, error_code=code, error_message=message,
        retryable=status == 503,
    )


def require_matching_target(target, project_id, guide_id, compilation_id):
    """Never let a body substitute an object from outside the selected path."""
    if (target.project_id, target.guide_id, target.compilation_id) != (
        project_id, guide_id, compilation_id
    ):
        raise proposal_http_error(GuideProposalError("proposal_unavailable"))


@router.get(
    "/proposal", response_model=GuideProposalReviewPackage,
    openapi_extra={"x-workstream-action-id": 'project.guide_compilation.review_package.read'},
)
async def review_proposal(
    project_id: UUID, guide_id: UUID, compilation_id: UUID,
    request: Annotated[ProposalRequest, Depends(get_proposal_request)],
) -> GuideProposalReviewPackage:
    """Read the exact finalized proposal and its approval/correction target."""
    try:
        response = await request.service.review_package(
            GuideProposalSelection(project_id=project_id, guide_id=guide_id, compilation_id=compilation_id),
            actor=request.actor, request_id=request.request_id,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/pre-submission-approval", response_model=GuideProposalApprovalReceipt,
    openapi_extra={"x-workstream-action-id": 'project.submission_artifact_policy.approve',
                   "parameters": [IDEMPOTENCY_PARAMETER]},
    dependencies=[Depends(require_proposal_key)],
)
async def approve_proposal(
    project_id: UUID, guide_id: UUID, compilation_id: UUID,
    payload: GuideProposalApprovalInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[ProposalRequest, Depends(get_proposal_request)],
) -> GuideProposalApprovalReceipt:
    """Approve one displayed pre-submission policy without running inference."""
    require_matching_target(payload.target, project_id, guide_id, compilation_id)
    planner, pre, post = project_guide_approval_compiler()
    try:
        response = await request.service.approve(
            GuideProposalApproval(**payload.model_dump(), idempotency_key=key),
            actor=request.actor, request_id=request.request_id,
            material=guide_document_manifest_port(request.session),
            pre_capabilities=pre, post_capabilities=post, planner=planner,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/corrections", response_model=GuideProposalCorrectionReceipt, status_code=201,
    openapi_extra={"x-workstream-action-id": 'project.guide_compilation.correction.request',
                   "parameters": [IDEMPOTENCY_PARAMETER]},
    dependencies=[Depends(require_proposal_key)],
)
async def correct_proposal(
    project_id: UUID, guide_id: UUID, compilation_id: UUID,
    payload: GuideProposalCorrectionInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[ProposalRequest, Depends(get_proposal_request)],
) -> GuideProposalCorrectionReceipt:
    """Commit one correction successor; explicit dispatch starts its async run."""
    require_matching_target(payload.target, project_id, guide_id, compilation_id)
    try:
        response = await request.service.request_correction(
            GuideProposalCorrection(**payload.model_dump(), idempotency_key=key),
            actor=request.actor, request_id=request.request_id,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/corrections/{correction_operation_id}/dispatch", response_model=GuideProposalDispatchResponse,
    status_code=202,
    openapi_extra={"x-workstream-action-id": 'project.guide_compilation.request'},
)
async def dispatch_correction(
    project_id: UUID, guide_id: UUID, compilation_id: UUID, correction_operation_id: UUID,
    request: Annotated[tuple, Depends(get_correction_dispatch)],
) -> GuideProposalDispatchResponse:
    """Manually dispatch the selected correction; its identity makes retries idempotent."""
    service, actor = request
    try:
        return await service.dispatch(
            GuideProposalSelection(project_id=project_id, guide_id=guide_id, compilation_id=compilation_id),
            correction_operation_id, actor=actor,
        )
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
