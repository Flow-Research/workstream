"""Authentication utility routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import (
    actor_registry_http_error,
    actor_registry_unavailable_error,
    get_registered_actor,
)
from app.api.deps.authorization import get_authorization_actor, get_authorization_service
from app.db.session import get_db_session
from app.modules.actors.schemas import ActorProfileSelfResponse, ActorProfileUpdateRequest
from app.modules.actors.service import ActorRegistryError, ActorService, ResolvedActor
from app.modules.authorization.admin_service import AdminRoleGrantService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.schemas.auth import ActorContext, ActorResponse

router = APIRouter(prefix="/auth", tags=["auth"])
actors_router = APIRouter(prefix="/actors", tags=["actors"])


@router.get("/me", response_model=ActorResponse)
async def read_current_actor(
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
) -> ActorResponse:
    """Return the actor context derived from the current bearer token.

    Args:
        actor: Verified actor resolved by auth dependencies.

    Returns:
        Public actor response including audit context.
    """
    return ActorResponse.from_actor(actor)


@actors_router.get(
    "/me",
    response_model=ActorProfileSelfResponse,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_PROFILE_READ_SELF.value},
)
async def read_current_actor_profile(
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorProfileSelfResponse:
    """Return the caller's canonical Contributor-domain profile."""
    try:
        await authorization.require(
            ActionId.ACTOR_PROFILE_READ_SELF,
            ActorService.actor_self_resource(resolved.profile.id, frozenset()),
        )
        resolved = await ActorService(session).touch_after_authorization(resolved)
        admin_roles = await AdminRoleGrantService(session).active_roles_for_actor(
            UUID(resolved.profile.id)
        )
        response = ActorService.self_response(resolved.profile, admin_roles=admin_roles)
        await session.commit()
        return response
    except ActorRegistryError as exc:
        await session.rollback()
        raise actor_registry_http_error(exc) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc


@actors_router.patch(
    "/me",
    response_model=ActorProfileSelfResponse,
    openapi_extra={"x-workstream-action-id": ActionId.ACTOR_PROFILE_UPDATE_SELF.value},
)
async def update_current_actor_profile(
    payload: ActorProfileUpdateRequest,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActorProfileSelfResponse:
    """Update only the caller-owned canonical display fields."""
    try:
        await authorization.require(
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
            ActorService.actor_self_resource(resolved.profile.id, payload.model_fields_set),
        )
        service = ActorService(session)
        resolved = await service.touch_after_authorization(resolved)
        response = await service.update_self(resolved, payload)
        admin_roles = await AdminRoleGrantService(session).active_roles_for_actor(
            UUID(resolved.profile.id)
        )
        response = response.model_copy(update={"admin_roles": admin_roles})
        await session.commit()
        return response
    except ActorRegistryError as exc:
        await session.rollback()
        raise actor_registry_http_error(exc) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise actor_registry_unavailable_error() from exc
