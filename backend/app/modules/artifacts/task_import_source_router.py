"""Covered-PM declaration, byte upload and verified task-import source reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.adapters.artifacts import get_task_import_source_commands
from app.api.deps.authorization import enforce_human_authorization_read
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key
from app.interfaces.artifacts import ArtifactInputMismatchError, ArtifactIntegrityError, ArtifactLimitExceededError, ArtifactStoreError
from app.modules.artifacts.api.task_import_source import (
    TaskImportSourceAction, TaskImportSourceCommandPort, TaskImportSourceDeclare, TaskImportSourceResponse,
)
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.service import ArtifactAdmissionError, ArtifactAdmissionConflictError, ArtifactAdmissionCapacityError
from app.modules.artifacts.task_import_sources import TaskImportSourceError


router = APIRouter(prefix="/projects/{project_id}/task-import-sources", tags=["task-import-sources"])


def _http_error(exc: Exception) -> StructuredHTTPException:
    if isinstance(exc, TaskImportSourceError):
        status_code, code = exc.status_code, exc.code
    elif isinstance(exc, ArtifactAuthorityDeniedError):
        status_code, code = 503, "task_import_source_service_unavailable"
    elif isinstance(exc, ArtifactAdmissionConflictError):
        status_code, code = 409, "task_import_source_conflict"
    elif isinstance(exc, (ArtifactAdmissionCapacityError, ArtifactLimitExceededError)):
        status_code, code = 413, "task_import_source_limit_exceeded"
    elif isinstance(exc, (ArtifactInputMismatchError, ArtifactIntegrityError)):
        status_code, code = 422, "task_import_source_commitment_mismatch"
    elif isinstance(exc, (ValidationError, ValueError)):
        status_code, code = 422, "task_import_source_json_invalid"
    else:
        status_code, code = 503, "task_import_source_unavailable"
    details = None
    if isinstance(exc, ValidationError):
        details = [{"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
                   for error in exc.errors(include_input=False, include_context=False, include_url=False)]
    return StructuredHTTPException(status_code=status_code, detail=details or code,
                                   error_code=code, error_message=code.replace("_", " "), retryable=status_code == 503)


def import_source_key(value: Annotated[str, Header(alias="Idempotency-Key")]) -> UUID:
    """Require a UUID declaration replay key using the shared API parser."""
    return parse_idempotency_key(value)


@router.post("", response_model=TaskImportSourceResponse, status_code=201,
             openapi_extra={"x-workstream-action-id": TaskImportSourceAction.DECLARE.value})
async def declare_task_import_source(
    project_id: UUID, payload: TaskImportSourceDeclare,
    key: Annotated[UUID, Depends(import_source_key)],
    commands: Annotated[TaskImportSourceCommandPort, Depends(get_task_import_source_commands)],
) -> TaskImportSourceResponse:
    """Declare immutable source bytes; exact same-key replay retains the original ID."""
    try:
        return await commands.declare(project_id, payload, key)
    except (TaskImportSourceError, ArtifactAdmissionError) as exc:
        raise _http_error(exc) from exc


@router.put("/{source_id}/content", response_model=TaskImportSourceResponse,
            openapi_extra={"x-workstream-action-id": TaskImportSourceAction.UPLOAD.value,
                           "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}})
async def upload_task_import_source(
    request: Request, project_id: UUID, source_id: UUID,
    commands: Annotated[TaskImportSourceCommandPort, Depends(get_task_import_source_commands)],
) -> TaskImportSourceResponse:
    """Admit raw JSON without HTTP parsing or reserialization changing its bytes."""
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise StructuredHTTPException(status_code=415, detail="application/json is required",
                                       error_code="task_import_source_media_type_invalid", error_message="application/json is required")
    try:
        return await commands.upload(project_id, source_id, request.stream())
    except (TaskImportSourceError, ArtifactStoreError, ArtifactAdmissionError, ArtifactAuthorityDeniedError,
            ValidationError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/{source_id}", response_model=TaskImportSourceResponse,
            dependencies=[Depends(enforce_human_authorization_read)],
            openapi_extra={"x-workstream-action-id": TaskImportSourceAction.READ.value})
async def get_task_import_source(
    project_id: UUID, source_id: UUID,
    commands: Annotated[TaskImportSourceCommandPort, Depends(get_task_import_source_commands)],
) -> TaskImportSourceResponse:
    """Read original commitments and storage status with concealed selector denials."""
    try:
        return await commands.status(project_id, source_id)
    except TaskImportSourceError as exc:
        raise _http_error(exc) from exc


async def verified_import_source(
    project_id: UUID, source_id: UUID,
    commands: Annotated[TaskImportSourceCommandPort, Depends(get_task_import_source_commands)],
):
    try:
        async with commands.open(project_id, source_id) as read:
            yield read
    except (TaskImportSourceError, ArtifactStoreError, ArtifactAdmissionError, ArtifactAuthorityDeniedError) as exc:
        raise _http_error(exc) from exc


@router.get("/{source_id}/content", dependencies=[Depends(enforce_human_authorization_read)],
            openapi_extra={"x-workstream-action-id": TaskImportSourceAction.READ.value},
            responses={200: {"content": {"application/json": {"schema": {"type": "object"}}}}})
async def read_task_import_source(read: Annotated[object, Depends(verified_import_source)]):
    """Deliver previously verified scratch bytes with private, non-cacheable headers."""
    return StreamingResponse(read.stream, media_type="application/json", headers={
        "Content-Length": str(read.source.byte_count), "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff", "Content-Disposition": f'attachment; filename="{read.source.source_id}.json"',
    })
