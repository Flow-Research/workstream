"""Reconstruct one exact provider context from canonical owned facts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifact_operations import (
    GuideSufficiencyMaterialPort,
    GuideSufficiencyMaterialRequest,
)
from app.interfaces.project_agents import (
    MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES,
    PROJECT_GUIDE_COMPILATION_AGENT_IDENTITY,
    PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
    PROJECT_GUIDE_COMPILATION_INSTRUCTION_VERSION,
    PostSubmissionCapabilityProjection,
    PreSubmissionCapabilityProjection,
    ProjectGuideCompilationContext,
    VerifiedGuideMaterialSnapshot,
    canonical_project_guide_compilation_context_bytes,
)
from app.modules.projects.models import GuideSourceSnapshot, ProjectGuide
from app.modules.projects.service import build_verified_guide_sufficiency_material

from .contracts import CompilationAttemptIdentity, CompilationExecutionState
from .repository import GuideCompilationIntegrityError


async def build_project_guide_compilation_context(
    session: AsyncSession,
    *,
    state: CompilationExecutionState,
    material: GuideSufficiencyMaterialPort,
    pre_submission_capabilities: PreSubmissionCapabilityProjection,
    post_submission_capabilities: PostSubmissionCapabilityProjection,
) -> ProjectGuideCompilationContext:
    """Return an immutable context only when every current fact matches custody."""
    if session.in_transaction():
        raise GuideCompilationIntegrityError(
            "guide compilation context requires a fresh root transaction"
        )
    identity = state.identity
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
            GuideSufficiencyMaterialRequest(
                project_id=identity.project_id,
                guide_id=identity.guide_id,
                guide_source_snapshot_id=identity.source_snapshot_id,
                project_setup_run_id=identity.setup_run_id,
                setup_generation=identity.setup_generation,
            )
        )
        verified = VerifiedGuideMaterialSnapshot.from_material(
            build_verified_guide_sufficiency_material(guide, snapshot, loaded.source_items)
        )
        context = ProjectGuideCompilationContext(
            material=verified,
            setup_run_id=identity.setup_run_id,
            setup_generation=identity.setup_generation,
            instruction_version=PROJECT_GUIDE_COMPILATION_INSTRUCTION_VERSION,
            agent_identity=PROJECT_GUIDE_COMPILATION_AGENT_IDENTITY,
            agent_version=PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
            pre_submission_capabilities=pre_submission_capabilities,
            post_submission_capabilities=post_submission_capabilities,
        )
        if (
            len(canonical_project_guide_compilation_context_bytes(context))
            > MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES
        ):
            raise GuideCompilationIntegrityError("compilation context exceeds its limit")
        if CompilationAttemptIdentity.from_context(context) != identity:
            raise GuideCompilationIntegrityError("compilation context identity mismatch")
        return context
