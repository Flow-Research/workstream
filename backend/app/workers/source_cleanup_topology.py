"""Keep deletion credentials and bounded reclamation on a dedicated worker."""
import os

from celery.concurrency import get_implementation
from celery.concurrency.prefork import TaskPool
from celery.exceptions import WorkerShutdown
from celery.signals import worker_init

from app.adapters.artifacts.source_cleanup_worker import validate_source_cleanup_startup
from app.workers.async_runner import run_async_task
from app.core.config import get_settings
from app.modules.artifacts.api.submission_cleanup import (
    SUBMISSION_SOURCE_CLEANUP_HARD_LIMIT_SECONDS, SubmissionSourceCleanupProfile,
)

SOURCE_CLEANUP_QUEUE = "workstream.source_cleanup"
SOURCE_CLEANUP_TASK = "workstream.artifacts.sweep_submission_sources"
SOURCE_CLEANUP_SCHEDULE = "submission-source-cleanup"
_validated_parent = None


@worker_init.connect
def validate_source_cleanup_worker(sender, **_kwargs):
    """Reject mixed queues, eager execution and unsupported pools before startup."""
    global _validated_parent
    _validated_parent = None
    queues = set(sender.app.amqp.queues.consume_from)
    if SOURCE_CLEANUP_QUEUE not in queues:
        return
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if queues != {SOURCE_CLEANUP_QUEUE} or pool is not TaskPool or sender.app.conf.task_always_eager:
        raise WorkerShutdown("source cleanup requires an exclusive non-eager prefork worker")
    try:
        SubmissionSourceCleanupProfile.model_validate(get_settings().submission_source_cleanup_profile)
        # Run before forking: Celery gives child-init receivers only four seconds.
        # This validator disposes all of its DB/provider resources before return.
        run_async_task(validate_source_cleanup_startup)
    except Exception as error:
        raise WorkerShutdown("source cleanup startup validation failed") from error
    _validated_parent = os.getpid()


def is_source_cleanup_worker_process():
    return _validated_parent is not None and os.getppid() == _validated_parent


def require_source_cleanup_worker(task):
    """Reject direct invocation and broker attempts to replace the hard bound."""
    if (not is_source_cleanup_worker_process() or task.app.conf.task_always_eager
            or task.request.is_eager or task.request.called_directly):
        raise RuntimeError("source cleanup requires a validated prefork worker")
    message_limit = (task.request.timelimit or (None, None))[0]
    if (type(task.time_limit) is not int or task.time_limit != SUBMISSION_SOURCE_CLEANUP_HARD_LIMIT_SECONDS
            or message_limit is not None and (type(message_limit) is not int
                or message_limit != SUBMISSION_SOURCE_CLEANUP_HARD_LIMIT_SECONDS)):
        raise RuntimeError("source cleanup requires its bounded hard time limit")
