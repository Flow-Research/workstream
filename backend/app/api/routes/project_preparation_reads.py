"""A Project Manager reads a project's ZIP preparations across contributors."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.project_preparation_reads import ProjectPreparationReads, get_project_preparation_reads
from app.core.api_controls import ApiErrorResponse
from app.modules.artifacts.api.submission_preparation import (
    PreparationOutcome, ProjectSubmissionBundlePreparationPage,
)

router = APIRouter(dependencies=[Depends(enforce_human_authorization_read)])
Reads = Annotated[ProjectPreparationReads, Depends(get_project_preparation_reads)]
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}


@router.get(
    "/projects/{project_id}/submission-bundle-preparations", response_model=ProjectSubmissionBundlePreparationPage,
    tags=["projects"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "project.submission_bundle_preparation.list"},
)
async def list_project_preparations(
    project_id: UUID, reads: Reads, outcome: PreparationOutcome | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
) -> ProjectSubmissionBundlePreparationPage:
    """Every contributor's ZIP preparations, newest first, with finding counts and no findings or files.

    ``outcome=failed`` lists completed intake checks that blocked the ZIP.
    """
    return await reads.list(project_id=project_id, outcome=outcome, limit=limit, cursor=cursor)
