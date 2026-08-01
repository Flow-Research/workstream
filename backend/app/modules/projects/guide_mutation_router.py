"""FastAPI boundary for authorized guide metadata mutations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_auth_verification_result
from app.api.deps.authorization import (
    prepared_authorization_service,
    resolve_authorization_actor,
)
from app.api.deps.rate_controls import get_rate_control_service
from app.core.api_controls import StructuredHTTPException
from app.db.session import get_db_session
from app.modules.actors.service import ResolvedActor
from app.modules.api_controls.service import RateControlService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.projects.guide_mutation_service import (
    GuideMutationIdempotencyConflict,
    GuideMutationService,
)
from app.modules.projects.schemas import (
    GuideSourceSnapshotCreate,
    GuideSourceSnapshotResponse,
    ProjectGuideCreate,
    ProjectGuideResponse,
    ProjectGuideUpdate,
)
from app.modules.projects.service import ProjectServiceError
from app.modules.projects.setup_queue import dispatch_pre_submit_setup_pipeline_after_commit
from app.schemas.auth import AuthVerificationResult

router = APIRouter(prefix="/projects", tags=["projects"])


def require_guide_mutation_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> UUID:
    """Validate replay custody before actor provisioning."""
    try:
        return UUID(idempotency_key)
    except ValueError as exc:
        raise StructuredHTTPException(
            status_code=422,
            detail="Idempotency-Key must be a UUID",
            error_code="validation_error",
            error_message="Idempotency-Key must be a UUID",
        ) from exc


async def guide_authorization_actor(
    key: Annotated[UUID, Depends(require_guide_mutation_key)],
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> ResolvedActor:
    """Provision an actor only after the replay key is present and valid."""
    del key
    return await resolve_authorization_actor(request, result, session, rate_control)


async def get_guide_prepared_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(guide_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Compose PREP only from the key-gated guide actor dependency."""
    async with prepared_authorization_service(request, resolved, session) as service:
        yield service


async def guide_authorization(
    key: Annotated[UUID, Depends(require_guide_mutation_key)],
    resolved: Annotated[ResolvedActor, Depends(guide_authorization_actor)],
    prepared: Annotated[
        PreparedAuthorizationService,
        Depends(get_guide_prepared_authorization_service),
    ],
):
    return key, resolved, prepared


def _error(exc: ProjectServiceError):
    if isinstance(exc, GuideMutationIdempotencyConflict):
        code = str(exc)
        return StructuredHTTPException(
            status_code=409,
            detail=code,
            error_code=code,
            error_message="Idempotency key does not match"
            if code == "idempotency_mismatch"
            else "Guide mutation is already in progress",
            retryable=code == "idempotency_pending",
        )
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _finish(session, outcome):
    await (session.rollback() if outcome.replayed else session.commit())
    if outcome.setup_run_id and not outcome.replayed:
        snapshot = outcome.response
        if outcome.setup_generation is None:
            raise RuntimeError("committed project setup generation is unavailable")
        await dispatch_pre_submit_setup_pipeline_after_commit(
            session,
            project_id=snapshot.project_id,
            guide_id=snapshot.guide_id,
            source_snapshot_id=snapshot.id,
            setup_run_id=outcome.setup_run_id,
            setup_generation=outcome.setup_generation,
        )
    return outcome.response


@router.post(
    "/{project_id}/guides",
    response_model=ProjectGuideResponse,
    status_code=201,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_GUIDE_CREATE.value},
)
async def create_guide(
    project_id: UUID,
    payload: ProjectGuideCreate,
    authorization: Annotated[tuple, Depends(guide_authorization)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    key, resolved, prepared = authorization
    try:
        return await _finish(
            session,
            await GuideMutationService(session).create_guide(
                resolved, prepared, key, project_id, payload
            ),
        )
    except ProjectServiceError as exc:
        raise _error(exc) from exc


@router.patch(
    "/{project_id}/guides/{guide_id}",
    response_model=ProjectGuideResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_GUIDE_UPDATE.value},
)
async def update_guide(
    project_id: UUID,
    guide_id: UUID,
    payload: ProjectGuideUpdate,
    authorization: Annotated[tuple, Depends(guide_authorization)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    key, resolved, prepared = authorization
    try:
        return await _finish(
            session,
            await GuideMutationService(session).update_guide(
                resolved, prepared, key, project_id, guide_id, payload
            ),
        )
    except ProjectServiceError as exc:
        raise _error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/source-snapshots",
    response_model=GuideSourceSnapshotResponse,
    status_code=201,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE.value},
)
async def create_snapshot(
    project_id: UUID,
    guide_id: UUID,
    payload: GuideSourceSnapshotCreate,
    authorization: Annotated[tuple, Depends(guide_authorization)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    key, resolved, prepared = authorization
    try:
        return await _finish(
            session,
            await GuideMutationService(session).create_snapshot(
                resolved, prepared, key, project_id, guide_id, payload
            ),
        )
    except ProjectServiceError as exc:
        raise _error(exc) from exc
