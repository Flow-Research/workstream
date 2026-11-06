"""Resolve canonical setup input from owned lineage and verified ART material."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


from app.modules.projects.api.guide_documents import (
    GuideDocumentManifestPort,
    GuideDocumentManifestRequest,
)
from app.modules.projects.models import (
    GuideSourceSnapshot,
    ProjectGuide,
    ProjectSetupRun,
)

from .context import compilation_context_from_material
from .repository import GuideCompilationIntegrityError
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import ModelProfileReaderPort


@dataclass(frozen=True)
class CompilationRequestInputs:
    """Composition supplies material access and a trusted setup runtime."""

    material: GuideDocumentManifestPort
    runtime_configuration: ProjectGuideRuntimeConfiguration | None

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
