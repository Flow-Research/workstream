"""Database-independent artifact scratch maintenance tasks."""

from __future__ import annotations

from app.adapters.artifacts import (
    cleanup_stale_artifact_scratch,
    require_artifact_runtime_eligible,
)
from app.core.config import get_settings
from app.workers.async_runner import run_async_task
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.workers.celery_app import (
    ARTIFACT_PUT_RESOLUTION_TASK,
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


def _deny_inactive_artifact_action() -> None:
    """Keep registered hidden mechanics unreachable before AUTH activation."""
    raise ArtifactAuthorityDeniedError("artifact internal action is unavailable")


@celery_app.task(name=ARTIFACT_PUT_RESOLUTION_TASK)
def resolve_put_attempt(attempt_id: str) -> None:
    """Registered contract only; AUTH activation later supplies composition."""
    del attempt_id
    _deny_inactive_artifact_action()


@celery_app.task(name=ARTIFACT_VERIFICATION_TASK)
def verify_object(job_id: str) -> None:
    """Registered contract only; AUTH activation later supplies composition."""
    del job_id
    _deny_inactive_artifact_action()
