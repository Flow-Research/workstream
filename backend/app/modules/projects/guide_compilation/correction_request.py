"""Admit a correction successor through the existing human request operation."""

from dataclasses import replace
from uuid import UUID, uuid5
from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.authorization.api import ProjectGuideCompilationRequestFacts
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.models import ProjectGuide, ProjectSetupRun

from .contracts import CompilationAttemptIdentity
from .correction_feedback import correction_feedback
from .models import ProjectGuideProposalCorrection
from .repository import GuideCompilationIntegrityError, GuideCompilationRepository
from .request_inputs import new_compilation_request_operation_id


def correction_request_selector(correction_id: UUID) -> UUID:
    """One non-row replay selector regardless of delivery or transport retries."""
    return uuid5(correction_id, "compilation-request")


async def correction_request_inputs(
    session, inputs, correction_id: UUID, *, operation_id: UUID | None = None
):
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
    selector_id = correction_request_selector(correction_id)
    operation_id = operation_id or selector_id
    return ProjectGuideCompilationRequestFacts(
        **identity.model_dump(),
        operation_id=operation_id,
        request_id=uuid5(selector_id, "request"),
        idempotency_key=uuid5(selector_id, "idempotency"),
        expected_predecessor_compilation_id=correction.compilation_id,
    ), identity


async def admit_correction_request(session, inputs, *, actor, facts, identity, operation_id=None):
    """Transition only the exact committed successor inside request reservation."""
    correction = await session.scalar(
        select(ProjectGuideProposalCorrection).where(
            ProjectGuideProposalCorrection.successor_setup_run_id == str(facts.setup_run_id),
        )
    )
    if correction is None:
        if inputs is None:
            raise GuideCompilationIntegrityError("compilation inputs unavailable")
        setup = await session.get(ProjectSetupRun, str(facts.setup_run_id))
        if setup is None or facts.expected_predecessor_compilation_id is not None:
            raise GuideCompilationIntegrityError("compilation request authority mismatch")
        # The manifest owner acquires guide/snapshot/setup and original metadata locks.
        context = await inputs.context_for_setup(session, setup)
        if CompilationAttemptIdentity.from_context(context) != identity:
            raise GuideCompilationIntegrityError("compilation request input mismatch")
        natural = await GuideCompilationRepository(session).request_operation_for_setup(
            facts.setup_run_id, facts.setup_generation, "project_manager", lock=True,
        )
        if natural is not None:
            return setup, None, natural
        if setup.status != "awaiting_documents" or setup.current_step != "awaiting_documents":
            raise GuideCompilationIntegrityError("compilation setup is not awaiting a request")
        setup.status, setup.current_step = "dispatch_pending", "dispatch"
        setup.celery_task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
        if setup.documents_ready_at is None:
            setup.documents_ready_at = datetime.now(UTC)
        return setup, replace(facts, operation_id=operation_id or new_compilation_request_operation_id()), None
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
    if setup is None:
        raise GuideCompilationIntegrityError("correction request successor unavailable")
    natural = await GuideCompilationRepository(session).request_operation_for_setup(
        UUID(setup.id), setup.setup_generation, "project_manager", lock=True
    )
    if natural is not None:
        return setup, None, natural
    resolved = await correction_request_inputs(
        session,
        inputs,
        correction.operation_id,
        operation_id=operation_id or new_compilation_request_operation_id(),
    )
    if (
        resolved[0].request_id != facts.request_id
        or resolved[0].idempotency_key != facts.idempotency_key
        or resolved[1] != identity
        or setup.current_step != "correction_requested"
    ):
        raise GuideCompilationIntegrityError("correction request input mismatch")
    setup.status = "queued"
    setup.current_step = "queued"
    setup.celery_task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
    await session.flush()
    return setup, resolved[0], None
