"""Public exact-compilation review and pre-submission policy decisions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.guide_proposals import (
    ProposalRequest,
    CompilationDispatchRequest,
    get_proposal_request,
    get_correction_dispatch,
    get_assistance_dispatch,
    get_requirements_dispatch,
)
from app.core.api_controls import ApiErrorResponse
from app.modules.projects.api.guide_proposal_package import GuideProposalReviewPackage
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalApprovalInput,
    GuideProposalApprovalReceipt,
    GuideProposalCorrection,
    GuideProposalCorrectionInput,
    GuideProposalCorrectionReceipt,
    GuideProposalError,
    GuideProposalSelection,
    GuideProposalDispatchResponse,
    GuideCompilationDispatchResponse,
)
from app.api.deps.guide_proposal_http import (
    IDEMPOTENCY_PARAMETER,
    require_proposal_key,
    proposal_http_error,
    require_matching_target,
)
from app.adapters.projects import dispatch_post_policy_derivation_after_commit

router = APIRouter(
    prefix="/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}",
    tags=["projects"],
    dependencies=[Depends(enforce_human_authorization_read)],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
)


@router.get(
    "/proposal",
    response_model=GuideProposalReviewPackage,
    openapi_extra={"x-workstream-action-id": "project.guide_compilation.review_package.read"},
)
async def review_proposal(
    project_id: UUID,
    guide_id: UUID,
    compilation_id: UUID,
    request: Annotated[ProposalRequest, Depends(get_proposal_request)],
) -> GuideProposalReviewPackage:
    """Read the exact finalized proposal and its approval/correction target."""
    try:
        response = await request.service.review_package(
            GuideProposalSelection(
                project_id=project_id, guide_id=guide_id, compilation_id=compilation_id
            ),
            actor=request.actor,
            request_id=request.request_id,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/pre-submission-approval",
    response_model=GuideProposalApprovalReceipt,
    openapi_extra={
        "x-workstream-action-id": "project.submission_artifact_policy.approve",
        "parameters": [IDEMPOTENCY_PARAMETER],
    },
    dependencies=[Depends(require_proposal_key)],
)
async def approve_proposal(
    project_id: UUID,
    guide_id: UUID,
    compilation_id: UUID,
    payload: GuideProposalApprovalInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[ProposalRequest, Depends(get_proposal_request)],
) -> GuideProposalApprovalReceipt:
    """Approve one displayed pre-submission policy without running inference."""
    require_matching_target(payload.target, project_id, guide_id, compilation_id)
    try:
        response = await request.service.approve(
            GuideProposalApproval(**payload.model_dump(), idempotency_key=key),
            actor=request.actor,
            request_id=request.request_id,
        )
        await request.session.commit()
        await dispatch_post_policy_derivation_after_commit(response.operation_id)
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/corrections",
    response_model=GuideProposalCorrectionReceipt,
    status_code=201,
    openapi_extra={
        "x-workstream-action-id": "project.guide_compilation.correction.request",
        "parameters": [IDEMPOTENCY_PARAMETER],
    },
    dependencies=[Depends(require_proposal_key)],
)
async def correct_proposal(
    project_id: UUID,
    guide_id: UUID,
    compilation_id: UUID,
    payload: GuideProposalCorrectionInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[ProposalRequest, Depends(get_proposal_request)],
) -> GuideProposalCorrectionReceipt:
    """Commit one correction successor; explicit dispatch starts its async run."""
    require_matching_target(payload.target, project_id, guide_id, compilation_id)
    try:
        response = await request.service.request_correction(
            GuideProposalCorrection(**payload.model_dump(), idempotency_key=key),
            actor=request.actor,
            request_id=request.request_id,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/corrections/{correction_operation_id}/dispatch",
    response_model=GuideProposalDispatchResponse,
    status_code=202,
    openapi_extra={"x-workstream-action-id": "project.guide_compilation.request"},
)
async def dispatch_correction(
    project_id: UUID,
    guide_id: UUID,
    compilation_id: UUID,
    correction_operation_id: UUID,
    request: Annotated[CompilationDispatchRequest, Depends(get_correction_dispatch)],
) -> GuideProposalDispatchResponse:
    """Manually dispatch the selected correction; its identity makes retries idempotent."""
    try:
        return await request.service.dispatch(
            GuideProposalSelection(
                project_id=project_id, guide_id=guide_id, compilation_id=compilation_id
            ),
            correction_operation_id,
            actor=request.actor,
        )
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc


initial_router = APIRouter(
    prefix="/projects/{project_id}/guides/{guide_id}", tags=["projects"],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
)


@initial_router.post("/setup", response_model=GuideCompilationDispatchResponse, status_code=202,
    openapi_extra={"x-workstream-action-id": "project.guide_compilation.request",
                   "parameters": [IDEMPOTENCY_PARAMETER]})
async def request_guide_assistance(
    project_id: UUID, guide_id: UUID,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[CompilationDispatchRequest, Depends(get_assistance_dispatch)],
) -> GuideCompilationDispatchResponse:
    """Explicitly request configured guide assistance."""
    try:
        return await request.service.request_initial(project_id, guide_id, key, actor=request.actor,
                                                     inference_required=True)
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc


@initial_router.post("/requirements/compile", response_model=GuideCompilationDispatchResponse, status_code=202,
    openapi_extra={"x-workstream-action-id": "project.guide_compilation.request",
                   "parameters": [IDEMPOTENCY_PARAMETER]})
async def compile_manager_requirements(
    project_id: UUID, guide_id: UUID,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[CompilationDispatchRequest, Depends(get_requirements_dispatch)],
) -> GuideCompilationDispatchResponse:
    """Compile the manager's uploaded rules without an inference provider."""
    try:
        return await request.service.request_initial(project_id, guide_id, key, actor=request.actor,
                                                     inference_required=False)
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
