"""Queue boundary for automatic project setup jobs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from app.modules.projects.api import setup_identity

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.projects.models import ProjectSetupRun

from app.workers.errors import CeleryConfigurationError
from app.workers.task_settings import sync_task_settings

from app.modules.projects.guide_setup_continuation import (
    dispatch_stale_before, retryable_compilation_dispatch_predicate,
)

logger = logging.getLogger(__name__)


class ProjectSetupQueueError(RuntimeError):
    """Raised when Workstream cannot enqueue project setup automation."""


def enqueue_project_guide_compilation(
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
        from app.workers.project_setup import run_project_guide_compilation

        sync_task_settings(run_project_guide_compilation)
        result = run_project_guide_compilation.apply_async(
            args=(project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation),
            task_id=task_id,
        )
    except (CeleryConfigurationError, CeleryError, KombuError, OSError) as exc:
        raise ProjectSetupQueueError("project setup pipeline could not be enqueued") from exc
    return result.id


async def dispatch_project_guide_compilation_after_commit(
    session: AsyncSession,
    *,
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
    claimed_task_id: str | None = None,
) -> str | None:
    """Dispatch one committed setup intent and record its bounded outcome."""
    from app.modules.projects.repository import ProjectRepository

    repository = ProjectRepository(session)
    expected_task_id = setup_identity.project_guide_compilation_task_id(
        setup_run_id, setup_generation
    )
    setup_run = await repository.lock_project_setup_run(setup_run_id)
    if setup_run is None:
        raise ProjectSetupQueueError("project setup run missing before dispatch")
    fresh_initial_claim = False
    if setup_run.status in {"dispatch_pending", "queued"} and setup_run.celery_task_id is not None:
        if setup_run.celery_task_id != expected_task_id:
            raise ProjectSetupQueueError("project setup task identity is stale before dispatch")
        if claimed_task_id is not None and claimed_task_id != setup_run.celery_task_id:
            raise ProjectSetupQueueError("project setup dispatch claim is stale")
        if (
            setup_run.status == "queued" or claimed_task_id is None
        ) and setup_run.updated_at > dispatch_stale_before():
            return setup_run.celery_task_id
        fresh_initial_claim = (
            setup_run.status == "dispatch_pending"
            and claimed_task_id is not None
            and setup_run.updated_at > dispatch_stale_before()
        )
        deterministic_task_id = setup_run.celery_task_id
    elif setup_run.status in {"queued", "enqueue_failed"}:
        deterministic_task_id = expected_task_id
    else:
        return setup_run.celery_task_id
    # Every recovery publication rechecks the shared rule under the setup lock.
    # Only the fresh explicit initial claim bypasses the stale-recovery cutoff.
    if not fresh_initial_claim:
        reclaimable = await session.scalar(
            select(ProjectSetupRun.id).where(
                ProjectSetupRun.id == setup_run.id, retryable_compilation_dispatch_predicate()
            )
        )
        if reclaimable is None:
            return setup_run.celery_task_id
    if setup_run.celery_task_id is not None:
        setup_run.updated_at = datetime.now(UTC)
    else:
        setup_run.status = "dispatch_pending"
        setup_run.current_step = "dispatch"
        setup_run.celery_task_id = deterministic_task_id
    setup_run.error_code = None
    setup_run.error_summary = None
    if deterministic_task_id != expected_task_id:
        raise ProjectSetupQueueError("project setup task identity is stale before dispatch")
    await session.commit()
    try:
        task_id = await asyncio.to_thread(
            enqueue_project_guide_compilation,
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
    if task_id != deterministic_task_id:
        logger.error(
            "project setup queue accepted the wrong task identity",
            extra={
                "project_id": project_id,
                "guide_id": guide_id,
                "source_snapshot_id": source_snapshot_id,
                "setup_run_id": setup_run_id,
                "error_code": "ProjectSetupTaskIdentityMismatch",
                "error_summary": "project setup delivery rejected",
            },
        )
        setup_run = await repository.lock_project_setup_run(setup_run_id)
        if setup_run is not None and setup_run.status == "dispatch_pending":
            setup_run.status = "enqueue_identity_mismatch"
            setup_run.current_step = "enqueue"
            setup_run.error_code = "ProjectSetupTaskIdentityMismatch"
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
