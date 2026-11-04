"""Reconstruct immutable correction input without granting execution authority."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    ProjectGuideCorrectionFeedback,
)
from app.modules.projects.api.guide_proposals import GuideProposalCorrection, GuideProposalTarget
from app.modules.projects.models import ProjectSetupRun

from .contracts import AcceptedCompilationResult
from .models import (
    ProjectGuideCompilation,
    ProjectGuideProposalCorrection,
    ProjectGuideSetupFinalization,
)
from .repository import GuideCompilationIntegrityError
from .retained_evidence import retained_target, verified_compilation_result


@dataclass(frozen=True)
class CompilationCorrectionInput:
    """Verified feedback and its exact immutable predecessor, without new authority."""

    feedback: ProjectGuideCorrectionFeedback
    predecessor: ProjectGuideCompilationResult


def correction_feedback(
    operation: ProjectGuideProposalCorrection,
) -> ProjectGuideCorrectionFeedback:
    """Validate the exact predecessor commitment and normalized manager input."""
    retained = "pre_catalogue_id" in operation.target_json
    target = (
        retained_target(operation.target_json)
        if retained
        else GuideProposalTarget.model_validate(operation.target_json)
    )
    request_json = (
        {
            "target": operation.target_json,
            "idempotency_key": str(operation.idempotency_key),
            "reason": operation.reason,
        }
        if retained
        else GuideProposalCorrection(
            target=target,
            idempotency_key=operation.idempotency_key,
            reason=operation.reason,
        ).model_dump(mode="json")
    )
    if (
        target.digest != operation.target_digest
        or target.compilation_id != operation.compilation_id
        or target.finalization_id != operation.finalization_id
        or str(target.project_id) != operation.project_id
        or str(target.guide_id) != operation.guide_id
        or target.setup_generation + 1 != operation.successor_setup_generation
        or canonical_json_hash(request_json) != operation.request_digest
    ):
        raise GuideCompilationIntegrityError("correction input custody mismatch")
    feedback = ProjectGuideCorrectionFeedback(
        operation_id=operation.operation_id,
        predecessor_compilation_id=operation.compilation_id,
        predecessor_result_hash=target.result_hash,
        target_digest=operation.target_digest,
        reason=operation.reason,
    )
    if canonical_json_hash(feedback.model_dump(mode="json")) != operation.feedback_hash:
        raise GuideCompilationIntegrityError("correction feedback hash mismatch")
    return feedback


async def load_correction_input(
    session: AsyncSession,
    setup_run_id: UUID,
) -> CompilationCorrectionInput | None:
    """Read the exact committed predecessor without acquiring new owner locks."""
    operation = await session.scalar(
        select(ProjectGuideProposalCorrection).where(
            ProjectGuideProposalCorrection.successor_setup_run_id == str(setup_run_id),
        )
    )
    if operation is None:
        return None
    feedback = correction_feedback(operation)
    target = (
        retained_target(operation.target_json)
        if "pre_catalogue_id" in operation.target_json
        else GuideProposalTarget.model_validate(operation.target_json)
    )
    successor = await session.get(ProjectSetupRun, str(setup_run_id))
    predecessor = await session.scalar(
        select(ProjectGuideCompilation).where(
            ProjectGuideCompilation.id == operation.compilation_id,
            ProjectGuideCompilation.project_id == operation.project_id,
            ProjectGuideCompilation.guide_id == operation.guide_id,
        )
    )
    if successor is None or predecessor is None:
        raise GuideCompilationIntegrityError("correction predecessor unavailable")
    finalization = await session.get(ProjectGuideSetupFinalization, target.finalization_id)
    if (
        finalization is None
        or finalization.compilation_id != predecessor.id
        or finalization.facts_digest != target.finalization_facts_digest
        or finalization.project_id != predecessor.project_id
        or finalization.guide_id != predecessor.guide_id
        or finalization.setup_run_id != predecessor.setup_run_id
        or finalization.setup_generation != predecessor.setup_generation
    ):
        raise GuideCompilationIntegrityError("correction predecessor finalization mismatch")
    for name in (
        "project_id",
        "guide_id",
        "source_snapshot_id",
        "guide_version",
        "source_snapshot_hash",
    ):
        if str(getattr(predecessor, name)) != str(getattr(target, name)) or (
            str(getattr(successor, name)) != str(getattr(target, name))
        ):
            raise GuideCompilationIntegrityError("correction predecessor lineage mismatch")
    if (
        predecessor.setup_run_id != str(target.setup_run_id)
        or predecessor.setup_generation != target.setup_generation
        or successor.setup_generation != target.setup_generation + 1
    ):
        raise GuideCompilationIntegrityError("correction predecessor generation mismatch")
    if predecessor.result_schema_version is None:
        # Old correction requests remain evidence. The retired provider result
        # cannot be replayed into the current correction execution contract.
        verified_compilation_result(predecessor)
        raise GuideCompilationIntegrityError("retained correction cannot execute")
    try:
        accepted = AcceptedCompilationResult(
            canonical_result=predecessor.canonical_result,
            result_hash=predecessor.result_hash,
            component_hashes=predecessor.component_hashes,
        )
    except ValueError:
        raise GuideCompilationIntegrityError("correction predecessor hash mismatch") from None
    if accepted.result_hash != target.result_hash or (
        accepted.component_hashes != target.component_hashes
    ):
        raise GuideCompilationIntegrityError("correction predecessor target mismatch")
    return CompilationCorrectionInput(
        feedback=feedback,
        predecessor=ProjectGuideCompilationResult.model_validate(accepted.canonical_result),
    )
