"""FastAPI dependencies for bearer-token actor resolution."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_controls import StructuredHTTPException, request_ids
from app.api.deps.rate_controls import (
    enforce_rate_control,
    get_rate_control_service,
    service_unavailable_error,
)
from app.core.auth import get_auth_verifier
from app.db.session import get_db_session
from app.interfaces.auth import (
    AuthVerificationError,
    AuthVerificationUnavailableError,
    AuthVerifier,
)
from app.modules.actors.service import (
    ActorDeactivated,
    ActorRegistryError,
    ActorService,
    ActorSuspended,
    ResolvedActor,
    ServiceActorNotProvisioned,
    UnsupportedSubjectKind,
)
from app.modules.api_controls.service import (
    FIRST_ACCESS_SCOPE,
    RateControlService,
)
from app.schemas.auth import ActorContext, AuthVerificationResult, VerifiedIssuerToken

bearer_scheme = HTTPBearer(auto_error=False)


def get_application_auth_verifier(request: Request) -> AuthVerifier:
    """Return the verifier retained by this application instance."""
    if request.app.state.settings.auth_provider == "dev":
        return get_auth_verifier()
    return request.app.state.auth_verifier


def unauthorized(detail: str, *, error_code: str) -> HTTPException:
    """Build a bearer-auth unauthorized response.

    Args:
        detail: Public error detail to return to the client.

    Returns:
        HTTP exception with the bearer challenge header.
    """
    return StructuredHTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        error_code=error_code,
        error_message=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_auth_verification_result(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[AuthVerifier, Depends(get_application_auth_verifier)],
) -> AuthVerificationResult:
    """Verify the request bearer token once for derived auth dependencies.

    Args:
        credentials: Parsed HTTP bearer credentials, when supplied.
        verifier: Configured auth verifier dependency.

    Returns:
        Canonical and bounded compatibility verification result.

    Raises:
        HTTPException: If the bearer token is missing or invalid.
    """
    if credentials is None:
        raise unauthorized("Missing bearer token", error_code="missing_token")

    try:
        return await verifier.verify(credentials.credentials)
    except AuthVerificationUnavailableError as exc:
        raise StructuredHTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity verification unavailable",
            error_code="identity_verification_unavailable",
            error_message="Identity verification unavailable",
            retryable=True,
        ) from exc
    except AuthVerificationError as exc:
        raise unauthorized("Invalid bearer token", error_code="invalid_token") from exc


async def get_current_actor(
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> VerifiedIssuerToken:
    """Expose only canonical identity and coarse-access claims."""
    return result.token


def actor_registry_http_error(exc: ActorRegistryError) -> StructuredHTTPException:
    """Map actor resolution to the stable structured API envelope."""
    return StructuredHTTPException(
        status_code=exc.status_code,
        detail=str(exc),
        error_code=exc.code,
        error_message=str(exc),
    )


def actor_registry_unavailable_error() -> StructuredHTTPException:
    """Build the canonical retryable actor-registry unavailable response."""
    return service_unavailable_error("Actor registry unavailable")


async def get_canonical_actor(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> ResolvedActor:
    """Resolve one verified token to the canonical local actor."""
    if result.token.subject_kind == "service":
        raise actor_registry_http_error(
            ServiceActorNotProvisioned("Service actor is not provisioned")
        )
    if result.token.subject_kind != "human":
        raise actor_registry_http_error(UnsupportedSubjectKind("Unsupported subject kind"))
    service = ActorService(session)
    try:
        existing = await service.find_verified_actor(result.token)
        if existing is None and result.token.subject_kind == "human":
            settings = request.app.state.settings
            await enforce_rate_control(
                request=request,
                result=result,
                service=rate_control,
                control_scope=FIRST_ACCESS_SCOPE,
                limit=settings.api_first_access_rate_limit,
                window_seconds=settings.api_first_access_rate_window_seconds,
            )
        request_id, correlation_id = request_ids(request)
        return await service.resolve_verified_actor(
            result.token,
            request_id=UUID(request_id),
            correlation_id=UUID(correlation_id),
        )
    except ActorRegistryError as exc:
        await session.rollback()
        raise actor_registry_http_error(exc) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc


async def get_registered_actor(
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    resolved: Annotated[ResolvedActor, Depends(get_canonical_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorContext:
    """Return the bounded legacy context after canonical actor resolution."""
    if result.token.subject_kind != "human" or result.legacy is None:
        raise StructuredHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unsupported subject kind",
            error_code="unsupported_subject_kind",
            error_message="Unsupported subject kind",
        )
    actor = result.legacy_actor()
    try:
        if resolved.profile.status == "suspended":
            raise ActorSuspended("Actor is suspended")
        if resolved.profile.status == "deactivated":
            raise ActorDeactivated("Actor is deactivated")
        await ActorService(session).refresh_legacy_identity(actor)
    except ActorRegistryError as exc:
        await session.rollback()
        raise actor_registry_http_error(exc) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc
    return actor
