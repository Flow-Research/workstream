"""Artifact scratch maintenance and fixed-service execution tasks."""

from __future__ import annotations

from uuid import UUID

from app.adapters.artifacts import (
    cleanup_stale_artifact_scratch,
    require_artifact_runtime_eligible,
)
from app.core.config import get_settings
from app.workers.async_runner import run_async_task
from app.adapters.artifacts.internal_workers import (
    run_artifact_internal_operation,
    scan_artifact_pending_work,
)
from app.workers.celery_app import (
    ARTIFACT_PUT_RESOLUTION_TASK,
    ARTIFACT_PENDING_WORK_SCAN_TASK,
    ARTIFACT_SCRATCH_CLEANUP_TASK,
    ARTIFACT_VERIFICATION_TASK,
    celery_app,
)


@celery_app.task(name=ARTIFACT_SCRATCH_CLEANUP_TASK)
def cleanup_stale_scratch() -> int:
    """Remove only expired scratch reservations for enabled artifact storage."""
    settings = get_settings()
    if settings.artifact_store_backend == "disabled":
        return 0
    require_artifact_runtime_eligible(settings)
    return run_async_task(lambda: cleanup_stale_artifact_scratch(settings))


@celery_app.task(name=ARTIFACT_PUT_RESOLUTION_TASK)
def resolve_put_attempt(attempt_id: str) -> None:
    """Resolve one exact put attempt as the fixed resolver service."""
    run_async_task(lambda: run_artifact_internal_operation("put", UUID(attempt_id)))


@celery_app.task(name=ARTIFACT_VERIFICATION_TASK)
def verify_object(job_id: str) -> None:
    """Verify one exact object as the fixed verifier service."""
    run_async_task(lambda: run_artifact_internal_operation("verification", UUID(job_id)))


@celery_app.task(name=ARTIFACT_PENDING_WORK_SCAN_TASK)
def scan_pending_work() -> int:
    """Publish one authority-bound database-cutoff page of pending work."""
    async def publish_put_attempt(attempt_id: str) -> None:
        resolve_put_attempt.delay(attempt_id)

    async def publish_verification_job(job_id: str) -> None:
        verify_object.delay(job_id)

    return run_async_task(
        lambda: scan_artifact_pending_work(
            publish_put_attempt,
            publish_verification_job,
        )
    )
