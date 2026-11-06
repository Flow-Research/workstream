"""Bind worker admission to the existing immutable request's trigger."""

from uuid import uuid5

from sqlalchemy import select

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryError

from .correction_request import correction_request_selector
from .models import ProjectGuideCompilationRequestOperation, ProjectGuideProposalCorrection


async def manual_delivery_attempt(session, setup, attempt):
    """Require an exact committed PM request before any worker execution."""
    correction = (await session.execute(
        select(ProjectGuideProposalCorrection).where(
            ProjectGuideProposalCorrection.successor_setup_run_id == setup.id,
        )
    )).scalar_one_or_none()
    if attempt is None:
        raise ProjectGuideCompilationDeliveryError()
    operations = (await session.scalars(
        select(ProjectGuideCompilationRequestOperation).where(
            ProjectGuideCompilationRequestOperation.attempt_id == attempt.id,
        )
    )).all()
    if len(operations) != 1:
        raise ProjectGuideCompilationDeliveryError()
    operation = operations[0]
    if any(getattr(operation, name) != getattr(attempt, name) for name in (
        "project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation",
    )) or any(getattr(attempt, name) != getattr(setup, name) for name in (
        "project_id", "guide_id", "source_snapshot_id", "setup_generation",
    )) or attempt.setup_run_id != setup.id:
        raise ProjectGuideCompilationDeliveryError()
    if (operation.request_trigger != "project_manager" or operation.operation_id.version != 7
            or operation.source_mutation_operation_id is not None
            or operation.source_authorization_decision_event_id is not None
            or attempt.runtime_configuration is None):
        raise ProjectGuideCompilationDeliveryError()
    if correction is None:
        if (operation.expected_predecessor_compilation_id is not None
                or operation.request_id != uuid5(operation.idempotency_key, "guide-compilation-request")):
            raise ProjectGuideCompilationDeliveryError()
        return attempt.id
    if (
        operation.request_trigger != "project_manager"
        or correction is None
        or correction.project_id != setup.project_id
        or correction.guide_id != setup.guide_id
        or correction.successor_setup_generation != setup.setup_generation
        or correction.target_json["source_snapshot_id"] != setup.source_snapshot_id
        or operation.operation_id.version != 7
        or operation.request_id
        != uuid5(correction_request_selector(correction.operation_id), "request")
        or operation.idempotency_key
        != uuid5(correction_request_selector(correction.operation_id), "idempotency")
        or operation.expected_predecessor_compilation_id != correction.compilation_id
        or operation.source_mutation_operation_id is not None
        or operation.source_authorization_decision_event_id is not None
        or attempt.runtime_configuration is None
    ):
        raise ProjectGuideCompilationDeliveryError()
    return attempt.id
