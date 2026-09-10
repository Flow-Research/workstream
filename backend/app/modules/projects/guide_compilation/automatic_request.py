"""Resolve automatic request input from owned lineage and verified ART material."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.modules.projects.api.guide_documents import GuideDocumentManifestPort, GuideDocumentManifestRequest
from app.modules.checkers.api.pre_submit_catalogue import (
    PreSubmissionCapabilityProjection,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitCatalogue,
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


@dataclass(frozen=True)
class AutomaticCompilationInputs:
    """Composition supplies material access and canonical CHECKERS projections, never a runtime."""

    material: GuideDocumentManifestPort
    pre_submission_capabilities: PreSubmissionCapabilityProjection
    post_submission_capabilities: PostSubmitCatalogue
    runtime_configuration: ProjectGuideRuntimeConfiguration | None

    async def resolve(
        self,
        session: AsyncSession,
        setup_run_id: UUID,
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
        setup = await session.get(ProjectSetupRun, str(setup_run_id))
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
            pre_submission_capabilities=self.pre_submission_capabilities,
            post_submission_capabilities=self.post_submission_capabilities,
            runtime_configuration=self.runtime_configuration,
        )
        identity = CompilationAttemptIdentity.from_context(context)
        operation_id = automatic_operation_id(setup_run_id, setup.setup_generation)
        predecessor = await GuideCompilationRepository(session).current_compilation(
            UUID(setup.project_id),
            UUID(setup.guide_id),
            lock=False,
        )
        facts = ProjectGuideCompilationRequestFacts(
            **identity.model_dump(),
            operation_id=operation_id,
            request_id=uuid5(operation_id, "request"),
            idempotency_key=uuid5(operation_id, "idempotency"),
            expected_predecessor_compilation_id=predecessor.id if predecessor else None,
        )
        await GuideCompilationRepository(session).require_automatic_request_origin(facts, origin)
        return facts, identity, origin


def automatic_operation_id(setup_run_id: UUID, generation: int) -> UUID:
    """Bind callback replay identity to exactly one immutable setup generation."""
    return uuid5(
        NAMESPACE_URL, f"workstream.project.guide_compilation.automatic:{setup_run_id}:{generation}"
    )
