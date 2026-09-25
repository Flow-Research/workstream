"""FastAPI routes for task queue and assignment lifecycle operations."""

from __future__ import annotations

from uuid import UUID
from app.api.deps.authorization import get_task_commands, enforce_human_authorization_read
from app.modules.tasks.queue_router import router as queue_router
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.api import TaskAuthorityOperation, ContributorTaskDetail, ManagementTaskDetail
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_registered_actor
from app.core.api_controls import StructuredHTTPException, error_response, parse_idempotency_key
from app.core.permissions import PermissionDenied
from app.db.session import get_db_session
from app.modules.tasks.schemas import (
    ContributorTaskWorkContext, ManagementTaskWorkContext,
    AuditEventResponse,
    ContributorTaskSubmissionRequirements, ManagementTaskSubmissionRequirements,
    SubmissionResponse,
    TaskCreate,
    ManagementTaskLockedContext, OperationalTaskLockedContext, AuditTaskLockedContext,
    TaskResponse,
    TaskTransitionRequest,
    TaskWithAssignmentResponse,
)
from app.modules.tasks.service import TaskProjectNotReady, TaskServiceError, TaskNotFound
from app.adapters.tasks import task_service
from app.schemas.auth import ActorContext

router = APIRouter(tags=["tasks"])
# Static queue routes precede the project-scoped task UUID route.
router.include_router(queue_router)

