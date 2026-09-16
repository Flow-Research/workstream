"""Current guide creation and compilation prerequisites; no lifecycle guards disabled."""

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.projects.guide_mutation_service import GuideMutationService
from app.modules.projects.schemas import ProjectGuideCreate
from app.modules.projects.models import ProjectSetupRun
from app.interfaces.project_agents import GuideEvidenceRef
from tests.committed_guide_fixtures import (
    create_committed_document_fixture,
    seed_setup_service_for_compiled_fixture,
)
from tests.project_create_fixtures import seed_authorized_project
from tests.projects.guide_compilation.helpers import ids, context, result
from tests.projects.guide_compilation.finalization.pg_prerequisites import (
    compilation_and_projections,
)
from tests.projects.guide_compilation.finalization.pg_support import finalize
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor


async def create_compiled_guide(factory, values, actor, *, version="v1", artifact_proposal=None):
    """Create declarations with real AUTH, then execute/project/finalize scripted findings."""
    async with factory() as session, session.begin():
        resolved = ResolvedActor(
            await session.get(ActorProfile, str(actor.actor_profile_id)),
            await session.get(ActorIdentityLink, str(actor.identity_link_id)),
        )
        authority = HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=actor.identity_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(session, authority, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, authority, kernel, repository)
        created = await GuideMutationService(session).create_guide(
            resolved,
            prepared,
            uuid4(),
            values["project"],
            ProjectGuideCreate(
                version=version,
                change_summary=f"Guide {version}",
                task_examples=[{"content": "Review a claim using the project guide."}],
                documents=[
                    {"label": name, "media_type": "application/pdf"}
                    for name in ("guide.pdf", "rubric.pdf")
                ],
            ),
        )
        setup = await session.get(ProjectSetupRun, str(created.response.setup.id))
        snapshot_id = setup.source_snapshot_id
    manifest = await create_committed_document_fixture(str(snapshot_id), sessions=factory)
    # Arrange the completed durable dispatch prerequisite; no broker is exercised here.
    async with factory() as session, session.begin():
        setup = await session.get(ProjectSetupRun, str(manifest.setup_run_id))
        setup.status = setup.current_step = "queued"
        from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

        setup.celery_task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
    values = {
        **values,
        "guide": manifest.guide_id,
        "snapshot": manifest.source_snapshot_id,
        "setup_1": manifest.setup_run_id,
    }
    compilation_context = context(values, guide_version=version).model_copy(
        update={"material": manifest}
    )
    outcome = result()
    if artifact_proposal is not None:
        outcome = outcome.model_copy(update={"submission_artifact_policy": artifact_proposal})
    refs = tuple(
        GuideEvidenceRef(
            source_item_id=item.source_item_id,
            document_version_id=item.ingest_id,
            sha256=item.sha256,
        )
        for item in manifest.documents
    )
    outcome = outcome.model_copy(
        update={"findings": (outcome.findings[0].model_copy(update={"evidence_refs": refs}),)}
    )
    url = factory.kw["bind"].url.render_as_string(hide_password=False)
    finalization = await compilation_and_projections(
        url,
        factory,
        values,
        compilation_context=compilation_context,
        outcome=outcome,
    )
    await finalize(factory, values, finalization)
    return values, finalization


@asynccontextmanager
async def source_case(url, *, namespace=None, guide_version="v1", artifact_proposal=None):
    """An authorized draft Project plus a genuinely created complete guide source."""
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if namespace is not None:
            from app.modules.artifacts.models import ArtifactStorageNamespace
            async with factory() as session, session.begin():
                existing = await session.get(ArtifactStorageNamespace, "primary")
                if existing is None:
                    session.add(ArtifactStorageNamespace(
                        id="primary", backend=namespace.backend, adapter=namespace.adapter,
                        provider_profile=namespace.provider_profile,
                        namespace_descriptor=namespace.namespace_descriptor,
                        namespace_fingerprint=namespace.namespace_fingerprint,
                    ))
                else:
                    assert existing.namespace_fingerprint == namespace.namespace_fingerprint
        values = ids()
        async with factory() as session, session.begin():
            await seed_authorized_project(
                session,
                project_id=str(values["project"]),
                name="Activation",
                slug="activation-" + uuid4().hex,
            )
        await seed_setup_service_for_compiled_fixture(factory)
        async with factory() as session:
            service_id, link_id = (
                await session.execute(
                    select(ActorProfile.id, ActorIdentityLink.id)
                    .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
                    .where(ActorProfile.service_identity == "workstream.project.setup")
                )
            ).one()
            values.update(actor=UUID(service_id), link=UUID(link_id))
        actor, grant = await seed_review_actor(factory, values["project"])
        values, finalization = await create_compiled_guide(factory, values, actor, version=guide_version,
                                                           artifact_proposal=artifact_proposal)
        yield values, factory, finalization, actor, grant
    finally:
        await engine.dispose()
