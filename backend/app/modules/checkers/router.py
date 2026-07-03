"""FastAPI routes for checker feedback and durable checker runs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_actor
from app.core.permissions import PermissionDenied
from app.db.session import get_db_session
from app.modules.checkers.schemas import (
    CheckerRunRequest,
    CheckerRunPublicResponse,
    CheckerRunResponse,
    PreSubmitCheckRequest,
    PreSubmitCheckResponse,
)
from app.modules.checkers.service import CheckerService, CheckerServiceError
from app.schemas.auth import ActorContext

router = APIRouter(tags=["checkers"])

CHECKER_RUN_PUBLIC_RESPONSE = {
    200: {
        "model": CheckerRunPublicResponse,
        "description": (
            "Role-sensitive checker run response. Worker-readable OpenAPI "
            "documents only the public subset; admin and project_manager actors "
            "may receive additional internal routing and provenance fields."
        ),
    }
}


def checker_http_error(exc: CheckerServiceError) -> HTTPException:
    """Convert a checker service error into an HTTP error.

    Args:
        exc: Checker service exception with an API status code.

    Returns:
        HTTP exception carrying the service error details.
    """
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def permission_http_error(exc: PermissionDenied) -> HTTPException:
    """Convert a permission failure into a 403 HTTP error.

    Args:
        exc: Permission exception raised by the service layer.

    Returns:
        HTTP exception with a forbidden status.
    """
    return HTTPException(status_code=403, detail=str(exc))


def checker_run_response(payload: CheckerRunResponse | list[CheckerRunResponse]) -> JSONResponse:
    """Serialize role-sensitive checker-run responses without null hidden fields."""
    return JSONResponse(content=jsonable_encoder(payload, exclude_none=True))


@router.post("/tasks/{task_id}/submission-precheck", response_model=PreSubmitCheckResponse)
async def pre_submit_check(
    task_id: str,
    payload: PreSubmitCheckRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreSubmitCheckResponse:
    """Return non-authoritative static checker feedback for a draft packet."""
    try:
        return await CheckerService(session).pre_submit_check(actor, task_id, payload.submission)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except CheckerServiceError as exc:
        raise checker_http_error(exc) from exc


@router.post(
    "/submissions/{submission_id}/checker-runs",
    response_model=None,
    responses=CHECKER_RUN_PUBLIC_RESPONSE,
)
async def run_submission_checkers(
    submission_id: str,
    payload: CheckerRunRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    """Trigger a durable internal checker run for a locked submission."""
    try:
        result = await CheckerService(session).run_submission_checkers(
            actor,
            submission_id,
            payload.trigger_reason,
        )
        return checker_run_response(result)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except CheckerServiceError as exc:
        raise checker_http_error(exc) from exc


@router.get(
    "/submissions/{submission_id}/checker-runs",
    response_model=None,
    responses={
        200: {
            "model": list[CheckerRunPublicResponse],
            "description": (
                "Role-sensitive checker run list. Worker-readable OpenAPI "
                "documents only the public subset; admin and project_manager "
                "actors may receive additional internal routing and provenance fields."
            ),
        }
    },
)
async def list_submission_checker_runs(
    submission_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    """Return checker runs for one visible submission."""
    try:
        result = await CheckerService(session).list_submission_checker_runs(actor, submission_id)
        return checker_run_response(result)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except CheckerServiceError as exc:
        raise checker_http_error(exc) from exc


@router.get(
    "/checker-runs/{checker_run_id}",
    response_model=None,
    responses=CHECKER_RUN_PUBLIC_RESPONSE,
)
async def get_checker_run(
    checker_run_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    """Return one visible checker run."""
    try:
        result = await CheckerService(session).get_checker_run(actor, checker_run_id)
        return checker_run_response(result)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except CheckerServiceError as exc:
        raise checker_http_error(exc) from exc
