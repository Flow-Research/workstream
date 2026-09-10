"""Project-owned dispatch after all exact guide document uploads have committed."""

from __future__ import annotations

from datetime import UTC, datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, func, select
from sqlalchemy.sql.elements import ColumnElement
from .guide_compilation.models import ProjectGuideCompilationAttempt, ProjectGuideSetupFinalization
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest, GuideDocumentUnavailable
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
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
                ProjectGuideCompilationAttempt.status.in_(
                    ("compilation_invalid_terminal", "compilation_provider_uncertain")
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
        recoverable,
        unfinished,
        or_(
            ProjectSetupRun.status == "awaiting_documents",
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
    """Claim one current generation only after every assigned original is committed."""
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
        if run.status == "awaiting_documents":
            claimed_task_id = project_guide_compilation_task_id(run.id, run.setup_generation)
            run.status, run.current_step = "dispatch_pending", "dispatch"
            run.celery_task_id = claimed_task_id
            if run.documents_ready_at is None:
                run.documents_ready_at = datetime.now(timezone.utc)
    from app.modules.projects.setup_queue import dispatch_project_guide_compilation_after_commit
    async with session_factory() as session:
        await dispatch_project_guide_compilation_after_commit(
            session, project_id=project_id, guide_id=guide_id,
            source_snapshot_id=str(source_snapshot_id), setup_run_id=run_id,
            setup_generation=generation, claimed_task_id=claimed_task_id,
        )
