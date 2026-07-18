"""FastAPI composition root for request-scoped local authorization."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import (
    actor_registry_http_error,
    actor_registry_unavailable_error,
    get_auth_verification_result,
)
from app.api.deps.rate_controls import enforce_rate_control, get_rate_control_service
from app.core.api_controls import StructuredHTTPException, request_ids
from app.db.session import get_db_session
from app.modules.actors.service import (
    ActorRegistryError,
    ActorService,
    ResolvedActor,
    ServiceActorNotProvisioned,
    UnsupportedSubjectKind,
)
from app.modules.api_controls.service import FIRST_ACCESS_SCOPE, RateControlService
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorSelfResourceContext,
    ActorStatus,
    AuthorizationContext,
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    IdentityLinkStatus,
)
from app.schemas.auth import AuthVerificationResult


def _authorization_context(
    resolved: ResolvedActor,
    request_id: UUID,
    correlation_id: UUID,
) -> AuthorizationContext:
    """Project canonical actor rows into the strict request context."""
    return AuthorizationContext(
        actor_profile_id=UUID(resolved.profile.id),
        actor_kind=ActorKind(resolved.profile.actor_kind),
        actor_status=ActorStatus(resolved.profile.status),
        identity_link_id=UUID(resolved.identity_link.id),
        identity_link_status=IdentityLinkStatus(resolved.identity_link.status),
        request_id=request_id,
        correlation_id=correlation_id,
    )


async def get_authorization_actor(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> ResolvedActor:
    """Resolve an exact human self target without pre-kernel lifecycle denial."""
    if result.token.subject_kind == "service":
        raise actor_registry_http_error(
            ServiceActorNotProvisioned("Service actor is not provisioned")
        )
    if result.token.subject_kind != "human":
        raise actor_registry_http_error(UnsupportedSubjectKind("Unsupported subject kind"))
    service = ActorService(session)
    try:
        existing = await service.find_actor_for_authorization(result.token)
        if existing is None:
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
        return await service.resolve_actor_for_authorization(
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


def authorization_http_error(exc: AuthorizationDenied) -> StructuredHTTPException:
    """Translate a bounded decision without exposing internal catalogue state."""
    messages = {
        "identity_link_revoked": "Identity link is revoked",
        "actor_deactivated": "Actor is deactivated",
        "actor_suspended": "Actor is suspended",
        "resource_guard_denied": "Resource guard denied",
        "permission_not_granted": "Permission not granted",
        "scope_not_authorized": "Scope not authorized",
        "self_grant_forbidden": "Self grant is forbidden",
        "self_role_revoke_forbidden": "Self role revocation is forbidden",
        "actor_not_found": "Actor not found",
        "grant_not_found": "Grant not found",
        "resource_not_found": "Resource not found",
    }
    code = exc.public_code
    message = messages[code]
    status_code = (
        status.HTTP_404_NOT_FOUND
        if code in {"actor_not_found", "grant_not_found", "resource_not_found"}
        else status.HTTP_403_FORBIDDEN
    )
    return StructuredHTTPException(
        status_code=status_code,
        detail=message,
        error_code=code,
        error_message=message,
    )


async def get_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[AuthorizationService]:
    """Yield one service and own final decision transaction cleanup."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    actor_service = ActorService(session)

    async def revalidate_actor_self(
        context: AuthorizationContext,
        resource: ActorSelfResourceContext,
    ) -> AuthorizationContext:
        """Rebuild actor state from exact rows locked in the caller transaction."""
        if resource.resource_id != context.actor_profile_id:
            return context
        locked = await actor_service.lock_actor_self_for_authorization(resolved)
        return _authorization_context(locked, request_id, correlation_id)

    service = AuthorizationService(
        session,
        _authorization_context(resolved, request_id, correlation_id),
        revalidate_actor_self=revalidate_actor_self,
    )
    try:
        yield service
    except AuthorizationDenied as exc:
        await session.rollback()
        try:
            await service._restage_denial(exc.decision)
            await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as persistence_error:
            await session.rollback()
            raise actor_registry_unavailable_error() from persistence_error
        raise authorization_http_error(exc) from exc
    except AuthorizationEvidenceUnavailable as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc
    except BaseException:
        await session.rollback()
        raise
    else:
        if session.in_transaction():
            await session.rollback()
