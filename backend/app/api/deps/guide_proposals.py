"""HTTP composition for exact human guide proposal operations."""

from dataclasses import dataclass
from functools import partial
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from app.modules.projects.api.guide_proposals import (
    GuideProposalOperationsPort,
    GuideCompilationDispatchPort,
)
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import (
    _authorization_context,
    get_authorization_actor,
    get_authorization_actor_identity,
)
from app.core.api_controls import request_ids
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.adapters.auth import guide_proposal_authorization, human_guide_compilation_authorization
from app.adapters.projects import project_guide_proposal_service, project_guide_compilation_dispatch


@dataclass(frozen=True)
class ProposalRequest:
    """One request's explicit authority and caller-owned SQL transaction."""

    session: AsyncSession
    service: GuideProposalOperationsPort[ActorIdentityFacts]
    actor: ActorIdentityFacts
    request_id: UUID


@dataclass(frozen=True)
class CompilationDispatchRequest:
    """Typed correction delivery owner and resolved human identity."""

    service: GuideCompilationDispatchPort[ActorIdentityFacts]
    actor: ActorIdentityFacts


async def get_proposal_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[ProposalRequest]:
    """Discard identity refresh reads before the proposal's sole transaction."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    try:
        async with session.begin():
            yield ProposalRequest(
                session,
                project_guide_proposal_service(
                    session, guide_proposal_authorization(session, context)
                ),
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
) -> AsyncIterator[CompilationDispatchRequest]:
    """Compose the existing human compilation request port without a runtime."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.api.deps.authorization import prepared_authorization_service
    from app.core.config import get_settings
    from app.core.project_agents import project_guide_runtime_configuration
    from app.adapters.project_agents import build_project_guide_adapter_profile

    settings = get_settings()

    actor = await get_authorization_actor_identity(resolved)
    async with prepared_authorization_service(request, resolved, session) as prepared:
        # Capture the immutable AUTH context before rollback expires the ORM
        # identity rows; dispatch still owns a fresh product transaction.
        await session.rollback()
        yield CompilationDispatchRequest(
            project_guide_compilation_dispatch(
                session,
                human_guide_compilation_authorization(prepared),
                material=guide_document_manifest_port(session),
                configuration=project_guide_runtime_configuration(
                    settings,
                    adapter_profile_builder=partial(
                        build_project_guide_adapter_profile, settings.project_agent_runtime
                    ),
                ),
            ),
            actor,
        )


@asynccontextmanager
async def _initial_dispatch(request, resolved, session, configuration):
    """Compose the shared owner with the command's trusted configuration."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.api.deps.authorization import prepared_authorization_service

    actor = await get_authorization_actor_identity(resolved)
    async with prepared_authorization_service(request, resolved, session) as prepared:
        await session.rollback()
        yield CompilationDispatchRequest(project_guide_compilation_dispatch(
            session, human_guide_compilation_authorization(prepared),
            material=guide_document_manifest_port(session), configuration=configuration), actor)


async def get_assistance_dispatch(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CompilationDispatchRequest]:
    """Select configured inference only for an explicit assistance command."""
    from app.core.config import get_settings
    from app.core.project_agents import project_guide_runtime_configuration
    from app.adapters.project_agents import build_project_guide_adapter_profile

    settings = get_settings()
    configuration = project_guide_runtime_configuration(settings,
        adapter_profile_builder=partial(build_project_guide_adapter_profile, settings.project_agent_runtime))
    async with _initial_dispatch(request, resolved, session, configuration) as value:
        yield value


async def get_requirements_dispatch(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CompilationDispatchRequest]:
    """Select provider-free compilation independently of configured inference."""
    from app.core.config import get_settings
    from app.core.project_agents import manager_authored_guide_configuration

    async with _initial_dispatch(request, resolved, session,
                                 manager_authored_guide_configuration(get_settings())) as value:
        yield value
