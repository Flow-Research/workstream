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
OUTBOX_SCAN_QUEUE = "workstream.outbox_scan"
OUTBOX_SCAN_TASK = "workstream.outbox.scan_pending"
OUTBOX_SCAN_HARD_LIMIT_SECONDS = 60
FINALIZATION_QUEUE = "workstream.submission_finalization"
FINALIZATION_DELIVERY_TASK = "workstream.outbox.finalize_submission"
FINALIZATION_HARD_LIMIT_SECONDS = SUBMISSION_FINALIZATION_DELIVERY_LEASE_SECONDS + OUTBOX_PROCESS_SHUTDOWN_MARGIN_SECONDS
_validated_parent: int | None = None
_validated_finalization = False
_validated_scan = False


@worker_init.connect
def validate_outbox_worker(sender, **_kwargs):
    """Validate the actual selected queues and pool before the worker starts."""
    global _validated_parent, _validated_finalization, _validated_scan
    _validated_parent = None
    queues = set(sender.app.amqp.queues.consume_from)
    _validated_finalization = FINALIZATION_QUEUE in queues
    _validated_scan = OUTBOX_SCAN_QUEUE in queues
    selected = queues & {OUTBOX_QUEUE, OUTBOX_SCAN_QUEUE, FINALIZATION_QUEUE}
    if not selected:
        return
    if queues != selected or len(selected) != 1:
        raise WorkerShutdown("OUTBOX workers require an exclusive worker queue")
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if pool is not TaskPool or sender.app.conf.task_always_eager:
        raise WorkerShutdown("OUTBOX delivery requires a non-eager prefork worker")
    _validated_parent = os.getpid()


def is_finalization_worker_process() -> bool:
    """Identify only a child of the validated exclusive finalization consumer."""
    return (_validated_finalization and _validated_parent is not None
            and os.getppid() == _validated_parent)


def is_outbox_scan_worker_process() -> bool:
    """Identify only a child of the validated exclusive scanner consumer."""
    return (_validated_scan and _validated_parent is not None
            and os.getppid() == _validated_parent)


def require_outbox_scan_worker(task) -> None:
    """Reject direct scans and broker attempts to extend the per-page bound."""
    if (
        not is_outbox_scan_worker_process() or task.app.conf.task_always_eager
        or task.request.is_eager or task.request.called_directly
    ):
        raise RuntimeError("OUTBOX scan requires a validated prefork worker")
    message_limit = (task.request.timelimit or (None, None))[0]
    if (
        type(task.time_limit) is not int or task.time_limit != OUTBOX_SCAN_HARD_LIMIT_SECONDS
        or message_limit is not None
        and (type(message_limit) is not int or message_limit != OUTBOX_SCAN_HARD_LIMIT_SECONDS)
    ):
        raise RuntimeError("OUTBOX scan requires a bounded hard time limit")


def require_outbox_worker(task, *, finalization=False):
    """Reject direct/eager delivery and consumers not validated for this queue."""
    if (
        _validated_parent is None or os.getppid() != _validated_parent
        or task.app.conf.task_always_eager or task.request.is_eager
        or task.request.called_directly
        or finalization != _validated_finalization or _validated_scan
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
