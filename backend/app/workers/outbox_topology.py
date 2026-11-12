"""Require a validated prefork worker for bounded OUTBOX effect delivery."""

import os

from celery.concurrency import get_implementation
from celery.concurrency.prefork import TaskPool
from celery.exceptions import WorkerShutdown
from celery.signals import worker_init
from app.modules.checkers.api.external_policy import SELECTED_POST_DELIVERY_LEASE_SECONDS
from app.modules.artifacts.api.submission_finalization import SUBMISSION_FINALIZATION_DELIVERY_LEASE_SECONDS

OUTBOX_PROCESS_SHUTDOWN_MARGIN_SECONDS = 60
OUTBOX_HARD_LIMIT_SECONDS = (
    SELECTED_POST_DELIVERY_LEASE_SECONDS + OUTBOX_PROCESS_SHUTDOWN_MARGIN_SECONDS
)
OUTBOX_QUEUE = "workstream.outbox"
OUTBOX_DELIVERY_TASK = "workstream.outbox.deliver_event"
FINALIZATION_QUEUE = "workstream.submission_finalization"
FINALIZATION_DELIVERY_TASK = "workstream.outbox.finalize_submission"
FINALIZATION_HARD_LIMIT_SECONDS = SUBMISSION_FINALIZATION_DELIVERY_LEASE_SECONDS + OUTBOX_PROCESS_SHUTDOWN_MARGIN_SECONDS
_validated_parent: int | None = None
_validated_finalization = False


@worker_init.connect
def validate_outbox_worker(sender, **_kwargs):
    """Validate the actual selected queues and pool before the worker starts."""
    global _validated_parent, _validated_finalization
    _validated_parent = None
    queues = set(sender.app.amqp.queues.consume_from)
    _validated_finalization = FINALIZATION_QUEUE in queues
    if _validated_finalization and queues != {FINALIZATION_QUEUE}:
        raise WorkerShutdown("submission finalization requires an exclusive worker queue")
    if OUTBOX_QUEUE not in queues and not _validated_finalization:
        return
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if pool is not TaskPool or sender.app.conf.task_always_eager:
        raise WorkerShutdown("OUTBOX delivery requires a non-eager prefork worker")
    _validated_parent = os.getpid()


def require_outbox_worker(task, *, finalization=False):
    """Reject direct/eager delivery and consumers not validated for this queue."""
    if (
        _validated_parent is None or os.getppid() != _validated_parent
        or task.app.conf.task_always_eager or task.request.is_eager
        or task.request.called_directly
        or finalization != _validated_finalization
    ):
        raise RuntimeError("OUTBOX delivery requires a validated prefork worker")
    message_limit = (task.request.timelimit or (None, None))[0]
    expected_limit = FINALIZATION_HARD_LIMIT_SECONDS if finalization else OUTBOX_HARD_LIMIT_SECONDS
    if (
        type(task.time_limit) is not int or task.time_limit != expected_limit
        or message_limit is not None
        and (type(message_limit) is not int or message_limit != expected_limit)
    ):
        raise RuntimeError("OUTBOX delivery requires a bounded hard time limit")
