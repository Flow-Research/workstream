"""Queue boundary for automatic project setup jobs."""

from __future__ import annotations

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError

from app.workers.errors import CeleryConfigurationError
from app.workers.task_settings import sync_task_settings


class ProjectSetupQueueError(RuntimeError):
    """Raised when Workstream cannot enqueue project setup automation."""


def enqueue_pre_submit_setup_pipeline(
    *,
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
) -> str:
    """Enqueue the Celery project setup pipeline.

    Args:
        project_id: Project that owns the guide.
        guide_id: Guide whose source snapshot should be processed.
        source_snapshot_id: Immutable source snapshot to analyze.
        setup_run_id: Project setup run ledger row to update from the worker.

    Returns:
        Celery task id.

    Raises:
        ProjectSetupQueueError: If the broker cannot accept the job.
    """
    try:
        from app.workers.project_setup import run_pre_submit_setup_pipeline

        sync_task_settings(run_pre_submit_setup_pipeline)
        result = run_pre_submit_setup_pipeline.apply_async(
            args=(project_id, guide_id, source_snapshot_id, setup_run_id)
        )
    except (CeleryConfigurationError, CeleryError, KombuError, OSError) as exc:
        raise ProjectSetupQueueError("project setup pipeline could not be enqueued") from exc
    return result.id


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
        raise ProjectSetupQueueError(
            "project setup continuation could not be enqueued"
        ) from exc
    return result.id
