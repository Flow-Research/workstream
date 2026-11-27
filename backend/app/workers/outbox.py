"""Durable selector delivery; OUTBOX owns all claim and recovery decisions."""

from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.outbox import production_outbox_delivery
from app.db.session import get_database_url
from app.modules.artifacts.api.submission_recovery import FINALIZATION_RECOVERY_EVENT
from app.modules.tasks.api.routing_outcome import SUBMISSION_FEEDBACK_EMAIL_EVENT
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app
from app.workers.outbox_topology import (
    require_outbox_worker, require_outbox_scan_worker,
    OUTBOX_SCAN_TASK, OUTBOX_SCAN_HARD_LIMIT_SECONDS, FINALIZATION_HARD_LIMIT_SECONDS,
    FEEDBACK_EMAIL_DELIVERY_TASK, FEEDBACK_EMAIL_HARD_LIMIT_SECONDS, FEEDBACK_EMAIL_QUEUE,
    FINALIZATION_DELIVERY_TASK, FINALIZATION_QUEUE, OUTBOX_DELIVERY_TASK, OUTBOX_QUEUE,
)

logger = get_task_logger(__name__)


def _uuid(value):
    """Accept only canonical transport UUIDs before opening SQL resources."""
    if type(value) is not str:
        raise ValueError("invalid outbox selector")
    parsed = UUID(value)
    if str(parsed) != value:
        raise ValueError("invalid outbox selector")
    return parsed


@celery_app.task(
    name=OUTBOX_DELIVERY_TASK, bind=True, acks_late=True,
    reject_on_worker_lost=True, acks_on_failure_or_timeout=True,
)
def deliver_event(self, event_id, project_id):
    """Process POST events under durable delivery ownership."""
    return _run_delivery(self, event_id, project_id, queue=OUTBOX_QUEUE, group="post")


@celery_app.task(
    name=FINALIZATION_DELIVERY_TASK, bind=True, acks_late=True,
    reject_on_worker_lost=True, acks_on_failure_or_timeout=True, time_limit=FINALIZATION_HARD_LIMIT_SECONDS,
)
def finalize_submission(self, event_id, project_id):
    """Use reserved finalization workers and the same durable delivery owner."""
    return _run_delivery(self, event_id, project_id, queue=FINALIZATION_QUEUE, group="finalization")


@celery_app.task(
    name=FEEDBACK_EMAIL_DELIVERY_TASK, bind=True, acks_late=True,
    reject_on_worker_lost=True, acks_on_failure_or_timeout=True, time_limit=FEEDBACK_EMAIL_HARD_LIMIT_SECONDS,
)
def send_submission_feedback_email(self, event_id, project_id):
    """Process only feedback email selectors on the exclusive email queue."""
    return _run_delivery(self, event_id, project_id, queue=FEEDBACK_EMAIL_QUEUE, group="feedback")


def _run_delivery(self, event_id, project_id, *, queue, group):
    """Deliver an event only from its validated dedicated worker queue."""
    require_outbox_worker(self, queue=queue)
    try:
        event, project, task = _uuid(event_id), _uuid(project_id), _uuid(self.request.id)
    except (TypeError, ValueError):
        return {"status": "delivery_rejected"}
    try:
        return run_async_task(lambda: _deliver(event, project, task, group))
    except Exception:
        logger.warning("outbox delivery unavailable")
        raise self.retry(
            exc=RuntimeError("outbox delivery unavailable"),
            countdown=30 * (2**self.request.retries),
            max_retries=3,
        ) from None


async def _deliver(event_id, project_id, task_id, group):
    """Compose once; shared delivery owns short transactions and invocation custody."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        receipt = await production_outbox_delivery(
            async_sessionmaker(engine, expire_on_commit=False), worker_group=group,
        ).deliver(event_id, project_id, "celery:" + str(task_id), registered_only=True)
        return {"status": "delivery_recorded" if receipt is not None else "delivery_unavailable"}
    finally:
        await engine.dispose()


@celery_app.task(name=OUTBOX_SCAN_TASK, bind=True, time_limit=OUTBOX_SCAN_HARD_LIMIT_SECONDS)
def scan_pending(self, after=None):
    """One stable page continues despite a failed publication; periodic scans repair gaps."""
    require_outbox_scan_worker(self)
    return _scan_pending(self, after)


def _scan_pending(self, after=None):
    """Publish one bounded page; the next periodic scan repairs interrupted pages."""
    try:
        cursor = _uuid(after) if after is not None else None
    except (TypeError, ValueError):
        return {"status": "scan_rejected"}
    try:
        page = run_async_task(lambda: _candidates(cursor))
    except Exception:
        logger.warning("outbox discovery unavailable")
        raise self.retry(
            exc=RuntimeError("outbox discovery unavailable"),
            countdown=30 * (2**self.request.retries),
            max_retries=3,
        ) from None
    published = 0
    for candidate in page.items:
        try:
            task = {
                "SubmissionFinalizationRequested": finalize_submission,
                FINALIZATION_RECOVERY_EVENT: finalize_submission,
                SUBMISSION_FEEDBACK_EMAIL_EVENT: send_submission_feedback_email,
            }.get(candidate.event_type, deliver_event)
            task.apply_async(args=(str(candidate.event_id), str(candidate.project_id)))
            published += 1
        except Exception:
            logger.warning("outbox publication unavailable")
    if page.next_after is not None:
        try:
            scan_pending.apply_async(args=(str(page.next_after),))
        except Exception:
            logger.warning("outbox continuation unavailable")
    return {"selected": len(page.items), "published": published}


async def _candidates(after):
    """Close every SQL resource before the caller publishes broker messages."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        return await production_outbox_delivery(
            async_sessionmaker(engine, expire_on_commit=False)
        ).candidates(after=after, limit=100)
    finally:
        await engine.dispose()
