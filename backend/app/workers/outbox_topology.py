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
FEEDBACK_EMAIL_QUEUE = "workstream.submission_feedback_email"
FEEDBACK_EMAIL_DELIVERY_TASK = "workstream.outbox.send_submission_feedback_email"
FEEDBACK_EMAIL_HARD_LIMIT_SECONDS = 55
_DELIVERY_LIMITS = {
    OUTBOX_QUEUE: OUTBOX_HARD_LIMIT_SECONDS,
    FINALIZATION_QUEUE: FINALIZATION_HARD_LIMIT_SECONDS,
    FEEDBACK_EMAIL_QUEUE: FEEDBACK_EMAIL_HARD_LIMIT_SECONDS,
}
_validated_parent: int | None = None
_validated_queue: str | None = None


@worker_init.connect
def validate_outbox_worker(sender, **_kwargs):
    """Validate the actual selected queues and pool before the worker starts."""
    global _validated_parent, _validated_queue
    _validated_parent = None
    _validated_queue = None
    queues = set(sender.app.amqp.queues.consume_from)
    selected = queues & (_DELIVERY_LIMITS.keys() | {OUTBOX_SCAN_QUEUE})
    if not selected:
        return
    if queues != selected or len(selected) != 1:
        raise WorkerShutdown("OUTBOX workers require an exclusive worker queue")
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if pool is not TaskPool or sender.app.conf.task_always_eager:
        raise WorkerShutdown("OUTBOX delivery requires a non-eager prefork worker")
    queue = next(iter(selected))
    if queue == FEEDBACK_EMAIL_QUEUE:
        from app.adapters.submission_feedback_email import validate_submission_feedback_email_worker
        from app.core.config import get_settings

        try:
            validate_submission_feedback_email_worker(get_settings())
        except Exception:
            raise WorkerShutdown("submission feedback email worker configuration invalid") from None
    _validated_queue = queue
    _validated_parent = os.getpid()


def is_finalization_worker_process() -> bool:
    """Identify only a child of the validated exclusive finalization consumer."""
    return _is_validated_child(FINALIZATION_QUEUE)


def is_outbox_scan_worker_process() -> bool:
    """Identify only a child of the validated exclusive scanner consumer."""
    return _is_validated_child(OUTBOX_SCAN_QUEUE)


def is_feedback_email_worker_process() -> bool:
    """Identify only a child of the validated exclusive feedback email consumer."""
    return _is_validated_child(FEEDBACK_EMAIL_QUEUE)


def _is_validated_child(queue: str) -> bool:
    return _validated_queue == queue and _validated_parent is not None and os.getppid() == _validated_parent


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


def require_outbox_worker(task, *, queue=OUTBOX_QUEUE):
    """Reject direct/eager delivery and consumers not validated for this queue."""
    if (
        not _is_validated_child(queue)
        or task.app.conf.task_always_eager or task.request.is_eager
        or task.request.called_directly
    ):
        raise RuntimeError("OUTBOX delivery requires a validated prefork worker")
    message_limit = (task.request.timelimit or (None, None))[0]
    expected_limit = _DELIVERY_LIMITS[queue]
    if (
        type(task.time_limit) is not int or task.time_limit != expected_limit
        or message_limit is not None
        and (type(message_limit) is not int or message_limit != expected_limit)
    ):
        raise RuntimeError("OUTBOX delivery requires a bounded hard time limit")
