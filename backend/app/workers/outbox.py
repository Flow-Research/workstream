"""Durable selector delivery; OUTBOX owns all claim and recovery decisions."""

from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.outbox import production_outbox_delivery
from app.db.session import get_database_url
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app
from app.workers.outbox_topology import (
    require_outbox_worker, OUTBOX_HARD_LIMIT_SECONDS, FINALIZATION_HARD_LIMIT_SECONDS,
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
    name="workstream.outbox.deliver_event", bind=True, acks_late=True,
    reject_on_worker_lost=True, acks_on_failure_or_timeout=True, time_limit=OUTBOX_HARD_LIMIT_SECONDS,
)
def deliver_event(self, event_id, project_id):
    """Run under prefork: its hard limit also bounds async shutdown after UNKNOWN."""
    return _run_delivery(self, event_id, project_id, finalization=False)


@celery_app.task(
    name="workstream.outbox.finalize_submission", bind=True, acks_late=True,
    reject_on_worker_lost=True, acks_on_failure_or_timeout=True, time_limit=FINALIZATION_HARD_LIMIT_SECONDS,
)
def finalize_submission(self, event_id, project_id):
    """Use reserved finalization workers and the same durable delivery owner."""
    return _run_delivery(self, event_id, project_id, finalization=True)


def _run_delivery(self, event_id, project_id, *, finalization):
    require_outbox_worker(self, finalization=finalization)
    try:
        event, project, task = _uuid(event_id), _uuid(project_id), _uuid(self.request.id)
    except (TypeError, ValueError):
        return {"status": "delivery_rejected"}
    try:
        return run_async_task(lambda: _deliver(event, project, task, finalization))
    except Exception:
        logger.warning("outbox delivery unavailable")
        raise self.retry(
            exc=RuntimeError("outbox delivery unavailable"),
            countdown=30 * (2**self.request.retries),
            max_retries=3,
        ) from None


async def _deliver(event_id, project_id, task_id, finalization=False):
    """Compose once; shared delivery owns short transactions and invocation custody."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        receipt = await production_outbox_delivery(
            async_sessionmaker(engine, expire_on_commit=False), finalization_worker=finalization,
        ).deliver(event_id, project_id, "celery:" + str(task_id), registered_only=True)
        return {"status": "delivery_recorded" if receipt is not None else "delivery_unavailable"}
    finally:
        await engine.dispose()


@celery_app.task(name="workstream.outbox.scan_pending", bind=True)
def scan_pending(self, after=None):
    """One stable page continues despite a failed publication; periodic scans repair gaps."""
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
            task = finalize_submission if candidate.event_type in {"SubmissionFinalizationRequested", "SubmissionFinalizationRecoveryRequested"} else deliver_event
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
