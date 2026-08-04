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


async def require_sufficiency_human(
    key: Annotated[UUID, Depends(require_guide_mutation_key)],
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> AuthVerificationResult:
    """Reject nonhuman public callers before database dependencies resolve."""
    del key
    if result.token.subject_kind != "human":
        raise StructuredHTTPException(
            status_code=404,
            detail="Project authorization resource not found",
            error_code="project_authorization_resource_not_found",
            error_message="Project authorization resource not found",
        )
    return result


async def sufficiency_authorization_actor(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(require_sufficiency_human)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> ResolvedActor:
    """Resolve the canonical actor only after human-only admission succeeds."""
    return await resolve_authorization_actor(request, result, session, rate_control)


async def get_sufficiency_prepared_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(sufficiency_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Compose PREP only after the public human-only admission check."""
    async with prepared_authorization_service(request, resolved, session) as service:
        yield service


async def sufficiency_authorization(
    key: Annotated[UUID, Depends(require_guide_mutation_key)],
    resolved: Annotated[ResolvedActor, Depends(sufficiency_authorization_actor)],
    prepared: Annotated[
        PreparedAuthorizationService,
        Depends(get_sufficiency_prepared_authorization_service),
    ],
):
    """Return one exact human actor and request-local sufficiency PREP service."""
    return key, resolved, prepared


def mutation_conflict_error(code: str) -> StructuredHTTPException:
    """Return the canonical structured mutation-conflict envelope."""
    messages = {
        "idempotency_mismatch": "Idempotency key does not match",
        "idempotency_pending": "Guide mutation is already in progress",
    }
    return StructuredHTTPException(
        status_code=409,
        detail=code,
        error_code=code,
        error_message=messages.get(code, "Guide mutation conflicts with current state"),
        retryable=code == "idempotency_pending",
    )


def _error(exc: ProjectServiceError):
    if isinstance(exc, GuideMutationIdempotencyConflict):
        return mutation_conflict_error(str(exc))
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _finish(session, outcome):
    if outcome.setup_run_id and not outcome.replayed and outcome.setup_generation is None:
        raise RuntimeError("committed project setup generation is unavailable")
    await (session.rollback() if outcome.replayed else session.commit())
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
