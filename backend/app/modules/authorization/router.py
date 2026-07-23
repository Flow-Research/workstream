"""Protected administrative authorization APIs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Annotated, Literal, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.api_controls import enforce_admin_mutation_rate_limit
from app.api.deps.rate_controls import service_unavailable_error
from app.api.deps.auth import get_application_auth_verifier
from app.api.deps.authorization import (
    enforce_human_authorization_read,
    get_authorization_actor,
    get_authorization_service,
    get_prepared_authorization_service,
)
from app.core.api_controls import ApiErrorResponse, StructuredHTTPException
from app.core.config import decode_pagination_cursor_hmac_secret
from app.db.session import get_db_session
from app.interfaces.auth import AuthVerificationUnavailableError, AuthVerifier
from app.modules.actors.service import ActorService, ResolvedActor
from app.modules.actors.repository import ActorRepository
from app.modules.actors.schemas import (
    ActorIdentityLinkAdminResponse,
    ActorProfileAdminResponse,
)
from app.modules.authorization.admin_schemas import (
    AdminRoleDefinitionsResponse,
    AdminRoleGrantCollectionResponse,
    AdminRoleGrantIssueBody,
    AdminRoleGrantRevokeBody,
    AuthorityMutationResponse,
    PermissionDefinitionsResponse,
)
from app.modules.authorization.admin_service import (
    AdminRoleGrantService,
    LastAccessAdministratorConflict,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.pagination import (
    AuthorizationReadCursorCodec,
    InvalidPaginationCursor,
)
from app.modules.authorization.read_service import (
    ProjectRoleReadResourceNotFound,
    ProjectRoleReadService,
)
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.project_role_schemas import (
    ProjectRoleGrantIssueBody,
    ProjectRoleGrantMutationResponse,
    ProjectRoleGrantRevokeBody,
)
from app.modules.authorization.project_role_service import (
    ProjectRoleGrantConflict,
    ProjectRoleGrantMutationService,
    project_role_issue_lock_key,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.lifecycle_schemas import (
    ActorLifecycleBody,
    ActorLifecycleMutationResponse,
    IdentityLinkLifecycleMutationResponse,
)
from app.modules.authorization.lifecycle_service import (
    ActorLifecycleConflict,
    ActorLifecycleRequest,
    ActorLifecycleService,
    IdentityLinkLifecycleConflict,
    IdentityLinkLifecycleRequest,
    IdentityLinkLifecycleService,
)
from app.modules.authorization.runtime import (
    ActorAdminRoleGrantHistoryResourceContext,
    ActorIdentityLinkAdminReadResourceContext,
    ActorIdentityLinkLifecycleResourceContext,
    ActorProfileAdminReadResourceContext,
    ActorProfileLifecycleResourceContext,
    AdminRoleDefinitionsResourceContext,
    AdminRoleGrantCollectionResourceContext,
    AdminRoleGrantIssueResourceContext,
    AdminRoleGrantResourceContext,
    PermissionCatalogueResourceContext,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectRoleGrantIssueResourceContext,
    ProjectRoleGrantRevokeResourceContext,
    ServiceActorProvisionResourceContext,
)
from app.modules.authorization.schemas import (
    AdminRole,
    AdminRoleGrantIssueRequest,
    AdminRoleGrantRevokeRequest,
    ActorProfileDeactivateRequest,
    ActorProfileReactivateRequest,
    ActorProfileSuspendRequest,
    ActorIdentityLinkReactivateRequest,
    ActorIdentityLinkRevokeRequest,
    AdminScope,
    AuthorityOperation,
    ServiceActorCreateRequest,
    ContributorCandidateListResponse,
    ProjectRole,
    ProjectRoleGrantListResponse,
    ProjectRoleGrantRead,
    ProjectRoleGrantIssueRequest,
    ProjectRoleGrantRevokeRequest,
    derive_reason_digest,
    derive_service_identity_digest,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.authorization.service_actor_schemas import (
    ServiceActorProvisionBody,
    ServiceActorProvisionResponse,
)
from app.modules.authorization.service_actor_service import (
    ServiceActorConflict,
    ServiceActorProvisioningUnavailable,
    ServiceActorProvisioningService,
)

router = APIRouter(tags=["authorization"])
T = TypeVar("T")


def _domain_error(status_code: int, code: str, message: str) -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=status_code,
        detail=message,
        error_code=code,
        error_message=message,
    )


def _actor_resource_not_found() -> StructuredHTTPException:
    return _domain_error(404, "actor_resource_not_found", "Actor resource not found")


def _project_role_resource_not_found() -> StructuredHTTPException:
    return _domain_error(
        404,
        "project_authorization_resource_not_found",
        "Project authorization resource not found",
    )


def _project_role_read_service(
    request: Request,
    session: AsyncSession,
    authorization: AuthorizationService,
) -> ProjectRoleReadService:
    secret = request.app.state.settings.pagination_cursor_hmac_secret
    if secret is None:
        raise service_unavailable_error()
    return ProjectRoleReadService(
        authorization,
        ActorRepository(session),
        AdminAuthorizationRepository(session),
        AuthorizationReadCursorCodec(decode_pagination_cursor_hmac_secret(secret)),
    )


def _scope_resource_id(scope_type: AdminScope, project_id: UUID | None):
    if scope_type is AdminScope.SYSTEM and project_id is None:
        return "workstream:admin_role_grants"
    if scope_type is AdminScope.PROJECT and project_id is not None:
        return project_id
    raise _domain_error(400, "invalid_request", "Invalid scope selector")


def _validate_role_scope(payload: AdminRoleGrantIssueBody) -> None:
    system_only = payload.role in {AdminRole.ACCESS_ADMINISTRATOR, AdminRole.OPERATOR}
    complete_scope = (payload.scope_type is AdminScope.PROJECT) == (
        payload.scope_project_id is not None
    )
    if not complete_scope:
        raise _domain_error(400, "invalid_request", "Invalid scope selector")
    if system_only and payload.scope_type is not AdminScope.SYSTEM:
        raise _domain_error(422, "invalid_role_scope", "Role is incompatible with scope")


def _issue_request(payload: AdminRoleGrantIssueBody) -> AdminRoleGrantIssueRequest:
    _validate_role_scope(payload)
    return AdminRoleGrantIssueRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE,
        target_actor_id=payload.target_actor_profile_id,
        role=payload.role,
        scope_type=payload.scope_type,
        scope_project_id=payload.scope_project_id,
        reason_digest=derive_reason_digest(payload.reason),
    )


def _revoke_request(grant_id: UUID, reason: str) -> AdminRoleGrantRevokeRequest:
    return AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=grant_id,
        reason_digest=derive_reason_digest(reason),
    )


def _lifecycle_request(
    actor_profile_id: UUID,
    reason: str,
    operation: AuthorityOperation,
) -> ActorLifecycleRequest:
    values = {
        "operation": operation,
        "actor_profile_id": actor_profile_id,
        "reason_digest": derive_reason_digest(reason),
    }
    request_type = {
        AuthorityOperation.ACTOR_PROFILE_SUSPEND: ActorProfileSuspendRequest,
        AuthorityOperation.ACTOR_PROFILE_REACTIVATE: ActorProfileReactivateRequest,
        AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: ActorProfileDeactivateRequest,
    }[operation]
    return request_type(**values)


def _identity_link_lifecycle_request(
    identity_link_id: UUID,
    reason: str,
    operation: AuthorityOperation,
) -> IdentityLinkLifecycleRequest:
    values = {
        "operation": operation,
        "identity_link_id": identity_link_id,
        "reason_digest": derive_reason_digest(reason),
    }
    request_type = {
        AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: ActorIdentityLinkRevokeRequest,
        AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: ActorIdentityLinkReactivateRequest,
    }[operation]
    return request_type(**values)


def _service_actor_request(
    payload: ServiceActorProvisionBody,
    issuer: str,
) -> ServiceActorCreateRequest:
    return ServiceActorCreateRequest(
        operation=AuthorityOperation.SERVICE_ACTOR_CREATE,
        service_identity=payload.service_identity,
        identity_reference_digest=derive_service_identity_digest(issuer, payload.subject),
        reason_digest=derive_reason_digest(payload.reason),
    )


def _configured_issuer(verifier: AuthVerifier) -> str:
    try:
        issuer = verifier.canonical_issuer()
        derive_service_identity_digest(issuer, "validation-anchor")
        return issuer
    except (AuthVerificationUnavailableError, TypeError) as exc:
        raise StructuredHTTPException(
            status_code=503,
            detail="Identity verification unavailable",
            error_code="identity_verification_unavailable",
            error_message="Identity verification unavailable",
            retryable=True,
        ) from exc


async def _commit_or_unavailable(session: AsyncSession) -> None:
    try:
        await session.commit()
    except asyncio.CancelledError:
        await session.rollback()
        raise
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


async def _database_call(session: AsyncSession, operation: Awaitable[T]) -> T:
    """Map feature-owned SQL failures without relabeling authorization evidence errors."""
    try:
        return await operation
    except asyncio.CancelledError:
        await session.rollback()
        raise
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


async def _mutate_actor_lifecycle(
    *,
    actor_profile_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: UUID,
    resolved: ResolvedActor,
    authorization: AuthorizationService,
    session: AsyncSession,
    operation: AuthorityOperation,
    action: ActionId,
    transition: Literal["suspend", "reactivate", "deactivate"],
) -> ActorLifecycleMutationResponse:
    canonical = _lifecycle_request(actor_profile_id, payload.reason, operation)
    caller_id = UUID(resolved.profile.id)
    service = ActorLifecycleService(session)
    reservation = await _database_call(
        session,
        service.reserve(
            idempotency_key=idempotency_key,
            actor_profile_id=caller_id,
            request=canonical,
        ),
    )
    decision = await _database_call(
        session,
        authorization.require(
            action,
            ActorProfileLifecycleResourceContext(
                resource_type="actor_profile",
                resource_id=actor_profile_id,
                transition=transition,
                existing_idempotency_record=reservation.outcome in {"replay", "mismatch"},
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=caller_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        response = ActorLifecycleMutationResponse(
            resource_type="actor_profile",
            resource_id=reservation.response.resource_id,
            version=None,
            http_status=200,
        )
        await _database_call(session, ActorService(session).touch_after_authorization(resolved))
        await _commit_or_unavailable(session)
        return response
    try:
        await ActorService(session).touch_after_authorization(resolved)
        response = await service.complete(
            claim=reservation.claim,
            request=canonical,
            decision=decision,
            actor_profile_id=caller_id,
            reason=payload.reason,
        )
        await session.commit()
        return response
    except ActorLifecycleConflict as exc:
        await session.rollback()
        await _database_call(
            session,
            service.record_conflict(
                actor_profile_id=caller_id,
                request=canonical,
                decision=decision,
                code=exc.code,
            ),
        )
        await _commit_or_unavailable(session)
        messages = {
            "actor_already_suspended": "Actor is already suspended",
            "actor_not_suspended": "Actor is not suspended",
            "actor_deactivated_terminal": "Actor is permanently deactivated",
            "last_access_administrator": "Final Access Administrator cannot be disabled",
        }
        raise _domain_error(409, exc.code, messages[exc.code]) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


async def _mutate_identity_link_lifecycle(
    *,
    identity_link_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: UUID,
    resolved: ResolvedActor,
    authorization: AuthorizationService,
    session: AsyncSession,
    operation: AuthorityOperation,
    action: ActionId,
    transition: Literal["revoke", "reactivate"],
) -> IdentityLinkLifecycleMutationResponse:
    canonical = _identity_link_lifecycle_request(identity_link_id, payload.reason, operation)
    caller_id = UUID(resolved.profile.id)
    service = IdentityLinkLifecycleService(session)
    reservation = await _database_call(
        session,
        service.reserve(
            idempotency_key=idempotency_key,
            actor_profile_id=caller_id,
            request=canonical,
        ),
    )
    decision = await _database_call(
        session,
        authorization.require(
            action,
            ActorIdentityLinkLifecycleResourceContext(
                resource_type="actor_identity_link",
                resource_id=identity_link_id,
                transition=transition,
                existing_idempotency_record=reservation.outcome in {"replay", "mismatch"},
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=caller_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        response = IdentityLinkLifecycleMutationResponse(
            resource_type="actor_identity_link",
            resource_id=reservation.response.resource_id,
            version=None,
            http_status=200,
        )
        await _database_call(session, ActorService(session).touch_after_authorization(resolved))
        await _commit_or_unavailable(session)
        return response
    try:
        await ActorService(session).touch_after_authorization(resolved)
        response = await service.complete(
            claim=reservation.claim,
            request=canonical,
            decision=decision,
            actor_profile_id=caller_id,
            reason=payload.reason,
        )
        await session.commit()
        return response
    except IdentityLinkLifecycleConflict as exc:
        await session.rollback()
        await _database_call(
            session,
            service.record_conflict(
                actor_profile_id=caller_id,
                target_actor_profile_id=exc.actor_profile_id,
                request=canonical,
                decision=decision,
                code=exc.code,
            ),
        )
        await _commit_or_unavailable(session)
        messages = {
            "identity_link_already_revoked": "Identity link is already revoked",
            "identity_link_not_revoked": "Identity link is not revoked",
            "actor_deactivated_terminal": "Actor is permanently deactivated",
            "last_access_administrator": "Final Access Administrator cannot be disabled",
        }
        raise _domain_error(409, exc.code, messages[exc.code]) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


@router.post(
    "/service-actors",
    status_code=status.HTTP_201_CREATED,
    response_model=ServiceActorProvisionResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses={409: {"model": ApiErrorResponse, "description": "Provisioning conflict."}},
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_SERVICE_PROVISION.value},
)
async def provision_service_actor(
    payload: ServiceActorProvisionBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    verifier: Annotated[AuthVerifier, Depends(get_application_auth_verifier)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceActorProvisionResponse:
    issuer = _configured_issuer(verifier)
    canonical = _service_actor_request(payload, issuer)
    actor_profile_id = UUID(resolved.profile.id)
    service = ServiceActorProvisioningService(session)
    reservation = await _database_call(
        session,
        service.reserve(
            idempotency_key=idempotency_key,
            actor_profile_id=actor_profile_id,
            request=canonical,
        ),
    )
    decision = await _database_call(
        session,
        authorization.require(
            ActionId.ACTOR_SERVICE_PROVISION,
            ServiceActorProvisionResourceContext(
                resource_type="service_actor_provisioning",
                resource_id=payload.service_identity,
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=actor_profile_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        try:
            response = await _database_call(
                session,
                service.replay_response(
                    response=reservation.response,
                    request=canonical,
                    issuer=issuer,
                    subject=payload.subject,
                ),
            )
        except ServiceActorProvisioningUnavailable as exc:
            await session.rollback()
            raise service_unavailable_error() from exc
        await _database_call(session, ActorService(session).touch_after_authorization(resolved))
        await _commit_or_unavailable(session)
        return response

    conflict = await _database_call(
        session,
        service.lock_and_find_conflict(
            service_identity=payload.service_identity,
            issuer=issuer,
            subject=payload.subject,
        ),
    )
    if conflict is not None:
        await session.rollback()
        await _database_call(
            session,
            service.record_conflict(
                actor_profile_id=actor_profile_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _service_actor_conflict(conflict)
    try:
        await ActorService(session).touch_after_authorization(resolved)
        response = await service.complete(
            claim=reservation.claim,
            request=canonical,
            decision=decision,
            actor_profile_id=actor_profile_id,
            issuer=issuer,
            subject=payload.subject,
            reason=payload.reason,
        )
        await session.commit()
        return response
    except IntegrityError as exc:
        await session.rollback()
        conflict = await _database_call(
            session,
            service.find_conflict(
                service_identity=payload.service_identity,
                issuer=issuer,
                subject=payload.subject,
            ),
        )
        if conflict is None:
            raise service_unavailable_error() from exc
        await _database_call(
            session,
            service.record_conflict(
                actor_profile_id=actor_profile_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _service_actor_conflict(conflict) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


def _service_actor_conflict(conflict: ServiceActorConflict) -> StructuredHTTPException:
    if conflict is ServiceActorConflict.SERVICE_IDENTITY:
        return _domain_error(409, conflict.value, "Service identity is already provisioned")
    return _domain_error(409, conflict.value, "Identity subject is already linked")


_LIFECYCLE_CONFLICT_RESPONSE = {
    409: {"model": ApiErrorResponse, "description": "Actor lifecycle conflict."}
}


@router.post(
    "/actors/{actor_profile_id}/suspend",
    response_model=ActorLifecycleMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses=_LIFECYCLE_CONFLICT_RESPONSE,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_PROFILE_SUSPEND.value},
)
async def suspend_actor_profile(
    actor_profile_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorLifecycleMutationResponse:
    return await _mutate_actor_lifecycle(
        actor_profile_id=actor_profile_id,
        payload=payload,
        idempotency_key=idempotency_key,
        resolved=resolved,
        authorization=authorization,
        session=session,
        operation=AuthorityOperation.ACTOR_PROFILE_SUSPEND,
        action=ActionId.ACTOR_PROFILE_SUSPEND,
        transition="suspend",
    )


@router.post(
    "/actors/{actor_profile_id}/reactivate",
    response_model=ActorLifecycleMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses=_LIFECYCLE_CONFLICT_RESPONSE,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_PROFILE_REACTIVATE.value},
)
async def reactivate_actor_profile(
    actor_profile_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorLifecycleMutationResponse:
    return await _mutate_actor_lifecycle(
        actor_profile_id=actor_profile_id,
        payload=payload,
        idempotency_key=idempotency_key,
        resolved=resolved,
        authorization=authorization,
        session=session,
        operation=AuthorityOperation.ACTOR_PROFILE_REACTIVATE,
        action=ActionId.ACTOR_PROFILE_REACTIVATE,
        transition="reactivate",
    )


@router.post(
    "/actors/{actor_profile_id}/deactivate",
    response_model=ActorLifecycleMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses=_LIFECYCLE_CONFLICT_RESPONSE,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_PROFILE_DEACTIVATE.value},
)
async def deactivate_actor_profile(
    actor_profile_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorLifecycleMutationResponse:
    return await _mutate_actor_lifecycle(
        actor_profile_id=actor_profile_id,
        payload=payload,
        idempotency_key=idempotency_key,
        resolved=resolved,
        authorization=authorization,
        session=session,
        operation=AuthorityOperation.ACTOR_PROFILE_DEACTIVATE,
        action=ActionId.ACTOR_PROFILE_DEACTIVATE,
        transition="deactivate",
    )


@router.post(
    "/actor-identity-links/{identity_link_id}/revoke",
    response_model=IdentityLinkLifecycleMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses=_LIFECYCLE_CONFLICT_RESPONSE,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_IDENTITY_LINK_REVOKE.value},
)
async def revoke_actor_identity_link(
    identity_link_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IdentityLinkLifecycleMutationResponse:
    return await _mutate_identity_link_lifecycle(
        identity_link_id=identity_link_id,
        payload=payload,
        idempotency_key=idempotency_key,
        resolved=resolved,
        authorization=authorization,
        session=session,
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
        action=ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        transition="revoke",
    )


@router.post(
    "/actor-identity-links/{identity_link_id}/reactivate",
    response_model=IdentityLinkLifecycleMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses=_LIFECYCLE_CONFLICT_RESPONSE,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_IDENTITY_LINK_REACTIVATE.value},
)
async def reactivate_actor_identity_link(
    identity_link_id: UUID,
    payload: ActorLifecycleBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IdentityLinkLifecycleMutationResponse:
    return await _mutate_identity_link_lifecycle(
        identity_link_id=identity_link_id,
        payload=payload,
        idempotency_key=idempotency_key,
        resolved=resolved,
        authorization=authorization,
        session=session,
        operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE,
        action=ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
        transition="reactivate",
    )


@router.get(
    "/actors/{actor_profile_id}",
    response_model=ActorProfileAdminResponse,
    responses={404: {"model": ApiErrorResponse, "description": "Actor resource not found."}},
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_PROFILE_READ.value},
)
async def read_actor_profile(
    actor_profile_id: UUID,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorProfileAdminResponse:
    await _database_call(
        session,
        authorization.require(
            ActionId.ACTOR_PROFILE_READ,
            ActorProfileAdminReadResourceContext(
                resource_type="actor_profile",
                resource_id=actor_profile_id,
                read_kind="profile",
            ),
        ),
    )
    response = await _database_call(
        session,
        ActorService(session).read_admin_profile(actor_profile_id),
    )
    if response is None:
        await session.rollback()
        raise _actor_resource_not_found()
    await _database_call(session, ActorService(session).touch_after_authorization(resolved))
    if actor_profile_id == UUID(resolved.profile.id):
        response = response.model_copy(
            update={
                "updated_at": resolved.profile.updated_at,
                "last_seen_at": resolved.profile.last_seen_at,
            }
        )
    await _commit_or_unavailable(session)
    return response


@router.get(
    "/actors/{actor_profile_id}/identity-links",
    response_model=ActorIdentityLinkAdminResponse,
    responses={404: {"model": ApiErrorResponse, "description": "Actor resource not found."}},
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_IDENTITY_LINK_READ.value},
)
async def read_actor_identity_link(
    actor_profile_id: UUID,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorIdentityLinkAdminResponse:
    await _database_call(
        session,
        authorization.require(
            ActionId.ACTOR_IDENTITY_LINK_READ,
            ActorIdentityLinkAdminReadResourceContext(
                resource_type="actor_profile",
                resource_id=actor_profile_id,
                read_kind="identity_link",
            ),
        ),
    )
    response = await _database_call(
        session,
        ActorService(session).read_admin_identity_link(actor_profile_id),
    )
    if response is None:
        await session.rollback()
        raise _actor_resource_not_found()
    await _database_call(session, ActorService(session).touch_after_authorization(resolved))
    if actor_profile_id == UUID(resolved.profile.id):
        response = response.model_copy(
            update={"last_verified_at": resolved.identity_link.last_verified_at}
        )
    await _commit_or_unavailable(session)
    return response


@router.get(
    "/authorization/permissions",
    response_model=PermissionDefinitionsResponse,
    openapi_extra={
        "x-workstream-action-id": ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ.value
    },
)
async def read_permission_definitions(
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PermissionDefinitionsResponse:
    await _database_call(
        session,
        authorization.require(
            ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
            PermissionCatalogueResourceContext(
                resource_type="permission_catalogue",
                resource_id="workstream:permission_catalogue",
            ),
        ),
    )
    await _database_call(session, ActorService(session).touch_after_authorization(resolved))
    response = AdminRoleGrantService.permission_definitions()
    await _commit_or_unavailable(session)
    return response


@router.get(
    "/authorization/admin-role-definitions",
    response_model=AdminRoleDefinitionsResponse,
    openapi_extra={
        "x-workstream-action-id": ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ.value
    },
)
async def read_admin_role_definitions(
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminRoleDefinitionsResponse:
    await _database_call(
        session,
        authorization.require(
            ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
            AdminRoleDefinitionsResourceContext(
                resource_type="admin_role_definitions",
                resource_id="workstream:admin_role_definitions",
            ),
        ),
    )
    await _database_call(session, ActorService(session).touch_after_authorization(resolved))
    response = AdminRoleGrantService.role_definitions()
    await _commit_or_unavailable(session)
    return response


async def _grant_page(
    *,
    authorization: AuthorizationService,
    session: AsyncSession,
    resolved: ResolvedActor,
    action_id: ActionId,
    actor_profile_id: UUID | None,
    scope_type: AdminScope,
    scope_project_id: UUID | None,
    grant_status: Literal["active", "revoked", "all"],
    limit: int,
    cursor: str | None,
) -> AdminRoleGrantCollectionResponse:
    resource_id = _scope_resource_id(scope_type, scope_project_id)
    if actor_profile_id is None:
        resource = AdminRoleGrantCollectionResourceContext(
            resource_type="admin_role_grant_collection",
            resource_id=resource_id,
            scope_type=scope_type,
            scope_project_id=scope_project_id,
        )
    else:
        resource = ActorAdminRoleGrantHistoryResourceContext(
            resource_type="actor_admin_role_grant_history",
            resource_id=actor_profile_id,
            scope_type=scope_type,
            scope_project_id=scope_project_id,
        )
    await _database_call(session, authorization.require(action_id, resource))
    try:
        response = await _database_call(
            session,
            AdminRoleGrantService(session).list_page(
                scope_type=scope_type,
                scope_project_id=scope_project_id,
                target_actor_profile_id=actor_profile_id,
                status=grant_status,
                limit=limit,
                cursor=cursor,
            ),
        )
    except ValueError as exc:
        await session.rollback()
        raise _domain_error(400, "invalid_request", "Invalid cursor") from exc
    await _database_call(session, ActorService(session).touch_after_authorization(resolved))
    await _commit_or_unavailable(session)
    return response


@router.get(
    "/admin-role-grants",
    response_model=AdminRoleGrantCollectionResponse,
    openapi_extra={"x-workstream-action-id": ActionId.ADMIN_ROLE_GRANT_LIST.value},
)
async def list_admin_role_grants(
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    scope_type: Annotated[AdminScope, Query()],
    scope_project_id: Annotated[UUID | None, Query()] = None,
    grant_status: Annotated[Literal["active", "revoked", "all"], Query(alias="status")] = "active",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> AdminRoleGrantCollectionResponse:
    return await _grant_page(
        authorization=authorization,
        session=session,
        resolved=resolved,
        action_id=ActionId.ADMIN_ROLE_GRANT_LIST,
        actor_profile_id=None,
        scope_type=scope_type,
        scope_project_id=scope_project_id,
        grant_status=grant_status,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/actors/{actor_profile_id}/admin-role-grants",
    response_model=AdminRoleGrantCollectionResponse,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ.value},
)
async def read_actor_admin_role_grants(
    actor_profile_id: UUID,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    scope_type: Annotated[AdminScope, Query()],
    scope_project_id: Annotated[UUID | None, Query()] = None,
    grant_status: Annotated[Literal["active", "revoked", "all"], Query(alias="status")] = "active",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> AdminRoleGrantCollectionResponse:
    return await _grant_page(
        authorization=authorization,
        session=session,
        resolved=resolved,
        action_id=ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        actor_profile_id=actor_profile_id,
        scope_type=scope_type,
        scope_project_id=scope_project_id,
        grant_status=grant_status,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/admin-role-grants",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthorityMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    openapi_extra={"x-workstream-action-id": ActionId.ADMIN_ROLE_GRANT_ISSUE.value},
)
async def issue_admin_role_grant(
    payload: AdminRoleGrantIssueBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthorityMutationResponse:
    canonical = _issue_request(payload)
    actor_profile_id = UUID(resolved.profile.id)
    service = AdminRoleGrantService(session)
    reservation = await _database_call(
        session,
        service.reserve(
            idempotency_key=idempotency_key,
            actor_profile_id=actor_profile_id,
            request=canonical,
        ),
    )
    decision = await _database_call(
        session,
        authorization.require(
            ActionId.ADMIN_ROLE_GRANT_ISSUE,
            AdminRoleGrantIssueResourceContext(
                resource_type="admin_role_grant_issue",
                resource_id=payload.target_actor_profile_id,
                role=payload.role,
                scope_type=payload.scope_type,
                scope_project_id=payload.scope_project_id,
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=actor_profile_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        response = AuthorityMutationResponse.model_validate(
            reservation.response.model_dump(mode="json")
        )
        await _database_call(session, ActorService(session).touch_after_authorization(resolved))
        await _commit_or_unavailable(session)
        return response
    duplicate = await _database_call(session, service.find_active_duplicate(canonical))
    if duplicate is not None:
        duplicate_id = duplicate.id
        await session.rollback()
        await _database_call(
            session,
            service.record_issue_conflict(
                actor_profile_id=actor_profile_id,
                request=canonical,
                grant_id=duplicate_id,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "admin_role_grant_exists", "Admin role grant exists")
    try:
        await ActorService(session).touch_after_authorization(resolved)
        response = await service.complete_issue(
            claim=reservation.claim,
            request=canonical,
            decision=decision,
            actor_profile_id=actor_profile_id,
            reason=payload.reason,
        )
        await session.commit()
        return response
    except IntegrityError as exc:
        await session.rollback()
        duplicate = await _database_call(session, service.find_active_duplicate(canonical))
        if duplicate is None:
            raise service_unavailable_error() from exc
        duplicate_id = duplicate.id
        await _database_call(
            session,
            service.record_issue_conflict(
                actor_profile_id=actor_profile_id,
                request=canonical,
                grant_id=duplicate_id,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "admin_role_grant_exists", "Admin role grant exists") from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


@router.post(
    "/admin-role-grants/{grant_id}/revoke",
    response_model=AuthorityMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    openapi_extra={"x-workstream-action-id": ActionId.ADMIN_ROLE_GRANT_REVOKE.value},
)
async def revoke_admin_role_grant(
    grant_id: UUID,
    payload: AdminRoleGrantRevokeBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthorityMutationResponse:
    canonical = _revoke_request(grant_id, payload.reason)
    actor_profile_id = UUID(resolved.profile.id)
    service = AdminRoleGrantService(session)
    reservation = await _database_call(
        session,
        service.reserve(
            idempotency_key=idempotency_key,
            actor_profile_id=actor_profile_id,
            request=canonical,
        ),
    )
    decision = await _database_call(
        session,
        authorization.require(
            ActionId.ADMIN_ROLE_GRANT_REVOKE,
            AdminRoleGrantResourceContext(
                resource_type="admin_role_grant",
                resource_id=grant_id,
                existing_idempotency_record=reservation.outcome in {"replay", "mismatch"},
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=actor_profile_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        response = AuthorityMutationResponse.model_validate(
            reservation.response.model_dump(mode="json")
        )
        await _database_call(session, ActorService(session).touch_after_authorization(resolved))
        await _commit_or_unavailable(session)
        return response
    try:
        await ActorService(session).touch_after_authorization(resolved)
        response = await service.complete_revoke(
            claim=reservation.claim,
            request=canonical,
            decision=decision,
            actor_profile_id=actor_profile_id,
            reason=payload.reason,
        )
        await session.commit()
        return response
    except LastAccessAdministratorConflict as exc:
        await session.rollback()
        await _database_call(
            session,
            service.record_last_admin_denial(
                actor_profile_id=actor_profile_id,
                grant_id=exc.grant_id,
                target_actor_profile_id=exc.target_actor_profile_id,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(
            409,
            "last_access_administrator",
            "Final Access Administrator cannot be revoked",
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise service_unavailable_error() from exc


async def _canonical_project(session: AsyncSession, project_id: UUID):
    project = await ProjectRepository(session).get_project(str(project_id))
    if project is None:
        raise _project_role_resource_not_found()
    return project


def _project_role_response(grant) -> ProjectRoleGrantMutationResponse:
    return ProjectRoleGrantMutationResponse(
        id=grant.id,
        qualification_snapshot_id=grant.qualification_snapshot_id,
        project_id=UUID(grant.project_id),
        actor_profile_id=UUID(grant.actor_profile_id),
        role=grant.role,
        status=grant.status,
        version=grant.version,
    )


@router.post(
    "/projects/{project_id}/role-grants",
    response_model=ProjectRoleGrantMutationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_ROLE_GRANT_ISSUE.value},
)
async def issue_project_role_grant(
    project_id: UUID,
    payload: ProjectRoleGrantIssueBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    prepared: Annotated[PreparedAuthorizationService, Depends(get_prepared_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRoleGrantMutationResponse:
    canonical = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=project_id,
        target_actor_id=payload.target_actor_profile_id,
        role=payload.role,
        qualification=payload.qualification,
        reason_digest=derive_reason_digest(payload.reason),
    )
    actor_id = UUID(resolved.profile.id)
    service = ProjectRoleGrantMutationService(session)
    reservation = await _database_call(
        session,
        service.reserve(key=idempotency_key, actor_profile_id=actor_id, request=canonical),
    )
    prepared_input = PreparedAuthorizationInput(
        idempotency_key=idempotency_key,
        request_value=canonical.model_dump(mode="json"),
    )
    try:
        handle = await _database_call(
            session,
            prepared.prepare(
                ActionId.PROJECT_ROLE_GRANT_ISSUE,
                prepared_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=project_id,
                    target_actor_profile_id=payload.target_actor_profile_id,
                    role=payload.role,
                ),
            ),
        )
    except PreparedAuthorizationUnsupported as exc:
        raise _project_role_resource_not_found() from exc
    project = await _database_call(session, service.repository.lock_project(project_id))
    if project is None:
        raise _project_role_resource_not_found()
    await _database_call(
        session,
        service.repository.take_project_role_issue_lock(
            project_role_issue_lock_key(
                payload.target_actor_profile_id,
                project_id,
                payload.role.value,
            )
        ),
    )
    target_eligible = (
        await _database_call(
            session,
            service.repository.lock_eligible_human(payload.target_actor_profile_id),
        )
        is not None
    )
    active_exact_role = await _database_call(
        session,
        service.repository.find_active_project_role(
            project_id=project_id,
            actor_profile_id=payload.target_actor_profile_id,
            role=payload.role.value,
        ),
    )
    decision = await _database_call(
        session,
        prepared.consume(
            handle,
            ActionId.PROJECT_ROLE_GRANT_ISSUE,
            prepared_input,
            ProjectRoleGrantIssueResourceContext(
                resource_type="project_role_grant_issue",
                resource_id=project_id,
                scope_project_id=project_id,
                target_actor_profile_id=payload.target_actor_profile_id,
                role=payload.role,
                project_status=project.status,
                target_eligible=target_eligible,
                active_exact_role_exists=active_exact_role is not None,
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=actor_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        row = await _database_call(
            session,
            service.repository.lock_project_role_grant(
                project_id=project_id, grant_id=reservation.response.resource_id
            ),
        )
        if (
            reservation.response.resource_type.value != "project_role_grant"
            or reservation.response.http_status != 201
            or reservation.response.version != 1
            or row is None
            or row[0].status != "active"
            or row[0].version != 1
            or row[0].project_id != str(project_id)
            or row[0].actor_profile_id != str(payload.target_actor_profile_id)
            or row[0].role != payload.role.value
            or row[1].id != row[0].qualification_snapshot_id
            or row[1].project_id != row[0].project_id
            or row[1].actor_profile_id != row[0].actor_profile_id
            or row[1].requested_role != row[0].role
        ):
            raise _domain_error(
                409,
                "project_role_grant_replay_state_changed",
                "Project role grant replay state changed",
            )
        await _commit_or_unavailable(session)
        return _project_role_response(row[0])
    try:
        if active_exact_role is not None:
            raise ProjectRoleGrantConflict(
                "project_role_grant_exists", active_exact_role.id
            )
        response = await _database_call(
            session,
            service.complete_issue(
                claim=reservation.claim,
                request=canonical,
                decision=decision,
                actor_profile_id=actor_id,
                reason=payload.reason,
            ),
        )
        await _commit_or_unavailable(session)
        return response
    except ProjectRoleGrantConflict as exc:
        await session.rollback()
        conflict_grant_id = exc.grant_id
        if conflict_grant_id is None:
            conflict = await _database_call(
                session,
                service.repository.find_active_project_role(
                    project_id=project_id,
                    actor_profile_id=payload.target_actor_profile_id,
                    role=payload.role.value,
                ),
            )
            if conflict is None:
                raise service_unavailable_error() from exc
            conflict_grant_id = conflict.id
        await _database_call(
            session,
            service.record_conflict(
                actor_profile_id=actor_id,
                project_id=project_id,
                grant_id=conflict_grant_id,
                decision=decision,
                code=exc.code,
                action_id=ActionId.PROJECT_ROLE_GRANT_ISSUE,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, exc.code, "Project role grant already exists") from exc


@router.post(
    "/projects/{project_id}/role-grants/{grant_id}/revoke",
    response_model=ProjectRoleGrantMutationResponse,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_ROLE_GRANT_REVOKE.value},
)
async def revoke_project_role_grant(
    project_id: UUID,
    grant_id: UUID,
    payload: ProjectRoleGrantRevokeBody,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    prepared: Annotated[PreparedAuthorizationService, Depends(get_prepared_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRoleGrantMutationResponse:
    canonical = ProjectRoleGrantRevokeRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE,
        project_id=project_id,
        grant_id=grant_id,
        reason_digest=derive_reason_digest(payload.reason),
    )
    actor_id = UUID(resolved.profile.id)
    service = ProjectRoleGrantMutationService(session)
    reservation = await _database_call(
        session,
        service.reserve(key=idempotency_key, actor_profile_id=actor_id, request=canonical),
    )
    prepared_input = PreparedAuthorizationInput(
        idempotency_key=idempotency_key,
        request_value=canonical.model_dump(mode="json"),
    )
    try:
        handle = await _database_call(
            session,
            prepared.prepare(
                ActionId.PROJECT_ROLE_GRANT_REVOKE,
                prepared_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=project_id,
                    grant_id=grant_id,
                ),
            ),
        )
    except PreparedAuthorizationUnsupported as exc:
        raise _project_role_resource_not_found() from exc
    project = await _database_call(session, service.repository.lock_project(project_id))
    row = await _database_call(
        session,
        service.repository.lock_project_role_grant(project_id=project_id, grant_id=grant_id),
    )
    if project is None or row is None:
        raise _project_role_resource_not_found()
    grant, _snapshot = row
    decision = await _database_call(
        session,
        prepared.consume(
            handle,
            ActionId.PROJECT_ROLE_GRANT_REVOKE,
            prepared_input,
            ProjectRoleGrantRevokeResourceContext(
                resource_type="project_role_grant_revoke",
                resource_id=grant_id,
                scope_project_id=project_id,
                actor_profile_id=UUID(grant.actor_profile_id),
                role=ProjectRole(grant.role),
                project_status=project.status,
                status=grant.status,
                version=grant.version,
            ),
        ),
    )
    if reservation.outcome == "mismatch":
        await session.rollback()
        await _database_call(
            session,
            service.record_mismatch(
                actor_profile_id=actor_id,
                request=canonical,
                decision=decision,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, "idempotency_mismatch", "Idempotency key does not match")
    if reservation.outcome == "replay":
        if (
            reservation.response.resource_type.value != "project_role_grant"
            or reservation.response.resource_id != grant_id
            or reservation.response.http_status != 200
            or reservation.response.version != 2
            or grant.status != "revoked"
            or grant.version != 2
            or grant.project_id != str(project_id)
            or _snapshot.id != grant.qualification_snapshot_id
            or _snapshot.project_id != grant.project_id
            or _snapshot.actor_profile_id != grant.actor_profile_id
            or _snapshot.requested_role != grant.role
        ):
            raise _domain_error(
                409,
                "project_role_grant_replay_state_changed",
                "Project role grant replay state changed",
            )
        await _commit_or_unavailable(session)
        return _project_role_response(grant)
    try:
        response = await _database_call(
            session,
            service.complete_revoke(
                claim=reservation.claim,
                request=canonical,
                decision=decision,
                actor_profile_id=actor_id,
                reason=payload.reason,
                grant=grant,
            ),
        )
        await _commit_or_unavailable(session)
        return response
    except ProjectRoleGrantConflict as exc:
        await session.rollback()
        if exc.grant_id is None:
            raise service_unavailable_error() from exc
        await _database_call(
            session,
            service.record_conflict(
                actor_profile_id=actor_id,
                project_id=project_id,
                grant_id=exc.grant_id,
                decision=decision,
                code=exc.code,
                action_id=ActionId.PROJECT_ROLE_GRANT_REVOKE,
            ),
        )
        await _commit_or_unavailable(session)
        raise _domain_error(409, exc.code, "Project role grant is already revoked") from exc


@router.get(
    "/projects/{project_id}/contributor-candidates",
    response_model=ContributorCandidateListResponse,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST.value},
)
async def list_project_contributor_candidates(
    project_id: UUID,
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ContributorCandidateListResponse:
    """List privacy-safe contributor candidates for one canonical project."""
    project = await _canonical_project(session, project_id)
    service = _project_role_read_service(request, session, authorization)
    try:
        return await service.list_contributor_candidates(
            project=project,
            caller_actor_profile_id=UUID(resolved.profile.id),
            limit=limit,
            cursor=cursor,
        )
    except InvalidPaginationCursor as exc:
        raise _domain_error(400, "invalid_cursor", "Invalid cursor") from exc


@router.get(
    "/projects/{project_id}/role-grants",
    response_model=ProjectRoleGrantListResponse,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_ROLE_GRANT_LIST.value},
)
async def list_project_role_grants(
    project_id: UUID,
    request: Request,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status_filter: Annotated[
        Literal["active", "revoked"] | None,
        Query(alias="status"),
    ] = None,
    role: Annotated[ProjectRole | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ProjectRoleGrantListResponse:
    """List immutable project-role grant history without a count."""
    project = await _canonical_project(session, project_id)
    service = _project_role_read_service(request, session, authorization)
    try:
        return await service.list_project_role_grants(
            project=project,
            status=status_filter,
            role=role,
            limit=limit,
            cursor=cursor,
        )
    except InvalidPaginationCursor as exc:
        raise _domain_error(400, "invalid_cursor", "Invalid cursor") from exc


@router.get(
    "/projects/{project_id}/role-grants/{grant_id}",
    response_model=ProjectRoleGrantRead,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_ROLE_GRANT_READ.value},
)
async def read_project_role_grant(
    project_id: UUID,
    grant_id: UUID,
    request: Request,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRoleGrantRead:
    """Read one grant only through its canonical project relationship."""
    project = await _canonical_project(session, project_id)
    service = _project_role_read_service(request, session, authorization)
    try:
        return await service.read_project_role_grant(
            project=project,
            grant_id=grant_id,
        )
    except ProjectRoleReadResourceNotFound as exc:
        raise _project_role_resource_not_found() from exc
