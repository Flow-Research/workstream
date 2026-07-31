"""FastAPI boundary for authorized project creation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import (
    get_authorization_actor,
    get_prepared_authorization_service,
)
from app.core.api_controls import StructuredHTTPException
from app.core.permissions import PermissionDenied
from app.db.errors import integrity_constraint_name
from app.db.session import get_db_session
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.projects.create_service import (
    ProjectCreateIdempotencyConflict,
    ProjectCreateService,
)
from app.modules.projects.schemas import ProjectCreate, ProjectResponse
from app.modules.projects.service import ProjectServiceError

router = APIRouter(prefix="/projects", tags=["projects"])


def require_project_create_idempotency_key(request: Request) -> UUID:
    """Validate replay custody before actor first-access provisioning can run."""
    try:
        return UUID(request.headers["Idempotency-Key"])
    except (KeyError, ValueError) as exc:
        raise StructuredHTTPException(
            status_code=422,
            detail="Idempotency-Key must be a UUID",
            error_code="validation_error",
            error_message="Idempotency-Key must be a UUID",
        ) from exc


async def get_project_create_authorization(
    idempotency_key: Annotated[UUID, Depends(require_project_create_idempotency_key)],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    prepared: Annotated[
        PreparedAuthorizationService, Depends(get_prepared_authorization_service)
    ],
) -> tuple[UUID, ResolvedActor, PreparedAuthorizationService]:
    """Order idempotency validation before the mutating actor dependency graph."""
    return idempotency_key, resolved, prepared


def project_create_http_error(
    exc: ProjectServiceError,
) -> StructuredHTTPException | HTTPException:
    """Translate one bounded project-create service failure."""
    if isinstance(exc, ProjectCreateIdempotencyConflict):
        code = str(exc)
        return StructuredHTTPException(
            status_code=exc.status_code,
            detail=code,
            error_code=code,
            error_message=(
                "Idempotency key does not match"
                if code == "idempotency_mismatch"
                else "Project creation is already in progress"
            ),
            retryable=code == "idempotency_pending",
        )
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=201,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_CREATE.value},
)
async def create_project(
    payload: ProjectCreate,
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(get_project_create_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse:
    """Create one authorized draft project shell or recover its exact replay."""
    idempotency_key, resolved, prepared = authorization
    try:
        outcome = await ProjectCreateService(session).create(
            resolved, prepared, idempotency_key, payload
        )
        if outcome.replayed:
            await session.rollback()
        else:
            await session.commit()
        return outcome.response
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProjectServiceError as exc:
        raise project_create_http_error(exc) from exc
    except IntegrityError as exc:
        await session.rollback()
        constraint_name = integrity_constraint_name(exc)
        if constraint_name not in {
            "projects_slug_key",
            "ix_projects_slug",
            "uq_projects_slug",
        }:
            raise
        raise StructuredHTTPException(
            status_code=409,
            detail="Project slug already exists",
            error_code="project_slug_conflict",
            error_message="Project slug already exists",
        ) from exc
