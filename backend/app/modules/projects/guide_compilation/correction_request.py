"""Admit a correction successor through the existing human request operation."""

from uuid import UUID, uuid5

from sqlalchemy import select

from app.modules.authorization.api import ProjectGuideCompilationRequestFacts
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.models import ProjectGuide, ProjectSetupRun

from .contracts import CompilationAttemptIdentity
from .correction_feedback import correction_feedback
from .models import ProjectGuideProposalCorrection
from .repository import GuideCompilationIntegrityError


def correction_request_operation_id(correction_id: UUID) -> UUID:
    """One request identity, regardless of delivery retries or transport requests."""
    return uuid5(correction_id, "compilation-request")


async def correction_request_inputs(session, inputs, correction_id: UUID):
    """Build canonical request facts without creating or invoking a provider."""
    correction = await session.get(ProjectGuideProposalCorrection, correction_id)
    if correction is None:
        raise GuideCompilationIntegrityError("correction operation unavailable")
    correction_feedback(correction)
    setup = await session.get(ProjectSetupRun, correction.successor_setup_run_id)
    if setup is None or setup.status != "correction_requested":
        raise GuideCompilationIntegrityError("correction request successor unavailable")
    context = await inputs.context_for_setup(session, setup)
    identity = CompilationAttemptIdentity.from_context(context)
    operation_id = correction_request_operation_id(correction_id)
    return ProjectGuideCompilationRequestFacts(
        **identity.model_dump(),
        operation_id=operation_id,
        request_id=uuid5(operation_id, "request"),
        idempotency_key=uuid5(operation_id, "idempotency"),
        expected_predecessor_compilation_id=correction.compilation_id,
    ), identity


async def admit_correction_request(session, inputs, *, actor, facts, identity) -> None:
    """Transition only the exact committed successor inside request reservation."""
    correction = await session.scalar(
        select(ProjectGuideProposalCorrection).where(
            ProjectGuideProposalCorrection.successor_setup_run_id == str(facts.setup_run_id),
        )
    )
    if correction is None:
        return
    if inputs is None:
        raise GuideCompilationIntegrityError("correction request authority mismatch")
    await session.scalar(
        select(ProjectGuide)
        .where(
            ProjectGuide.id == correction.guide_id,
        )
        .with_for_update()
    )
    setup = await session.scalar(
        select(ProjectSetupRun)
        .where(
            ProjectSetupRun.id == correction.successor_setup_run_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    resolved = await correction_request_inputs(session, inputs, correction.operation_id)
    if resolved != (facts, identity) or setup.current_step != "correction_requested":
        raise GuideCompilationIntegrityError("correction request input mismatch")
    setup.status = "queued"
    setup.current_step = "queued"
    setup.celery_task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
    await session.flush()
