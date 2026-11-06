"""Current guide creation and compilation prerequisites; no lifecycle guards disabled."""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.core.identifiers import new_record_id
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
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CheckFailureFinding,
    CheckInabilityToEvaluate,
    CheckInput,
    CheckNegativeTest,
    CheckSpecification,
    GuideEvidenceRef,
)
from app.modules.checkers.api.external import ExternalCheckerRegistryEntry
from app.modules.checkers.api.external_policy import ExternalCheckerImageAttachment
from tests.committed_guide_fixtures import (
    create_committed_document_fixture,
    seed_setup_service_for_compiled_fixture,
)
from tests.project_create_fixtures import seed_authorized_project
from tests.projects.guide_compilation.helpers import ids, context, generated_result
from tests.projects.guide_compilation.finalization.pg_prerequisites import (
    compilation_and_projections,
)
from tests.projects.guide_compilation.finalization.pg_support import finalize
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor


async def _create_guide_source(factory, values, actor, version):
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
        return setup.source_snapshot_id


PostSubmitConfigurationSetup = Callable[
    [async_sessionmaker, UUID, ExternalCheckerRegistryEntry],
    Awaitable[dict],
]


@dataclass(frozen=True, slots=True)
class PostSubmitAttachmentCase:
    """One human-defined execution member with exact image configuration."""

    requirement_id: str
    configuration: dict


PostSubmitConfigurationsSetup = Callable[
    [async_sessionmaker, UUID, ExternalCheckerRegistryEntry],
    Awaitable[tuple[PostSubmitAttachmentCase, ...]],
]


def _post_check_suggestion(refs, specification=None):
    """Describe POST work from source evidence, without consulting registered images."""
    check = specification or CheckSpecification(
        evaluation_method="Assess submitted claims against the project guide.",
        inputs=(CheckInput(
            input_id="submitted_work", kind="package", purpose="Work and evidence to assess.",
        ),),
        check_steps=("Read the submitted claims and supporting evidence.",
                     "Compare each material claim with its supporting evidence."),
        pass_conditions=("Every material claim has adequate supporting evidence.",),
        failure_findings=(CheckFailureFinding(
            code="unsupported_claim", level="error",
            condition="A material claim lacks adequate supporting evidence.",
            message="Support the claim with evidence.",
        ),),
        positive_tests=("A supported claim passes.",),
        negative_tests=(CheckNegativeTest(
            name="unsupported_claim", scenario="A material claim lacks evidence.",
            expected_verdict="failed", expected_finding_codes=("unsupported_claim",),
        ),),
        implementation_needs=("Read submitted work and compare claims with evidence.",),
        inability_to_evaluate=(CheckInabilityToEvaluate(
            code="material_unavailable", condition="The submitted work cannot be read.",
        ),),
    )
    return AtomicGuideRequirement(
        suggestion_id="review_claim_evidence",
        statement="Material claims in the submitted work need supporting evidence.",
        stage="post_submit",
        classification_rationale="Evidence assessment follows immutable submission.",
        check_specification=check,
        evidence_refs=refs,
    )


async def create_compiled_guide(
    factory,
    values,
    actor,
    *,
    version="v1",
    artifact_proposal=None,
    post_submit_specification=None,
    compilation_outcome=None,
    configuration=None,
):
    """Create declarations with real AUTH, then execute/project/finalize scripted findings."""
    snapshot_id = await _create_guide_source(factory, values, actor, version)
    manifest = await create_committed_document_fixture(str(snapshot_id), sessions=factory)
    values = {
        **values,
        "guide": manifest.guide_id,
        "snapshot": manifest.source_snapshot_id,
        "setup_1": manifest.setup_run_id,
    }
    compilation_context = context(
        values,
        guide_version=version,
        configuration=configuration,
    ).model_copy(update={"material": manifest})
    outcome = compilation_outcome or generated_result()
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
        update={
            field: tuple(
                item.model_copy(update={"evidence_refs": refs}) for item in getattr(outcome, field)
            )
            for field in ("findings", "requirements")
        }
    )
    if outcome.status != "guide_blocked" and compilation_outcome is None:
        outcome = outcome.model_copy(update={
            "requirements": (*outcome.requirements, _post_check_suggestion(refs, post_submit_specification)),
        })
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
async def source_case(
    url,
    *,
    namespace=None,
    guide_version="v1",
    artifact_proposal=None,
    pre_submit_registry_spec=None,
    post_submit_registry_spec=None,
    post_submit_configuration_setup: PostSubmitConfigurationSetup | None = None,
    post_submit_configurations_setup: PostSubmitConfigurationsSetup | None = None,
    post_submit_specification=None,
    compilation_outcome=None,
    configuration=None,
):
    """An authorized draft Project plus a genuinely created complete guide source."""
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if namespace is not None:
            from app.modules.artifacts.models import ArtifactStorageNamespace

            async with factory() as session, session.begin():
                existing = await session.get(ArtifactStorageNamespace, "primary")
                if existing is None:
                    session.add(
                        ArtifactStorageNamespace(
                            id="primary",
                            backend=namespace.backend,
                            adapter=namespace.adapter,
                            provider_profile=namespace.provider_profile,
                            namespace_descriptor=namespace.namespace_descriptor,
                            namespace_fingerprint=namespace.namespace_fingerprint,
                        )
                    )
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
        values.update(await _prepare_human_attachments(
            factory, values["project"], pre_submit_registry_spec, post_submit_registry_spec,
            post_submit_configuration_setup, post_submit_configurations_setup,
        ))
        values, finalization = await create_compiled_guide(
            factory,
            values,
            actor,
            version=guide_version,
            artifact_proposal=artifact_proposal,
            post_submit_specification=post_submit_specification,
            compilation_outcome=compilation_outcome,
            configuration=configuration,
        )
        yield values, factory, finalization, actor, grant
    finally:
        await engine.dispose()


