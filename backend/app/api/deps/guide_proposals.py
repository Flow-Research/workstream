"""HTTP composition for exact human guide proposal operations."""

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import (
    _authorization_context, get_authorization_actor, get_authorization_actor_identity,
)
from app.core.api_controls import request_ids
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.adapters.auth import guide_proposal_authorization, human_guide_compilation_authorization
from app.adapters.projects import project_guide_proposal_service, project_guide_correction_dispatch


@dataclass(frozen=True)
class ProposalRequest:
    """One request's explicit authority and caller-owned SQL transaction."""

    session: AsyncSession
    service: Any
    actor: ActorIdentityFacts
    request_id: UUID


async def get_proposal_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Discard identity refresh reads before the proposal's sole transaction."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    try:
        async with session.begin():
            yield ProposalRequest(
                session,
                project_guide_proposal_service(session, guide_proposal_authorization(session, context)),
                actor,
                request_id,
            )
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_correction_dispatch(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Compose the existing human compilation request port without a runtime."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.adapters.checkers import project_guide_approval_compiler
    from app.api.deps.authorization import prepared_authorization_service
    from app.core.config import get_settings
    from app.core.project_agents import project_guide_runtime_configuration

    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    _, pre, post = project_guide_approval_compiler()
    async with prepared_authorization_service(request, resolved, session) as prepared:
        yield project_guide_correction_dispatch(
            session, human_guide_compilation_authorization(prepared),
            material=guide_document_manifest_port(session), pre=pre, post=post,
            configuration=project_guide_runtime_configuration(get_settings()),
        ), actor
