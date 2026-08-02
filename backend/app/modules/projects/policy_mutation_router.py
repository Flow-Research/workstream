"""FastAPI boundary for authorized guide-bound policy mutations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_auth_verification_result
from app.api.deps.authorization import prepared_authorization_service, resolve_authorization_actor
from app.api.deps.rate_controls import get_rate_control_service
from app.core.api_controls import StructuredHTTPException
from app.db.session import get_db_session
from app.modules.actors.service import ResolvedActor
from app.modules.api_controls.service import RateControlService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.projects.policy_mutation_service import (
    PolicyMutationConflict,
    ProjectPolicyMutationService,
)
from app.modules.projects.schemas import (
    ReviewPolicyInput,
    ReviewPolicyResponse,
    RevisionPolicyInput,
    RevisionPolicyResponse,
)
from app.modules.projects.service import ProjectServiceError
from app.schemas.auth import AuthVerificationResult


router = APIRouter(prefix="/projects", tags=["projects"])


def require_policy_mutation_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> UUID:
    """Parse the required policy-mutation replay key."""
    try:
        return UUID(idempotency_key)
    except ValueError as exc:
        raise StructuredHTTPException(
            status_code=422,
            detail="Idempotency-Key must be a UUID",
            error_code="validation_error",
            error_message="Idempotency-Key must be a UUID",
        ) from exc


async def policy_authorization_actor(
    key: Annotated[UUID, Depends(require_policy_mutation_key)],
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> ResolvedActor:
    """Resolve the authenticated actor only after key validation."""
    # Keep this dependency so key validation precedes actor and rate-control work.
    del key
    return await resolve_authorization_actor(request, result, session, rate_control)


async def get_policy_prepared_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(policy_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Yield one request-local prepared authorization service."""
    async with prepared_authorization_service(request, resolved, session) as service:
        yield service


async def policy_authorization(
    key: Annotated[UUID, Depends(require_policy_mutation_key)],
    resolved: Annotated[ResolvedActor, Depends(policy_authorization_actor)],
    prepared: Annotated[
        PreparedAuthorizationService,
        Depends(get_policy_prepared_authorization_service),
    ],
) -> tuple[UUID, ResolvedActor, PreparedAuthorizationService]:
    """Compose the policy mutation authorization dependencies."""
    return key, resolved, prepared


def _error(exc: ProjectServiceError):
    """Translate one policy mutation domain error to HTTP."""
    if isinstance(exc, PolicyMutationConflict):
        code = str(exc)
        return StructuredHTTPException(
            status_code=409,
            detail=code,
            error_code=code,
            error_message="Policy mutation conflicts with current state",
            retryable=code == "idempotency_pending",
        )
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _finish(session: AsyncSession, outcome):
    """Commit a new mutation or roll back a replay-only transaction."""
    await (session.rollback() if outcome.replayed else session.commit())
    return outcome.response


@router.put(
    "/{project_id}/guides/{guide_id}/review-policy",
    response_model=ReviewPolicyResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_REVIEW_POLICY_UPDATE.value},
)
async def replace_review_policy(
    project_id: UUID,
    guide_id: UUID,
    payload: ReviewPolicyInput,
    if_match: Annotated[str, Header(alias="If-Match")],
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(policy_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Append and select one authorized review-policy version."""
    key, resolved, prepared = authorization
    try:
        outcome = await ProjectPolicyMutationService(session).replace_review_policy(
            resolved, prepared, key, if_match, project_id, guide_id, payload
        )
        return await _finish(session, outcome)
    except ProjectServiceError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.put(
    "/{project_id}/guides/{guide_id}/revision-policy",
    response_model=RevisionPolicyResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_REVISION_POLICY_UPDATE.value},
)
async def replace_revision_policy(
    project_id: UUID,
    guide_id: UUID,
    payload: RevisionPolicyInput,
    if_match: Annotated[str, Header(alias="If-Match")],
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(policy_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Append and select one authorized revision-policy version."""
    key, resolved, prepared = authorization
    try:
        outcome = await ProjectPolicyMutationService(session).replace_revision_policy(
            resolved, prepared, key, if_match, project_id, guide_id, payload
        )
        return await _finish(session, outcome)
    except ProjectServiceError as exc:
        await session.rollback()
        raise _error(exc) from exc
