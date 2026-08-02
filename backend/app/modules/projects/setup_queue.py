"""Queue boundary for automatic project setup jobs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.errors import CeleryConfigurationError
from app.workers.task_settings import sync_task_settings

logger = logging.getLogger(__name__)
DISPATCH_RETRY_AFTER_SECONDS = 60


def dispatch_stale_before() -> datetime:
    """Return the shared cutoff for reclaiming an abandoned dispatch claim."""
    return datetime.now(UTC) - timedelta(seconds=DISPATCH_RETRY_AFTER_SECONDS)


class ProjectSetupQueueError(RuntimeError):
    """Raised when Workstream cannot enqueue project setup automation."""


def enqueue_pre_submit_setup_pipeline(
    *,
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
    task_id: str | None = None,
) -> str:
    """Enqueue the Celery project setup pipeline.

    Args:
        project_id: Project that owns the guide.
        guide_id: Guide whose source snapshot should be processed.
        source_snapshot_id: Immutable source snapshot to analyze.
        setup_run_id: Project setup run ledger row to update from the worker.
        setup_generation: Exact setup generation to fence the continuation.

    Returns:
        Celery task id.

    Raises:
        ProjectSetupQueueError: If the broker cannot accept the job.
    """
    try:
        from app.workers.project_setup import run_pre_submit_setup_pipeline

        sync_task_settings(run_pre_submit_setup_pipeline)
        result = run_pre_submit_setup_pipeline.apply_async(
            args=(project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation),
            task_id=task_id,
        )
    except (CeleryConfigurationError, CeleryError, KombuError, OSError) as exc:
        raise ProjectSetupQueueError("project setup pipeline could not be enqueued") from exc
    return result.id


async def dispatch_pre_submit_setup_pipeline_after_commit(
    session: AsyncSession,
    *,
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
    verification_job_id: str | None = None,
) -> str | None:
    """Dispatch one committed setup intent and record its bounded outcome."""
    from app.modules.projects.repository import ProjectRepository

    repository = ProjectRepository(session)
    setup_run = await repository.lock_project_setup_run(setup_run_id)
    if setup_run is None:
        return None
    if setup_run.status == "dispatch_pending" and setup_run.celery_task_id is not None:
        if setup_run.updated_at > dispatch_stale_before():
            return setup_run.celery_task_id
        deterministic_task_id = setup_run.celery_task_id
        setup_run.updated_at = datetime.now(UTC)
    elif setup_run.status in {"queued", "enqueue_failed"}:
        deterministic_task_id = f"guide-setup-{setup_run_id}-g{setup_generation}"
        setup_run.status = "dispatch_pending"
        setup_run.current_step = "dispatch"
        setup_run.celery_task_id = deterministic_task_id
    elif setup_run.celery_task_id is not None:
        return setup_run.celery_task_id
    else:
        return None
    if setup_run.continuation_verification_job_id is None and verification_job_id is not None:
        setup_run.continuation_verification_job_id = verification_job_id
        setup_run.continuation_started_at = datetime.now(UTC)
    setup_run.error_code = None
    setup_run.error_summary = None
    await session.commit()
    try:
        task_id = await asyncio.to_thread(
            enqueue_pre_submit_setup_pipeline,
            project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            setup_run_id=setup_run_id,
            setup_generation=setup_generation,
            task_id=deterministic_task_id,
        )
    except ProjectSetupQueueError as exc:
        logger.warning(
            "project setup pipeline enqueue failed after commit",
            extra={
                "project_id": project_id,
                "guide_id": guide_id,
                "source_snapshot_id": source_snapshot_id,
                "setup_run_id": setup_run_id,
                "error_code": exc.__class__.__name__,
                "error_summary": "project setup failed",
            },
        )
        setup_run = await repository.lock_project_setup_run(setup_run_id)
        if setup_run is not None and setup_run.status == "dispatch_pending":
            setup_run.status = "enqueue_failed"
            setup_run.current_step = "enqueue"
            setup_run.celery_task_id = None
            setup_run.error_code = exc.__class__.__name__
            setup_run.error_summary = "project setup failed"
        await session.commit()
        return None
    setup_run = await repository.lock_project_setup_run(setup_run_id)
    if setup_run is not None and setup_run.status == "dispatch_pending":
        setup_run.status = "queued"
        setup_run.current_step = "queued"
        setup_run.celery_task_id = task_id
    await session.commit()
    return task_id


def enqueue_post_submit_setup_continuation(
    *,
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    effective_policy_id: str,
    pre_submit_checker_policy_id: str,
) -> str:
    """Enqueue the post-submit continuation for a project setup run.

    Args:
        project_id: Project that owns the guide.
        guide_id: Guide whose source snapshot should be processed.
        source_snapshot_id: Immutable source snapshot to analyze.
        setup_run_id: Existing setup-run ledger row to resume.
        effective_policy_id: Effective submission artifact policy produced by approval.
        pre_submit_checker_policy_id: Compiled pre-submit checker policy id.

    Returns:
        Celery task id.

    Raises:
        ProjectSetupQueueError: If the broker cannot accept the job.
    """
    try:
        from app.workers.project_setup import run_post_submit_setup_continuation

        sync_task_settings(run_post_submit_setup_continuation)
        result = run_post_submit_setup_continuation.apply_async(
            args=(
                project_id,
                guide_id,
                source_snapshot_id,
                setup_run_id,
                effective_policy_id,
                pre_submit_checker_policy_id,
            )
        )
    except (CeleryConfigurationError, CeleryError, KombuError, OSError) as exc:
        raise ProjectSetupQueueError("project setup continuation could not be enqueued") from exc
    return result.id
