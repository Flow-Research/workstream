"""Celery application configuration for Workstream workers."""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.adapters.artifacts import require_artifact_runtime_eligible
from app.adapters.artifacts.internal_workers import (
    initialize_artifact_internal_runtime,
    shutdown_artifact_internal_runtime,
)
from app.core.config import get_settings
from app.workers.async_runner import run_async_task
from app.workers.errors import CeleryConfigurationError

ARTIFACT_SCRATCH_CLEANUP_TASK = "workstream.artifacts.cleanup_stale_scratch"
ARTIFACT_SCRATCH_CLEANUP_SCHEDULE = "artifact-scratch-cleanup"
ARTIFACT_PUT_RESOLUTION_TASK = "workstream.artifacts.resolve_put_attempt"
ARTIFACT_VERIFICATION_TASK = "workstream.artifacts.verify_object"
ARTIFACT_PENDING_WORK_SCAN_TASK = "workstream.artifacts.scan_pending_work"
ARTIFACT_PENDING_WORK_SCAN_SCHEDULE = "artifact-pending-work-scan"


@worker_process_init.connect
def initialize_artifact_runtime_for_process(**_kwargs: object) -> None:
    """Claim and initialize the artifact provider once per Celery child."""
    run_async_task(initialize_artifact_internal_runtime)


@worker_process_shutdown.connect
def shutdown_artifact_runtime_for_process(**_kwargs: object) -> None:
    """Close the artifact provider after the Celery child drains tasks."""
    shutdown_artifact_internal_runtime()


def create_celery_app() -> Celery:
    """Create the Celery application from Workstream settings.

    Returns:
        Configured Celery application for durable background jobs.
    """
    settings = get_settings()
    require_artifact_runtime_eligible(settings)
    broker_url = settings.celery_broker_url
    if broker_url is None:
        if settings.celery_task_always_eager:
            broker_url = "memory://"
        else:
            raise CeleryConfigurationError(
                "WORKSTREAM_CELERY_BROKER_URL must be set for Celery workers"
            )
    celery_app = Celery(
        "workstream",
        broker=broker_url,
        backend=settings.celery_result_backend_url,
        include=[
            "app.workers.artifacts",
            "app.workers.checkers",
            "app.workers.project_setup",
        ],
    )
    celery_app.conf.update(
        accept_content=["json"],
        result_serializer="json",
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=True,
        task_ignore_result=True,
        task_serializer="json",
        timezone="UTC",
        beat_schedule={
            ARTIFACT_SCRATCH_CLEANUP_SCHEDULE: {
                "task": ARTIFACT_SCRATCH_CLEANUP_TASK,
                "schedule": settings.artifact_scratch_cleanup_interval_seconds,
            },
            ARTIFACT_PENDING_WORK_SCAN_SCHEDULE: {
                "task": ARTIFACT_PENDING_WORK_SCAN_TASK,
                "schedule": settings.artifact_pending_work_scan_interval_seconds,
            },
        },
    )
    return celery_app


celery_app = create_celery_app()
