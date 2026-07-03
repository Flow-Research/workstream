"""FastAPI routes for task queue and assignment lifecycle operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_actor
from app.core.permissions import PermissionDenied
from app.db.session import get_db_session
from app.modules.tasks.schemas import (
    AuditEventResponse,
    SubmissionCreate,
    SubmissionResponse,
    TaskCreate,
    TaskResponse,
    TaskTransitionRequest,
    TaskWithAssignmentResponse,
)
from app.modules.tasks.service import TaskService, TaskServiceError
from app.schemas.auth import ActorContext

router = APIRouter(tags=["tasks"])

DOMAIN_ERROR_RESPONSE_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "required": ["code", "details"],
            "properties": {
                "code": {
                    "type": "string",
                    "enum": ["pre_submission_checker_failed"],
                },
                "details": {"type": "object"},
            },
            "additionalProperties": False,
        },
        {"$ref": "#/components/schemas/HTTPValidationError"},
    ]
}


def task_http_error(exc: TaskServiceError) -> HTTPException:
    """Convert a service-layer task error into an HTTP error.

    Args:
        exc: Task service exception with an API status code.

    Returns:
        HTTP exception carrying the service error details.
    """
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def task_domain_error_response(exc: TaskServiceError) -> JSONResponse:
    """Convert a coded domain error into the public API error body."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": getattr(exc, "code"),
            "details": getattr(exc, "details", None) or {},
        },
    )


def permission_http_error(exc: PermissionDenied) -> HTTPException:
    """Convert a permission failure into a 403 HTTP error.

    Args:
        exc: Permission exception raised by the service layer.

    Returns:
        HTTP exception with a forbidden status.
    """
    return HTTPException(status_code=403, detail=str(exc))


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_task(
    project_id: str,
    payload: TaskCreate,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Create a draft task under a project."""
    try:
        return await TaskService(session).create_task(actor, project_id, payload)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.get("/tasks/{task_id}", response_model=TaskResponse, response_model_exclude_none=True)
async def get_task(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskResponse:
    """Return one task by id."""
    try:
        return await TaskService(session).get_task(actor, task_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/screen",
    response_model=TaskResponse,
    response_model_exclude_none=True,
)
async def screen_task(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: TaskTransitionRequest | None = None,
) -> TaskResponse:
    """Move a draft task into screening."""
    try:
        return await TaskService(session).move_to_screening(
            actor,
            task_id,
            None if payload is None else payload.reason,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/release",
    response_model=TaskResponse,
    response_model_exclude_none=True,
)
async def release_task(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: TaskTransitionRequest | None = None,
) -> TaskResponse:
    """Move a screened task into the ready queue."""
    try:
        return await TaskService(session).release_to_ready(
            actor,
            task_id,
            None if payload is None else payload.reason,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/claim",
    response_model=TaskWithAssignmentResponse,
    response_model_exclude_none=True,
)
async def claim_task(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: TaskTransitionRequest | None = None,
) -> TaskWithAssignmentResponse:
    """Claim a ready task for the current actor."""
    try:
        return await TaskService(session).claim_task(
            actor,
            task_id,
            None if payload is None else payload.reason,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/start",
    response_model=TaskResponse,
    response_model_exclude_none=True,
)
async def start_task(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: TaskTransitionRequest | None = None,
) -> TaskResponse:
    """Move a claimed task into active work."""
    try:
        return await TaskService(session).start_task(
            actor,
            task_id,
            None if payload is None else payload.reason,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/submissions",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
    status_code=201,
    responses={
        422: {
            "description": "Pre-submit domain failure or request validation error.",
            "content": {
                "application/json": {
                    "schema": DOMAIN_ERROR_RESPONSE_SCHEMA,
                }
            },
        }
    },
)
async def create_submission(
    task_id: str,
    payload: SubmissionCreate,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionResponse | JSONResponse:
    """Create a submission packet version for a task."""
    try:
        return await TaskService(session).create_submission(actor, task_id, payload)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        if getattr(exc, "code", None) is not None:
            return task_domain_error_response(exc)
        raise task_http_error(exc) from exc


@router.get(
    "/tasks/{task_id}/submissions",
    response_model=list[SubmissionResponse],
    response_model_exclude_none=True,
)
async def list_task_submissions(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SubmissionResponse]:
    """Return submission packet versions for one task."""
    try:
        return await TaskService(session).list_task_submissions(actor, task_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def get_submission(
    submission_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionResponse:
    """Return one submission packet version."""
    try:
        return await TaskService(session).get_submission(actor, submission_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/submissions/{submission_id}/lock",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def lock_submission(
    submission_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionResponse:
    """Lock a submission packet before checker execution."""
    try:
        return await TaskService(session).lock_submission(actor, submission_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.get("/tasks/{task_id}/audit-events", response_model=list[AuditEventResponse])
async def list_task_audit_events(
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AuditEventResponse]:
    """Return audit events for one task."""
    try:
        return await TaskService(session).list_task_audit_events(actor, task_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc
