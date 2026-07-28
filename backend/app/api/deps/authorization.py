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
from app.api.deps.api_controls import enforce_authorization_read_rate_limit
from app.core.api_controls import StructuredHTTPException, request_ids
from app.db.session import get_db_session
from app.modules.actors.service import (
    ActorRegistryError,
    ActorService,
    ResolvedActor,
    UnsupportedSubjectKind,
)
from app.modules.api_controls.service import FIRST_ACCESS_SCOPE, RateControlService
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorAuthorizationContextResourceContext,
    ActorSelfResourceContext,
    ActorStatus,
    AuthorizationContext,
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    ProjectReadResourceContext,
    ProjectDiagnosticReadResourceContext,
    ServiceAuthorizationContext,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.schemas.auth import AuthVerificationResult


def _authorization_context(
    resolved: ResolvedActor,
    request_id: UUID,
    correlation_id: UUID,
) -> AuthorizationContext:
    """Project canonical actor rows into the strict request context."""
    common = dict(
        actor_profile_id=UUID(resolved.profile.id),
        actor_status=ActorStatus(resolved.profile.status),
        identity_link_id=UUID(resolved.identity_link.id),
        identity_link_status=IdentityLinkStatus(resolved.identity_link.status),
        request_id=request_id,
        correlation_id=correlation_id,
    )
    if resolved.profile.actor_kind == ActorKind.SERVICE:
        return ServiceAuthorizationContext(
            actor_kind=ActorKind.SERVICE,
            service_identity=ServiceIdentity(resolved.profile.service_identity),
            **common,
        )
    return HumanAuthorizationContext(actor_kind=ActorKind.HUMAN, **common)


async def get_authorization_actor(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> ResolvedActor:
    """Resolve an exact human or fixed-service target before kernel lifecycle denial."""
    if result.token.subject_kind not in {"human", "service"}:
        raise actor_registry_http_error(UnsupportedSubjectKind("Unsupported subject kind"))
    service = ActorService(session)
    try:
        if result.token.subject_kind == "service":
            return await service.resolve_service_for_authorization(result.token)
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
    concealed_project_reads = {
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
        ActionId.PROJECT_READ,
        ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
    }
    if exc.decision.action_id in concealed_project_reads:
        return StructuredHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project authorization resource not found",
            error_code="project_authorization_resource_not_found",
            error_message="Project authorization resource not found",
        )
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


async def enforce_human_authorization_read(
    _rate_control: Annotated[None, Depends(enforce_authorization_read_rate_limit)],
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> None:
    """Consume rate first, then conceal every nonhuman authorization read."""
    if result.token.subject_kind != "human":
        raise StructuredHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project authorization resource not found",
            error_code="project_authorization_resource_not_found",
            error_message="Project authorization resource not found",
        )


async def get_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[AuthorizationService]:
    """Yield one service and own final decision transaction cleanup."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    service = _compose_authorization_service(resolved, session, request_id, correlation_id)
    actor_service = ActorService(session)

    context = _authorization_context(resolved, request_id, correlation_id)
    try:
        if (
            isinstance(context, ServiceAuthorizationContext)
            and context.actor_status is ActorStatus.ACTIVE
            and context.identity_link_status is IdentityLinkStatus.ACTIVE
        ):
            await actor_service.touch_after_authorization(resolved)
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
    except SQLAlchemyError as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc
    except BaseException:
        await session.rollback()
        raise
    else:
        if session.in_transaction():
            await session.rollback()


def _compose_authorization_service(
    resolved: ResolvedActor,
    session: AsyncSession,
    request_id: UUID,
    correlation_id: UUID,
    admin_repository: AdminAuthorizationRepository | None = None,
) -> AuthorizationService:
    """Build the shared kernel without assigning transaction ownership."""
    actor_service = ActorService(session)

    async def revalidate_actor_self(
        context: AuthorizationContext,
        resource: (
            ActorSelfResourceContext
            | ActorAuthorizationContextResourceContext
            | ProjectReadResourceContext
            | ProjectDiagnosticReadResourceContext
        ),
    ) -> AuthorizationContext:
        """Rebuild actor state from exact rows locked in the caller transaction."""
        if (
            isinstance(
                resource, (ActorSelfResourceContext, ActorAuthorizationContextResourceContext)
            )
            and resource.resource_id != context.actor_profile_id
        ):
            return context
        locked = await actor_service.lock_actor_self_for_authorization(resolved)
        return _authorization_context(locked, request_id, correlation_id)

    async def revalidate_service(
        context: ServiceAuthorizationContext,
        _action_id: ActionId,
    ) -> ServiceAuthorizationContext | None:
        """Rebuild fixed-service authority from exact locked actor rows."""
        try:
            locked = await actor_service.lock_actor_for_authorization(resolved)
            refreshed = _authorization_context(locked, request_id, correlation_id)
        except (RuntimeError, ValueError):
            return None
        if not isinstance(refreshed, ServiceAuthorizationContext):
            return None
        if refreshed.service_identity is not context.service_identity:
            return None
        return refreshed

    context = _authorization_context(resolved, request_id, correlation_id)
    return AuthorizationService(
        session,
        context,
        revalidate_actor_self=revalidate_actor_self,
        revalidate_service=revalidate_service,
        admin_repository=admin_repository,
    )


async def get_prepared_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[PreparedAuthorizationService]:
    """Compose one request-local prepared service without taking commit ownership."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    repository = AdminAuthorizationRepository(session)
    authorization = _compose_authorization_service(
        resolved, session, request_id, correlation_id, repository
    )
    service = PreparedAuthorizationService(
        session,
        context,
        authorization,
        repository,
    )
    try:
        yield service
    except AuthorizationDenied as exc:
        await session.rollback()
        raise authorization_http_error(exc) from exc
    except AuthorizationEvidenceUnavailable as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc
    except BaseException:
        await session.rollback()
        raise
    else:
        if session.in_transaction():
            await session.rollback()
    finally:
        service.close()
