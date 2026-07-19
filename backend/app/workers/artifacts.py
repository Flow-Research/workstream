"""Database-independent artifact scratch maintenance tasks."""

from __future__ import annotations

from app.adapters.artifacts import (
    cleanup_stale_artifact_scratch,
    require_artifact_runtime_eligible,
)
from app.core.config import get_settings
from app.workers.async_runner import run_async_task
from app.workers.celery_app import ARTIFACT_SCRATCH_CLEANUP_TASK, celery_app


@celery_app.task(name=ARTIFACT_SCRATCH_CLEANUP_TASK)
def cleanup_stale_scratch() -> int:
    """Remove only expired scratch reservations for enabled artifact storage."""
    settings = get_settings()
    if settings.artifact_store_backend == "disabled":
        return 0
    require_artifact_runtime_eligible(settings)
    return run_async_task(lambda: cleanup_stale_artifact_scratch(settings))
