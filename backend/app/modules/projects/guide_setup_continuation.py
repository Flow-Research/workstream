"""Recovery publication for already authorized explicit guide compilation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, func, select
from sqlalchemy.sql.elements import ColumnElement
from app.interfaces.project_guide_runtime import NO_INFERENCE_IDENTITY
from .guide_compilation.models import ProjectGuideCompilationAttempt, ProjectGuideSetupFinalization, ProjectGuideCompilationRequestOperation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest, GuideDocumentUnavailable
from app.modules.projects.models import ProjectSetupRun


DISPATCH_RETRY_AFTER_SECONDS = 60


def dispatch_stale_before() -> datetime:
    """Return the shared cutoff for reclaiming an abandoned dispatch claim."""
    return datetime.now(UTC) - timedelta(seconds=DISPATCH_RETRY_AFTER_SECONDS)


def retryable_compilation_dispatch_predicate() -> ColumnElement[bool]:
    """Reclaim stale exact deliveries without reviving terminal provider custody."""
    recoverable = (
        ~select(ProjectGuideCompilationAttempt.id)
        .where(
            ProjectGuideCompilationAttempt.setup_run_id == ProjectSetupRun.id,
            ProjectGuideCompilationAttempt.setup_generation == ProjectSetupRun.setup_generation,
            or_(
                ProjectGuideCompilationAttempt.runtime_configuration.is_(None),
                ProjectGuideCompilationAttempt.status == "compilation_invalid_terminal",
                # A no-inference fence guards no model call; recovery reopens it.
                and_(
                    ProjectGuideCompilationAttempt.status == "compilation_provider_uncertain",
                    ProjectGuideCompilationAttempt.runtime_configuration["model_provider"]
                    .as_string()
                    .is_distinct_from(NO_INFERENCE_IDENTITY),
                ),
            ),
        )
        .exists()
    )
    unfinished = (
        ~select(ProjectGuideSetupFinalization.id)
        .where(
            ProjectGuideSetupFinalization.setup_run_id == ProjectSetupRun.id,
            ProjectGuideSetupFinalization.setup_generation == ProjectSetupRun.setup_generation,
        )
        .exists()
    )
    return and_(
        select(ProjectGuideCompilationRequestOperation.operation_id).where(
            ProjectGuideCompilationRequestOperation.setup_run_id == ProjectSetupRun.id,
            ProjectGuideCompilationRequestOperation.setup_generation == ProjectSetupRun.setup_generation,
            ProjectGuideCompilationRequestOperation.request_trigger == "project_manager",
        ).exists(),
        recoverable,
        unfinished,
        or_(
            and_(
                ProjectSetupRun.status == "queued",
                ProjectSetupRun.current_step == "queued",
                ProjectSetupRun.celery_task_id.is_not(None),
                ProjectSetupRun.updated_at <= dispatch_stale_before(),
            ),
            and_(
                ProjectSetupRun.status == "dispatch_pending",
                ProjectSetupRun.updated_at <= dispatch_stale_before(),
            ),
            and_(
                ProjectSetupRun.status.in_(("queued", "enqueue_failed")),
                ProjectSetupRun.celery_task_id.is_(None),
            ),
        ),
    )


async def continue_setup_after_stored_guide_item(
    source_snapshot_id: UUID, *, session_factory: async_sessionmaker[AsyncSession], manifest_factory,
) -> None:
    """Recover an explicit request after all exact originals remain available."""
    async with session_factory() as session:
        run = await session.scalar(select(ProjectSetupRun).where(
            ProjectSetupRun.source_snapshot_id == str(source_snapshot_id),
            retryable_compilation_dispatch_predicate(),
        ).order_by(ProjectSetupRun.setup_generation.desc()).limit(1))
        if run is None:
            return
        run_id, project_id, guide_id, generation = run.id, run.project_id, run.guide_id, run.setup_generation
    claimed_task_id = None
    async with session_factory() as session, session.begin():
        try:
            await manifest_factory(session).load(GuideDocumentManifestRequest(
                project_id=UUID(project_id), guide_id=UUID(guide_id),
                guide_source_snapshot_id=source_snapshot_id,
                project_setup_run_id=UUID(run_id), setup_generation=generation,
            ))
        except GuideDocumentUnavailable:
            return
        # The manifest owner already holds guide -> snapshot -> run locks.
        run = await session.get(ProjectSetupRun, run_id)
        latest = await session.scalar(select(func.max(ProjectSetupRun.setup_generation))
                                      .where(ProjectSetupRun.guide_id == guide_id))
        if run is None or run.setup_generation != latest:
            return
    from app.modules.projects.setup_queue import dispatch_project_guide_compilation_after_commit
    async with session_factory() as session:
        await dispatch_project_guide_compilation_after_commit(
            session, project_id=project_id, guide_id=guide_id,
            source_snapshot_id=str(source_snapshot_id), setup_run_id=run_id,
            setup_generation=generation, claimed_task_id=claimed_task_id,
        )
