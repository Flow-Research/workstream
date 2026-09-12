"""Reconstruct one exact provider context from canonical owned facts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.modules.projects.api.guide_documents import (
    GuideDocumentManifestPort,
    GuideDocumentManifestRequest,
)
from app.interfaces.project_agents import (
    MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES,
    PROJECT_GUIDE_COMPILATION_AGENT_IDENTITY,
    PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
    ProjectGuideCompilationContext,
    canonical_project_guide_compilation_context_bytes,
)
from app.modules.checkers.api.pre_submit_catalogue import (
    PreSubmissionCapabilityProjection,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitCatalogue,
)
from app.modules.projects.models import GuideSourceSnapshot, ProjectGuide
from app.modules.projects.api.task_examples import require_task_example_commitment

from .contracts import CompilationAttemptIdentity, CompilationExecutionState
from .repository import GuideCompilationIntegrityError
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration


async def build_project_guide_compilation_context(
    session: AsyncSession,
    *,
    state: CompilationExecutionState,
    material: GuideDocumentManifestPort,
    pre_submission_capabilities: PreSubmissionCapabilityProjection,
    post_submission_capabilities: PostSubmitCatalogue,
) -> ProjectGuideCompilationContext:
    """Return an immutable context only when every current fact matches custody."""
    if session.in_transaction():
        raise GuideCompilationIntegrityError(
            "guide compilation context requires a fresh root transaction"
        )
    identity = state.identity
    if state.runtime_configuration is None:
        raise GuideCompilationIntegrityError("compilation runtime configuration is unavailable")
    async with session.begin():
        guide = await session.scalar(
            select(ProjectGuide).where(
                ProjectGuide.id == str(identity.guide_id),
                ProjectGuide.project_id == str(identity.project_id),
                ProjectGuide.version == identity.guide_version,
                ProjectGuide.status == "draft",
            )
        )
        snapshot = await session.scalar(
            select(GuideSourceSnapshot).where(
                GuideSourceSnapshot.id == str(identity.source_snapshot_id),
                GuideSourceSnapshot.project_id == str(identity.project_id),
                GuideSourceSnapshot.guide_id == str(identity.guide_id),
                GuideSourceSnapshot.guide_version == identity.guide_version,
                GuideSourceSnapshot.bundle_hash == identity.source_snapshot_hash,
            )
        )
        if guide is None or snapshot is None:
            raise GuideCompilationIntegrityError("compilation context lineage is unavailable")
        loaded = await material.load(
            GuideDocumentManifestRequest(
                project_id=identity.project_id,
                guide_id=identity.guide_id,
                guide_source_snapshot_id=identity.source_snapshot_id,
                project_setup_run_id=identity.setup_run_id,
                setup_generation=identity.setup_generation,
            )
        )
        context = compilation_context_from_material(
            guide=guide,
            snapshot=snapshot,
            loaded=loaded,
            setup_run_id=identity.setup_run_id,
            setup_generation=identity.setup_generation,
            pre_submission_capabilities=pre_submission_capabilities,
            post_submission_capabilities=post_submission_capabilities,
            runtime_configuration=state.runtime_configuration,
            correction_feedback=await _correction_feedback(session, identity.setup_run_id),
        )
        if CompilationAttemptIdentity.from_context(context) != identity:
            raise GuideCompilationIntegrityError("compilation context identity mismatch")
        return context


def compilation_context_from_material(
    *,
    guide,
    snapshot,
    loaded,
    setup_run_id,
    setup_generation,
    pre_submission_capabilities: PreSubmissionCapabilityProjection,
    post_submission_capabilities: PostSubmitCatalogue,
    runtime_configuration: ProjectGuideRuntimeConfiguration,
    correction_feedback=None,
) -> ProjectGuideCompilationContext:
    """Build the one bounded context used by both request and execution."""
    if (
        str(loaded.project_id) != guide.project_id
        or str(loaded.guide_id) != guide.id
        or loaded.guide_version != guide.version
        or str(loaded.source_snapshot_id) != snapshot.id
        or loaded.source_snapshot_hash != snapshot.bundle_hash
        or loaded.setup_run_id != setup_run_id
        or loaded.setup_generation != setup_generation
    ):
        raise GuideCompilationIntegrityError("compilation manifest lineage mismatch")
    try:
        examples = require_task_example_commitment(
            guide.task_examples,
            guide.task_examples_hash,
            manifest=snapshot.manifest_json,
        )
    except ValueError:
        raise GuideCompilationIntegrityError("guide task examples are unavailable") from None
    context = ProjectGuideCompilationContext(
        correction_feedback=correction_feedback,
        task_examples=examples,
        material=loaded,
        setup_run_id=setup_run_id,
        setup_generation=setup_generation,
        instruction_version=runtime_configuration.instruction_version,
        agent_identity=PROJECT_GUIDE_COMPILATION_AGENT_IDENTITY,
        agent_version=PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
        runtime_configuration=runtime_configuration,
        pre_submission_capabilities=pre_submission_capabilities,
        post_submission_capabilities=post_submission_capabilities,
    )
    if (
        len(canonical_project_guide_compilation_context_bytes(context))
        > MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES
    ):
        raise GuideCompilationIntegrityError("compilation context exceeds its limit")
    return context


async def _correction_feedback(session, setup_run_id):
    """Load downstream feedback without a context/repository import cycle."""
    from .correction_feedback import load_correction_feedback

    return await load_correction_feedback(session, setup_run_id)
