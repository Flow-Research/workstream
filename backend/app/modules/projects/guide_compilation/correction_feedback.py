"""Reconstruct immutable correction input without granting execution authority."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import ProjectGuideCorrectionFeedback
from app.modules.projects.api.guide_proposals import GuideProposalCorrection, GuideProposalTarget

from .models import ProjectGuideProposalCorrection
from .repository import GuideCompilationIntegrityError


def correction_feedback(
    operation: ProjectGuideProposalCorrection,
) -> ProjectGuideCorrectionFeedback:
    """Validate the exact predecessor commitment and normalized manager input."""
    target = GuideProposalTarget.model_validate(operation.target_json)
    request = GuideProposalCorrection(
        target=target,
        idempotency_key=operation.idempotency_key,
        reason=operation.reason,
    )
    if (
        target.digest != operation.target_digest
        or target.compilation_id != operation.compilation_id
        or target.finalization_id != operation.finalization_id
        or str(target.project_id) != operation.project_id
        or str(target.guide_id) != operation.guide_id
        or target.setup_generation + 1 != operation.successor_setup_generation
        or request.reason != operation.reason
        or canonical_json_hash(request.model_dump(mode="json")) != operation.request_digest
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


async def load_correction_feedback(
    session: AsyncSession,
    setup_run_id: UUID,
) -> ProjectGuideCorrectionFeedback | None:
    """Return feedback only for the exact successor named by immutable custody."""
    operation = await session.scalar(
        select(ProjectGuideProposalCorrection).where(
            ProjectGuideProposalCorrection.successor_setup_run_id == str(setup_run_id),
        )
    )
    return correction_feedback(operation) if operation is not None else None
