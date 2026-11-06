"""Public-created immutable guide inputs awaiting an explicit PM command."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import guide_document_manifest_port
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.authorization.models import AdminRoleGrant
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
from tests.projects.guide_fixtures import (
    create_project, create_guide, read_guide_source_snapshot, complete_guide_payload,
)
from .test_authorized_request_service import _authorized_service


@pytest.fixture
async def pending_source(project_client, project_database_env):
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    engine = create_async_engine(project_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            setup = await session.scalar(select(ProjectSetupRun).where(
                ProjectSetupRun.source_snapshot_id == snapshot["id"]))
            profile = await session.scalar(select(ActorProfile).where(
                ActorProfile.service_identity == "workstream.project.setup"))
            link = await session.scalar(select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == profile.id))
            actor = ActorIdentityFacts(UUID(profile.id), UUID(link.id), ActorKind.SERVICE,
                                       "workstream.project.setup")
            setup_id = UUID(setup.id)
        yield factory, actor, setup_id, snapshot
    finally:
        await engine.dispose()


async def manager_actor(factory, project_id):
    async with factory() as session:
        row = (await session.execute(select(ActorProfile, ActorIdentityLink)
            .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
            .join(AdminRoleGrant, AdminRoleGrant.target_actor_profile_id == ActorProfile.id)
            .where(AdminRoleGrant.role == "project_manager", AdminRoleGrant.scope_type == "project",
                   AdminRoleGrant.scope_project_id == str(project_id), AdminRoleGrant.status == "active")
            .order_by(AdminRoleGrant.granted_at, AdminRoleGrant.id).limit(1))).one()
        return ActorIdentityFacts(UUID(row[0].id), UUID(row[1].id), ActorKind.HUMAN)


async def request_pending_source(factory, setup_id, configuration, *, key=None):
    """Use real PM AUTH and original custody; no publication or provider call occurs here."""
    async with factory() as session:
        setup = await session.get(ProjectSetupRun, str(setup_id))
        project_id = setup.project_id
    actor = await manager_actor(factory, project_id)
    async with factory() as session:
        return await _authorized_service(session, actor, request_inputs=CompilationRequestInputs(
            guide_document_manifest_port(session), configuration,
        )).request_initial(actor=actor, setup_run_id=UUID(str(setup_id)), idempotency_key=key or uuid4(),
                           inference_required=configuration.uses_inference)
