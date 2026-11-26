"""The caller's own projects, claims, attempts, intake preparations and totals."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.contributor_reads import (
    ActorProjectPage, ContributorReadOperation, ContributorWorkSummary, ExactContributorAssignment, get_contributor_reads,
)
from app.api.routes.project_guide_reads import _ORIGINAL_TYPES, guide_original_response
from app.core.api_controls import ApiErrorResponse
from app.modules.artifacts.api.submission_preparation import (
    SubmissionBundlePreparationDetail, SubmissionBundlePreparationPage,
)
from app.modules.projects.api.guide_reads import ApprovedContributorGuide, VerifiedGuideDocumentRead
from app.modules.tasks.api.contributor_reads import (
    AssignmentState, ContributorAssignmentPage, ContributorSubmissionPage,
)
from app.modules.tasks.api.submission_history import SubmissionAttemptStatus

router = APIRouter(dependencies=[Depends(enforce_human_authorization_read)])
Reads = Annotated[ContributorReadOperation, Depends(get_contributor_reads)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[str | None, Query(min_length=1, max_length=512)]
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}


@router.get(
    "/actors/me/projects", response_model=ActorProjectPage, tags=["actors"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "actor.project.list"},
)
async def list_my_projects(reads: Reads, limit: PageLimit = 50, cursor: PageCursor = None) -> ActorProjectPage:
    """Projects where you hold an exact grant, your effective roles and the active guide version."""
    return await reads.projects(limit=limit, cursor=cursor)


@router.get(
    "/actors/me/assignments", response_model=ContributorAssignmentPage, tags=["actors"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "actor.assignment.list"},
)
async def list_my_assignments(
    reads: Reads, project_id: UUID | None = None, state: AssignmentState | None = None,
    updated_since: AwareDatetime | None = None, limit: PageLimit = 50, cursor: PageCursor = None,
) -> ContributorAssignmentPage:
    """Your claims in projects where you hold a Submitter grant, by activity time, with the next action."""
    return await reads.assignments(
        project_id=project_id, state=state, updated_since=updated_since, limit=limit, cursor=cursor,
    )


@router.get(
    "/tasks/{task_id}/assignments/{assignment_id}", response_model=ExactContributorAssignment,
    tags=["tasks"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "task.assignment.read"},
)
async def read_my_assignment(
    task_id: UUID, assignment_id: UUID, reads: Reads, limit: PageLimit = 25, cursor: PageCursor = None,
) -> ExactContributorAssignment:
    """Read your assignment status, feedback and earned evidence by task and assignment."""
    return await reads.assignment(task_id, assignment_id, limit=limit, cursor=cursor)


@router.get(
    "/actors/me/submissions", response_model=ContributorSubmissionPage, tags=["actors"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "actor.submission.list"},
)
async def list_my_submissions(
    reads: Reads, project_id: UUID | None = None, task_id: UUID | None = None,
    status: SubmissionAttemptStatus | None = None, updated_since: AwareDatetime | None = None,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> ContributorSubmissionPage:
    """Your attempts in projects where you hold a Submitter grant, by update time."""
    return await reads.submissions(
        project_id=project_id, task_id=task_id, status=status, updated_since=updated_since,
        limit=limit, cursor=cursor,
    )


@router.get(
    "/actors/me/summary", response_model=ContributorWorkSummary, tags=["actors"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "actor.work_summary.read"},
)
async def read_my_summary(reads: Reads, project_id: UUID | None = None) -> ContributorWorkSummary:
    """Counts of your claims and attempts, and your award totals per instrument and unit."""
    return await reads.summary(project_id=project_id)


@router.get(
    "/tasks/{task_id}/submission-bundle-preparations", response_model=SubmissionBundlePreparationPage,
    tags=["tasks"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "task.submission_bundle_preparation.list"},
)
async def list_my_preparations(
    task_id: UUID, reads: Reads, limit: PageLimit = 25, cursor: PageCursor = None,
) -> SubmissionBundlePreparationPage:
    """Your historical ZIP preparations for one task, newest first."""
    return await reads.preparations(task_id=task_id, limit=limit, cursor=cursor)


@router.get(
    "/tasks/{task_id}/submission-bundle-preparations/{preparation_id}",
    response_model=SubmissionBundlePreparationDetail, tags=["tasks"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "task.submission_bundle_preparation.read"},
)
async def read_my_preparation(
    task_id: UUID, preparation_id: UUID, reads: Reads,
) -> SubmissionBundlePreparationDetail:
    """One historical preparation with its intake findings; others are not found."""
    return await reads.preparation(task_id=task_id, preparation_id=preparation_id)


@router.get(
    "/projects/{project_id}/contributor-guide", response_model=ApprovedContributorGuide,
    tags=["projects"], responses=_ERRORS,
    openapi_extra={"x-workstream-action-id": "project.contributor_guide.read"},
)
async def read_approved_contributor_guide(project_id: UUID, reads: Reads) -> ApprovedContributorGuide:
    """Read the project's active approved contributor guide before claiming a task."""
    return await reads.approved_guide(project_id)


async def verified_contributor_guide_document(
    project_id: UUID, guide_id: UUID, document_id: UUID, reads: Reads,
) -> AsyncIterator[VerifiedGuideDocumentRead]:
    async with reads.approved_guide_document(project_id, guide_id, document_id) as read:
        yield read


@router.get(
    "/projects/{project_id}/contributor-guide/{guide_id}/documents/{document_id}/content",
    response_class=StreamingResponse, tags=["projects"],
    openapi_extra={"x-workstream-action-id": "project.contributor_guide.read"},
    responses={
        200: {"description": "Exact verified uploaded original", "content": {
            media_type: {"schema": {"type": "string", "format": "binary"}} for media_type in _ORIGINAL_TYPES
        }},
        **_ERRORS,
    },
)
async def read_contributor_guide_document(
    read: Annotated[VerifiedGuideDocumentRead, Depends(verified_contributor_guide_document)],
) -> StreamingResponse:
    """Download one exact original of the active approved guide."""
    return guide_original_response(read)