TASK_IDEMPOTENCY_PARAMETER = {
    "name": "Idempotency-Key", "in": "header", "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def require_task_command_key(request: Request) -> UUID:
    """Validate a single retry key before mutating actor resolution."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


CANONICAL_ERROR_OBJECT_SCHEMA = {"$ref": "#/components/schemas/ApiError"}


TASK_LOCKED_CONTEXT_DOMAIN_ERROR_RESPONSE_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "required": ["code", "details", "error"],
            "properties": {
                "code": {
                    "type": "string",
                    "enum": ["task_locked_context_invalid"],
                },
                "details": {"type": "object"},
                "error": CANONICAL_ERROR_OBJECT_SCHEMA,
            },
            "additionalProperties": False,
        },
        {"$ref": "#/components/schemas/HTTPValidationError"},
    ]
}


TASK_LOCKED_CONTEXT_RESPONSES = {
    422: {
        "description": "Locked task context is missing or inconsistent.",
        "content": {
            "application/json": {"schema": TASK_LOCKED_CONTEXT_DOMAIN_ERROR_RESPONSE_SCHEMA}
        },
    }
}


def task_http_error(exc: TaskServiceError) -> HTTPException:
    """Convert a service-layer task error into an HTTP error.

    Args:
        exc: Task service exception with an API status code.

    Returns:
        HTTP exception carrying the service error details.
    """
    code = getattr(exc, "code", None)
    if code is not None:
        message = getattr(exc, "message", str(exc))
        return StructuredHTTPException(
            status_code=exc.status_code,
            detail=message,
            error_code=code,
            error_message=message,
            retryable=getattr(exc, "retryable", False),
        )
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def task_domain_error_response(request: Request, exc: TaskServiceError) -> JSONResponse:
    """Convert a coded domain error into the public API error body."""
    code = getattr(exc, "code")
    details = getattr(exc, "details", None) or {}
    message = {
        "task_locked_context_invalid": "Task locked context is invalid",
    }[code]
    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
        retryable=getattr(exc, "retryable", False),
        compatibility={"code": code, "details": details},
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
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.CREATE.value,
                   "parameters": [TASK_IDEMPOTENCY_PARAMETER]},
    response_model=TaskResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_task(
    project_id: str,
    payload: TaskCreate,
    idempotency_key: Annotated[UUID, Depends(require_task_command_key)],
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
) -> TaskResponse:
    """Create a draft under exact project-manager authority."""
    try:
        try:
            project = UUID(project_id)
        except ValueError as exc:
            raise TaskProjectNotReady("project not found") from exc
        if str(project) != project_id:
            raise TaskProjectNotReady("project not found")
        return await commands.create_task(project, payload, idempotency_key=idempotency_key)
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


def task_read_error(request: Request, exc: TaskServiceError):
    """Use the same concealment for absent, foreign and denied read resources."""
    if isinstance(exc, TaskNotFound):
        raise StructuredHTTPException(
            status_code=404, detail="Project authorization resource not found",
            error_code="project_authorization_resource_not_found",
            error_message="Project authorization resource not found",
        ) from exc
    if getattr(exc, "code", None) is not None:
        return task_domain_error_response(request, exc)
    raise task_http_error(exc) from exc


@router.get(
    "/tasks/{task_id}", response_model=ContributorTaskDetail, response_model_exclude_none=True,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.READ.value},
)
async def get_task(
    request: Request, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read exact contributor work instructions under live project authority."""
    try:
        return await commands.contributor_detail(task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.get(
    "/projects/{project_id}/tasks/{task_id}", response_model=ManagementTaskDetail,
    response_model_exclude_none=True, dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.MANAGEMENT_READ.value},
)
async def get_management_task(
    request: Request, project_id: UUID, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read management instructions without requiring policy locks on drafts."""
    try:
        return await commands.management_detail(project_id, task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.get(
    "/tasks/{task_id}/submission-requirements", response_model=ContributorTaskSubmissionRequirements,
    response_model_exclude_none=True, responses=TASK_LOCKED_CONTEXT_RESPONSES,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.REQUIREMENTS.value},
)
async def get_task_submission_requirements(
    request: Request, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read contributor requirements from the task's exact historical policy."""
    try:
        return await commands.contributor_requirements(task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.get(
    "/projects/{project_id}/tasks/{task_id}/submission-requirements", response_model=ManagementTaskSubmissionRequirements,
    response_model_exclude_none=True, responses=TASK_LOCKED_CONTEXT_RESPONSES,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.MANAGEMENT_REQUIREMENTS.value},
)
async def get_management_task_submission_requirements(
    request: Request, project_id: UUID, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read exact management requirements under a covering Manager grant."""
    try:
        return await commands.management_requirements(project_id, task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.get(
    "/projects/{project_id}/tasks/{task_id}/locked-context", response_model=ManagementTaskLockedContext,
    response_model_exclude_none=True, responses=TASK_LOCKED_CONTEXT_RESPONSES,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.MANAGEMENT_LOCKED_CONTEXT.value},
)
async def get_management_task_locked_context(
    request: Request, project_id: UUID, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read original locked policy provenance under exact management authority."""
    try:
        return await commands.management_locked_context(project_id, task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.get(
    "/operations/projects/{project_id}/tasks/{task_id}/locked-context", response_model=OperationalTaskLockedContext,
    response_model_exclude_none=True, responses=TASK_LOCKED_CONTEXT_RESPONSES,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.OPERATIONAL_LOCKED_CONTEXT.value},
)
async def get_operational_task_locked_context(
    request: Request, project_id: UUID, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read original locked policy provenance under exact operational authority."""
    try:
        return await commands.operational_locked_context(project_id, task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.get(
    "/audit/projects/{project_id}/tasks/{task_id}/locked-context", response_model=AuditTaskLockedContext,
    response_model_exclude_none=True, responses=TASK_LOCKED_CONTEXT_RESPONSES,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.AUDIT_LOCKED_CONTEXT.value},
)
async def get_audit_task_locked_context(
    request: Request, project_id: UUID, task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
):
    """Read original locked policy provenance under exact audit authority."""
    try:
        return await commands.audit_locked_context(project_id, task_id)
    except TaskServiceError as exc:
        return task_read_error(request, exc)


@router.post(
    "/tasks/{task_id}/screen",
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.SCREEN.value,
                   "parameters": [TASK_IDEMPOTENCY_PARAMETER]},
    response_model=TaskResponse,
    response_model_exclude_none=True,
)
async def screen_task(
    task_id: UUID,
    idempotency_key: Annotated[UUID, Depends(require_task_command_key)],
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
    payload: TaskTransitionRequest | None = None,
) -> TaskResponse:
    """Apply the exact manager screen command atomically."""
    try:
        return await commands.screen(task_id, payload.reason if payload else None, idempotency_key=idempotency_key)
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/release",
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.RELEASE.value,
                   "parameters": [TASK_IDEMPOTENCY_PARAMETER]},
    response_model=TaskResponse,
    response_model_exclude_none=True,
)
async def release_task(
    task_id: UUID,
    idempotency_key: Annotated[UUID, Depends(require_task_command_key)],
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
    payload: TaskTransitionRequest | None = None,
) -> TaskResponse:
    """Apply the exact manager release command atomically."""
    try:
        return await commands.release(task_id, payload.reason if payload else None, idempotency_key=idempotency_key)
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.get(
    "/tasks/{task_id}/submissions",
    response_model=list[SubmissionResponse],
    response_model_exclude_none=True,
)
async def list_task_submissions(
    request: Request,
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SubmissionResponse]:
    """Return submission packet versions for one task."""
    try:
        return await task_service(session, settings=request.app.state.settings).list_task_submissions(actor, task_id)
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
    request: Request,
    submission_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionResponse:
    """Return one submission packet version."""
    try:
        return await task_service(session, settings=request.app.state.settings).get_submission(actor, submission_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/submissions/{submission_id}/finalize",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def finalize_submission(
    request: Request,
    submission_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionResponse:
    """Repair or re-check the automatic pre-review gate for a locked submission."""
    try:
        return await task_service(session, settings=request.app.state.settings).finalize_submission(actor, submission_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.get("/tasks/{task_id}/audit-events", response_model=list[AuditEventResponse])
async def list_task_audit_events(
    request: Request,
    task_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AuditEventResponse]:
    """Return audit events for one task."""
    try:
        return await task_service(session, settings=request.app.state.settings).list_task_audit_events(actor, task_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/claim", response_model=TaskWithAssignmentResponse, response_model_exclude_none=True,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.CLAIM.value,
                   "parameters": [TASK_IDEMPOTENCY_PARAMETER]},
)
async def claim_task(
    task_id: UUID,
    idempotency_key: Annotated[UUID, Depends(require_task_command_key)],
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
    payload: TaskTransitionRequest | None = None,
) -> TaskWithAssignmentResponse:
    try:
        return await commands.claim(task_id, payload.reason if payload else None, idempotency_key=idempotency_key)
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/start", response_model=TaskResponse, response_model_exclude_none=True,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.START.value,
                   "parameters": [TASK_IDEMPOTENCY_PARAMETER]},
)
async def start_task(
    task_id: UUID,
    idempotency_key: Annotated[UUID, Depends(require_task_command_key)],
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
    payload: TaskTransitionRequest | None = None,
) -> TaskResponse:
    try:
        return await commands.start(task_id, payload.reason if payload else None, idempotency_key=idempotency_key)
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.post(
    "/operations/tasks/{task_id}/start", response_model=TaskResponse, response_model_exclude_none=True,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.START_OVERRIDE.value,
                   "parameters": [TASK_IDEMPOTENCY_PARAMETER]},
)
async def override_task_start(
    task_id: UUID,
    idempotency_key: Annotated[UUID, Depends(require_task_command_key)],
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
    payload: TaskTransitionRequest,
) -> TaskResponse:
    try:
        return await commands.start(task_id, payload.reason, idempotency_key=idempotency_key, operator_override=True)
    except TaskServiceError as exc:
        raise task_http_error(exc) from exc


@router.get(
    "/tasks/{task_id}/work-context", response_model=ContributorTaskWorkContext, response_model_exclude_none=True,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.WORK_CONTEXT.value},
    responses=TASK_LOCKED_CONTEXT_RESPONSES,
)
async def get_task_work_context(
    request: Request,
    task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
) -> ContributorTaskWorkContext | JSONResponse:
    try:
        return await commands.contributor_work_context(task_id)
    except TaskServiceError as exc:
        if getattr(exc, "code", None) is not None:
            return task_domain_error_response(request, exc)
        raise task_http_error(exc) from exc


@router.get(
    "/projects/{project_id}/tasks/{task_id}/work-context", response_model=ManagementTaskWorkContext, response_model_exclude_none=True,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.MANAGEMENT_WORK_CONTEXT.value},
    responses=TASK_LOCKED_CONTEXT_RESPONSES,
)
async def get_management_task_work_context(
    request: Request,
    project_id: UUID,
    task_id: UUID,
    commands: Annotated[AuthorizedTaskCommands, Depends(get_task_commands)],
) -> ManagementTaskWorkContext | JSONResponse:
    try:
        return await commands.management_work_context(project_id, task_id)
    except TaskServiceError as exc:
        if getattr(exc, "code", None) is not None:
            return task_domain_error_response(request, exc)
        raise task_http_error(exc) from exc
