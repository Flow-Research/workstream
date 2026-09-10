"""Read-only setup diagnostics derived from durable compilation custody."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import GuideSourceSnapshot, ProjectGuide, ProjectSetupRun
from app.modules.projects.api.task_examples import GuideTaskExampleInputError, require_task_example_commitment
from app.modules.projects.schemas import ProjectSetupRunResponse
from .models import ProjectGuideCompilationAttempt, ProjectGuideSetupFinalization


async def compilation_setup_response(
    session: AsyncSession,
    setup: ProjectSetupRun,
) -> ProjectSetupRunResponse:
    """Overlay the current attempt outcome after the caller's diagnostic authorization."""
    response = ProjectSetupRunResponse.model_validate(setup)
    finalized = await session.scalar(
        select(ProjectGuideSetupFinalization.id).where(
            ProjectGuideSetupFinalization.setup_run_id == setup.id,
            ProjectGuideSetupFinalization.setup_generation == setup.setup_generation,
            ProjectGuideSetupFinalization.project_id == setup.project_id,
            ProjectGuideSetupFinalization.guide_id == setup.guide_id,
        )
    )
    if finalized is not None:
        return response
    attempt = await session.scalar(
        select(ProjectGuideCompilationAttempt).where(
            ProjectGuideCompilationAttempt.setup_run_id == setup.id,
            ProjectGuideCompilationAttempt.setup_generation == setup.setup_generation,
            ProjectGuideCompilationAttempt.project_id == setup.project_id,
            ProjectGuideCompilationAttempt.guide_id == setup.guide_id,
            ProjectGuideCompilationAttempt.guide_version == setup.guide_version,
            ProjectGuideCompilationAttempt.source_snapshot_id == setup.source_snapshot_id,
            ProjectGuideCompilationAttempt.source_snapshot_hash == setup.source_snapshot_hash,
        )
    )
    if attempt is None or attempt.status == "compilation_reserved":
        guide = await session.get(ProjectGuide, setup.guide_id)
        source = await session.get(GuideSourceSnapshot, setup.source_snapshot_id)
        if guide is not None and source is not None:
            try:
                require_task_example_commitment(
                    guide.task_examples, guide.task_examples_hash, manifest=source.manifest_json,
                )
            except GuideTaskExampleInputError as exc:
                response.status = "setup_input_invalid"
                response.current_step = "input_validation"
                response.error_code = exc.code
                response.error_summary = "Create a new guide version with at least one task example."
                return response
    if attempt is None:
        return response
    response.status = {
        "compilation_provider_uncertain": "provider_outcome_unresolved",
        "provider_result_accepted": "provider_result_accepted_not_persisted",
    }.get(attempt.status, attempt.status)
    response.current_step = "guide_compilation"
    response.started_at = attempt.provider_uncertain_at
    response.finished_at = None
    response.error_code = None
    response.error_summary = None
    if attempt.status == "compilation_invalid_terminal":
        response.error_code = attempt.failure_code
        response.error_summary = "Guide compilation returned an invalid result."
        response.finished_at = attempt.terminal_at
    elif attempt.status == "compilation_provider_uncertain":
        response.error_code = "provider_outcome_unresolved"
        response.error_summary = (
            "The provider outcome is unresolved; no further invocation is permitted."
        )
    return response