async def _prepare_human_attachments(
    factory,
    project_id,
    pre_submit_registry_spec,
    post_submit_registry_spec,
    post_submit_configuration_setup,
    post_submit_configurations_setup,
):
    """Register fixture images and return exact human-selected phase members."""
    pre_registry_entry = (
        await _register_external_checker_fixture(factory, pre_submit_registry_spec)
        if pre_submit_registry_spec is not None else None
    )
    post_registry_entry = (
        await _register_external_checker_fixture(factory, post_submit_registry_spec)
        if post_submit_registry_spec is not None else None
    )
    if post_submit_configuration_setup is not None and post_submit_configurations_setup is not None:
        raise ValueError("post-submit configuration setup is ambiguous")
    if (post_submit_configuration_setup is not None or post_submit_configurations_setup is not None) and post_registry_entry is None:
        raise ValueError("post-submit configuration requires a registered image")
    post_configuration = (
        await post_submit_configuration_setup(factory, project_id, post_registry_entry)
        if post_submit_configuration_setup is not None else {}
    )
    post_cases = (
        await post_submit_configurations_setup(factory, project_id, post_registry_entry)
        if post_submit_configurations_setup is not None
        else (PostSubmitAttachmentCase("project.post_evidence", post_configuration),)
    )
    pre_attachments = (
        (ExternalCheckerImageAttachment(
            requirement_id="project.archive_rules",
            registry_entry_id=pre_registry_entry.registry_entry_id,
            registry_entry_digest=pre_registry_entry.entry_digest,
            configuration={},
        ),)
        if pre_registry_entry is not None else ()
    )
    post_attachments = (
        tuple(ExternalCheckerImageAttachment(
            requirement_id=case.requirement_id,
            registry_entry_id=post_registry_entry.registry_entry_id,
            registry_entry_digest=post_registry_entry.entry_digest,
            configuration=case.configuration,
        ) for case in sorted(post_cases, key=lambda item: item.requirement_id))
        if post_registry_entry is not None else ()
    )
    return {"pre_submit_attachments": pre_attachments,
            "post_submit_attachments": post_attachments}


async def _register_external_checker_fixture(factory, spec):
    """Publish one real Operator-authorized immutable entry before compilation."""
    from app.modules.authorization.checker_registry_authorization import (
        ExternalCheckerRegistryAuthorizationAdapter,
    )
    from app.modules.checkers.api.external import ExternalCheckerRegistrationCommand
    from app.modules.checkers.external_registry import (
        ExternalCheckerRegistryReader, ExternalCheckerRegistryService,
    )
    from tests.project_create_fixtures import (
        grant_fixture_admin_role,
        seed_fixture_actor,
    )

    async with factory() as session, session.begin():
        reader = ExternalCheckerRegistryReader(session)
        existing = tuple(
            entry for entry in await reader.list_entries()
            if (entry.capability_id, entry.capability_version, entry.phase)
            == (spec.capability_id, spec.capability_version, spec.phase)
        )
        if existing:
            assert len(existing) == 1 and existing[0].entry_digest == spec.spec_digest
            return await reader.read_exact(
                UUID(str(existing[0].registry_entry_id)), existing[0].entry_digest,
            )
        profile, link = await seed_fixture_actor(
            session,
            issuer="https://external-checker-fixture.test",
            subject_prefix="external-checker-operator",
        )
        await grant_fixture_admin_role(
            session,
            profile.id,
            role="operator",
            scope="system",
        )
        operation_id = new_record_id()
        command = ExternalCheckerRegistrationCommand(
            actor_profile_id=UUID(profile.id),
            operation_id=operation_id,
            spec=spec,
        )
        authority_context = HumanAuthorizationContext(
            actor_profile_id=UUID(profile.id),
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=operation_id,
        )
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(
            session, authority_context, admin_repository=repository
        )
        return await ExternalCheckerRegistryService(
            session,
            ExternalCheckerRegistryAuthorizationAdapter(
                kernel,
                PreparedAuthorizationService(
                    session, authority_context, kernel, repository
                ),
            ),
        ).register(command)
