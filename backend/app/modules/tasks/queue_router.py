"""Compose exact AUTH decisions with TASK's existing bounded queue projections."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.repository import TaskRepository
from app.adapters.tasks import contributor_task_repository
from app.api.deps.authorization import (
    enforce_human_authorization_read, get_task_queue_authorization,
)
from app.db.session import get_db_session
from app.modules.authorization.api.task_queues import (
    READY_QUEUE_ACTION, MANAGEMENT_QUEUE_ACTION, OPERATIONAL_QUEUE_ACTION,
    TaskQueueReadAuthorizationPort, TaskQueueReadRequest, TaskQueuePosition,
    TaskQueueCursorInvalid, TaskQueueReadUnavailable,
)
from app.modules.tasks.api import TaskQueueCursor, TaskQueueRequest
from app.modules.tasks.schemas import (
    ContributorTaskQueueResponse, ManagementTaskQueueResponse, OperationalTaskQueueResponse,
)

router = APIRouter(tags=["tasks"], dependencies=[Depends(enforce_human_authorization_read)])
Authority = Annotated[TaskQueueReadAuthorizationPort, Depends(get_task_queue_authorization)]
Session = Annotated[AsyncSession, Depends(get_db_session)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[str | None, Query(max_length=512)]


async def _page(project_id, limit, cursor, authority, session, action, read, response_type):
    """Commit only after live authority, bounded projection and JSON validation."""
    query = TaskQueueReadRequest(action, project_id, limit, cursor)
    try:
        position = await authority.authorize_and_decode(query)
    except TaskQueueCursorInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TaskQueueReadUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    after = None if position is None else TaskQueueCursor(project_id, position.created_at, position.task_id)
    page = await read(TaskQueueRequest(project_id, limit, after))
    next_cursor = None if page.next_cursor is None else authority.encode(
        query, TaskQueuePosition(page.next_cursor.created_at, page.next_cursor.task_id),
    )
    response = response_type(project_id=page.project_id, items=page.items, next_cursor=next_cursor)
    response.model_dump(mode="json")
    await session.commit()
    return response


@router.get(
    "/projects/{project_id}/tasks/ready", response_model=ContributorTaskQueueResponse,
    openapi_extra={"x-workstream-action-id": READY_QUEUE_ACTION},
)
async def ready_tasks(
    project_id: UUID, authority: Authority, session: Session,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> ContributorTaskQueueResponse:
    """List ready work for an active exact-project Submitter or Reviewer."""
    return await _page(
        project_id, limit, cursor, authority, session, READY_QUEUE_ACTION,
        contributor_task_repository(session).read_ready_tasks, ContributorTaskQueueResponse,
    )


@router.get(
    "/projects/{project_id}/tasks", response_model=ManagementTaskQueueResponse,
    openapi_extra={"x-workstream-action-id": MANAGEMENT_QUEUE_ACTION},
)
async def management_tasks(
    project_id: UUID, authority: Authority, session: Session,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> ManagementTaskQueueResponse:
    """List project planning fields for a covering Project Manager."""
    return await _page(
        project_id, limit, cursor, authority, session, MANAGEMENT_QUEUE_ACTION,
        TaskRepository(session).read_management_tasks, ManagementTaskQueueResponse,
    )


@router.get(
    "/operations/projects/{project_id}/tasks", response_model=OperationalTaskQueueResponse,
    openapi_extra={"x-workstream-action-id": OPERATIONAL_QUEUE_ACTION},
)
async def operational_tasks(
    project_id: UUID, authority: Authority, session: Session,
    limit: PageLimit = 50, cursor: PageCursor = None,
) -> OperationalTaskQueueResponse:
    """List only project task status facts for a system Operator."""
    return await _page(
        project_id, limit, cursor, authority, session, OPERATIONAL_QUEUE_ACTION,
        TaskRepository(session).read_operational_tasks, OperationalTaskQueueResponse,
    )
