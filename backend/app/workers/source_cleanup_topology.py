"""Keep deletion credentials and bounded reclamation on a dedicated worker."""
import os

from celery import Task
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
_selected_queue_parent = None
_selected_queue = None


@worker_init.connect
def validate_workstream_queue_selection(sender, **_kwargs):
    """Require one declared queue for every Workstream application worker."""
    global _selected_queue_parent, _selected_queue
    from app.workers.project_setup_topology import PROJECT_GUIDE_CONSUMER_MARKER

    if getattr(sender.app.conf, PROJECT_GUIDE_CONSUMER_MARKER, False) is not True:
        return
    _selected_queue_parent = None
    _selected_queue = None
    queues = set(sender.app.amqp.queues.consume_from)
    declared = {queue.name for queue in sender.app.conf.task_queues}
    if len(queues) != 1 or not queues <= declared:
        raise WorkerShutdown("Workstream workers require one declared queue")
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if pool is not TaskPool or sender.app.conf.task_always_eager:
        raise WorkerShutdown("Workstream workers require non-eager prefork delivery")
    _selected_queue = next(iter(queues))
    _selected_queue_parent = os.getpid()


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


class WorkerTaskBoundary(Task):
    """Reject foreign task names on each dedicated worker before owner I/O."""

    def before_start(self, task_id, args, kwargs):
        if is_source_cleanup_worker_process() and self.name != SOURCE_CLEANUP_TASK:
            raise RuntimeError("dedicated source cleanup worker rejects foreign tasks")
        if _selected_queue_parent is not None and os.getppid() == _selected_queue_parent:
            from app.workers.celery_app import WORKSTREAM_TASK_ROUTES

            route = WORKSTREAM_TASK_ROUTES.get(self.name)
            expected = route.get("queue") if isinstance(route, dict) else None
            received = self.request.delivery_info.get("routing_key")
            if expected != _selected_queue or received != _selected_queue:
                raise RuntimeError("dedicated worker rejects a foreign task")
        return super().before_start(task_id, args, kwargs)
