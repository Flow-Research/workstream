"""A Project Manager's reads of a project's guides, activation readiness and uploaded originals."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.project_guide_reads import ProjectGuideReadOperation, get_project_guide_reads
from app.core.api_controls import ApiErrorResponse
from app.modules.projects.api.guide_activation import GuideActivationReadiness
from app.modules.projects.api.guide_reads import (
    GuideStatus, ProjectGuideDetail, ProjectGuidePage, VerifiedGuideDocumentRead,
)

router = APIRouter(
    prefix="/projects/{project_id}/guides", tags=["projects"],
    dependencies=[Depends(enforce_human_authorization_read)],
)
Reads = Annotated[ProjectGuideReadOperation, Depends(get_project_guide_reads)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[str | None, Query(min_length=1, max_length=512)]
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}
_ORIGINAL_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/markdown",
)


@router.get(
    "", response_model=ProjectGuidePage, responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "project.guide.list"},
)
async def list_project_guides(
    project_id: UUID, reads: Reads, status: GuideStatus | None = None,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> ProjectGuidePage:
    """The project's guide versions by creation order, with their stored status."""
    return await reads.guides(project_id, status=status, limit=limit, cursor=cursor)


@router.get(
    "/{guide_id}", response_model=ProjectGuideDetail, responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "project.guide.read"},
)
async def read_project_guide(project_id: UUID, guide_id: UUID, reads: Reads) -> ProjectGuideDetail:
    """One guide with its declared documents, selected policies and latest setup run and compilation."""
    return await reads.guide(project_id, guide_id)


@router.get(
    "/{guide_id}/activation-readiness", response_model=GuideActivationReadiness, responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "project.guide.activation_readiness.read"},
)
async def read_guide_activation_readiness(
    project_id: UUID, guide_id: UUID, reads: Reads,
) -> GuideActivationReadiness:
    """Dry-run activation over the current selections: ready, or the unmet conditions it evaluates, with refusal codes.

    A check whose inputs are missing is not evaluated.
    """
    return await reads.activation_readiness(project_id, guide_id)


async def verified_guide_document(
    project_id: UUID, guide_id: UUID, document_id: UUID, reads: Reads,
) -> AsyncIterator[VerifiedGuideDocumentRead]:
    """Hold the verified staged original open while the response streams."""
    async with reads.document(project_id, guide_id, document_id) as read:
        yield read


@router.get(
    "/{guide_id}/documents/{document_id}/content", response_class=StreamingResponse,
    openapi_extra={"x-workstream-action-id": "project.guide.document.read"},
    responses={
        200: {"description": "Exact verified uploaded original", "content": {
            media_type: {"schema": {"type": "string", "format": "binary"}} for media_type in _ORIGINAL_TYPES
        }},
        **{status: {"model": ApiErrorResponse} for status in (404, 409, 422, 503)},
    },
)
async def read_guide_document_content(
    read: Annotated[VerifiedGuideDocumentRead, Depends(verified_guide_document)],
) -> StreamingResponse:
    """Serve one uploaded guide original after its bytes are verified against committed custody."""
    return StreamingResponse(read.stream, media_type=read.media_type, headers={
        "Content-Length": str(read.byte_count),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{read.document_id}"',
    })
