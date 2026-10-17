"""A Project Manager's project-wide attempts, claims, summary and task import batches."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.project_work_reads import ProjectWorkReadOperation, ProjectWorkSummary, get_project_work_reads
from app.core.api_controls import ApiErrorResponse
from app.modules.tasks.api.contributor_reads import AssignmentState
from app.modules.tasks.api.project_reads import (
    ProjectAssignmentPage, ProjectSubmissionPage, ProjectTaskImportBatchPage,
)
from app.modules.tasks.api.submission_history import SubmissionAttemptStatus

router = APIRouter(dependencies=[Depends(enforce_human_authorization_read)])
Reads = Annotated[ProjectWorkReadOperation, Depends(get_project_work_reads)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[str | None, Query(min_length=1, max_length=512)]
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}


@router.get(
    "/projects/{project_id}/submissions", response_model=ProjectSubmissionPage, tags=["projects"],
    responses=_ERRORS, openapi_extra={"x-workstream-action-id": "project.submission.list"},
)
async def list_project_submissions(
    project_id: UUID, reads: Reads, status: SubmissionAttemptStatus | None = None, task_id: UUID | None = None,
    submitter_actor_id: UUID | None = None, updated_since: AwareDatetime | None = None,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> ProjectSubmissionPage:
    """Every attempt in the project by activity time, with its submitter and finding counts."""
    return await reads.submissions(
        project_id, status=status, task_id=task_id, submitter_actor_id=submitter_actor_id,
        updated_since=updated_since, limit=limit, cursor=cursor,
    )


@router.get(
    "/projects/{project_id}/assignments", response_model=ProjectAssignmentPage, tags=["projects"],
    responses=_ERRORS, openapi_extra={"x-workstream-action-id": "project.assignment.list"},
)
async def list_project_assignments(
    project_id: UUID, reads: Reads, state: AssignmentState | None = None,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> ProjectAssignmentPage:
    """Every claim in the project by activity time, with its contributor and the contributor's next action."""
    return await reads.assignments(project_id, state=state, limit=limit, cursor=cursor)


@router.get(
    "/projects/{project_id}/summary", response_model=ProjectWorkSummary, tags=["projects"],
    responses=_ERRORS, openapi_extra={"x-workstream-action-id": "project.summary.read"},
)
async def read_project_summary(project_id: UUID, reads: Reads) -> ProjectWorkSummary:
    """Task, claim and attempt counts, acceptance rate and checker infrastructure failures.

    Award totals appear only for a caller who also holds an exact-project Finance Authority grant.
    """
    return await reads.summary(project_id)


@router.get(
    "/projects/{project_id}/task-import-batches", response_model=ProjectTaskImportBatchPage, tags=["projects"],
    responses=_ERRORS, openapi_extra={"x-workstream-action-id": "project.task.import_batch.list"},
)
async def list_project_task_import_batches(
    project_id: UUID, reads: Reads, limit: PageLimit = 50, cursor: PageCursor = None,
) -> ProjectTaskImportBatchPage:
    """The project's native task import batches by creation time, with state and member task counts."""
    return await reads.import_batches(project_id, limit=limit, cursor=cursor)
