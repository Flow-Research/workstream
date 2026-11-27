"""Scheduled sealed-source reclamation through the existing ART custody owner."""
from app.adapters.artifacts.source_cleanup_worker import run_source_cleanup_sweep
from app.modules.artifacts.api.submission_cleanup import SUBMISSION_SOURCE_CLEANUP_HARD_LIMIT_SECONDS
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app
from app.workers.source_cleanup_topology import SOURCE_CLEANUP_TASK, require_source_cleanup_worker


@celery_app.task(name=SOURCE_CLEANUP_TASK, bind=True, acks_late=True,
                 reject_on_worker_lost=True, acks_on_failure_or_timeout=True,
                 time_limit=SUBMISSION_SOURCE_CLEANUP_HARD_LIMIT_SECONDS)
def sweep_submission_sources(self):
    """Broker redelivery rechecks current authority and durable deletion claims."""
    require_source_cleanup_worker(self)
    return run_async_task(run_source_cleanup_sweep)
