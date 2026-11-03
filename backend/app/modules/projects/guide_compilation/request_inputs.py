"""Resolve canonical setup input from owned lineage and verified ART material."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.modules.projects.api.guide_documents import (
    GuideDocumentManifestPort,
    GuideDocumentManifestRequest,
)
from app.modules.authorization.api import (
    ProjectGuideCompilationRequestFacts,
    ProjectGuideCompilationRequestOrigin,
)
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    GuideSourceSnapshot,
    ProjectGuide,
    ProjectSetupRun,
)

from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from .source_state import is_compilation_source_setup
from .context import compilation_context_from_material
from .contracts import CompilationAttemptIdentity
from .repository import GuideCompilationIntegrityError, GuideCompilationRepository
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import ModelProfileReaderPort


@dataclass(frozen=True)
class CompilationRequestInputs:
    """Composition supplies material access and a trusted setup runtime."""

    material: GuideDocumentManifestPort
    runtime_configuration: ProjectGuideRuntimeConfiguration | None

    async def resolve(
        self,
        session: AsyncSession,
        setup_run_id: UUID,
        *,
        operation_id: UUID | None = None,
        lock: bool = False,
    ) -> tuple[
        ProjectGuideCompilationRequestFacts,
        CompilationAttemptIdentity,
        ProjectGuideCompilationRequestOrigin,
    ]:
        """Derive exact request facts inside the caller's root transaction."""
        if self.runtime_configuration is None:
            raise GuideCompilationIntegrityError(
                "automatic compilation runtime configuration unavailable"
            )
        statement = select(ProjectSetupRun).where(ProjectSetupRun.id == str(setup_run_id))
        if lock:
            statement = statement.with_for_update()
        setup = await session.scalar(statement.execution_options(populate_existing=True))
        if setup is None or not is_compilation_source_setup(
            setup, project_guide_compilation_task_id(str(setup_run_id), setup.setup_generation)
        ):
            raise GuideCompilationIntegrityError("automatic compilation setup unavailable")
        guide = await session.get(ProjectGuide, setup.guide_id)
        snapshot = await session.get(GuideSourceSnapshot, setup.source_snapshot_id)
        mutation = await session.scalar(
            select(GuideMutationIdempotencyRecord).where(
                GuideMutationIdempotencyRecord.setup_run_id == setup.id,
                GuideMutationIdempotencyRecord.action_id == "project.guide_source_snapshot.create",
                GuideMutationIdempotencyRecord.status == "committed",
            )
        )
        if (
            guide is None
            or snapshot is None
            or mutation is None
            or setup.authorization_decision_event_id is None
        ):
            raise GuideCompilationIntegrityError("automatic compilation source unavailable")
        origin = ProjectGuideCompilationRequestOrigin(
            trigger="automatic_source_ready",
            source_mutation_operation_id=mutation.operation_id,
            source_authorization_decision_event_id=UUID(setup.authorization_decision_event_id),
        )
        context = await self.context_for_setup(session, setup)
        identity = CompilationAttemptIdentity.from_context(context)
        selector_id = automatic_request_selector(setup_run_id, setup.setup_generation)
        operation_id = operation_id or selector_id
        predecessor = await GuideCompilationRepository(session).current_compilation(
            UUID(setup.project_id),
            UUID(setup.guide_id),
            lock=False,
        )
        facts = ProjectGuideCompilationRequestFacts(
            **identity.model_dump(),
            operation_id=operation_id,
            request_id=uuid5(selector_id, "request"),
            idempotency_key=uuid5(selector_id, "idempotency"),
            expected_predecessor_compilation_id=predecessor.id if predecessor else None,
        )
        await GuideCompilationRepository(session).require_automatic_request_origin(facts, origin)
        return facts, identity, origin

    async def context_for_setup(self, session: AsyncSession, setup: ProjectSetupRun):
        """Use one document/context builder for automatic and correction requests."""
        from .correction_feedback import load_correction_input

        if self.runtime_configuration is None:
            raise GuideCompilationIntegrityError("compilation runtime configuration unavailable")
        guide = await session.get(ProjectGuide, setup.guide_id)
        snapshot = await session.get(GuideSourceSnapshot, setup.source_snapshot_id)
        if guide is None or snapshot is None:
            raise GuideCompilationIntegrityError("compilation source unavailable")
        setup_run_id = UUID(setup.id)
        loaded = await self.material.load(
            GuideDocumentManifestRequest(
                project_id=UUID(setup.project_id),
                guide_id=UUID(setup.guide_id),
                guide_source_snapshot_id=UUID(setup.source_snapshot_id),
                project_setup_run_id=setup_run_id,
                setup_generation=setup.setup_generation,
            )
        )
        context = compilation_context_from_material(
            guide=guide,
            snapshot=snapshot,
            loaded=loaded,
            setup_run_id=setup_run_id,
            setup_generation=setup.setup_generation,
            runtime_configuration=self.runtime_configuration,
            correction_input=await load_correction_input(session, setup_run_id),
        )
        return context


def automatic_request_selector(setup_run_id: UUID, generation: int) -> UUID:
    """Bind non-row request replay to exactly one immutable setup generation."""
    return uuid5(
        NAMESPACE_URL, f"workstream.project.guide_compilation.automatic:{setup_run_id}:{generation}"
    )


def new_compilation_request_operation_id() -> UUID:
    """Mint one persisted request-operation identity under its setup owner lock."""
    return new_record_id()


async def select_model_runtime_configuration(
    configuration: ProjectGuideRuntimeConfiguration,
    profiles: ModelProfileReaderPort,
    project_id: UUID,
) -> ProjectGuideRuntimeConfiguration:
    """Bind automatic and human setup requests to one immutable project profile."""
    if not configuration.uses_inference:
        return configuration
    profile = await profiles.read_latest_matching(
        project_id=project_id,
        provider=configuration.model_provider,
        api=configuration.model_api,
        model_snapshot=configuration.model,
    )
    return configuration.model_copy(
        update={
            "model_profile_id": profile.profile_id,
            "model_profile_version": profile.spec.profile_version,
            "model_profile_digest": profile.profile_digest,
        }
    )
